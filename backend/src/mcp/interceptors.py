"""Security and folder sandboxing interceptors for MCP tools."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.mcp.types import MCPToolCallResult, TenantSecurityContext

logger = logging.getLogger("mcp.security")

CREDENTIAL_PATTERNS = [
  re.compile(r"AIza[0-9A-Za-z-_]{35}"),
  re.compile(r"ghp_[0-9a-zA-Z]{36}"),
  re.compile(r"ya29\.[0-9A-Za-z-_]+"),
  re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
  re.compile(
    r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"
    r"[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
  ),
  re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]+['\"]"),
]

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


class TenantIsolationError(Exception):
  """Raised when a tool execution violates tenant boundary isolation."""


class MCPInterceptor:
  """Base class for tool execution interceptors."""

  async def before_execute(
    self,
    tool_name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None,
  ) -> dict[str, Any]:
    """Inspects and potentially mutates tool arguments before execution.

    Args:
      tool_name: Target tool identifier.
      arguments: Dict of input parameters.
      context: Active tenant security context.

    Returns:
      Potentially sanitized arguments dict.
    """
    return arguments

  async def after_execute(
    self,
    tool_name: str,
    result: MCPToolCallResult,
    context: TenantSecurityContext | None,
  ) -> MCPToolCallResult:
    """Inspects and sanitizes tool execution results before returning to LLM.

    Args:
      tool_name: Target tool identifier.
      result: Result payload from tool execution.
      context: Active tenant security context.

    Returns:
      Sanitized MCPToolCallResult.
    """
    return result


class TenantBoundaryInterceptor(MCPInterceptor):
  """Enforces tenant and folder isolation on Google Drive operations."""

  async def before_execute(
    self,
    tool_name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None,
  ) -> dict[str, Any]:
    """Verifies that arguments match the active tenant and folder boundaries.

    Args:
      tool_name: Tool name being invoked.
      arguments: Tool arguments dictionary.
      context: Caller's authenticated security context.

    Returns:
      Validated tool arguments.

    Raises:
      TenantBoundaryError: If argument tenant or folder violates context.
    """
    if context is None:
      return arguments

    # 1. Enforce tenant boundary
    arg_client_id = arguments.get("client_id")
    if arg_client_id and arg_client_id != context.client_id:
      logger.error(
        "Tenant mismatch: context=%s, arg=%s",
        context.client_id,
        arg_client_id,
      )
      raise TenantBoundaryError(
        f"Access denied: Tenant '{arg_client_id}' does not match "
        f"active security context '{context.client_id}'"
      )

    if "client_id" in arguments and not arguments["client_id"]:
      arguments["client_id"] = context.client_id

    # 2. Enforce folder sandboxing
    arg_folder = (
      arguments.get("folder_id") or arguments.get("parent_folder_id")
    )
    if (
      arg_folder
      and context.allowed_drive_folder_id
      and arg_folder != context.allowed_drive_folder_id
    ):
      logger.error(
        "Folder boundary mismatch: context=%s, arg=%s",
        context.allowed_drive_folder_id,
        arg_folder,
      )
      raise TenantBoundaryError(
        f"Access denied: Folder '{arg_folder}' is outside the authorized "
        f"Google Drive folder '{context.allowed_drive_folder_id}'"
      )

    # 3. Enforce read-only mode
    write_prefixes = ("create_", "update_", "delete_", "export_")
    if context.read_only and tool_name.startswith(write_prefixes):
      raise TenantBoundaryError(
        f"Operation '{tool_name}' blocked: Context is read-only for tenant "
        f"'{context.client_id}'"
      )

    return arguments


class ModelArmorScrubbingInterceptor(MCPInterceptor):
  """Scrubs secrets, credentials, and PII from inputs and outputs."""

  def _scrub_text(self, text: str) -> str:
    scrubbed = text
    for pattern in CREDENTIAL_PATTERNS:
      scrubbed = pattern.sub("[REDACTED_SECRET]", scrubbed)
    return scrubbed

  def _scrub_dict(self, data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in data.items():
      if isinstance(v, str):
        cleaned[k] = self._scrub_text(v)
      elif isinstance(v, dict):
        cleaned[k] = self._scrub_dict(v)
      elif isinstance(v, list):
        cleaned[k] = [
          self._scrub_text(item)
          if isinstance(item, str)
          else self._scrub_dict(item)
          if isinstance(item, dict)
          else item
          for item in v
        ]
      else:
        cleaned[k] = v
    return cleaned

  async def before_execute(
    self,
    tool_name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None,
  ) -> dict[str, Any]:
    return self._scrub_dict(arguments)

  async def after_execute(
    self,
    tool_name: str,
    result: MCPToolCallResult,
    context: TenantSecurityContext | None,
  ) -> MCPToolCallResult:
    for item in result.content:
      if hasattr(item, "text"):
        item.text = self._scrub_text(item.text)
    if result.structuredData:
      result.structuredData = self._scrub_dict(result.structuredData)
    return result


TenantBoundaryError = TenantIsolationError
