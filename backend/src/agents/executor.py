"""ADK ExecutorAgent for Deterministic Structured Action Synthesis."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.genai import types

from src.agents.llm_agent import LlmAgent
from src.core.config import config
from src.models.schemas import AgentAction

logger = logging.getLogger("artifactforge.executor")


class ExecutorAgent(LlmAgent):
  """Synthesizes structured domain actions using zero-temperature Gemini."""

  def __init__(
    self,
    prompt_path: str = "src/prompts/executor_prompt_v1.yaml",
    model_name: str | None = None,
  ) -> None:
    super().__init__(
      prompt_path=prompt_path,
      model_name=model_name or config.executor_model or "gemini-2.5-flash-lite",
    )

  async def generate_actions(
    self,
    steps: list[str],
    client_id: str = "default",
    target_context: str = "default",
  ) -> list[AgentAction]:
    """Translates planning steps into concrete, structured AgentActions.

    Args:
      steps: List of planned execution steps or action descriptions.
      client_id: Mandatory tenant ID for isolation.
      target_context: Execution sub-context or workspace folder.

    Returns:
      List of validated Pydantic AgentAction instances.
    """
    logger.info(
      "Synthesizing %d actions for tenant '%s' using %s",
      len(steps),
      client_id,
      self.model_name,
    )

    contents = [
      f"Target Tenant Client ID: {client_id}",
      f"Target Context: {target_context}",
      "Steps to Translate into AgentAction objects:\n"
      + "\n".join(f"- {s}" for s in steps),
    ]

    response = await self.client.aio.models.generate_content(
      model=self.model_name,
      contents=contents,
      config=types.GenerateContentConfig(
        system_instruction=self.system_instruction,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=list[AgentAction],
      ),
    )

    raw_items = json.loads(response.text)
    actions: list[AgentAction] = []
    for item in raw_items:
      action = AgentAction.model_validate(item)
      if not action.target_tenant_id:
        action.target_tenant_id = client_id
      actions.append(action)

    return actions
