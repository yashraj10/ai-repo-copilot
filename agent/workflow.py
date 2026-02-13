"""
Workflow entry point — delegates to LangGraph.
"""
from agent.state import AgentState
from agent.langgraph_workflow import run_langgraph_agent


def run_agent(task: str, repo_path: str) -> AgentState:
    return run_langgraph_agent(task=task, repo_path=repo_path)