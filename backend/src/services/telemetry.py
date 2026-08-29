"""OpenTelemetry tracing and BigQuery telemetry service for ArtifactForge."""

import concurrent.futures
from datetime import UTC, datetime
import logging
import re
from typing import Any

try:
  from google.cloud import bigquery  # type: ignore[attr-defined]
except ImportError:
  bigquery = None

try:
  from google.cloud import aiplatform  # type: ignore[attr-defined]
except ImportError:
  aiplatform = None

try:
  from opentelemetry import trace
  from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
  )
except ImportError:
  trace = None

from src.core.config import config

logger = logging.getLogger("artifactforge.telemetry")


class TelemetryService:
  """Centralized service for OpenTelemetry spans and BigQuery metrics."""

  def __init__(
    self,
    dataset_id: str = "telemetry_logs",
    table_id: str = "query_metrics",
  ) -> None:
    """Initializes TracerProvider and BigQuery client with offline fallback."""
    self.project_id = config.gcp_project_id
    self.dataset_id = dataset_id
    self.table_id = table_id
    self._tracer: Any = None
    self._bq_client: Any = None
    self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    self._setup_tracer()

  def _setup_tracer(self) -> None:
    """Configures OTEL TracerProvider with Cloud Trace or Console fallback."""
    if trace is None:
      logger.info("OpenTelemetry SDK unavailable; using no-op tracing.")
      return

    provider = TracerProvider()
    try:
      if (
        self.project_id
        and self.project_id != "dummy-gcp-project"
        and not self.project_id.startswith("test-")
      ):
        exporter = CloudTraceSpanExporter(project_id=self.project_id)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(
          "Configured OpenTelemetry with CloudTraceSpanExporter for %s",
          self.project_id,
        )
      else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Configured OpenTelemetry with ConsoleSpanExporter.")
    except Exception as exc:  # noqa: BLE001
      logger.warning("Trace exporter setup warning: %s; using Console.", exc)
      provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    self._tracer = trace.get_tracer("artifactforge.gateway")

  @property
  def tracer(self) -> Any:
    """Returns initialized OTEL Tracer instance."""
    if self._tracer is None and trace is not None:
      self._tracer = trace.get_tracer("artifactforge.gateway")
    return self._tracer

  def get_tracer(self) -> Any:
    """Returns initialized OTEL Tracer instance."""
    return self.tracer

  def record_span_attributes(
    self,
    span: Any,
    session_id: str,
    vais_hit_count: int = 0,
    step_count: int = 0,
    high_risk_count: int = 0,
    overridden: bool = False,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
  ) -> None:
    """Attaches standardized evaluation and observability attributes to span."""
    if not span:
      return
    span.set_attribute("artifactforge.query.session_id", session_id)
    span.set_attribute("artifactforge.planner.vais_hit_count", vais_hit_count)
    span.set_attribute("artifactforge.executor.step_count", step_count)
    span.set_attribute(
      "artifactforge.guardrail.high_risk_count", high_risk_count
    )
    span.set_attribute("artifactforge.guardrail.overridden", overridden)
    span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
    span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)
    span.set_attribute(
      "gen_ai.usage.total_tokens", prompt_tokens + completion_tokens
    )

  def calculate_query_cost_usd(
    self,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
  ) -> float:
    """Calculates estimated query cost in USD based on Gemini pricing tiers."""
    cost_prompt = (prompt_tokens / 1_000_000.0) * 0.075
    cost_completion = (completion_tokens / 1_000_000.0) * 0.30
    cost_cached = (cached_tokens / 1_000_000.0) * 0.01875
    return round(cost_prompt + cost_completion + cost_cached, 6)

  def _insert_bq_row(self, row: dict[str, Any]) -> None:
    """Worker function to insert a single telemetry row into BigQuery."""
    if (
      bigquery is None
      or not self.project_id
      or self.project_id == "dummy-gcp-project"
      or self.project_id.startswith("test-")
    ):
      logger.info(
        "BigQuery offline mode; logged query metric in-memory: %s", row
      )
      return

    try:
      if self._bq_client is None:
        self._bq_client = bigquery.Client(project=self.project_id)
      table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
      errors = self._bq_client.insert_rows_json(table_ref, [row])
      if errors:
        logger.warning(
          "BigQuery telemetry insert errors (non-fatal): %s", errors
        )
      else:
        logger.debug("Successfully exported query metrics to BigQuery.")
    except Exception as exc:  # noqa: BLE001
      logger.info("BigQuery telemetry export fallback: %s", exc)

  def record_query_metrics(
    self,
    session_id: str,
    query: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    high_risk_flagged: bool,
    user_rating: int = 0,
    cached_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
    rag_latency_ms: int = 0,
    planner_latency_ms: int = 0,
    executor_latency_ms: int = 0,
    model_version: str = "gemini-2.5-flash",
    prompt_template_version: str = "v1.0",
    client_id: str = "",
  ) -> None:
    """Non-blocking background export of query telemetry to BigQuery."""
    if estimated_cost_usd <= 0.0:
      estimated_cost_usd = self.calculate_query_cost_usd(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
      )

    row = {
      "session_id": session_id,
      "client_id": client_id,
      "timestamp": datetime.now(UTC).isoformat(),
      "query_length": len(query),
      "latency_ms": latency_ms,
      "prompt_tokens": prompt_tokens,
      "completion_tokens": completion_tokens,
      "cached_tokens": cached_tokens,
      "estimated_cost_usd": estimated_cost_usd,
      "high_risk_flagged": high_risk_flagged,
      "user_rating": user_rating,
      "rag_latency_ms": rag_latency_ms,
      "planner_latency_ms": planner_latency_ms,
      "executor_latency_ms": executor_latency_ms,
      "model_version": model_version,
      "prompt_template_version": prompt_template_version,
    }

    self._executor.submit(self._insert_bq_row, row)

  def log_vertex_experiment_run(
    self,
    experiment_name: str,
    run_name: str,
    metrics: dict[str, float | int],
    params: dict[str, Any],
  ) -> None:
    """Logs evaluation metrics and hyperparams to Vertex AI Experiments."""
    if (
      aiplatform is None
      or not self.project_id
      or self.project_id == "dummy-gcp-project"
      or self.project_id.startswith("test-")
    ):
      logger.info(
        "Vertex AI offline mode; recorded experiment run '%s' metrics: %s",
        run_name,
        metrics,
      )
      return

    try:
      aiplatform.init(
        project=self.project_id,
        location=config.gcp_location,
        experiment=experiment_name,
      )
      with aiplatform.start_run(run_name) as run:
        clean_params = {
          k: str(v) if isinstance(v, list | dict) else v
          for k, v in params.items()
        }
        run.log_params(clean_params)
        clean_metrics = {
          re.sub(r"[^a-zA-Z0-9_\-]", "_", k): float(v)
          for k, v in metrics.items()
        }
        run.log_metrics(clean_metrics)
      logger.info(
        "Logged evaluation run '%s' to Vertex AI Experiment '%s'.",
        run_name,
        experiment_name,
      )
    except Exception as exc:  # noqa: BLE001
      logger.info("Vertex AI Experiment logging fallback: %s", exc)


telemetry_service = TelemetryService()
