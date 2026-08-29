"""FastAPI HTTP Gateway Routing and Model Armor / DLP Integration."""

from __future__ import annotations

import time
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.agents.registry import agent_registry
from src.agents.triage import PrimaryTriageAgent
from src.core.auth import get_authenticated_user_id
from src.core.exceptions import GuardrailValidationError
from src.core.logging_config import get_logger
from src.models.guardrails import (
  sanitize_and_verify_commands,
  sanitize_user_prompt_with_dlp_and_model_armor,
)
from src.models.schemas import (
  ChatSessionState,
  ChatTurnRequest,
  ChatTurnResponse,
  ExecutionPlan,
  PlanQueryRequest,
)
from src.services.cache import plan_cache
from src.services.rag import rag_service
from src.services.session_service import FirestoreExternalSessionService
from src.services.telemetry import telemetry_service

logger = get_logger("artifactforge.gateway.router")
router = APIRouter()
gateway_router = router
session_service = FirestoreExternalSessionService()


@router.post(
  "/chat",
  response_model=ChatTurnResponse,
  summary="Multi-turn conversational dialogue with Sub-Agent delegation",
)
async def chat_endpoint(
  request_data: ChatTurnRequest,
  request: Request,
  operator_id: str | None = Depends(get_authenticated_user_id),
) -> ChatTurnResponse:
  """Processes multi-turn chat turns with Sub-Agent + Transfer pattern."""
  start_time = time.time()
  client_id = request_data.client_id
  session_id = request_data.session_id

  logger.info(
    "Received conversational chat turn for session '%s' (client: '%s')",
    session_id,
    client_id,
  )

  # 1. Retrieve or initialize session state
  raw_session = session_service.get_session(
    session_id=session_id, user_id=operator_id
  )
  active_agent_name = raw_session.get("metadata", {}).get(
    "active_agent", "triage_agent"
  )
  raw_history = raw_session.get("turns", [])

  session_state = ChatSessionState(
    session_id=session_id,
    client_id=client_id,
    active_agent=active_agent_name,
    allowed_drive_folder_id=request_data.allowed_drive_folder_id,
  )

  # 2. Scrub PII and credentials using DLP & Model Armor
  sanitized_msg, _ = sanitize_user_prompt_with_dlp_and_model_armor(
    request_data.message
  )
  request_data.message = sanitized_msg

  # 3. Route through Primary Triage Agent (Tier 1)
  triage_agent = agent_registry.get_agent("triage_agent")
  if not triage_agent or not isinstance(triage_agent, PrimaryTriageAgent):
    specialist = agent_registry.get_agent("scoping_specialist")
    triage_agent = PrimaryTriageAgent(sub_agents=[specialist])

  try:
    turn_response = await triage_agent.route_and_process(
      turn_req=request_data,
      session_state=session_state,
    )
  except GuardrailValidationError as g_err:
    logger.warning("Safety guardrail violation: %s", g_err)
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Security Guardrail Violation: {g_err}",
    )
  except Exception as exc:
    logger.exception("Chat turn processing failed: %s", exc)
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Agent Gateway processing failed: {exc}",
    )

  # 4. Update Firestore persistent session
  elapsed_ms = int((time.time() - start_time) * 1000)
  session_service.add_turn_to_session(
    session_id=session_id,
    turn_data={
      "role": "user",
      "content": request_data.message,
      "timestamp": int(time.time()),
    },
    user_id=operator_id,
  )
  session_service.add_turn_to_session(
    session_id=session_id,
    turn_data={
      "role": "agent",
      "agent_name": turn_response.active_agent,
      "content": turn_response.reply,
      "timestamp": int(time.time()),
      "doc_url": turn_response.doc_url,
    },
    user_id=operator_id,
  )
  session_service.save_session(
    session_id=session_id,
    session_data={
      "metadata": {
        "active_agent": session_state.active_agent,
        "client_id": client_id,
      }
    },
  )

  # 5. Record BigQuery telemetry
  telemetry_service.record_query_metrics(
    session_id=session_id,
    query=request_data.message,
    latency_ms=elapsed_ms,
    prompt_tokens=len(request_data.message.split()) * 2,
    completion_tokens=len(turn_response.reply.split()) * 2,
    high_risk_flagged=False,
    client_id=client_id,
  )

  return turn_response


@router.post(
  "/query",
  response_model=ExecutionPlan,
  summary="Direct single-shot plan generation for backwards compatibility",
)
async def query_endpoint(
  request_data: PlanQueryRequest,
  request: Request,
  operator_id: str | None = Depends(get_authenticated_user_id),
) -> ExecutionPlan:
  """Synthesizes an In-Scope Deliverables ExecutionPlan for target tenant."""
  start_time = time.time()
  client_id = request_data.client_id or "default_client"

  logger.info(
    "Received single-shot plan query for tenant '%s': '%s'",
    client_id,
    request_data.query,
  )

  # 1. Sanitize user prompt with Model Armor / DLP
  sanitized_query, _ = sanitize_user_prompt_with_dlp_and_model_armor(
    request_data.query
  )

  # 2. Check Semantic Cache
  cached_plan = plan_cache.get_plan(
    query=sanitized_query,
    namespace=request_data.target_context,
    cluster_context=client_id,
    user_id=operator_id,
  )
  if cached_plan:
    logger.info("Serving scoping plan from semantic cache for '%s'", client_id)
    return cached_plan

  # 3. Grounding Context via Vertex AI Search
  context_snippets: list[dict[str, Any]] = []
  try:
    context_snippets = rag_service.search_documentation(
      query=sanitized_query, page_size=3
    )
  except Exception as rag_err:
    logger.warning("RAG retrieval fallback: %s", rag_err)

  # 4. Dispatch to Infill Planner via Registry
  planner = agent_registry.get_agent("planner")
  executor = agent_registry.get_agent("executor")
  if not planner or not executor:
    raise HTTPException(
      status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
      detail="Core Planner or Executor agent unavailable in AgentRegistry.",
    )

  try:
    plan: ExecutionPlan = await planner.generate_plan(
      query=sanitized_query,
      client_id=client_id,
      context_snippets=context_snippets,
    )
    actions = await executor.generate_actions(
      plan=plan,
      client_id=client_id,
    )
    sanitized_actions, high_risk_flagged, _ = sanitize_and_verify_commands(
      actions,
      allowed_tenant_id=client_id,
    )
    plan.actions = sanitized_actions

  except GuardrailValidationError as g_err:
    logger.warning("Safety guardrail violation: %s", g_err)
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Security Guardrail Violation: {g_err}",
    )
  except Exception as exc:
    logger.exception("Agent processing failed: %s", exc)
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Agent Gateway processing failed: {exc}",
    )

  # 5. Populate cache and telemetry
  plan_cache.set_plan(
    query=sanitized_query,
    plan=plan,
    namespace=request_data.target_context,
    cluster_context=client_id,
    user_id=operator_id,
  )

  elapsed_ms = int((time.time() - start_time) * 1000)
  telemetry_service.record_query_metrics(
    session_id=request_data.session_id or "adhoc_session",
    query=sanitized_query,
    latency_ms=elapsed_ms,
    prompt_tokens=plan.prompt_tokens or 0,
    completion_tokens=plan.completion_tokens or 0,
    high_risk_flagged=high_risk_flagged,
    client_id=client_id,
  )

  return plan
