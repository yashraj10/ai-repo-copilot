from __future__ import annotations

from agent.state import AgentState
from eval.schema_validate import validate_output_schema
from eval.citation_validate import validate_citations


def verify_output(state: AgentState) -> AgentState:
    print("VERIFIER: checking rules")

    used_tools = len(state.tool_calls) > 0
    read_calls = [c for c in state.tool_calls if c.get("tool") == "read_file"]
    citations_possible = len(read_calls) > 0

    schema_valid = False
    schema_error = ""

    citations_valid = False
    citations_error = ""

    # If LLM failed, we store {"error": "..."} so everything should fail.
    if isinstance(state.output, dict) and "error" not in state.output:
        schema_valid, schema_error = validate_output_schema(state.output)

        if schema_valid:
            citations_valid, citations_error = validate_citations(state.output, state.retrieved_files)
        else:
            citations_valid = False
            citations_error = "Skipped citation check because schema is invalid."
    else:
        err = state.output.get("error", "Missing output") if isinstance(state.output, dict) else "Missing output"
        schema_error = err
        citations_error = err

    state.verification = {
        "used_tools": used_tools,
        "citations_present": citations_possible,  # still means "citations possible"
        "schema_valid": schema_valid,
        "citations_valid": citations_valid,
    }

    if used_tools:
        print("   OK: Tools were used.")
    else:
        print("   FAIL: No tools were used.")

    if citations_possible:
        print("   OK: At least one file was read with line numbers.")
    else:
        print("   FAIL: No files were read; citations not possible.")

    if schema_valid:
        print("   OK: Output matches JSON schema.")
    else:
        print(f"   FAIL: Output schema invalid: {schema_error}")

    if citations_valid:
        print("   OK: Citations reference read files and valid line ranges.")
    else:
        print(f"   FAIL: Citation integrity invalid: {citations_error}")

    return state
