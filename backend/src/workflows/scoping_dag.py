"""Tier 2 Workflow Graph DAG for Scoping Deliverables."""

from src.agents.planner import PlannerAgent
from src.agents.tools.audit_tool import ZeroLeakageAuditTool
from src.agents.tools.drive_tool import GoogleDriveExportTool
from src.agents.tools.research_tool import ResearchAgentTool
from src.core.logging_config import get_logger
from src.models.guardrails import sanitize_user_prompt_with_dlp_and_model_armor
from src.models.schemas import ActionCategory, AgentAction, RiskLevel
from src.workflows.base import BaseWorkflowGraph
from src.workflows.state import ScopingWorkflowState

logger = get_logger("artifactforge.workflows.scoping_dag")


class ScopingDeliverablesWorkflowGraph(BaseWorkflowGraph):
  """Deterministic 5-node DAG for Scoping Deliverables lifecycle."""

  def __init__(
    self,
    research_tool: ResearchAgentTool | None = None,
    planner_agent: PlannerAgent | None = None,
    audit_tool: ZeroLeakageAuditTool | None = None,
    drive_tool: GoogleDriveExportTool | None = None,
  ) -> None:
    super().__init__(name="scoping_deliverables_dag")
    self.research_tool = research_tool or ResearchAgentTool()
    self.planner_agent = planner_agent or PlannerAgent()
    self.audit_tool = audit_tool or ZeroLeakageAuditTool()
    self.drive_tool = drive_tool or GoogleDriveExportTool()

  async def run(
    self, initial_state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Executes the 5-node state-machine DAG in deterministic sequence."""
    state = initial_state
    logger.info(
      "Starting ScopingDeliverablesWorkflowGraph for session '%s'",
      state.session_id,
    )

    try:
      # Node 1: Ingest & DLP / Model Armor Sanitization
      state = await self._node_ingest_and_sanitize(state)

      # Node 2: Deep Research via Isolated Tool Worker
      state = await self._node_execute_research(state)

      # Node 3: Infill Structural Skeleton
      state = await self._node_infill_structural_skeleton(state)

      # Node 4: Zero-Leakage & Multi-Tenant Audit
      state = await self._node_audit_leakage_safety(state)

      # Node 5: Google Drive MCP Export
      if state.leakage_audit_passed and state.deliverables:
        state = await self._node_export_to_google_drive(state)

      state.completed = True
      logger.info(
        "Successfully completed ScopingDeliverablesWorkflowGraph for '%s'",
        state.session_id,
      )

    except Exception as err:
      logger.error("Workflow DAG execution error: %s", err)
      state.error_message = str(err)
      state.completed = False

    return state

  async def _node_ingest_and_sanitize(
    self, state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Node 1: Sanitizes prompt with Model Armor & Cloud DLP."""
    logger.debug("Node 1: Sanitizing prompt for client '%s'", state.client_id)
    sanitized, modified = sanitize_user_prompt_with_dlp_and_model_armor(
      state.raw_user_prompt
    )
    state.sanitized_prompt = sanitized
    state.actions_taken.append(
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id=state.client_id,
        payload="DLP & Model Armor Sanitization",
        description="Prompt sanitized for secrets and PII.",
        risk_level=RiskLevel.LOW,
        status="COMPLETED",
      )
    )
    return state

  async def _node_execute_research(
    self, state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Node 2: Runs deep research in isolated Tier 3 worker sandbox."""
    logger.debug("Node 2: Executing research for '%s'", state.client_id)
    findings = await self.research_tool.execute_research(
      query=state.sanitized_prompt,
      client_id=state.client_id,
      allowed_folder_id=state.allowed_drive_folder_id,
    )
    state.research_findings = findings
    state.actions_taken.append(
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id=state.client_id,
        payload=f"Gathered {len(findings)} research findings.",
        description="Deep research conducted via RAG and sandboxed Drive.",
        risk_level=RiskLevel.LOW,
        status="COMPLETED",
      )
    )
    return state

  async def _node_infill_structural_skeleton(
    self, state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Node 3: Infills abstract 3-column skeleton with active facts."""
    logger.debug("Node 3: Infilling deliverables for '%s'", state.client_id)
    context_snippets = [{"snippet": f} for f in state.research_findings]
    plan = await self.planner_agent.generate_plan(
      query=state.sanitized_prompt,
      client_id=state.client_id,
      context_snippets=context_snippets,
    )
    state.deliverables = plan.deliverables
    items_count = len(plan.deliverables.items) if plan.deliverables else 0
    state.actions_taken.append(
      AgentAction(
        action_type=ActionCategory.FACT_INFILL_GENERATE,
        target_tenant_id=state.client_id,
        payload=f"Infilled {items_count} scope areas.",
        description="Synthesized 3-column scoping deliverables matrix.",
        risk_level=RiskLevel.MEDIUM,
        status="COMPLETED",
      )
    )
    return state

  async def _node_audit_leakage_safety(
    self, state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Node 4: Evaluates deliverables for foreign client contamination."""
    logger.debug("Node 4: Auditing zero-leakage for '%s'", state.client_id)
    if not state.deliverables:
      state.leakage_audit_passed = False
      state.audit_violations = ["No deliverables generated to audit."]
      return state

    passed, violations = self.audit_tool.audit_deliverables(
      deliverables=state.deliverables,
      allowed_client_id=state.client_id,
    )
    state.leakage_audit_passed = passed
    state.audit_violations = violations
    state.actions_taken.append(
      AgentAction(
        action_type=ActionCategory.LEAKAGE_AUDIT_SCREEN,
        target_tenant_id=state.client_id,
        payload=f"Audit result: {'PASSED' if passed else 'FAILED'}",
        description="Zero-leakage multi-tenant screening.",
        risk_level=RiskLevel.LOW,
        status="COMPLETED" if passed else "FAILED",
      )
    )
    return state

  async def _node_export_to_google_drive(
    self, state: ScopingWorkflowState
  ) -> ScopingWorkflowState:
    """Node 5: Exports formatted table to client's Google Drive folder."""
    logger.debug("Node 5: Exporting to Google Drive for '%s'", state.client_id)
    if not state.deliverables:
      return state

    res = await self.drive_tool.export_matrix_to_doc(
      deliverables=state.deliverables,
      allowed_folder_id=state.allowed_drive_folder_id,
    )
    state.exported_doc_url = res.get("document_url")
    state.exported_doc_id = res.get("document_id")
    state.actions_taken.append(
      AgentAction(
        action_type=ActionCategory.DRIVE_EXPORT,
        target_tenant_id=state.client_id,
        payload=f"Doc exported: {state.exported_doc_url}",
        description="Exported 3-column table to Google Docs.",
        risk_level=RiskLevel.LOW,
        status="COMPLETED",
      )
    )
    return state
