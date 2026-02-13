"""
Schema validator with strict checking for phase 2 adversarial tests.
This replaces your existing eval/schema_validate.py
"""

from typing import Any, Dict, List, Tuple


def validate_output_schema(output: Any) -> Tuple[bool, List[str]]:
    """
    Validate that output matches the EXACT required schema.
    
    Required schema:
    {
        "summary": str,
        "high_risk_areas": [
            {
                "file_path": str,
                "line_start": int,
                "line_end": int,
                "description": str
            }
        ],
        "confidence": "low" | "medium" | "high"
    }
    
    Returns:
        (is_valid, error_list)
    """
    errors: List[str] = []
    
    # 1. Must be a dict
    if not isinstance(output, dict):
        errors.append(f"Output must be dict, got {type(output).__name__}")
        return False, errors
    
    # 2. EXACT key match - no extra fields allowed
    required_keys = {"summary", "high_risk_areas", "confidence"}
    actual_keys = set(output.keys())
    
    if actual_keys != required_keys:
        extra = actual_keys - required_keys
        missing = required_keys - actual_keys
        
        if extra:
            errors.append(f"Extra fields not allowed: {sorted(extra)}")
        if missing:
            errors.append(f"Missing required fields: {sorted(missing)}")
        
        return False, errors
    
    # 3. Validate summary
    summary = output.get("summary")
    if not isinstance(summary, str):
        errors.append(f"summary must be str, got {type(summary).__name__}")
        return False, errors
    
    # 4. Validate confidence
    confidence = output.get("confidence")
    if confidence not in ("low", "medium", "high"):
        errors.append(f"confidence must be 'low', 'medium', or 'high', got {repr(confidence)}")
        return False, errors
    
    # 5. Validate high_risk_areas is a list
    hra = output.get("high_risk_areas")
    if not isinstance(hra, list):
        errors.append(f"high_risk_areas must be list, got {type(hra).__name__}")
        return False, errors
    
    # 6. Validate each high_risk_area item
    for i, item in enumerate(hra):
        # Must be dict
        if not isinstance(item, dict):
            errors.append(f"high_risk_areas[{i}] must be dict, got {type(item).__name__}")
            continue
        
        # Check for exact keys (no extras)
        item_required = {"file_path", "line_start", "line_end", "description"}
        item_actual = set(item.keys())
        
        if item_actual != item_required:
            extra = item_actual - item_required
            missing = item_required - item_actual
            
            if extra:
                errors.append(f"high_risk_areas[{i}] has extra fields: {sorted(extra)}")
            if missing:
                errors.append(f"high_risk_areas[{i}] missing fields: {sorted(missing)}")
            continue
        
        # Validate field types
        fp = item.get("file_path")
        if not isinstance(fp, str):
            errors.append(f"high_risk_areas[{i}].file_path must be str, got {type(fp).__name__}")
        
        ls = item.get("line_start")
        if not isinstance(ls, int):
            errors.append(f"high_risk_areas[{i}].line_start must be int, got {type(ls).__name__}")
        
        le = item.get("line_end")
        if not isinstance(le, int):
            errors.append(f"high_risk_areas[{i}].line_end must be int, got {type(le).__name__}")
        
        desc = item.get("description")
        if not isinstance(desc, str):
            errors.append(f"high_risk_areas[{i}].description must be str, got {type(desc).__name__}")
        
        # Check for nested arrays/dicts (ELITE test)
        for key, value in item.items():
            if isinstance(value, (list, dict)):
                errors.append(
                    f"high_risk_areas[{i}].{key} contains nested structure "
                    f"({type(value).__name__}), only primitives allowed"
                )
    
    # Return result
    if errors:
        return False, errors
    
    return True, []