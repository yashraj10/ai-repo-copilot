"""
LangGraph workflow — replaces the linear pipeline with a stateful graph.

Graph structure:
    [START] → plan → execute → analyze → route_after_analyze
                                              ↓              ↓
                                          summarize      (skip_llm/error)
                                              ↓                  ↓
                                           verify              END
                                          ↓      ↓
                                       retry    END

Key features over linear pipeline:
1. Conditional routing: empty repos, binary files, security → skip LLM entirely
2. Retry loop: if validation fails, re-prompt LLM with error feedback
3. Error handling: all-tools-failed → clean error output
4. State management: clear transitions with typed state
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.planner import plan_task
from agent.executor import execute_plan
from agent.analyzer import analyze_evidence
from agent.summarizer import generate_structured_summary, _get_context_notes
from agent.verifier import verify_output


# ----------------------------
# LangGraph State Container
# ----------------------------
class GraphState(TypedDict):
    agent: AgentState


# ----------------------------
# Graph Nodes
# ----------------------------
def node_plan(gs: GraphState) -> GraphState:
    """Plan node — analyze task and create execution plan."""
    state = gs["agent"]
    state = plan_task(state)
    return {"agent": state}


def node_execute(gs: GraphState) -> GraphState:
    """Execute node — call tools to gather evidence."""
    state = gs["agent"]
    state = execute_plan(state)
    return {"agent": state}


def node_analyze(gs: GraphState) -> GraphState:
    """Analyze node — examine evidence, decide routing."""
    state = gs["agent"]
    state = analyze_evidence(state)
    return {"agent": state}


def node_summarize(gs: GraphState) -> GraphState:
    """Summarize node — call LLM to generate structured output."""
    state = gs["agent"]

    state.llm_attempts += 1
    print(f" - Generate structured output (attempt {state.llm_attempts}/{state.max_llm_attempts})")

    # Get context notes from analyzer
    context_notes = _get_context_notes(state.output) if isinstance(state.output, dict) else []

    # Get retry feedback (None on first attempt)
    retry_feedback = state.last_validation_feedback

    state.output = generate_structured_summary(
        task=state.task,
        retrieved_files=state.retrieved_files,
        context_notes=context_notes,
        retry_feedback=retry_feedback,
    )

    return {"agent": state}


def node_verify(gs: GraphState) -> GraphState:
    """Verify node — validate schema and citations."""
    state = gs["agent"]
    print(" - Verify reliability")
    state = verify_output(state)
    return {"agent": state}


def node_handle_error(gs: GraphState) -> GraphState:
    """Error node — all tools failed, produce error output."""
    state = gs["agent"]
    print(" - Handle error (all tools failed)")

    # Output is already set by analyzer; mark validation as failed
    state.schema_valid = False
    state.schema_errors = ["Agent failed: all tool operations failed"]
    state.citations_valid = False
    state.citation_errors = ["No valid tool results; cannot validate citations"]

    print("\n===== FINAL AGENT OUTPUT =====")
    print(state.output)
    print("================================\n")
    print("VERIFIER: skipped (all tools failed)")

    return {"agent": state}


def node_finalize(gs: GraphState) -> GraphState:
    """Finalize node — print output for skip_llm path."""
    state = gs["agent"]

    print(" - Generate structured output")
    print(" - Verify reliability")

    # Run verifier even for skip_llm (to set validation flags)
    state = verify_output(state)

    print("\n===== FINAL AGENT OUTPUT =====")
    print(state.output)
    print("================================\n")

    return {"agent": state}


# ----------------------------
# Routing Functions
# ----------------------------
def route_after_analyze(gs: GraphState) -> str:
    """Conditional edge after analyze: decide next node."""
    state = gs["agent"]
    decision = state.route_decision

    if decision == "error":
        return "handle_error"
    elif decision == "skip_llm":
        return "finalize"
    else:
        return "summarize"


def should_retry(gs: GraphState) -> str:
    """Conditional edge after verify: retry or finish."""
    state = gs["agent"]

    # If both valid → done
    if state.schema_valid and state.citations_valid:
        return "end"

    # If retries exhausted → done
    if state.llm_attempts >= state.max_llm_attempts:
        return "end"

    # Retry — but only if the errors are LLM-fixable
    # (Don't retry for security errors, binary files, etc.)
    non_retryable = ["binary", "symlink", "path traversal", "outside repository"]
    all_errors = state.schema_errors + state.citation_errors
    if any(any(kw in err.lower() for kw in non_retryable) for err in all_errors):
        return "end"

    print(f"\n--- RETRY: validation failed, re-prompting LLM "
          f"(attempt {state.llm_attempts + 1}/{state.max_llm_attempts}) ---\n")

    # Reset validation state for retry
    state.schema_valid = False
    state.citations_valid = False
    state.schema_errors = []
    state.citation_errors = []

    return "retry"


# ----------------------------
# Graph Builder
# ----------------------------
def build_graph() -> StateGraph:
    """Build the LangGraph state graph."""
    g = StateGraph(GraphState)

    # Add nodes
    g.add_node("plan", node_plan)
    g.add_node("execute", node_execute)
    g.add_node("analyze", node_analyze)
    g.add_node("summarize", node_summarize)
    g.add_node("verify", node_verify)
    g.add_node("handle_error", node_handle_error)
    g.add_node("finalize", node_finalize)

    # Linear edges
    g.set_entry_point("plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "analyze")

    # Conditional: after analyze
    g.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {
            "summarize": "summarize",
            "finalize": "finalize",
            "handle_error": "handle_error",
        },
    )

    # After summarize → always verify
    g.add_edge("summarize", "verify")

    # Conditional: after verify → retry or end
    g.add_conditional_edges(
        "verify",
        should_retry,
        {
            "retry": "summarize",
            "end": END,
        },
    )

    # Terminal nodes
    g.add_edge("handle_error", END)
    g.add_edge("finalize", END)

    return g.compile()


# ----------------------------
# Public API
# ----------------------------
@contextmanager
def _pushd(path: str):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def run_langgraph_agent(task: str, repo_path: str) -> AgentState:
    """
    Run the agent using LangGraph.
    Same signature as the old run_agent for evaluator compatibility.
    """
    print("AGENT: started")

    app = build_graph()

    with _pushd(repo_path):
        initial: GraphState = {"agent": AgentState(task=task, repo_path=repo_path)}
        final = app.invoke(initial)
        state = final["agent"]

    # Print final output for non-skip paths (skip paths print in their nodes)
    if state.route_decision == "call_llm":
        print("\n===== FINAL AGENT OUTPUT =====")
        print(state.output)
        print("================================\n")

    print("AGENT: finished")
    return state


# Allow running directly for testing
if __name__ == "__main__":
    import sys
    task = sys.argv[1] if len(sys.argv) > 1 else "Identify high-risk areas."
    repo = sys.argv[2] if len(sys.argv) > 2 else "sample_repo"
    fs = run_langgraph_agent(task, repo_path=repo)
    print(f"\nSchema valid: {fs.schema_valid}")
    print(f"Citations valid: {fs.citations_valid}")