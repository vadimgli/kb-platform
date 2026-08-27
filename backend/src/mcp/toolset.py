"""Model Context Protocol (MCP) toolset management and dispatch."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

try:
  from google.adk.tools.mcp_tool import McpToolset
except ImportError:

  class McpToolset:
    pass


from src.mcp.client import MCPClient
from src.mcp.interceptors import (
  MCPInterceptor,
  ModelArmorScrubbingInterceptor,
  TenantBoundaryInterceptor,
)
from src.mcp.servers.google_drive import GoogleDriveMCPProvider
from src.mcp.types import (
  MCPTool,
  MCPToolCallResult,
  TenantSecurityContext,
)

logger = logging.getLogger("mcp.toolset")


class McpToolsetManager:
  """Coordinates MCP tool discovery, tenant sandboxing, and dispatch."""

  def __init__(
    self,
    client: MCPClient | None = None,
    drive_provider: GoogleDriveMCPProvider | None = None,
    interceptors: list[MCPInterceptor] | None = None,
  ):
    """Initializes McpToolsetManager.

    Args:
      client: Optional remote or subprocess MCP client.
      drive_provider: Optional in-process Google Drive provider.
      interceptors: Security interceptor middleware list.
    """
    self.client = client
    self.drive_provider = drive_provider or GoogleDriveMCPProvider()
    self.interceptors: list[MCPInterceptor] = (
      interceptors
      if interceptors is not None
      else [TenantBoundaryInterceptor(), ModelArmorScrubbingInterceptor()]
    )
    self._registered_tools: dict[str, MCPTool] = {}
    self._custom_callables: dict[str, Callable[..., Any]] = {}

  async def initialize(self) -> None:
    """Discovers and caches tool definitions from providers and clients."""
    self._registered_tools.clear()

    if self.drive_provider:
      for tool in self.drive_provider.get_tool_definitions():
        self._registered_tools[tool.name] = tool

    if self.client:
      if not self.client.is_connected:
        await self.client.connect()
      for tool in self.client.get_tools():
        self._registered_tools[tool.name] = tool

    logger.info(
      "McpToolset initialized with %d active tools: %s",
      len(self._registered_tools),
      list(self._registered_tools.keys()),
    )

  def register_custom_tool(
    self, tool: MCPTool, handler: Callable[..., Any]
  ) -> None:
    """Registers an in-process tool definition and callback handler.

    Args:
      tool: MCPTool metadata and schema.
      handler: Async callable executing the tool logic.
    """
    self._registered_tools[tool.name] = tool
    self._custom_callables[tool.name] = handler

  def get_tool_names(self) -> list[str]:
    """Returns the names of all registered tools."""
    return list(self._registered_tools.keys())

  def get_tool(self, name: str) -> MCPTool | None:
    """Retrieves tool metadata by name."""
    return self._registered_tools.get(name)

  def to_genai_function_declarations(
    self, allowed_names: Sequence[str] | None = None
  ) -> list[dict[str, Any]]:
    """Converts MCP Tool JSON Schemas into GenAI FunctionDeclarations.

    Args:
      allowed_names: Optional whitelist of tool names to convert.

    Returns:
      List of FunctionDeclaration dictionary structures.
    """
    declarations: list[dict[str, Any]] = []

    for name, tool in self._registered_tools.items():
      if allowed_names is not None and name not in allowed_names:
        continue

      schema = tool.inputSchema.model_dump(exclude_none=True)
      declarations.append(
        {
          "name": tool.name,
          "description": tool.description,
          "parameters": schema,
        }
      )

    return declarations

  def to_genai_tools(self, allowed_names: Sequence[str] | None = None) -> Any:
    """Creates a Google GenAI Tool list containing function declarations.

    Args:
      allowed_names: Optional whitelist of tool names to convert.

    Returns:
      List of types.Tool instances or dictionary declarations.
    """
    declarations = self.to_genai_function_declarations(allowed_names)
    try:
      from google.genai import types  # type: ignore

      func_decls = [
        types.FunctionDeclaration(
          name=d["name"],
          description=d["description"],
          parameters=d.get("parameters"),
        )
        for d in declarations
      ]
      return [types.Tool(function_declarations=func_decls)]
    except ImportError:
      logger.debug("google.genai unavailable; returning declaration list.")
      return declarations

  async def execute_tool(
    self,
    name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None = None,
  ) -> MCPToolCallResult:
    """Executes tool through interceptor pipeline and dispatches to handler.

    Args:
      name: Registered tool identifier.
      arguments: Tool input parameters.
      context: Tenant security context.

    Returns:
      MCPToolCallResult with output content.

    Raises:
      ValueError: If tool name is unregistered.
      RuntimeError: If no execution handler is available.
    """
    if name not in self._registered_tools:
      logger.error("Attempted to execute unregistered tool: %s", name)
      raise ValueError(f"Tool '{name}' is not registered in McpToolset.")

    current_args = arguments
    for interceptor in self.interceptors:
      current_args = await interceptor.before_execute(
        name, current_args, context
      )

    result: MCPToolCallResult
    if name in self._custom_callables:
      raw_res = await self._custom_callables[name](**current_args)
      if isinstance(raw_res, MCPToolCallResult):
        result = raw_res
      else:
        result = MCPToolCallResult(structuredData={"result": raw_res})
    elif self.drive_provider and name.startswith("drive_"):
      result = await self.drive_provider.execute_tool(
        name, current_args, context
      )
    elif self.client and self.client.is_connected:
      result = await self.client.call_tool(name, current_args)
    else:
      raise RuntimeError(f"No available executor or client for tool '{name}'")

    for interceptor in self.interceptors:
      result = await interceptor.after_execute(name, result, context)

    return result

  async def close(self) -> None:
    """Cleans up all client connections and child processes."""
    if self.client:
      await self.client.disconnect()


MCPToolSet = McpToolsetManager
McpToolset = McpToolsetManager
