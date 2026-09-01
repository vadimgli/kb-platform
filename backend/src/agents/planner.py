"""ADK PlannerAgent for In-Scope Responsibilities Matrix planning."""

from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from src.agents.llm_agent import LlmAgent
from src.core.config import config
from src.models.schemas import (
  AgentQueryRequest,
  ExecutionPlan,
  InScopeResponsibilitiesMatrix,
  ResponsibilityMatrixItem,
)

logger = logging.getLogger("artifactforge.planner")


class PlannerAgent(LlmAgent):
  """Plans and infills the In-Scope Responsibilities Matrix."""

  def __init__(
    self,
    prompt_path: str = "src/prompts/planner_prompt_v1.yaml",
    model_name: str | None = None,
  ) -> None:
    super().__init__(
      prompt_path=prompt_path,
      model_name=model_name or config.planner_model or "gemini-2.5-flash",
    )

  async def generate_plan(
    self,
    query: str | AgentQueryRequest,
    client_id: str = "default",
    context_snippets: list[dict[str, Any]] | None = None,
    image_bytes: bytes | None = None,
  ) -> ExecutionPlan:
    """Generates an ExecutionPlan with the In-Scope Responsibilities Matrix.

    Args:
      query: User prompt, scoping requirements, or request object.
      client_id: Mandatory client tenant ID for zero-leakage grounding.
      context_snippets: Grounding snippets from discovery notes.
      image_bytes: Optional screenshot or diagram image data.

    Returns:
      Validated Pydantic ExecutionPlan instance.
    """
    if isinstance(query, AgentQueryRequest):
      raw_query = query.query
      client_id = query.client_id or client_id
    else:
      raw_query = str(query)

    logger.info(
      "Generating scoping matrix for tenant '%s' using %s",
      client_id,
      self.model_name,
    )

    contents: list[Any] = [
      f"Target Tenant Client ID: {client_id}",
      f"User Query / Scoping Requirements:\n{raw_query}",
      f"Grounded Discovery Notes (CONFIDENTIAL - CLIENT {client_id} ONLY):\n"
      f"{context_snippets or []}",
    ]

    if image_bytes:
      contents.append(
        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
      )

    response = await self.client.aio.models.generate_content(
      model=self.model_name,
      contents=contents,
      config=types.GenerateContentConfig(
        system_instruction=self.system_instruction,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=ExecutionPlan,
      ),
    )

    plan = ExecutionPlan.model_validate_json(response.text)
    plan.target_tenant_id = client_id
    if plan.matrix:
      plan.matrix.client_id = client_id
    return plan

  async def converse(
    self,
    query: str,
    client_id: str = "default",
  ) -> str:
    """Answers general questions conversationally with Enterprise context."""
    system_prompt = (
      "You are the Enterprise Assistant for ArtifactForge integrated within Gemini Enterprise.\n"
      "You can answer general technical, cloud architecture, and project management questions.\n"
      "You have integrated Model Context Protocol (MCP) access to the authorized client Google Drive folder "
      "(ID: 1IIxHSQLgvUSTwBpuZXDvTcUTWIBCWxHn) for reading discovery notes and exporting In-Scope Responsibilities Matrices into Google Docs.\n"
      "If the user asks general questions or asks about your capabilities/Google Drive access, answer accurately, "
      "professionally, and helpfully. Offer to generate a 3-column In-Scope Responsibilities Matrix or implementation workplan if relevant."
    )
    response = await self.client.aio.models.generate_content(
      model=self.model_name,
      contents=[query],
      config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
      ),
    )
    return response.text or "I am your Gemini Enterprise assistant. How can I assist you today?"

