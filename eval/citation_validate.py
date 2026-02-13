"""
Citation validator with duplicate detection, validation_rules support,
and content_aware mode.
"""

import re
from typing import Any, Dict, List, Set, Tuple, Optional


LINE_PREFIX_RE = re.compile(r"^\s*(\d+)\|\s*(.*)$")


def validate_citations(
    output: Dict[str, Any],
    retrieved_files: List[Dict[str, Any]],
    repo_path: str,
    mode: Optional[str] = None,
    patterns: Optional[Any] = None,
    rules: Optional[Dict[str, Any]] = None,
    content_validation: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Tuple[bool, List[str]]:
    """
    Validate that all citations in output reference actual lines from retrieved_files.

    Supports:
    - Basic range validation (default)
    - validation_rules: reject_if_line_start_greater_than_line_end,
                        reject_if_line_number_negative, reject_if_line_number_zero
    - content_aware mode with content_validation assertions
    """
    errors: List[str] = []
    rules = rules or {}

    if not isinstance(output, dict):
        errors.append("Output is not a dict, cannot validate citations")
        return False, errors

    high_risk_areas = output.get("high_risk_areas", [])

    # Empty citations list is valid (unless content_validation requires citations)
    if not high_risk_areas:
        return True, []

    # Build evidence map: file_path -> {line_num: line_text}
    evidence_map: Dict[str, Dict[int, str]] = {}

    for item in retrieved_files:
        if item.get("tool") != "read_file":
            continue

        path = str(item.get("path", "")).strip()
        if not path:
            continue

        lines = item.get("lines", []) or []
        line_data: Dict[int, str] = {}

        for raw_line in lines:
            m = LINE_PREFIX_RE.match(raw_line)
            if m:
                line_num = int(m.group(1))
                line_text = m.group(2)
                line_data[line_num] = line_text

        if line_data:
            evidence_map[path] = line_data

    # Track duplicates
    seen_citations: Set[Tuple[str, int, int]] = set()

    # Validate each citation
    for i, area in enumerate(high_risk_areas):
        if not isinstance(area, dict):
            errors.append(f"Citation {i} is not a dict")
            continue

        file_path = area.get("file_path")
        line_start = area.get("line_start")
        line_end = area.get("line_end")

        # Type checking
        if not isinstance(file_path, str):
            errors.append(f"Citation {i}: file_path is not a string")
            continue
        if not isinstance(line_start, int):
            errors.append(f"Citation {i}: line_start is not an int")
            continue
        if not isinstance(line_end, int):
            errors.append(f"Citation {i}: line_end is not an int")
            continue

        # Validation rules: negative/zero line numbers
        if rules.get("reject_if_line_number_negative") or rules.get("reject_if_line_number_zero"):
            if line_start < 1 or line_end < 1:
                errors.append(
                    f"Citation {i}: invalid line number (line_start={line_start}, "
                    f"line_end={line_end}); negative or zero line numbers rejected"
                )
                continue

        # Check for duplicates
        citation_key = (file_path, line_start, line_end)
        if citation_key in seen_citations:
            errors.append(f"Duplicate citation: {file_path} lines {line_start}-{line_end}")
            continue
        seen_citations.add(citation_key)

        # Validation rules: reversed bounds
        if line_start > line_end:
            errors.append(
                f"Citation {i}: line_start ({line_start}) > line_end ({line_end})"
            )
            continue

        # Check file exists in evidence
        if file_path not in evidence_map:
            errors.append(
                f"Citation {i}: file '{file_path}' not found in retrieved evidence"
            )
            continue

        # Check lines exist in evidence
        available_lines = evidence_map[file_path]
        if not available_lines:
            errors.append(
                f"Citation {i}: file '{file_path}' has no readable lines in evidence"
            )
            continue

        min_line = min(available_lines)
        max_line = max(available_lines)

        for line_num in range(line_start, line_end + 1):
            if line_num not in available_lines:
                errors.append(
                    f"Citation {i}: line {line_num} in '{file_path}' not found in evidence "
                    f"(evidence has lines {min_line}-{max_line})"
                )
                break

    # Content-aware validation
    if mode == "content_aware" and content_validation:
        assertions = content_validation.get("assertions", [])
        for assertion in assertions:
            # Check if cited range includes lines that shouldn't be included
            afile = assertion.get("file")
            must_not = assertion.get("must_not_contain_text")
            aline = assertion.get("line")

            if afile and must_not and aline:
                # Check if any citation covers this line
                for area in high_risk_areas:
                    if not isinstance(area, dict):
                        continue
                    fp = area.get("file_path")
                    ls = area.get("line_start")
                    le = area.get("line_end")
                    if fp == afile and isinstance(ls, int) and isinstance(le, int):
                        if ls <= aline <= le:
                            # This citation covers the assertion line
                            # Check if the line content contains the forbidden text
                            if afile in evidence_map and aline in evidence_map[afile]:
                                actual_text = evidence_map[afile][aline]
                                if must_not.lower() not in actual_text.lower():
                                    errors.append(
                                        f"Citation covers line {aline} in '{afile}' which "
                                        f"does not contain expected text for the cited function"
                                    )

    if errors:
        return False, errors
    return True, []