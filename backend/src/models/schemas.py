"""Domain schemas for Scoping Deliverables and Conversational Multi-Agent."""

from __future__ import annotations

from enum import Enum
import time
from typing import Any
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
  """Risk classification for agent actions."""

  LOW = "LOW"
  MEDIUM = "MEDIUM"
  HIGH = "HIGH"


class ActionCategory(str, Enum):
  """Category of action synthesized by executor."""

  DISCOVERY_SEARCH = "DISCOVERY_SEARCH"
  FACT_INFILL_GENERATE = "FACT_INFILL_GENERATE"
  LEAKAGE_AUDIT_SCREEN = "LEAKAGE_AUDIT_SCREEN"
  DRIVE_EXPORT = "DRIVE_EXPORT"
  DRIVE_MATRIX_EXPORT = "DRIVE_MATRIX_EXPORT"
  NOTIFY_OPERATOR = "NOTIFY_OPERATOR"


class ArtifactType(str, Enum):
  """Artifact classification type."""

  SCOPING_DOC = "SCOPING_DOC"
  DELIVERABLES = "DELIVERABLES"
  MATRIX = "MATRIX"


class ScopingDeliverableItem(BaseModel):
  """A single scope area with a constrained list of technical deliverables."""

  project_scope_area: str = Field(
    ...,
    description="Scope area (e.g. 'Model Evals Setup', 'Productization')",
  )
  technical_deliverables: list[str] = Field(
    ...,
    description="Constrained list of bulleted technical deliverables",
  )
  responsible_party: str = Field(
    ...,
    description="Assigned owner (e.g. 'Google FDE Team', 'Google & Client')",
  )


class ScopingDeliverables(BaseModel):
  """Complete Scoping Deliverables matrix."""

  title: str = Field(
    default="In-Scope Scoping Deliverables",
    description="Title of the scoping document",
  )
  client_id: str = Field(
    ...,
    description="Target tenant client identifier",
  )
  items: list[ScopingDeliverableItem] = Field(
    default_factory=list,
    description="List of scoping deliverable items",
  )
  timeline_weeks: int = Field(
    default=6,
    description="Total project duration in weeks",
  )

  def __init__(self, **data: Any):
    if "rows" in data and "items" not in data:
      data["items"] = data.pop("rows")
    super().__init__(**data)

  @property
  def rows(self) -> list[ScopingDeliverableItem]:
    """Backward compatibility alias for items."""
    return self.items


# Aliases for backward compatibility
ResponsibilityMatrixItem = ScopingDeliverableItem
InScopeResponsibilitiesMatrix = ScopingDeliverables


class AgentAction(BaseModel):
  """Deterministic execution step synthesized by ExecutorAgent."""

  action_type: ActionCategory
  target_tenant_id: str
  payload: str
  description: str
  risk_level: RiskLevel = RiskLevel.LOW
  status: str = "PENDING"


class ExecutionPlan(BaseModel):
  """Structured execution plan emitted by PlannerAgent."""

  summary: str = Field(
    ...,
    description="Executive summary of the synthesized scoping deliverables",
  )
  target_tenant_id: str
  artifact_type: ArtifactType | str | None = None
  deliverables: ScopingDeliverables | None = None
  actions: list[AgentAction] = Field(default_factory=list)
  citations: list[str] = Field(default_factory=list)

  @property
  def matrix(self) -> ScopingDeliverables | None:
    """Alias for deliverables matrix."""
    return self.deliverables


TroubleshootingPlan = ExecutionPlan


class AgentQueryRequest(BaseModel):
  """Inbound single-shot API request payload."""

  query: str = Field(
    ...,
    description="User prompt or requirements for the scoping deliverables",
  )
  client_id: str = Field(
    default="default_client",
    description="Client tenant ID for vault sandboxing",
  )
  target_context: str = Field(
    default="default",
    description="Target namespace or workspace context",
  )
  session_id: str = Field(
    default="default_session",
    description="Unique conversational session identifier",
  )
  image_data: bytes | None = None


# --- Conversational Multi-Turn Tier 1 Data Contracts ---


class ChatSessionTurn(BaseModel):
  """A single turn in a multi-turn conversation."""

  turn_id: str = Field(
    default_factory=lambda: f"turn_{int(time.time() * 1000)}"
  )
  role: str = Field(
    ...,
    description="Role of turn author ('user' | 'agent')",
  )
  agent_name: str = Field(
    default="triage_agent",
    description="Active agent handling the turn",
  )
  message: str = Field(
    ...,
    description="Text content of the message",
  )
  deliverables: ScopingDeliverables | None = None
  actions_taken: list[AgentAction] = Field(default_factory=list)
  doc_url: str | None = None
  timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))


class ChatSessionState(BaseModel):
  """Complete conversation history and active pointer for a session."""

  session_id: str
  client_id: str
  active_agent: str = "triage_agent"
  history: list[ChatSessionTurn] = Field(default_factory=list)
  allowed_drive_folder_id: str | None = None


class ChatTurnRequest(BaseModel):
  """Inbound request payload for multi-turn chat endpoint."""

  session_id: str = Field(
    ...,
    description="Conversational session UUID",
  )
  client_id: str = Field(
    default="default_client",
    description="Target tenant client identifier",
  )
  message: str = Field(
    ...,
    description="User chat message or refinement instruction",
  )
  allowed_drive_folder_id: str | None = Field(
    default=None,
    description="Authorized Google Drive folder ID for client sandboxing",
  )


class ChatTurnResponse(BaseModel):
  """Outbound response payload for multi-turn chat endpoint."""

  session_id: str
  client_id: str
  active_agent: str
  reply: str
  deliverables: ScopingDeliverables | None = None
  actions_taken: list[AgentAction] = Field(default_factory=list)
  doc_url: str | None = None
