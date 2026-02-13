# State.py — Agent state with LangGraph retry support
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentState:
    task: str
    repo_path: str

    # Planner
    plan: List[str] = field(default_factory=list)

    # Executor
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    retrieved_files: List[Dict[str, Any]] = field(default_factory=list)

    # Summarizer
    output: Dict[str, Any] = field(default_factory=dict)

    # Verifier
    schema_valid: bool = False
    citations_valid: bool = False
    schema_errors: List[str] = field(default_factory=list)
    citation_errors: List[str] = field(default_factory=list)

    # LangGraph retry loop
    llm_attempts: int = 0
    max_llm_attempts: int = 2
    last_validation_feedback: Optional[str] = None

    # Routing flags (set by analyze node)
    route_decision: str = "call_llm"  # "call_llm" | "skip_llm" | "error"