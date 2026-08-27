"""Unit tests for Agent2Agent (A2A) protocol implementation."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.a2a.registry import A2ARegistry
from src.a2a.types import AgentCard, AgentSkill
from src.main import app


class TestA2AProtocol(unittest.IsolatedAsyncioTestCase):
  """Test suite covering Agent Card publishing, discovery, and A2A dispatch."""

  def setUp(self):
    self.client = TestClient(app)

  def test_agent_card_endpoint(self):
    """Tests GET /.well-known/agent-card.json returns valid Agent Card."""
    response = self.client.get("/.well-known/agent-card.json")
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["name"], "artifactforge_agent")
    self.assertIn("skills", data)
    self.assertGreater(len(data["skills"]), 0)

  @patch("src.main.planner_agent.generate_plan")
  def test_a2a_message_endpoint(self, mock_gen):
    """Tests POST /a2a/v1/message handles incoming agent messages."""
    from src.models.schemas import ArtifactType, ExecutionPlan

    mock_gen.return_value = ExecutionPlan(
      summary="A2A Scoping Plan",
      target_tenant_id="a2a_caller",
      artifact_type=ArtifactType.SCOPING_DOC,
      actions=[],
    )
    payload = {"role": "user", "content": "What is the project scope?"}
    response = self.client.post("/a2a/v1/message", json=payload)
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["role"], "agent")
    self.assertIn("content", data)

  async def test_a2a_registry_discovery_and_fanout(self):
    """Tests A2ARegistry card discovery and fan-out querying."""
    mock_card = AgentCard(
      name="pricing_agent",
      description="Market pricing checker",
      url="http://pricing-agent:8001",
      skills=[
        AgentSkill(
          id="pricing",
          name="Price Check",
          description="Check prices",
        )
      ],
    )

    registry = A2ARegistry()

    with patch.object(registry, "_fetch_card_http", return_value=mock_card):
      card = await registry.register_remote_agent("http://pricing-agent:8001")
      self.assertEqual(card.name, "pricing_agent")

      resolved = registry.get_card("pricing_agent")
      self.assertIsNotNone(resolved)
      self.assertEqual(resolved.name, "pricing_agent")

      skills_found = registry.find_agents_by_skill("pricing")
      self.assertEqual(len(skills_found), 1)

    async def mock_stream(target, content):
      yield f"Result from {target}: 42 USD"

    with patch.object(registry, "send_message", side_effect=mock_stream):
      results = await registry.fan_out_query(
        targets=["pricing_agent"],
        content="Get market price",
      )
      self.assertEqual(
        results["pricing_agent"], "Result from pricing_agent: 42 USD"
      )

    await registry.close()


if __name__ == "__main__":
  unittest.main()
