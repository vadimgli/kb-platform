"""Agent2Agent (A2A) Server Router for ArtifactForge."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

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
  agent_name: str = "artifactforge_agent",
  description: str = (
    "Enterprise Multi-Agent Platform for Deliverable Generation."
  ),
  base_url: str = "https://artifactforge-api-415008794281.us-central1.run.app",
  version: str = "1.0.0",
  skills: list[AgentSkill] | None = None,
) -> APIRouter:
  """Creates a FastAPI router implementing the A2A server specification."""
  router = APIRouter(tags=["A2A Protocol"])

  default_skills = skills or [
    AgentSkill(
      id="scoping_deliverables",
      name="scoping_deliverables",
      description=(
        "Synthesizes 3-column in-scope responsibilities matrix (Scope Area,"
        " Technical Deliverables, Responsible Party) with zero cross-tenant"
        " leakage."
      ),
      tags=["SCOPING_DELIVERABLES"],
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

  async def _handle_incoming_a2a(
    raw_payload: dict[str, Any],
  ) -> dict[str, Any]:
    """Processes incoming A2A payloads from Gemini Enterprise or peer agents."""
    logger.info("Processing A2A payload keys: %s", list(raw_payload.keys()))

    # Extract user message/query from flexible A2A formats
    query_text = ""
    client_id = raw_payload.get("client_id", "client-fsi-alpha")

    if "messages" in raw_payload and isinstance(raw_payload["messages"], list):
      last_msg = raw_payload["messages"][-1]
      if isinstance(last_msg, dict):
        query_text = last_msg.get("content", "")
      elif isinstance(last_msg, str):
        query_text = last_msg

    if not query_text:
      query_text = (
        raw_payload.get("query")
        or raw_payload.get("message")
        or raw_payload.get("content")
        or raw_payload.get("prompt")
        or ""
      )

    task_dict = raw_payload.get("task", {})
    if isinstance(task_dict, dict) and not query_text:
      input_payload = task_dict.get("input_payload", {})
      query_text = input_payload.get("query", "")
      client_id = input_payload.get("client_id", client_id)

    if not query_text:
      query_text = "Generate an in-scope deliverables matrix and implementation workplan."

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

      return {
        "role": "agent",
        "sender": agent_name,
        "recipient": raw_payload.get("sender", "gemini_enterprise"),
        "in_response_to": raw_payload.get("id"),
        "content": summary_text,
        "reply": summary_text,
        "task": {
          "skill_id": "scoping_deliverables",
          "input_payload": {"query": query_text, "client_id": client_id},
          "status": "COMPLETED",
          "result": summary_text,
        },
        "response": {
          "status": "SUCCESS",
          "result_data": output_data,
        },
      }
    except Exception as err:
      logger.exception("Error processing A2A task")
      return {
        "role": "agent",
        "sender": agent_name,
        "content": f"Task processing failed: {err!s}",
        "reply": f"Task processing failed: {err!s}",
        "error": str(err),
      }

  @router.post("/", summary="Root A2A Agent Endpoint")
  @router.post("/tasks", summary="A2A Tasks Endpoint")
  @router.post("/messages", summary="A2A Messages Endpoint")
  @router.post("/a2a/v1/message", summary="A2A v1 Message Endpoint")
  @router.post("/v1/tasks", summary="A2A v1 Tasks Endpoint")
  async def receive_a2a_entrypoint(request: Request) -> dict[str, Any]:
    """Unified entrypoint handling root POST and sub-path A2A invocations."""
    try:
      payload = await request.json()
    except Exception:
      payload = {}
    return await _handle_incoming_a2a(payload)

  return router


def export_as_a2a_app(
  agent: Any,
  agent_name: str = "artifactforge_platform",
  **kwargs: Any,
) -> Any:
  """Wraps an agent in a standalone FastAPI application implementing A2A."""
  from fastapi import FastAPI

  app = FastAPI(title=agent_name)
  app.include_router(create_a2a_router(agent, agent_name=agent_name, **kwargs))
  return app
