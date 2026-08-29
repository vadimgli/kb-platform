"""Unit and evaluation tests for OpenTelemetry and BigQuery telemetry."""

from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.agents.registry import agent_registry
from src.main import app
from src.services import telemetry
from src.services.telemetry import TelemetryService, telemetry_service

client = TestClient(app)


def test_telemetry_service_initialization() -> None:
  """Verifies TelemetryService initializes in offline/dummy projects."""
  service = TelemetryService(
    dataset_id="test_dataset", table_id="test_query_metrics"
  )
  assert service.dataset_id == "test_dataset"
  assert service.table_id == "test_query_metrics"
  assert service.get_tracer() is not None


def test_record_span_attributes_schema() -> None:
  """Verifies attributes are attached to OpenTelemetry spans."""
  mock_span = MagicMock()
  telemetry_service.record_span_attributes(
    span=mock_span,
    session_id="session-eval-123",
    vais_hit_count=3,
    step_count=4,
    high_risk_count=1,
    overridden=True,
    prompt_tokens=450,
    completion_tokens=180,
  )

  calls = {
    call.args[0]: call.args[1]
    for call in mock_span.set_attribute.call_args_list
  }
  assert calls["artifactforge.query.session_id"] == "session-eval-123"
  assert calls["artifactforge.planner.vais_hit_count"] == 3
  assert calls["artifactforge.executor.step_count"] == 4
  assert calls["artifactforge.guardrail.high_risk_count"] == 1
  assert calls["artifactforge.guardrail.overridden"] is True
  assert calls["gen_ai.usage.prompt_tokens"] == 450
  assert calls["gen_ai.usage.completion_tokens"] == 180
  assert calls["gen_ai.usage.total_tokens"] == 630


def test_record_query_metrics_offline_fallback() -> None:
  """Verifies record_query_metrics catches offline/dummy project."""
  service = TelemetryService()
  service.project_id = "dummy-gcp-project"

  service.record_query_metrics(
    session_id="session-offline-001",
    query="Draft scoping deliverables matrix",
    latency_ms=1250,
    prompt_tokens=500,
    completion_tokens=250,
    high_risk_flagged=True,
    user_rating=5,
  )
  service._executor.shutdown(wait=True)


def test_log_vertex_experiment_run_offline() -> None:
  """Verifies log_vertex_experiment_run handles offline project."""
  service = TelemetryService()
  service.project_id = "dummy-gcp-project"

  service.log_vertex_experiment_run(
    experiment_name="artifactforge-evals",
    run_name="run-offline-test",
    params={"planner_model": "gemini-2.5-flash"},
    metrics={"average_score": 3.0},
  )


def test_log_vertex_experiment_run_active(monkeypatch: Any) -> None:
  """Verifies log_vertex_experiment_run handles active project gracefully."""
  mock_aiplatform = MagicMock()
  monkeypatch.setattr(telemetry, "aiplatform", mock_aiplatform)

  service = TelemetryService()
  service.project_id = "real-project-id"
  service.log_vertex_experiment_run(
    experiment_name="artifactforge-evals",
    run_name="run-active-test",
    params={"planner_model": "gemini-2.5-flash"},
    metrics={"average_score": 3.0},
  )
  mock_aiplatform.init.assert_called_once()


def test_log_vertex_experiment_run_exception_fallback(
  monkeypatch: Any,
) -> None:
  """Verifies log_vertex_experiment_run handles exceptions gracefully."""

  def mock_init(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("Vertex API Error")

  monkeypatch.setattr(telemetry, "aiplatform", MagicMock())
  monkeypatch.setattr(telemetry.aiplatform, "init", mock_init)

  service = TelemetryService()
  service.project_id = "real-project-id"
  service.log_vertex_experiment_run(
    experiment_name="artifactforge-evals",
    run_name="run-error-test",
    params={"planner_model": "gemini-2.5-flash"},
    metrics={"average_score": 3.0},
  )


def test_record_query_metrics_bigquery_schema_integrity() -> None:
  """Verifies payload schema sent to BigQuery matches query_metrics table."""
  service = TelemetryService()
  service.project_id = "prod-test-project"
  mock_bq = MagicMock()
  mock_bq.insert_rows_json.return_value = []
  service._bq_client = mock_bq

  row = {
    "timestamp": "2026-08-04T03:00:00+00:00",
    "session_id": "session-bq-eval-001",
    "query": "Scoping deliverables query",
    "latency_ms": 1100,
    "prompt_tokens": 400,
    "completion_tokens": 200,
    "high_risk_flagged": False,
    "user_rating": 0,
  }
  with patch("src.services.telemetry.bigquery", MagicMock()):
    service._insert_bq_row(row)

  mock_bq.insert_rows_json.assert_called_once()
  args = mock_bq.insert_rows_json.call_args[0]
  assert args[0] == "prod-test-project.telemetry_logs.query_metrics"
  inserted_row = args[1][0]
  required_cols = [
    "timestamp",
    "session_id",
    "query",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "high_risk_flagged",
    "user_rating",
  ]
  for col in required_cols:
    assert col in inserted_row


def test_query_api_emits_telemetry() -> None:
  """Verifies /api/v1/query emits BigQuery telemetry metrics."""
  payload = {
    "query": "Generate scoping deliverables for cloud platform",
    "client_id": "default",
    "session_id": "session-api-telemetry-001",
  }

  from src.models.schemas import (
    ActionCategory,
    AgentAction,
    ExecutionPlan,
    RiskLevel,
  )

  mock_plan = ExecutionPlan(
    summary="Scoping plan for platform",
    target_tenant_id="default",
    actions=[
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id="default",
        payload="Search discovery notes",
        description="Check status",
        risk_level=RiskLevel.LOW,
      )
    ],
    citations=["https://docs.google.com/test"],
  )
  planner = agent_registry.get_agent("planner")
  executor = agent_registry.get_agent("executor")

  with (
    patch.object(planner, "generate_plan", return_value=mock_plan),
    patch.object(
      executor, "generate_actions", return_value=mock_plan.actions
    ),
    patch.object(
      telemetry_service, "record_query_metrics"
    ) as mock_record_metrics,
  ):
    response = client.post("/api/v1/query", json=payload)
    assert response.status_code == 200
    mock_record_metrics.assert_called_once()
    kwargs = mock_record_metrics.call_args.kwargs
    assert kwargs["session_id"] == "session-api-telemetry-001"
    assert kwargs["query"] == payload["query"]
    assert "latency_ms" in kwargs
