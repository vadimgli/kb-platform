"""Model Context Protocol (MCP) types and schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MCPToolInputSchema(BaseModel):
  """JSON Schema definition for MCP tool arguments."""

  type: str = "object"
  properties: dict[str, Any] = Field(default_factory=dict)
  required: list[str] = Field(default_factory=list)
  additionalProperties: bool | None = None


class MCPTool(BaseModel):
  """Tool descriptor exposed by an MCP Server."""

  name: str = Field(..., description="Unique tool identifier")
  description: str = Field(..., description="Description of tool functionality")
  inputSchema: MCPToolInputSchema = Field(
    default_factory=MCPToolInputSchema,
    description="JSON Schema describing parameters",
  )


class MCPTextContent(BaseModel):
  """Text payload returned in MCP tool call results."""

  type: Literal["text"] = "text"
  text: str


class MCPImageContent(BaseModel):
  """Image payload returned in MCP tool call results."""

  type: Literal["image"] = "image"
  data: str
  mimeType: str


class MCPEmbeddedResource(BaseModel):
  """Embedded resource payload returned in MCP tool call results."""

  type: Literal["resource"] = "resource"
  resource: dict[str, Any]


MCPContentItem = MCPTextContent | MCPImageContent | MCPEmbeddedResource


class MCPToolCallResult(BaseModel):
  """Result payload returned by an MCP tool invocation."""

  content: list[MCPContentItem] = Field(default_factory=list)
  isError: bool = False
  structuredData: dict[str, Any] | None = None

  def get_text_content(self) -> str:
    """Extracts and concatenates all text fragments in the result."""
    return "\n".join(
      item.text for item in self.content if isinstance(item, MCPTextContent)
    )


class JSONRPCRequest(BaseModel):
  """JSON-RPC 2.0 Request envelope."""

  jsonrpc: Literal["2.0"] = "2.0"
  id: int | str
  method: str
  params: dict[str, Any] | None = None


class JSONRPCResponse(BaseModel):
  """JSON-RPC 2.0 Response envelope."""

  jsonrpc: Literal["2.0"] = "2.0"
  id: int | str | None = None
  result: Any | None = None
  error: dict[str, Any] | None = None


class MCPInitializeParams(BaseModel):
  """Parameters sent during MCP initialize handshake."""

  protocolVersion: str = "2024-11-05"
  capabilities: dict[str, Any] = Field(
    default_factory=lambda: {
      "roots": {"listChanged": True},
      "sampling": {},
    }
  )
  clientInfo: dict[str, str] = Field(
    default_factory=lambda: {
      "name": "ArtifactForge-MCP-Client",
      "version": "1.0.0",
    }
  )


class TenantSecurityContext(BaseModel):
  """Security context propagated into tool calls for tenant isolation."""

  client_id: str = Field(..., description="Unique client/tenant identifier")
  allowed_drive_folder_id: str | None = Field(
    default=None,
    description="Restricted Google Drive root folder ID for this tenant",
  )
  user_email: str | None = None
  read_only: bool = False
