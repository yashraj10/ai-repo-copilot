from __future__ import annotations

from agent.state import AgentState


def verify_output(state: AgentState) -> AgentState:
    print("VERIFIER: checking rules")

    used_tools = len(state.tool_calls) > 0
    read_calls = [c for c in state.tool_calls if c.get("tool") == "read_file"]
    citations_possible = len(read_calls) > 0

    # "Schema valid" (lightweight check for now)
    # Later we will enforce a real JSON Schema with jsonschema.
    has_json_output = isinstance(state.output, dict) and "summary" in state.output

    state.verification = {
        "used_tools": used_tools,
        "citations_present": citations_possible,  # currently means "citations possible"
        "schema_valid": has_json_output,
    }

    if used_tools:
        print("   OK: Tools were used.")
    else:
        print("   FAIL: No tools were used.")

    if citations_possible:
        print("   OK: At least one file was read with line numbers.")
    else:
        print("   FAIL: No files were read; citations not possible.")

    if has_json_output:
        print("   OK: JSON output generated.")
    else:
        # If LLM failed, you might have state.output={"error": "..."}
        if isinstance(state.output, dict) and "error" in state.output:
            print(f"   FAIL: JSON output missing. LLM error: {state.output['error']}")
        else:
            print("   FAIL: JSON output missing or invalid.")

    return state
