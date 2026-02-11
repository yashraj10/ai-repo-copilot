from agent.state import AgentState


def verify_output(state: AgentState) -> AgentState:
    print("VERIFIER: checking rules")

    used_tools = len(state.tool_calls) > 0

    state.verification = {
        "used_tools": used_tools,
        "citations_present": False,
        "schema_valid": False
    }

    if used_tools:
        print("   OK: Tools were used.")
    else:
        print("   FAIL: No tools were used.")

    return state
