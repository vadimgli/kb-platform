"""Typed state models for Tier 2 Workflow Graph DAGs."""

from pydantic import BaseModel, Field
from src.models.schemas import AgentAction, ScopingDeliverables


class ScopingWorkflowState(BaseModel):
  """Typed Global State mutated along the DAG edges."""

  session_id: str
  client_id: str
  allowed_drive_folder_id: str | None = None
  raw_user_prompt: str
  sanitized_prompt: str = ""
  research_findings: list[str] = Field(default_factory=list)
  deliverables: ScopingDeliverables | None = None
  actions_taken: list[AgentAction] = Field(default_factory=list)
  leakage_audit_passed: bool = False
  audit_violations: list[str] = Field(default_factory=list)
  exported_doc_url: str | None = None
  exported_doc_id: str | None = None
  error_message: str | None = None
  completed: bool = False
