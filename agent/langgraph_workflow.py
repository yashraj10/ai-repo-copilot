from __future__ import annotations

from typing import TypedDict

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.planner import plan_task
from agent.executor import execute_plan
from agent.verifier import verify_output
from agent.summarizer import generate_structured_summary


class GraphState(TypedDict):
    state: AgentState


def node_plan(gs: GraphState) -> GraphState:
    s = gs["state"]
    s = plan_task(s)
    return {"state": s}


def node_execute(gs: GraphState) -> GraphState:
    s = gs["state"]
    s = execute_plan(s)
    return {"state": s}


def node_summarize(gs: GraphState) -> GraphState:
    s = gs["state"]

    s.llm_attempts += 1
    print(f"LLM: attempt {s.llm_attempts}/{s.max_llm_attempts}")

    try:
        s.output = generate_structured_summary(s.task, s.retrieved_files)
    except Exception as e:
        s.output = {"error": str(e)}

    return {"state": s}


def node_verify(gs: GraphState) -> GraphState:
    s = gs["state"]
    s = verify_output(s)
    return {"state": s}


def should_retry(gs: GraphState) -> str:
    s = gs["state"]
    schema_valid = bool(s.verification.get("schema_valid", False))

    if schema_valid:
        return "end"

    if s.llm_attempts >= s.max_llm_attempts:
        return "end"

    return "retry"


def build_graph():
    g = StateGraph(GraphState)

    g.add_node("plan", node_plan)
    g.add_node("execute", node_execute)
    g.add_node("summarize", node_summarize)
    g.add_node("verify", node_verify)

    g.set_entry_point("plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "summarize")
    g.add_edge("summarize", "verify")

    g.add_conditional_edges(
        "verify",
        should_retry,
        {
            "retry": "summarize",
            "end": END,
        },
    )

    return g.compile()


def run(task: str, repo_path: str = "sample_repo") -> AgentState:
    print("LANGGRAPH AGENT: started")

    app = build_graph()
    initial: GraphState = {"state": AgentState(task=task, repo_path=repo_path)}

    final = app.invoke(initial)
    final_state = final["state"]

    print("LANGGRAPH AGENT: finished")
    return final_state


if __name__ == "__main__":
    fs = run("Identify high-risk areas a new developer should understand.", repo_path="sample_repo")
    print("\nFINAL STATE:")
    print(fs)
