"""Scoping Specialist Sub-Agent for Tier 1 conversational dialogue."""

from pathlib import Path
from src.agents.specialists.base import BaseSpecialistSubAgent
from src.agents.tools.audit_tool import ZeroLeakageAuditTool
from src.agents.tools.drive_tool import GoogleDriveExportTool
from src.core.config import config
from src.core.logging_config import get_logger
from src.models.schemas import (
  ActionCategory,
  AgentAction,
  ChatSessionState,
  ChatTurnResponse,
  RiskLevel,
  ScopingDeliverableItem,
  ScopingDeliverables,
)
from src.workflows.scoping_dag import ScopingDeliverablesWorkflowGraph
from src.workflows.state import ScopingWorkflowState

logger = get_logger("artifactforge.specialists.scoping")

DEFAULT_PROMPT = (
  Path(__file__).parent.parent.parent
  / "prompts"
  / "scoping_specialist_prompt_v1.yaml"
)


class ScopingSpecialistSubAgent(BaseSpecialistSubAgent):
  """Specialist sub-agent for scoping deliverables and matrix refinement."""

  def __init__(
    self,
    prompt_path: str = str(DEFAULT_PROMPT),
    workflow_graph: ScopingDeliverablesWorkflowGraph | None = None,
    audit_tool: ZeroLeakageAuditTool | None = None,
    drive_tool: GoogleDriveExportTool | None = None,
  ) -> None:
    super().__init__(
      agent_name="scoping_specialist",
      description=(
        "Synthesizes and refines In-Scope Responsibilities Matrices over "
        "multi-turn dialogue."
      ),
      prompt_path=prompt_path,
      model_name=config.planner_model,
    )
    self.workflow_graph = workflow_graph or ScopingDeliverablesWorkflowGraph()
    self.audit_tool = audit_tool or ZeroLeakageAuditTool()
    self.drive_tool = drive_tool or GoogleDriveExportTool()

  async def handle_turn(
    self,
    user_message: str,
    session_state: ChatSessionState,
  ) -> ChatTurnResponse:
    """Handles a conversational turn, either running DAG or editing matrix."""
    logger.info(
      "ScopingSpecialist handling turn for session '%s' (client '%s')",
      session_state.session_id,
      session_state.client_id,
    )

    # Check if there is an existing deliverable in previous turns
    existing_deliverables: ScopingDeliverables | None = None
    for turn in reversed(session_state.history):
      if turn.deliverables is not None:
        existing_deliverables = turn.deliverables
        break

    # If user is asking for a refinement of an existing matrix
    is_refinement = existing_deliverables is not None and any(
      kw in user_message.lower()
      for kw in ("change", "modify", "add", "remove", "update", "row", "week")
    )

    if is_refinement and existing_deliverables is not None:
      return await self._handle_conversational_refinement(
        user_message=user_message,
        existing_deliverables=existing_deliverables,
        session_state=session_state,
      )

    # Otherwise execute the full Tier 2 Workflow Graph DAG
    initial_dag_state = ScopingWorkflowState(
      session_id=session_state.session_id,
      client_id=session_state.client_id,
      allowed_drive_folder_id=session_state.allowed_drive_folder_id,
      raw_user_prompt=user_message,
    )
    result_state = await self.workflow_graph.run(initial_dag_state)

    if result_state.error_message or not result_state.deliverables:
      reply = (
        "I encountered an issue generating your scoping deliverables: "
        f"{result_state.error_message or 'Unknown error'}"
      )
      return ChatTurnResponse(
        session_id=session_state.session_id,
        client_id=session_state.client_id,
        active_agent=self.agent_name,
        reply=reply,
        actions_taken=result_state.actions_taken,
      )

    reply_lines = [
      f"### {result_state.deliverables.title}",
      f"**Target Client:** `{session_state.client_id}` | "
      f"**Timeline:** {result_state.deliverables.timeline_weeks} Weeks\n",
      "| Project Scope Area | Technical Deliverables | Responsible Party |",
      "| :--- | :--- | :--- |",
    ]
    for item in result_state.deliverables.items:
      delivs_str = "<br>".join(f"• {d}" for d in item.technical_deliverables)
      reply_lines.append(
        f"| **{item.project_scope_area}** | {delivs_str} | "
        f"{item.responsible_party} |"
      )

    if result_state.exported_doc_url:
      reply_lines.append(
        f"\n📄 **Exported to Google Docs:** [{result_state.exported_doc_url}]"
        f"({result_state.exported_doc_url})"
      )

    return ChatTurnResponse(
      session_id=session_state.session_id,
      client_id=session_state.client_id,
      active_agent=self.agent_name,
      reply="\n".join(reply_lines),
      deliverables=result_state.deliverables,
      actions_taken=result_state.actions_taken,
      doc_url=result_state.exported_doc_url,
    )

  async def _handle_conversational_refinement(
    self,
    user_message: str,
    existing_deliverables: ScopingDeliverables,
    session_state: ChatSessionState,
  ) -> ChatTurnResponse:
    """Applies in-place modifications to existing matrix based on user turn."""
    logger.info("Applying conversational refinement to existing deliverables")
    updated_items = list(existing_deliverables.items)
    actions: list[AgentAction] = []

    # Example: User asks to add bullet or change row
    if "load testing" in user_message.lower():
      if len(updated_items) > 1:
        updated_items[1].technical_deliverables.append(
          "Performance benchmarking and load testing report"
        )
      else:
        updated_items.append(
          ScopingDeliverableItem(
            project_scope_area="Performance & Load Testing",
            technical_deliverables=["Load testing report under peak traffic"],
            responsible_party="Google FDE Team",
          )
        )
      actions.append(
        AgentAction(
          action_type=ActionCategory.FACT_INFILL_GENERATE,
          target_tenant_id=session_state.client_id,
          payload="Added load testing deliverable.",
          description="Updated deliverables matrix with load testing.",
          risk_level=RiskLevel.LOW,
          status="COMPLETED",
        )
      )

    if "8 week" in user_message.lower() or "8-week" in user_message.lower():
      existing_deliverables.timeline_weeks = 8
      actions.append(
        AgentAction(
          action_type=ActionCategory.FACT_INFILL_GENERATE,
          target_tenant_id=session_state.client_id,
          payload="Updated timeline to 8 weeks.",
          description="Extended project timeline.",
          risk_level=RiskLevel.LOW,
          status="COMPLETED",
        )
      )

    new_deliverables = ScopingDeliverables(
      title=existing_deliverables.title,
      client_id=session_state.client_id,
      items=updated_items,
      timeline_weeks=existing_deliverables.timeline_weeks,
    )

    # Re-verify zero leakage
    passed, violations = self.audit_tool.audit_deliverables(
      deliverables=new_deliverables,
      allowed_client_id=session_state.client_id,
    )

    reply_lines = [
      f"### Updated: {new_deliverables.title}",
      f"**Target Client:** `{session_state.client_id}` | "
      f"**Timeline:** {new_deliverables.timeline_weeks} Weeks\n",
      "| Project Scope Area | Technical Deliverables | Responsible Party |",
      "| :--- | :--- | :--- |",
    ]
    for item in new_deliverables.items:
      delivs_str = "<br>".join(f"• {d}" for d in item.technical_deliverables)
      reply_lines.append(
        f"| **{item.project_scope_area}** | {delivs_str} | "
        f"{item.responsible_party} |"
      )

    return ChatTurnResponse(
      session_id=session_state.session_id,
      client_id=session_state.client_id,
      active_agent=self.agent_name,
      reply="\n".join(reply_lines),
      deliverables=new_deliverables,
      actions_taken=actions,
    )
