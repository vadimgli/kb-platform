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
    default="default_client",
    description="Client tenant ID for vault sandboxing",
  )
  timeline_weeks: int = Field(
    default=6,
    description="Engagement timeline duration in weeks",
  )
  items: list[ScopingDeliverableItem] = Field(
    default_factory=list,
    description="List of scope areas and deliverables",
  )
  rows: list[ScopingDeliverableItem] | None = None

  def model_post_init(self, __context: Any) -> None:
    """Synchronizes items and legacy rows alias."""
    if self.rows and not self.items:
      self.items = list(self.rows)
    elif self.items and self.rows is None:
      self.rows = list(self.items)


# Backward compatibility aliases
InScopeResponsibilitiesMatrix = ScopingDeliverables
InScopeMatrixItem = ScopingDeliverableItem
ResponsibilityMatrixItem = ScopingDeliverableItem


class AgentAction(BaseModel):
  """Deterministic structured command action synthesized by executor."""

  action_type: ActionCategory = Field(
    ...,
    description="Standardized action classification category",
  )
  target_tenant_id: str = Field(
    ...,
    description="Mandatory client tenant identifier for boundary checks",
  )
  payload: str = Field(
    ...,
    description="Payload or instruction text for tool execution",
  )
  description: str = Field(
    ...,
    description="Human-readable summary of this execution step",
  )
  risk_level: RiskLevel = Field(
    default=RiskLevel.LOW,
    description="Evaluated risk level classification",
  )
  status: str = Field(
    default="PENDING",
    description="Current execution lifecycle status",
  )


class ExecutionPlan(BaseModel):
  """Structured execution plan synthesized by planner."""

  summary: str = Field(
    ...,
    description="Executive summary of the scoping deliverables",
  )
  target_tenant_id: str = Field(
    ...,
    description="Target tenant client ID",
  )
  deliverables: ScopingDeliverables | None = Field(
    default=None,
    description="Structured 3-column in-scope responsibilities matrix",
  )
  matrix: ScopingDeliverables | None = None
  actions: list[AgentAction] = Field(
    default_factory=list,
    description="Ordered sequence of verified actions",
  )
  citations: list[str] = Field(
    default_factory=list,
    description="Citations and grounding URLs",
  )
  prompt_tokens: int | None = 0
  completion_tokens: int | None = 0

  def model_post_init(self, __context: Any) -> None:
    """Synchronizes deliverables and legacy matrix alias."""
    if self.matrix and not self.deliverables:
      self.deliverables = self.matrix
    elif self.deliverables and self.matrix is None:
      self.matrix = self.deliverables


# --- Single-Shot Query API Payloads ---


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


# Backward compatibility aliases
PlanQueryRequest = AgentQueryRequest
QueryRequest = AgentQueryRequest


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
