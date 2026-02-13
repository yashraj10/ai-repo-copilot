"""
Verifier node — validates schema and citations, sets validation feedback for retries.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from eval.schema_validate import validate_output_schema
from eval.citation_validate import validate_citations
from agent.state import AgentState


def _is_path_traversal_task(task: str) -> bool:
    patterns = [r'\.\./\.\.', r'/etc/', r'/usr/', r'/var/', r'/tmp/', r'/home/', r'\\windows\\']
    return any(re.search(pat, task.lower()) for pat in patterns)


def verify_output(state: AgentState) -> AgentState:
    """Validate the agent's output and build retry feedback."""
    print("VERIFIER: checking rules")

    # Schema validation
    schema_ok, schema_errs = validate_output_schema(state.output)
    state.schema_valid = schema_ok
    state.schema_errors = schema_errs

    # Citation validation
    citations_ok, citation_errs = validate_citations(
        output=state.output,
        retrieved_files=state.retrieved_files,
        repo_path=state.repo_path,
    )
    state.citations_valid = citations_ok
    state.citation_errors = citation_errs

    # ---- Additional invalidation rules ----

    # Check for security errors in BOTH retrieved_files AND tool_calls
    security_keywords = ["symlink", "path traversal", "escapes repo", "symlink not allowed"]
    
    for source_list in [state.retrieved_files or [], state.tool_calls or []]:
        for x in source_list:
            if not isinstance(x, dict):
                continue
            tool = x.get("tool") or x.get("name")
            if tool != "read_file":
                continue
            err = str(x.get("error", "") or "")
            if any(kw in err.lower() for kw in security_keywords):
                if state.citations_valid:
                    state.citations_valid = False
                    state.citation_errors.append(
                        f"Security error for '{x.get('path', 'unknown')}': {err}"
                    )

    # Check path traversal in task
    if _is_path_traversal_task(state.task):
        if state.citations_valid:
            state.citations_valid = False
            state.citation_errors.append(
                "Task references paths outside repository; citations cannot be validated."
            )

    # Check binary files targeted by task
    task_lower = state.task.lower()
    for x in (state.retrieved_files or []):
        if x.get("tool") == "read_file" and x.get("is_binary"):
            bf = x.get("path", "")
            bf_lower = bf.lower()
            basename = os.path.basename(bf_lower)
            if bf_lower in task_lower or basename in task_lower:
                if state.citations_valid:
                    state.citations_valid = False
                    state.citation_errors.append(
                        f"Task targets binary file '{bf}'; citations cannot be validated."
                    )

    # Build retry feedback for LangGraph retry loop
    if not state.schema_valid or not state.citations_valid:
        parts = []
        if not state.schema_valid:
            parts.append("SCHEMA ERRORS: " + "; ".join(state.schema_errors))
        if not state.citations_valid:
            parts.append("CITATION ERRORS: " + "; ".join(state.citation_errors))
        state.last_validation_feedback = "\n".join(parts)
    else:
        state.last_validation_feedback = None

    # Print
    if state.schema_valid:
        print("   OK: Output matches JSON schema.")
    else:
        print("   FAIL: Schema validation failed.")
        for err in state.schema_errors:
            print(f"      - {err}")

    if state.citations_valid:
        print("   OK: Citations reference read files and valid line ranges.")
    else:
        print("   FAIL: Citation validation failed.")
        for err in state.citation_errors:
            print(f"      - {err}")

    return state