"""
Analyzer node — pre-LLM analysis that determines routing.

This node examines the executor's evidence and decides:
- "call_llm": Normal path — send evidence to LLM for analysis
- "skip_llm": Evidence triggers a pre-built response (empty repo, binary, security)
- "error": Catastrophic failure — all tools failed

It also builds context notes for the LLM when routing to "call_llm".
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from agent.state import AgentState


def _is_path_traversal_task(task: str) -> bool:
    """Detect if the task references paths outside the repository."""
    patterns = [r'\.\./\.\.', r'/etc/', r'/usr/', r'/var/', r'/tmp/', r'/home/', r'\\windows\\']
    task_lower = task.lower()
    return any(re.search(pat, task_lower) for pat in patterns)


def _task_targets_file(task: str, filename: str) -> bool:
    """Check if the task specifically asks about a given file."""
    task_lower = task.lower()
    fname_lower = filename.lower()
    basename = os.path.basename(fname_lower)
    return fname_lower in task_lower or basename in task_lower


def _task_mentions_missing_file(task: str, listed_files: List[str]) -> Optional[str]:
    """Check if task references a file that doesn't exist in the repo."""
    task_files_re = re.findall(r'([a-zA-Z0-9_/\\.\-]+\.\w{1,5})', task)
    listed_lower = {f.lower().replace("\\", "/") for f in listed_files}
    for tf in task_files_re:
        tf_norm = tf.lower().replace("\\", "/").strip("./")
        if tf_norm and tf_norm not in listed_lower:
            # Check if basename matches
            basename = os.path.basename(tf_norm)
            if not any(f.lower().endswith(basename) for f in listed_files):
                return tf
    return None


def _all_tools_failed(state: AgentState) -> bool:
    """Check if ALL tool calls failed."""
    if not state.tool_calls:
        return True
    return all(
        tc.get("result_status") != "success"
        for tc in state.tool_calls
    )


def _get_listed_files(state: AgentState) -> List[str]:
    """Get the file list from retrieved evidence."""
    for item in state.retrieved_files:
        if item.get("tool") == "list_files" and isinstance(item.get("files"), list):
            return item["files"]
    return []


def _get_binary_files(state: AgentState) -> List[str]:
    """Get files that were detected as binary."""
    return [
        x.get("path", "")
        for x in state.retrieved_files
        if x.get("tool") == "read_file" and x.get("is_binary")
    ]


def _get_error_files(state: AgentState) -> List[str]:
    """Get files that had read errors."""
    return [
        x.get("path", "")
        for x in state.retrieved_files
        if x.get("tool") == "read_file" and x.get("error") and not x.get("is_binary")
    ]


def _fallback_output(summary: str, confidence: str = "low") -> Dict[str, Any]:
    """Create a schema-compliant output with no citations."""
    return {"summary": summary, "high_risk_areas": [], "confidence": confidence}


def analyze_evidence(state: AgentState) -> AgentState:
    """
    Analyze executor results and decide routing.
    
    Sets state.route_decision to one of:
    - "call_llm": Proceed to LLM summarization
    - "skip_llm": Use pre-built response (state.output already set)
    - "error": All tools failed (state.output already set)
    """
    print(" - Analyze code")

    listed_files = _get_listed_files(state)
    binary_files = _get_binary_files(state)
    error_files = _get_error_files(state)

    # Route 1: All tools failed → error
    if _all_tools_failed(state):
        state.output = {
            "error": "Agent failed: all tool operations failed.",
            "summary": "Cannot analyze: all tool operations failed.",
        }
        state.route_decision = "error"
        return state

    # Route 2: Path traversal in task → security rejection
    if _is_path_traversal_task(state.task):
        state.output = _fallback_output(
            "Cannot analyze: the requested path appears to be outside repository boundaries. "
            "This is a path traversal security issue. Only files within the repository can be analyzed.",
            confidence="high"
        )
        state.route_decision = "skip_llm"
        return state

    # Route 3: Empty repository
    if not listed_files:
        state.output = _fallback_output(
            "Repository is empty, no files to analyze.",
            confidence="high"
        )
        state.route_decision = "skip_llm"
        return state

    # Route 4: Task targets a binary file specifically
    for bf in binary_files:
        if _task_targets_file(state.task, bf):
            state.output = _fallback_output(
                f"{bf} is a binary file and cannot analyze its contents as text. "
                "Binary files require specialized tools for inspection.",
                confidence="high"
            )
            state.route_decision = "skip_llm"
            return state

    # Route 5: All reads failed (but list_files worked)
    readable_files = [
        x for x in state.retrieved_files
        if x.get("tool") == "read_file"
        and not x.get("is_binary")
        and not x.get("error")
        and (x.get("lines") or [])
    ]
    if not readable_files:
        failed = ", ".join(error_files) if error_files else "all files"
        state.output = _fallback_output(
            f"Cannot analyze: all file reads failed ({failed}).",
            confidence="low"
        )
        state.route_decision = "skip_llm"
        return state

    # Route 6: Normal path — call LLM
    # Build context notes for the summarizer
    context_notes = []

    # Note missing files
    missing = _task_mentions_missing_file(state.task, listed_files)
    if missing:
        context_notes.append(f"MISSING FILE: {missing} not found. {missing} is not available for analysis.")

    # Note binary files
    for bf in binary_files:
        context_notes.append(f"NOTE: {bf} is a binary file")

    # Note error files
    for ef in error_files:
        context_notes.append(f"NOTE: {ef} could not be read (error)")

    # Store context notes for the summarizer to use
    state.output = {"_context_notes": context_notes}  # temporary, replaced by summarizer
    state.route_decision = "call_llm"
    return state