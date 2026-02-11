from agent.state import AgentState


def verify_output(state: AgentState) -> AgentState:
    print("VERIFIER: checking rules")

    state.verification = {
        "used_tools": False,
        "citations_present": False,
        "schema_valid": False
    }
    return state
