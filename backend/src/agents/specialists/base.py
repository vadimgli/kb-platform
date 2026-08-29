"""Abstract Base Specialist Sub-Agent for Tier 1 conversational delegation."""

from abc import ABC, abstractmethod
from typing import Any
from src.agents.llm_agent import LlmAgent
from src.models.schemas import ChatSessionState, ChatTurnResponse


class BaseSpecialistSubAgent(LlmAgent, ABC):
  """Abstract base class for domain specialist sub-agents."""

  def __init__(
    self,
    agent_name: str,
    description: str,
    prompt_path: str,
    model_name: str | None = None,
  ) -> None:
    super().__init__(prompt_path=prompt_path, model_name=model_name)
    self.agent_name = agent_name
    self.description = description

  @abstractmethod
  async def handle_turn(
    self,
    user_message: str,
    session_state: ChatSessionState,
  ) -> ChatTurnResponse:
    """Processes a conversational turn within the specialist's domain."""
