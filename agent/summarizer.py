import json
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI


def _evidence_blob(retrieved_files: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    parts: List[str] = []
    for item in retrieved_files:
        if item.get("tool") != "read_file":
            continue
        path = item.get("path", "")
        lines = item.get("lines", [])
        parts.append(f"FILE: {path}\n" + "\n".join(lines))
    blob = "\n\n".join(parts)
    return blob[:max_chars] + ("\n\n[TRUNCATED]" if len(blob) > max_chars else "")


def generate_structured_summary(task: str, retrieved_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    evidence = _evidence_blob(retrieved_files)

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0,
    )

    prompt = f"""
You are an AI Repo Co-Pilot. Output JSON only. No markdown, no extra text.

Task:
{task}

Evidence (line-numbered excerpts):
{evidence}

Return JSON with this shape:
{{
  "summary": "string",
  "high_risk_areas": [
    {{
      "area": "string",
      "risk": "string",
      "files": [{{"path":"string","lines":"string"}}],
      "recommendation": "string"
    }}
  ],
  "confidence": "low|medium|high"
}}

Rules:
- Use ONLY the Evidence. Do not invent files or code.
- Every files[].path must match a FILE shown in Evidence.
- lines must be a range like "1-5" based on the evidence line numbers.
- If evidence is too thin, return empty high_risk_areas and confidence="low".
""".strip()

    msg = llm.invoke(prompt)
    text = msg.content.strip()
    return json.loads(text)
