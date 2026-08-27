"""Agent2Agent (A2A) protocol type definitions and data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentSkill(BaseModel):
  """Capability or skill descriptor published by an A2A agent."""

  id: str = Field(..., description="Unique skill identifier")
  name: str = Field(..., description="Human-readable skill name")
  description: str = Field(..., description="Description of the skill")
  tags: list[str] = Field(default_factory=list)
  input_schema: dict[str, Any] | None = None
  output_schema: dict[str, Any] | None = None


class AgentCard(BaseModel):
  """A2A Agent Card published at /.well-known/agent-card.json."""

  name: str = Field(..., description="Agent service identifier")
  description: str = Field(..., description="Agent role and responsibilities")
  url: str = Field(..., description="Base URL of the agent service")
  version: str = Field(default="1.0.0", description="Agent service version")
  skills: list[AgentSkill] = Field(
    default_factory=list, description="Supported skills"
  )
  documentation_url: str | None = None
  provider: dict[str, str] | None = None


class A2AArtifact(BaseModel):
  """Artifact payload generated during A2A task execution."""

  artifact_id: str
  name: str
  mime_type: str = "text/plain"
  content: str | None = None
  uri: str | None = None
  metadata: dict[str, Any] = Field(default_factory=dict)


class A2AResponsePayload(BaseModel):
  """A2A task response data payload."""

  status: str = "SUCCESS"
  result_data: dict[str, Any] = Field(default_factory=dict)
  error: str | None = None


class A2ATask(BaseModel):
  """A2A asynchronous task execution state."""

  task_id: str | None = None
  skill_id: str | None = None
  input_payload: dict[str, Any] | None = None
  status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"] = "PENDING"
  result: str | None = None
  artifacts: list[A2AArtifact] = Field(default_factory=list)
  error: str | None = None


class A2AMessage(BaseModel):
  """A2A protocol communication message envelope."""

  id: str | None = None
  role: Literal["user", "agent", "system"] = "user"
  sender: str | None = None
  recipient: str | None = None
  in_response_to: str | None = None
  content: str = ""
  context_id: str | None = None
  task_id: str | None = None
  task: A2ATask | None = None
  response: A2AResponsePayload | None = None
  artifacts: list[A2AArtifact] = Field(default_factory=list)
  error: str | None = None
