"""Enterprise Agent Gateway Router for ArtifactForge."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.registry import agent_registry
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


@gateway_router.post(
  "/query",
  response_model=ExecutionPlan,
  status_code=status.HTTP_200_OK,
)
async def query_scoping_deliverables(
  request_data: AgentQueryRequest,
  operator_id: str | None = Depends(get_authenticated_user_id),
) -> ExecutionPlan:
  """Orchestrates generation of the In-Scope Scoping Deliverables."""
  start_time = time.time()
  client_id = request_data.client_id
  session_id = request_data.session_id

  logger.info(
    "Gateway received scoping request for tenant '%s' [User: %s]",
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
    return cached_plan

  # 3. Grounding Document Retrieval (Vertex AI Search)
  rag_snippets: list[dict[str, Any]] = []
  rag_start = time.time()
  try:
    rag_snippets = rag_service.search_k8s_documentation(sanitized_query)
  except Exception as e:
    logger.warning("RAG retrieval fallback: %s", e)
  rag_latency = int((time.time() - rag_start) * 1000)

  # 4. Agent 1: Infill Planner via AgentRegistry
  planner_start = time.time()
  planner = agent_registry.get_agent("planner")
  if planner and hasattr(planner, "generate_plan"):
    plan = await planner.generate_plan(
      query=sanitized_query,
      client_id=client_id,
      context_snippets=rag_snippets,
      image_bytes=request_data.image_data,
    )
  else:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="PlannerAgent is not registered in AgentRegistry",
    )
  planner_latency = int((time.time() - planner_start) * 1000)

  # 5. Agent 2: Action Synthesis via ExecutorAgent
  executor_start = time.time()
  executor = agent_registry.get_agent("executor")
  if executor and hasattr(executor, "generate_actions") and plan.actions:
    step_descs = [a.description for a in plan.actions]
    try:
      synthesized_actions = await executor.generate_actions(
        steps=step_descs,
        client_id=client_id,
        target_context=request_data.target_context,
      )
      if synthesized_actions:
        plan.actions = synthesized_actions
    except Exception as err:
      logger.warning("Executor synthesis fallback: %s", err)
  executor_latency = int((time.time() - executor_start) * 1000)

  # 6. Safety Guardrails & Zero-Leakage Verification
  try:
    plan = sanitize_and_verify_commands(plan)
  except GuardrailValidationError as g_err:
    logger.error("Plan failed safety verification: %s", g_err)
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Security Guardrail Violation: {g_err!s}",
    ) from g_err

  # 7. Store in Cache and Session
  plan_cache.set_plan(
    plan=plan,
    query=sanitized_query,
    namespace=request_data.target_context,
    cluster_context=client_id,
    user_id=operator_id,
  )

  session_service.add_turn_to_session(
    session_id=session_id,
    turn_data={
      "query": sanitized_query,
      "summary": plan.summary,
      "deliverables": (
        plan.deliverables.model_dump() if plan.deliverables else None
      ),
      "actions": [a.model_dump() for a in plan.actions],
    },
    user_id=operator_id,
  )

  # 8. Asynchronous Telemetry
  total_latency_ms = int((time.time() - start_time) * 1000)
  has_high_risk = any(a.risk_level == RiskLevel.HIGH for a in plan.actions)
  telemetry_service.record_query_metrics(
    session_id=session_id,
    query=sanitized_query,
    latency_ms=total_latency_ms,
    prompt_tokens=len(sanitized_query.split()) * 2,
    completion_tokens=len(plan.summary.split()) * 2,
    high_risk_flagged=has_high_risk,
    rag_latency_ms=rag_latency,
    planner_latency_ms=planner_latency,
    executor_latency_ms=executor_latency,
  )

  return plan
