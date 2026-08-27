"""Agent2Agent (A2A) Server Router for ArtifactForge."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from src.a2a.types import (
  A2AMessage,
  A2AResponsePayload,
  A2ATask,
  AgentCard,
  AgentSkill,
)

logger = logging.getLogger("a2a.server")


def create_a2a_router(
  agent: Any,
  agent_name: str = "artifactforge_platform",
  description: str = (
    "Enterprise Multi-Agent Platform for Deliverable Generation."
  ),
  base_url: str = "http://localhost:8000",
  version: str = "1.0.0",
  skills: list[AgentSkill] | None = None,
) -> APIRouter:
  """Creates a FastAPI router implementing the A2A server specification.

  Args:
    agent: Target backend agent instance.
    agent_name: Unique agent identifier.
    description: Agent summary for discovery.
    base_url: Public base URL where agent is hosted.
    version: Agent implementation version string.
    skills: List of AgentSkill descriptors exposed.

  Returns:
    Configured FastAPI APIRouter.
  """
  router = APIRouter(tags=["A2A Protocol"])

  default_skills = skills or [
    AgentSkill(
      id="scoping_deliverables",
      name="Scoping Deliverables Generation",
      description="Generates zero-leakage enterprise scoping deliverables.",
    ),
    AgentSkill(
      id="quality_critique",
      name="Quality and Leakage Audit",
      description="Screens cross-tenant leakage and verifies rubrics.",
    ),
  ]

  card = AgentCard(
    name=agent_name,
    description=description,
    url=base_url,
    version=version,
    skills=default_skills,
  )

  @router.get("/.well-known/agent-card.json", response_model=AgentCard)
  async def get_agent_card() -> AgentCard:
    """Publishes the A2A Agent Card."""
    return card

  @router.post("/a2a/v1/message", response_model=A2AMessage)
  async def receive_a2a_message(message: A2AMessage) -> A2AMessage:
    """Receives and processes incoming A2A message tasks."""
    logger.info(
      "Received A2A message %s from '%s' [Task Skill: %s]",
      message.id,
      message.sender,
      message.task.skill_id if message.task else "None",
    )

    skill_id = message.task.skill_id if message.task else "scoping_deliverables"
    input_payload = (
      message.task.input_payload
      if message.task and message.task.input_payload
      else {}
    )
    query_text = input_payload.get("query", message.content or "")
    client_id = input_payload.get("client_id", "default")

    if not query_text and not message.task:
      return A2AMessage(
        role="agent",
        sender=agent_name,
        recipient=message.sender,
        in_response_to=message.id,
        error="Message did not contain an actionable task or content",
      )

    try:
      if hasattr(agent, "generate_plan"):
        plan = await agent.generate_plan(
          query=query_text,
          client_id=client_id,
        )
        output_data = (
          plan.model_dump(mode="json")
          if hasattr(plan, "model_dump")
          else plan
        )
        summary_text = getattr(plan, "summary", str(output_data))
      else:
        output_data = {
          "status": "acknowledged",
          "query": query_text,
          "agent": agent_name,
        }
        summary_text = str(output_data)

      return A2AMessage(
        role="agent",
        sender=agent_name,
        recipient=message.sender,
        in_response_to=message.id,
        content=summary_text,
        task=A2ATask(
          skill_id=skill_id,
          input_payload=input_payload or {"query": query_text},
          status="COMPLETED",
          result=summary_text,
        ),
        response=A2AResponsePayload(
          status="SUCCESS",
          result_data=output_data,
        ),
      )
    except Exception as err:
      logger.exception("Error processing A2A task %s", message.id)
      return A2AMessage(
        role="agent",
        sender=agent_name,
        recipient=message.sender,
        in_response_to=message.id,
        error=f"Task processing failed: {err!s}",
      )

  return router


def export_as_a2a_app(
  agent: Any,
  agent_name: str = "artifactforge_platform",
  **kwargs: Any,
) -> Any:
  """Wraps an agent in a standalone FastAPI application implementing A2A.

  Args:
    agent: Target backend agent instance.
    agent_name: Unique agent identifier.
    **kwargs: Additional parameters passed to create_a2a_router.

  Returns:
    FastAPI application instance.
  """
  from fastapi import FastAPI

  app = FastAPI(title=agent_name)
  app.include_router(create_a2a_router(agent, agent_name=agent_name, **kwargs))
  return app

