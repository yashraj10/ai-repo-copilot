from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentState:
    task: str
    repo_path: str = "sample_repo"

    plan: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    retrieved_files: List[Dict[str, Any]] = field(default_factory=list)
    analysis: str = ""
    output: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, bool] = field(default_factory=dict)
