"""Enterprise Agent Gateway Router for ArtifactForge."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.registry import agent_registry
from src.agents.triage import PrimaryTriageAgent
from src.core.auth import get_authenticated_user_id
from src.core.exceptions import GuardrailValidationError
from src.models.guardrails import (
  classify_action_risk,
  sanitize_and_verify_commands,
  sanitize_user_prompt_with_dlp_and_model_armor,
)
from src.models.schemas import (
  AgentAction,
  AgentQueryRequest,
  ChatSessionState,
  ChatTurnRequest,
  ChatTurnResponse,
  ExecutionPlan,
  RiskLevel,
)
from src.services.cache import SemanticPlanCache
from src.services.rag import VertexRAGService
from src.services.session_service import FirestoreExternalSessionService
from src.services.telemetry import telemetry_service

logger = logging.getLogger("artifactforge.gateway")

gateway_router = APIRouter(prefix="/api/v1", tags=["Agent Gateway"])
plan_cache = SemanticPlanCache()
session_service = FirestoreExternalSessionService()
rag_service = VertexRAGService()
triage_agent = PrimaryTriageAgent()


@gateway_router.post(
  "/chat",
  response_model=ChatTurnResponse,
  status_code=status.HTTP_200_OK,
)
async def chat_conversational_turn(
  request_data: ChatTurnRequest,
  operator_id: str | None = Depends(get_authenticated_user_id),
) -> ChatTurnResponse:
  """Orchestrates Tier 1 multi-turn chat and specialist sub-agent handoffs."""
  start_time = time.time()
  session_id = request_data.session_id
  client_id = request_data.client_id

  logger.info(
    "Gateway chat turn for tenant '%s' [User: %s, Session: %s]",
    client_id,
    operator_id or "anonymous",
    session_id,
  )

  # 1. Fetch or initialize conversation session state
  raw_session = session_service.get_session(
    session_id=session_id, user_id=operator_id
  )
  session_state = ChatSessionState(
    session_id=session_id,
    client_id=client_id,
    active_agent=raw_session.get("metadata", {}).get(
      "active_agent", "triage_agent"
    ),
    allowed_drive_folder_id=request_data.allowed_drive_folder_id,
  )

  # 2. Dispatch turn to Tier 1 Primary Triage Agent
  try:
    response = await triage_agent.route_and_process(
      turn_req=request_data,
      session_state=session_state,
    )

    # 3. Persist session history
    turn_dict = {
      "query": request_data.message,
      "reply": response.reply,
      "active_agent": response.active_agent,
      "deliverables": (
        response.deliverables.model_dump()
        if response.deliverables
        else None
      ),
      "doc_url": response.doc_url,
    }
    session_service.add_turn_to_session(
      session_id=session_id,
      turn_data=turn_dict,
      user_id=operator_id,
    )

    # 4. Stream BigQuery telemetry metrics asynchronously
    latency_ms = int((time.time() - start_time) * 1000)
    telemetry_service.record_query_metrics(
      session_id=session_id,
      query=request_data.message,
      latency_ms=latency_ms,
      prompt_tokens=400,
      completion_tokens=250,
      high_risk_flagged=False,
      user_rating=0,
    )

    return response

  except Exception as exc:
    logger.error("Chat gateway failure: %s", exc)
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Conversational Gateway Error: {exc}",
    ) from exc


@gateway_router.post(
  "/query",
  response_model=ExecutionPlan,
  status_code=status.HTTP_200_OK,
)
async def query_scoping_deliverables(
  request_data: AgentQueryRequest,
  operator_id: str | None = Depends(get_authenticated_user_id),
) -> ExecutionPlan:
  """Orchestrates single-shot generation of In-Scope Scoping Deliverables."""
  start_time = time.time()
  client_id = request_data.client_id
  session_id = request_data.session_id

  logger.info(
    "Gateway received scoping query for tenant '%s' [User: %s]",
    client_id,
    operator_id or "anonymous",
  )

  # 1. DLP & Model Armor Input Redaction
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
    context_snippets = rag_service.search_k8s_documentation(
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

    # 5. Deterministic Action Synthesis via Executor
    steps = [
      f"Synthesize deliverables for area: {item.project_scope_area}"
      for item in (plan.deliverables.items if plan.deliverables else [])
    ]
    actions: list[AgentAction] = await executor.generate_actions(
      steps=steps, client_id=client_id
    )

    # 6. Safety Guardrail & Tenant Isolation
    sanitized_actions, high_risk_flagged, _ = sanitize_and_verify_commands(
      actions=actions,
      allowed_tenant_id=client_id,
    )
    plan.actions = sanitized_actions

    # 7. Store in Cache
    plan_cache.set_plan(
      plan=plan,
      query=sanitized_query,
      namespace=request_data.target_context,
      cluster_context=client_id,
      user_id=operator_id,
    )

    # 8. Record Telemetry
    latency_ms = int((time.time() - start_time) * 1000)
    telemetry_service.record_query_metrics(
      session_id=session_id,
      query=sanitized_query,
      latency_ms=latency_ms,
      prompt_tokens=500,
      completion_tokens=300,
      high_risk_flagged=high_risk_flagged,
      user_rating=0,
    )

    return plan

  except GuardrailValidationError as g_err:
    logger.error("Safety guardrail violation: %s", g_err.message)
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Security Guardrail Violation: {g_err.message}",
    ) from g_err
  except Exception as exc:
    logger.error("Agent Gateway processing failed: %s", exc)
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Agent Gateway Execution Error: {exc}",
    ) from exc
