"""SemanticPlanCache for low-latency Telemetry-Fingerprinted plan caching."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import threading
import time
from typing import Any
from pydantic import BaseModel, Field

from src.core.logging_config import get_logger
from src.models.guardrails import sanitize_and_verify_commands
from src.models.schemas import ExecutionPlan

logger = get_logger("artifactforge.cache")


class CacheMetadata(BaseModel):
  """Metadata tracking cache entry lifecycle and telemetry fingerprint."""

  created_at: float = Field(default_factory=time.time)
  ttl_seconds: int = Field(default=300)
  hit_count: int = Field(default=0)
  telemetry_hash: str


class CachedTroubleshootingEntry(BaseModel):
  """Immutable cache wrapper storing validated plans and metadata."""

  plan: ExecutionPlan
  metadata: CacheMetadata

  def is_expired(self) -> bool:
    """Returns True if current time exceeds created_at + ttl_seconds."""
    return (time.time() - self.metadata.created_at) > self.metadata.ttl_seconds


class SemanticPlanCache:
  """LRU-backed semantic cache with telemetry fingerprinting and short TTL.

  Serves identical repeat scoping queries in <15ms while enforcing
  mandatory guardrail re-validation.
  """

  def __init__(
    self,
    maxsize: int = 500,
    default_ttl: int = 300,
    ttl_seconds: int | None = None,
  ) -> None:
    """Initializes SemanticPlanCache with LRU capacity and default TTL.

    Args:
      maxsize: Maximum number of cached plans.
      default_ttl: Expiration time in seconds (default 300s / 5m).
      ttl_seconds: Alias for default_ttl.
    """
    self._cache: OrderedDict[str, CachedTroubleshootingEntry] = OrderedDict()
    self._lock = threading.Lock()
    self.maxsize = maxsize
    self.default_ttl = ttl_seconds if ttl_seconds is not None else default_ttl

  @staticmethod
  def compute_fingerprint(
    query: str,
    namespace: str | None = None,
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> str:
    """Calculates deterministic SHA256 telemetry fingerprint."""
    raw_payload = (
      f"q:{query.strip().lower()}|ns:{namespace or ''}|"
      f"cc:{cluster_context or ''}|u:{user_id or ''}"
    )
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

  def get_plan(
    self,
    query: str,
    namespace: str | None = None,
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> ExecutionPlan | None:
    """Retrieves cached plan and re-applies security guardrails."""
    fingerprint = self.compute_fingerprint(
      query=query,
      namespace=namespace,
      cluster_context=cluster_context,
      user_id=user_id,
    )

    with self._lock:
      entry = self._cache.get(fingerprint)
      if not entry:
        return None

      if entry.is_expired():
        logger.debug(
          "Cache entry expired for fingerprint: %s", fingerprint[:8]
        )
        del self._cache[fingerprint]
        return None

      self._cache.move_to_end(fingerprint)
      entry.metadata.hit_count += 1

      cached_plan = entry.plan.model_copy(deep=True)

    try:
      sanitized_plan = sanitize_and_verify_commands(cached_plan)
      logger.info(
        "Semantic cache HIT for query '%s' (hits=%d)",
        query[:30],
        entry.metadata.hit_count,
      )
      return sanitized_plan
    except Exception as exc:  # noqa: BLE001
      logger.warning(
        "Cached plan failed re-verification (%s); invalidating entry.", exc
      )
      with self._lock:
        if fingerprint in self._cache:
          del self._cache[fingerprint]
      return None

  def set_plan(
    self,
    query: str,
    plan: ExecutionPlan,
    namespace: str | None = None,
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> None:
    """Stores plan in cache with LRU eviction policy."""
    fingerprint = self.compute_fingerprint(
      query=query,
      namespace=namespace,
      cluster_context=cluster_context,
      user_id=user_id,
    )

    metadata = CacheMetadata(
      ttl_seconds=self.default_ttl,
      telemetry_hash=fingerprint,
    )
    entry = CachedTroubleshootingEntry(plan=plan, metadata=metadata)

    with self._lock:
      if fingerprint in self._cache:
        self._cache.move_to_end(fingerprint)
      self._cache[fingerprint] = entry
      if len(self._cache) > self.maxsize:
        oldest_key, _ = self._cache.popitem(last=False)
        logger.debug(
          "LRU semantic cache evicted oldest entry: %s", oldest_key[:8]
        )


plan_cache = SemanticPlanCache()
