"""
Planner node — analyzes the task and produces a dynamic execution plan.
In LangGraph, this is the entry node that sets up the workflow.
"""
from __future__ import annotations

import re
from agent.state import AgentState


def _detect_task_type(task: str) -> str:
    """Classify the task to inform planning."""
    task_lower = task.lower()

    # Security / traversal
    traversal_patterns = [r'\.\./\.\.', r'/etc/', r'/usr/', r'/var/', r'/tmp/', r'/home/']
    for pat in traversal_patterns:
        if re.search(pat, task_lower):
            return "security_reject"

    # Binary file analysis
    binary_extensions = ['.db', '.sqlite', '.exe', '.bin', '.dll', '.so', '.dylib']
    for ext in binary_extensions:
        if ext in task_lower:
            return "possibly_binary"

    # Specific file analysis
    if re.search(r'(file|path)\s+\S+\.\w+', task_lower):
        return "targeted_file"

    # Multi-file / broad analysis
    if any(kw in task_lower for kw in ['all files', 'every file', 'each file', 'across']):
        return "multi_file"

    return "general"


def plan_task(state: AgentState) -> AgentState:
    """Create an execution plan based on task analysis."""
    print("PLANNER: creating plan")

    task_type = _detect_task_type(state.task)

    # All plans start with listing files
    plan = ["List repository files"]

    if task_type == "security_reject":
        # Don't even try to read — go straight to analysis
        plan.append("Analyze code")
    else:
        plan.append("Read relevant files")
        plan.append("Analyze code")

    plan.append("Generate structured output")
    plan.append("Verify reliability")

    state.plan = plan
    return state