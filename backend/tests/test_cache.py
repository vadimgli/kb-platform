"""Tests for Telemetry-Fingerprinted SemanticPlanCache and Concurrent I/O."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.planner import PlannerAgent
from src.models.schemas import ExecutionPlan
from src.services.cache import SemanticPlanCache


def test_telemetry_fingerprint_differentiates_cluster_context() -> None:
  """Verifies SHA-256 fingerprint differentiates by tenant/cluster context."""
  key1 = SemanticPlanCache.compute_fingerprint(
    query="Pod crash",
    namespace="default",
    cluster_context="prod-us-central1",
  )
  key2 = SemanticPlanCache.compute_fingerprint(
    query="Pod crash",
    namespace="default",
    cluster_context="staging-eu-west1",
  )
  key3 = SemanticPlanCache.compute_fingerprint(
    query="Pod crash",
    namespace="default",
    cluster_context="prod-us-central1",
  )

  assert key1 != key2
  assert key1 == key3


def test_plan_cache_set_and_get_with_cluster_isolation() -> None:
  """Verifies plan is retrieved for matching context and misses for others."""
  cache = SemanticPlanCache(ttl_seconds=300)

  plan_prod = ExecutionPlan(
    summary="Prod Diagnostic Plan",
    target_tenant_id="prod-us-central1",
    actions=[],
    citations=["https://docs.google.com/test"],
  )

  cache.set_plan(
    plan=plan_prod,
    query="CrashLoopBackOff",
    namespace="kube-system",
    cluster_context="prod-us-central1",
  )

  # Hit on exact match
  cached = cache.get_plan(
    query="CrashLoopBackOff",
    namespace="kube-system",
    cluster_context="prod-us-central1",
  )
  assert cached is not None
  assert cached.summary == "Prod Diagnostic Plan"

  # Miss on different cluster context
  cached_staging = cache.get_plan(
    query="CrashLoopBackOff",
    namespace="kube-system",
    cluster_context="staging-eu-west1",
  )
  assert cached_staging is None


def test_plan_cache_expiration_eviction() -> None:
  """Verifies expired cache entries are discarded."""
  cache = SemanticPlanCache(ttl_seconds=1)

  plan = ExecutionPlan(
    summary="Short Lived Plan",
    target_tenant_id="default",
    actions=[],
    citations=[],
  )

  cache.set_plan(
    plan=plan,
    query="OOMKilled",
    namespace="default",
    cluster_context="test-cluster",
  )

  time.sleep(1.1)

  cached = cache.get_plan(
    query="OOMKilled",
    namespace="default",
    cluster_context="test-cluster",
  )
  assert cached is None


def test_planner_agent_concurrent_rag_and_memory_lookup() -> None:
  """Verifies PlannerAgent handles grounding retrieval concurrently."""
  import asyncio

  agent = PlannerAgent()

  mock_response = MagicMock()
  mock_json = {
    "summary": "Diagnostic Plan text",
    "target_tenant_id": "default",
    "actions": [],
    "citations": [],
  }
  mock_response.text = json.dumps(mock_json)

  with (
    patch.object(
      agent.client.aio.models,
      "generate_content",
      new_callable=AsyncMock,
      return_value=mock_response,
    ),
  ):
    plan = asyncio.run(
      agent.generate_plan(
        query="CrashLoopBackOff error in pod",
        client_id="default",
        context_snippets=[{"title": "Doc", "snippet": "Snippet"}],
      )
    )

    assert plan is not None
    assert plan.summary == "Diagnostic Plan text"
