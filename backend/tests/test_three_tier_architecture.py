"""Unit and integration tests for the 3-Tier Enterprise Architecture."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.agents.planner import PlannerAgent
from src.agents.specialists.scoping import ScopingSpecialistSubAgent
from src.agents.tools.audit_tool import ZeroLeakageAuditTool
from src.agents.tools.drive_tool import GoogleDriveExportTool
from src.agents.tools.research_tool import ResearchAgentTool
from src.agents.triage import PrimaryTriageAgent
from src.main import app
from src.models.schemas import (
  ChatSessionState,
  ChatTurnRequest,
  ExecutionPlan,
  ScopingDeliverableItem,
  ScopingDeliverables,
)
from src.services.rag import VertexRAGService
from src.workflows.scoping_dag import ScopingDeliverablesWorkflowGraph
from src.workflows.state import ScopingWorkflowState


def _get_mock_plan(client_id: str) -> ExecutionPlan:
  return ExecutionPlan(
    summary=f"In-Scope Deliverables for {client_id}",
    target_tenant_id=client_id,
    deliverables=ScopingDeliverables(
      title="In-Scope Scoping Deliverables",
      client_id=client_id,
      items=[
        ScopingDeliverableItem(
          project_scope_area="Model Evals Setup",
          technical_deliverables=["Clean deliverable without foreign data"],
          responsible_party="Google FDE Team",
        ),
        ScopingDeliverableItem(
          project_scope_area="Productization in Target Environment",
          technical_deliverables=["Deploy headless agents to Cloud Run"],
          responsible_party="Google FDE Team",
        ),
      ],
      timeline_weeks=6,
    ),
    actions=[],
    citations=[],
  )


class TestThreeTierArchitecture(unittest.IsolatedAsyncioTestCase):
  """Comprehensive test suite covering Tier 1, Tier 2, and Tier 3."""

  def setUp(self):
    self.client = TestClient(app)

  # --- Tier 3: Isolated Leaf Tools Tests ---

  async def test_tier3_research_tool_bounds_context(self):
    """Verifies ResearchAgentTool aggregates grounding without context bleed."""
    mock_rag = MagicMock(spec=VertexRAGService)
    mock_rag.search_documentation.return_value = [
      {"snippet": "Grounded ML evals and monitoring context."}
    ]
    tool = ResearchAgentTool(rag_service=mock_rag)
    findings = await tool.execute_research(
      query="Scoping requirements for data platform",
      client_id="client_d",
      allowed_folder_id="folder_123",
    )
    self.assertIsInstance(findings, list)
    self.assertGreater(len(findings), 0)

  def test_tier3_audit_tool_catches_foreign_tenant(self):
    """Verifies ZeroLeakageAuditTool flags foreign client names in matrix."""
    audit_tool = ZeroLeakageAuditTool()
    clean_matrix = ScopingDeliverables(
      title="In-Scope Scoping Deliverables",
      client_id="client_d",
      items=[
        ScopingDeliverableItem(
          project_scope_area="Model Evals Setup",
          technical_deliverables=["Clean deliverable without foreign data"],
          responsible_party="Google FDE Team",
        )
      ],
    )
    passed, violations = audit_tool.audit_deliverables(
      deliverables=clean_matrix, allowed_client_id="client_d"
    )
    self.assertTrue(passed)
    self.assertEqual(len(violations), 0)

    # Matrix with foreign tenant contamination
    leaked_matrix = ScopingDeliverables(
      title="In-Scope Scoping Deliverables",
      client_id="client_d",
      items=[
        ScopingDeliverableItem(
          project_scope_area="Model Evals Setup",
          technical_deliverables=["Configure cluster for client_healthcare"],
          responsible_party="Google FDE Team",
        )
      ],
    )
    passed_leaked, violations_leaked = audit_tool.audit_deliverables(
      deliverables=leaked_matrix, allowed_client_id="client_d"
    )
    self.assertFalse(passed_leaked)
    self.assertIn("Foreign Client Leakage", violations_leaked[0])

  # --- Tier 2: Workflow Graph DAG Tests ---

  async def test_tier2_workflow_dag_executes_all_nodes(self):
    """Verifies ScopingDeliverablesWorkflowGraph executes 5 nodes in order."""
    mock_planner = MagicMock(spec=PlannerAgent)
    mock_planner.generate_plan = AsyncMock(
      return_value=_get_mock_plan("client_d")
    )
    mock_rag = MagicMock(spec=VertexRAGService)
    mock_rag.search_documentation.return_value = [
      {"snippet": "Grounded context"}
    ]
    research_tool = ResearchAgentTool(rag_service=mock_rag)
    mock_drive_tool = MagicMock(spec=GoogleDriveExportTool)
    mock_drive_tool.export_matrix_to_doc = AsyncMock(
      return_value={
        "document_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "document_id": "doc_mock_123",
        "drive_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "title": "In-Scope Scoping Deliverables",
      }
    )
    dag = ScopingDeliverablesWorkflowGraph(
      research_tool=research_tool,
      planner_agent=mock_planner,
      drive_tool=mock_drive_tool,
    )

    initial_state = ScopingWorkflowState(
      session_id="test-session-dag-01",
      client_id="client_d",
      allowed_drive_folder_id="folder_999",
      raw_user_prompt="Draft our scoping deliverables matrix",
    )

    result_state = await dag.run(initial_state)

    self.assertTrue(result_state.completed)
    self.assertTrue(result_state.leakage_audit_passed)
    self.assertIsNotNone(result_state.deliverables)
    self.assertIsNotNone(result_state.exported_doc_url)
    self.assertEqual(len(result_state.actions_taken), 5)

  # --- Tier 1: Conversational Sub-Agent + Transfer Tests ---

  async def test_tier1_primary_triage_delegation(self):
    """Verifies PrimaryTriageAgent transfers active session to specialist."""
    mock_planner = MagicMock(spec=PlannerAgent)
    mock_planner.generate_plan = AsyncMock(
      return_value=_get_mock_plan("client_d")
    )
    mock_rag = MagicMock(spec=VertexRAGService)
    mock_rag.search_documentation.return_value = [
      {"snippet": "Grounded context"}
    ]
    research_tool = ResearchAgentTool(rag_service=mock_rag)
    mock_drive_tool = MagicMock(spec=GoogleDriveExportTool)
    mock_drive_tool.export_matrix_to_doc = AsyncMock(
      return_value={
        "document_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "document_id": "doc_mock_123",
        "drive_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "title": "In-Scope Scoping Deliverables",
      }
    )
    mock_dag = ScopingDeliverablesWorkflowGraph(
      research_tool=research_tool,
      planner_agent=mock_planner,
      drive_tool=mock_drive_tool,
    )
    specialist = ScopingSpecialistSubAgent(workflow_graph=mock_dag)

    triage = PrimaryTriageAgent(sub_agents=[specialist])
    session_state = ChatSessionState(
      session_id="chat-sess-001",
      client_id="client_d",
      active_agent="triage_agent",
    )
    req = ChatTurnRequest(
      session_id="chat-sess-001",
      client_id="client_d",
      message="Please draft our 6-week deliverables matrix",
    )

    response = await triage.route_and_process(
      turn_req=req, session_state=session_state
    )

    self.assertEqual(session_state.active_agent, "scoping_specialist")
    self.assertEqual(response.active_agent, "scoping_specialist")
    self.assertIn("In-Scope Scoping Deliverables", response.reply)
    self.assertIsNotNone(response.deliverables)
    self.assertEqual(len(session_state.history), 2)

  async def test_tier1_multi_turn_conversational_refinement(self):
    """Verifies conversational follow-up turns modify existing deliverables."""
    mock_planner = MagicMock(spec=PlannerAgent)
    mock_planner.generate_plan = AsyncMock(
      return_value=_get_mock_plan("client_d")
    )
    mock_rag = MagicMock(spec=VertexRAGService)
    mock_rag.search_documentation.return_value = [
      {"snippet": "Grounded context"}
    ]
    research_tool = ResearchAgentTool(rag_service=mock_rag)
    mock_drive_tool = MagicMock(spec=GoogleDriveExportTool)
    mock_drive_tool.export_matrix_to_doc = AsyncMock(
      return_value={
        "document_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "document_id": "doc_mock_123",
        "drive_url": "https://docs.google.com/document/d/doc_mock_123/edit",
        "title": "In-Scope Scoping Deliverables",
      }
    )
    mock_dag = ScopingDeliverablesWorkflowGraph(
      research_tool=research_tool,
      planner_agent=mock_planner,
      drive_tool=mock_drive_tool,
    )
    specialist = ScopingSpecialistSubAgent(workflow_graph=mock_dag)

    session_state = ChatSessionState(
      session_id="chat-sess-002",
      client_id="client_d",
      active_agent="scoping_specialist",
    )

    # Turn 1: Initial creation
    initial_req = ChatTurnRequest(
      session_id="chat-sess-002",
      client_id="client_d",
      message="Create scoping deliverables",
    )
    resp1 = await specialist.handle_turn(
      user_message=initial_req.message, session_state=session_state
    )
    self.assertIsNotNone(resp1.deliverables)
    session_state.history.append(
      MagicMock(deliverables=resp1.deliverables, role="agent")
    )

    # Turn 2: Refinement ("Add load testing and make timeline 8 weeks")
    resp2 = await specialist.handle_turn(
      user_message="Add load testing to row 2 and make timeline 8 weeks",
      session_state=session_state,
    )
    self.assertIsNotNone(resp2.deliverables)
    self.assertEqual(resp2.deliverables.timeline_weeks, 8)
    deliv_text = " ".join(
      " ".join(item.technical_deliverables)
      for item in resp2.deliverables.items
    )
    self.assertIn("load testing", deliv_text.lower())

  # --- Gateway API /chat Endpoint Integration Test ---

  @patch(
    "src.agents.specialists.scoping.ScopingSpecialistSubAgent.handle_turn"
  )
  def test_chat_gateway_api_endpoint(self, mock_handle):
    """Tests POST /api/v1/chat endpoint integration."""
    from src.models.schemas import ChatTurnResponse

    mock_handle.return_value = ChatTurnResponse(
      session_id="sess-gateway-chat-01",
      client_id="client_d",
      active_agent="scoping_specialist",
      reply="### In-Scope Scoping Deliverables\nExported to Google Docs.",
      deliverables=_get_mock_plan("client_d").deliverables,
      doc_url="https://docs.google.com/document/d/doc_mock_123/edit",
    )

    payload = {
      "session_id": "sess-gateway-chat-01",
      "client_id": "client_d",
      "message": "Draft our scoping deliverables matrix",
      "allowed_drive_folder_id": "folder_client_d",
    }

    response = self.client.post("/api/v1/chat", json=payload)
    self.assertEqual(response.status_code, 200)
    data = response.json()
    self.assertEqual(data["session_id"], "sess-gateway-chat-01")
    self.assertEqual(data["active_agent"], "scoping_specialist")
    self.assertIn("In-Scope Scoping Deliverables", data["reply"])
    self.assertIsNotNone(data["deliverables"])
    self.assertIsNotNone(data["doc_url"])


if __name__ == "__main__":
  unittest.main()
