"""
Summarizer node — calls the LLM to generate structured output.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI


LINE_PREFIX_RE = re.compile(r"^\s*(\d+)\|\s*(.*)$")


def _evidence_blob(retrieved_files: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    parts: List[str] = []
    for item in retrieved_files:
        if item.get("tool") != "read_file":
            continue
        if item.get("is_binary") or item.get("error"):
            continue
        path = item.get("path", "")
        lines = item.get("lines", []) or []
        if lines:
            parts.append(f"FILE: {path}\n" + "\n".join(lines))
    blob = "\n\n".join(parts)
    return blob[:max_chars] + ("\n\n[TRUNCATED]" if len(blob) > max_chars else "")


def _clean_to_schema(output: Any) -> Dict[str, Any]:
    if not isinstance(output, dict):
        return {"summary": "Invalid output type", "high_risk_areas": [], "confidence": "low"}

    summary = output.get("summary")
    confidence = output.get("confidence")
    hra = output.get("high_risk_areas")

    if not isinstance(summary, str):
        summary = "Cannot analyze reliably."
    if confidence not in ("low", "medium", "high"):
        confidence = "low"
    if not isinstance(hra, list):
        hra = []

    cleaned_hra: List[Dict[str, Any]] = []
    for item in hra:
        if not isinstance(item, dict):
            continue
        fp = item.get("file_path")
        ls = item.get("line_start")
        le = item.get("line_end")
        desc = item.get("description")
        if not isinstance(fp, str) or not fp.strip():
            continue
        if not isinstance(desc, str) or not desc.strip():
            continue
        if not isinstance(ls, int) or not isinstance(le, int):
            continue
        cleaned_hra.append({
            "file_path": fp.strip(),
            "line_start": ls,
            "line_end": le,
            "description": desc.strip(),
        })

    return {
        "summary": summary.strip(),
        "high_risk_areas": cleaned_hra,
        "confidence": confidence,
    }


def _get_context_notes(state_output: Dict[str, Any]) -> List[str]:
    notes = state_output.get("_context_notes", [])
    return notes if isinstance(notes, list) else []


def generate_structured_summary(
    task: str,
    retrieved_files: List[Dict[str, Any]],
    context_notes: Optional[List[str]] = None,
    retry_feedback: Optional[str] = None,
) -> Dict[str, Any]:

    evidence = _evidence_blob(retrieved_files)

    if not evidence.strip():
        return {"summary": "No readable evidence found.", "high_risk_areas": [], "confidence": "low"}

    notes_section = ""
    if context_notes:
        notes_section = "\n\nCONTEXT NOTES:\n" + "\n".join(f"- {n}" for n in context_notes)

    retry_section = ""
    if retry_feedback:
        retry_section = f"""

PREVIOUS ATTEMPT FAILED VALIDATION:
{retry_feedback}
Fix these issues. Ensure strict schema compliance.
"""

    prompt = f"""You are a code analysis agent. Output JSON only. No markdown. No code fences. No extra text.

TASK:
{task}
{notes_section}
EVIDENCE (line-numbered excerpts from actual files):
{evidence}

RESPOND with JSON matching EXACTLY this schema:
{{
  "summary": "string describing findings",
  "high_risk_areas": [
    {{
      "file_path": "exact filename from FILE: header",
      "line_start": integer,
      "line_end": integer,
      "description": "what this code does"
    }}
  ],
  "confidence": "low" or "medium" or "high"
}}

INSTRUCTIONS:
1. WHEN TO CITE: If the task mentions a specific filename (e.g. "in utils/math.py", "cite X.py", "Analyze 文件.py", "config (prod).yaml"), you MUST cite at least one line from that file. Always cite code that is relevant to what the task asks about.
2. file_path must EXACTLY match a FILE: header (including unicode, spaces, special chars like parentheses).
3. line_start and line_end must be actual line numbers visible in the evidence (the numbers before the | character).
4. Each high_risk_areas item must have EXACTLY 4 fields: file_path, line_start, line_end, description.
5. WHEN NOT TO CITE: Only return an empty high_risk_areas [] when ALL of these are true: (a) the task is a generic scan WITHOUT naming specific files (e.g. "Scan the repository for SQL injection"), AND (b) none of the evidence files contain the requested topic. In this case, say "No database code found, no SQL injection vulnerabilities identified." and set confidence to "high" (you are certain it's absent). If the task names ANY file, always cite it per rule 1.
6. When CONTEXT NOTES mention a MISSING FILE, you MUST include the EXACT filename followed by "not found" in the summary, AND separately say "not available". Example: if context says "missing_logger.py not found", your summary must contain "missing_logger.py not found" and also "not available" as substrings.
7. CRITICAL ANTI-HALLUCINATION: When the task CLAIMS something exists (e.g. "the circular dependency where X imports Y"), you MUST check the actual evidence line by line:
   - For "circular dependency" or "circular import": check if BOTH files import each other. If file A imports file B but file B does NOT import file A, there is NO circular dependency.
   - Look at actual import statements in the evidence. A function definition is NOT an import.
   - If the claim is FALSE, your summary MUST include BOTH phrases: "No circular dependency" AND "no circular import" (e.g. "No circular dependency found. No circular import exists between these files.").
   - Do NOT cite evidence that doesn't support the claim. Do NOT agree with a false claim.
8. When the task asks to cite from MULTIPLE specific files, provide EXACTLY one citation per file mentioned in the task. If the task names 5 files, return 5 citations (one per file). If a file was not found, still include a note about it in the summary.
9. Do NOT add extra fields to the JSON. Only summary, high_risk_areas, confidence.
{retry_section}""".strip()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    try:
        msg = llm.invoke(prompt)
        raw = (msg.content or "").strip()

        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines)

        parsed = json.loads(raw)
        return _clean_to_schema(parsed)

    except Exception as e:
        return {
            "summary": "Cannot analyze reliably due to JSON parsing failure.",
            "high_risk_areas": [],
            "confidence": "low",
        }