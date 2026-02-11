from agent.state import AgentState


def execute_plan(state: AgentState) -> AgentState:
    print("EXECUTOR: executing plan")

    for step in state.plan:
        print(f" - {step}")

    return state
