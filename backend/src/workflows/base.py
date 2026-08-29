"""Abstract Base Workflow Graph engine for Tier 2 DAG governance."""

from abc import ABC, abstractmethod
from typing import Any
from src.core.logging_config import get_logger

logger = get_logger("artifactforge.workflows.base")


class BaseWorkflowGraph(ABC):
  """Abstract state-machine DAG engine managing node sequence execution."""

  def __init__(self, name: str) -> None:
    self.name = name

  @abstractmethod
  async def run(self, initial_state: Any) -> Any:
    """Executes the workflow graph DAG across all defined nodes."""
