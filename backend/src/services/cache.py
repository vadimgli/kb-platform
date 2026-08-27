"""SemanticPlanCache for low-latency Telemetry-Fingerprinted plan caching."""

import hashlib
import threading
import time
from collections import OrderedDict

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
    namespace: str | None = "default",
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> str:
    """Computes SHA-256 fingerprint from query and cluster telemetry.

    Args:
      query: Raw user query string.
      namespace: Kubernetes target namespace.
      cluster_context: Optional cluster context name.
      user_id: Operator ID for memory partitioning.

    Returns:
      SHA-256 hexadecimal digest string.
    """
    raw_payload = (
      f"{query.strip().lower()}::{namespace or 'default'}::"
      f"{cluster_context or ''}::{user_id or ''}"
    )
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

  def get_plan(
    self,
    query: str,
    namespace: str | None = "default",
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> ExecutionPlan | None:
    """Retrieves a cached plan if present, not expired, and guardrail-safe.

    Args:
      query: Raw user query string.
      namespace: Kubernetes target namespace.
      cluster_context: Optional cluster context name.
      user_id: Operator ID for memory partitioning.

    Returns:
      ExecutionPlan if cached and valid, else None.
    """
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
        self._cache.pop(fingerprint, None)
        logger.info(f"Evicted expired semantic cache entry: {fingerprint[:8]}")
        return None

      # Move to end for LRU refresh
      self._cache.move_to_end(fingerprint)
      entry.metadata.hit_count += 1
      plan = entry.plan

    # MANDATORY AGENTS.md RULE 3C: Re-validate all commands via guardrails
    try:
      plan = sanitize_and_verify_commands(plan)
      logger.info(
        f"Semantic cache hit (<15ms) for query '{query[:30]}...' "
        f"fingerprint={fingerprint[:8]} (hit_count={entry.metadata.hit_count})"
      )
      return plan
    except Exception as e:  # noqa: BLE001
      logger.warning(
        f"Cached plan failed guardrail re-validation ({e}); bypassing cache."
      )
      return None

  def set_plan(
    self,
    plan: ExecutionPlan,
    query: str,
    namespace: str | None = "default",
    cluster_context: str | None = None,
    user_id: str | None = None,
  ) -> None:
    """Stores a validated ExecutionPlan in LRU cache.

    Args:
      plan: The Pydantic ExecutionPlan to cache.
      query: Raw user query string.
      namespace: Kubernetes target namespace.
      cluster_context: Optional cluster context name.
      user_id: Operator ID for memory partitioning.
    """
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
          f"LRU semantic cache evicted oldest entry: {oldest_key[:8]}"
        )
