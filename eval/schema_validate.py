from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from jsonschema import Draft202012Validator


_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "output.schema.json"


def validate_output_schema(output: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Returns (is_valid, error_message). error_message is empty when valid.
    """
    if not isinstance(output, dict):
        return False, "Output is not a JSON object."

    schema: Dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors = sorted(validator.iter_errors(output), key=lambda e: list(e.path))
    if not errors:
        return True, ""

    e = errors[0]
    path = ".".join([str(p) for p in e.path]) if e.path else "(root)"
    return False, f"{path}: {e.message}"
