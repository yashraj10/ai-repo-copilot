from agent.state import AgentState
from agent.planner import plan_task
from agent.executor import execute_plan
from agent.verifier import verify_output
from agent.summarizer import generate_structured_summary


def run_agent(task: str) -> AgentState:
    print("AGENT: started")
    state = AgentState(task=task, repo_path="sample_repo")

    state = plan_task(state)
    state = execute_plan(state)
    try:
        state.output = generate_structured_summary(state.task, state.retrieved_files)
    except Exception as e:
        state.output = {"error": str(e)}

    state = verify_output(state)

    print("AGENT: finished")
    return state


if __name__ == "__main__":
    final_state = run_agent("Identify high-risk areas a new developer should understand.")
    print("\nFINAL STATE:")
    print(final_state)
