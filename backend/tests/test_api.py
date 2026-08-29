"""Unit and integration tests for FastAPI gateway endpoints."""

import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from src.main import app
from src.models.schemas import (
  ActionCategory,
  AgentAction,
  ExecutionPlan,
  RiskLevel,
  ScopingDeliverableItem,
  ScopingDeliverables,
)


class TestAPIGateway(unittest.TestCase):
  """Test suite covering REST query and health checks."""

  def setUp(self):
    self.client = TestClient(app)

  def test_healthz_endpoint(self):
    """Tests GET /healthz returns 200 OK."""
    response = self.client.get("/healthz")
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data.get("status"), "ok")
    self.assertEqual(data.get("service"), "artifactforge-api")

  def test_readyz_endpoint(self):
    """Tests GET /readyz returns 200 OK with readiness details."""
    response = self.client.get("/readyz")
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data.get("status"), "ready")
    self.assertIn("capabilities", data)
    self.assertIn("scoping_deliverables", data["capabilities"])

  @patch("src.gateway.router.rag_service.search_k8s_documentation")
  @patch("src.agents.planner.PlannerAgent.generate_plan")
  @patch("src.agents.executor.ExecutorAgent.generate_actions")
  def test_query_endpoint_success(self, mock_actions, mock_plan, mock_rag):
    """Tests POST /api/v1/query returns valid ExecutionPlan."""
    mock_rag.return_value = [{"snippet": "Mock grounding context"}]
    mock_plan.return_value = ExecutionPlan(
      summary="Test Scoping Deliverables for Client D",
      target_tenant_id="client_d",
      deliverables=ScopingDeliverables(
        title="In-Scope Scoping Deliverables",
        client_id="client_d",
        items=[
          ScopingDeliverableItem(
            project_scope_area="Model Evals Setup",
            technical_deliverables=[
              "Evaluation report across Gemini versions"
            ],
            responsible_party="Google FDE Team",
          )
        ],
      ),
      actions=[
        AgentAction(
          action_type=ActionCategory.DISCOVERY_SEARCH,
          target_tenant_id="client_d",
          payload="Search notes",
          description="Discovery Search",
          risk_level=RiskLevel.LOW,
        )
      ],
      citations=["https://docs.google.com/test"],
    )
    mock_actions.return_value = [
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id="client_d",
        payload="Search notes",
        description="Discovery Search",
        risk_level=RiskLevel.LOW,
      )
    ]

    payload = {
      "query": "Create scoping deliverables for data platform",
      "client_id": "client_d",
      "session_id": "session-test-01",
    }

    response = self.client.post("/api/v1/query", json=payload)
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["target_tenant_id"], "client_d")
    self.assertIsNotNone(data["deliverables"])
    self.assertEqual(len(data["deliverables"]["items"]), 1)
    self.assertEqual(
      data["deliverables"]["items"][0]["responsible_party"], "Google FDE Team"
    )

  @patch("src.gateway.router.rag_service.search_k8s_documentation")
  @patch("src.agents.planner.PlannerAgent.generate_plan")
  @patch("src.agents.executor.ExecutorAgent.generate_actions")
  def test_query_endpoint_guardrail_violation_blocks(
    self, mock_actions, mock_plan, mock_rag
  ):
    """Tests that cross-tenant access is blocked by safety guardrail."""
    mock_rag.return_value = [{"snippet": "Mock grounding context"}]
    mock_plan.return_value = ExecutionPlan(
      summary="Malicious cross-tenant plan",
      target_tenant_id="client_d",
      actions=[
        AgentAction(
          action_type=ActionCategory.DISCOVERY_SEARCH,
          target_tenant_id="client_b",  # Foreign tenant
          payload="Read client_b vault",
          description="Cross tenant read",
          risk_level=RiskLevel.LOW,
        )
      ],
    )
    mock_actions.return_value = [
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id="client_b",
        payload="Read client_b vault",
        description="Cross tenant read",
        risk_level=RiskLevel.LOW,
      )
    ]

    payload = {
      "query": "Read another client data",
      "client_id": "client_d",
    }

    response = self.client.post("/api/v1/query", json=payload)
    self.assertEqual(response.status_code, 400)
    self.assertIn("Security Guardrail Violation", response.json()["detail"])


if __name__ == "__main__":
  unittest.main()
