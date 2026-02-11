from agent.state import AgentState


def plan_task(state: AgentState) -> AgentState:
    print("PLANNER: creating plan")

    state.plan = [
        "List repository files",
        "Read relevant files",
        "Analyze code",
        "Generate structured output",
        "Verify reliability"
    ]
    return state
