from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")


def validate_citations(output: Dict[str, Any], retrieved_files: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Ensures output citations reference files we actually read, and line ranges are in bounds.
    Returns (is_valid, error_message).
    """
    if not isinstance(output, dict):
        return False, "Output is not an object."
    if "high_risk_areas" not in output or not isinstance(output["high_risk_areas"], list):
        return False, "Missing or invalid high_risk_areas."

    # Build map of read files -> total_lines
    read_map: Dict[str, int] = {}
    for item in retrieved_files:
        if item.get("tool") == "read_file":
            path = item.get("path")
            total_lines = item.get("total_lines")
            if isinstance(path, str) and isinstance(total_lines, int):
                read_map[path] = total_lines

    # If no risk areas, citations are trivially valid
    if len(output["high_risk_areas"]) == 0:
        return True, ""

    for i, area in enumerate(output["high_risk_areas"]):
        if not isinstance(area, dict):
            return False, f"high_risk_areas[{i}] is not an object."

        files = area.get("files")
        if not isinstance(files, list) or len(files) == 0:
            return False, f"high_risk_areas[{i}].files missing or empty."

        for j, f in enumerate(files):
            if not isinstance(f, dict):
                return False, f"high_risk_areas[{i}].files[{j}] is not an object."

            path = f.get("path")
            line_range = f.get("lines")

            if path not in read_map:
                return False, f"high_risk_areas[{i}].files[{j}].path not read: {path}"

            if not isinstance(line_range, str):
                return False, f"high_risk_areas[{i}].files[{j}].lines is not a string."

            m = _RANGE_RE.match(line_range.strip())
            if not m:
                return False, f"high_risk_areas[{i}].files[{j}].lines bad format: {line_range}"

            start = int(m.group(1))
            end = int(m.group(2))
            if start < 1 or end < 1 or end < start:
                return False, f"high_risk_areas[{i}].files[{j}].lines invalid range: {line_range}"

            max_line = read_map[path]
            if end > max_line:
                return False, (
                    f"high_risk_areas[{i}].files[{j}].lines out of bounds for {path}: "
                    f"{line_range} (max {max_line})"
                )

    return True, ""
