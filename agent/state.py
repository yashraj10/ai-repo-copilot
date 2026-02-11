from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentState:
    task: str
    plan: List[str] = field(default_factory=list)
    retrieved_files: List[Dict[str, Any]] = field(default_factory=list)
    analysis: str = ""
    output: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, bool] = field(default_factory=dict)
