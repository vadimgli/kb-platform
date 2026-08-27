"""Asynchronous Model Context Protocol (MCP) Client.

Implements JSON-RPC 2.0 transport, tool discovery, and tool execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.mcp.types import (
  JSONRPCRequest,
  JSONRPCResponse,
  MCPInitializeParams,
  MCPTextContent,
  MCPTool,
  MCPToolCallResult,
)

logger = logging.getLogger("mcp.client")


class MCPClientError(Exception):
  """Base exception for MCP client errors."""


class MCPClient:
  """Asynchronous MCP Client implementing MCP 2024-11-05 JSON-RPC 2.0."""

  def __init__(
    self,
    server_command: list[str] | None = None,
    env: dict[str, str] | None = None,
  ):
    """Initializes the MCP Client.

    Args:
      server_command: Optional CLI execution arguments for MCP server process.
      env: Environment variables to pass to the subprocess.
    """
    self.server_command = server_command
    self.env = env
    self._process: asyncio.subprocess.Process | None = None
    self._request_id = 0
    self._pending_requests: dict[
      int | str, asyncio.Future[JSONRPCResponse]
    ] = {}
    self._reader_task: asyncio.Task[None] | None = None
    self._tools_cache: list[MCPTool] = []
    self._is_connected = False
    self._lock = asyncio.Lock()

  @property
  def is_connected(self) -> bool:
    """Returns True if client has established an active session."""
    return self._is_connected

  async def connect(self) -> None:
    """Launches the MCP server subprocess and executes initialize handshake.

    Raises:
      MCPClientError: If the initialize handshake or startup fails.
    """
    async with self._lock:
      if self._is_connected:
        return

      if self.server_command:
        logger.info(
          "Starting MCP server process: %s", " ".join(self.server_command)
        )
        self._process = await asyncio.create_subprocess_exec(
          *self.server_command,
          stdin=asyncio.subprocess.PIPE,
          stdout=asyncio.subprocess.PIPE,
          stderr=asyncio.subprocess.PIPE,
          env=self.env,
        )
        self._reader_task = asyncio.create_task(self._listen_stdout())

      init_params = MCPInitializeParams()
      response = await self._send_request(
        "initialize", init_params.model_dump()
      )
      if response.error:
        raise MCPClientError(f"MCP Handshake Failed: {response.error}")

      await self._send_notification("notifications/initialized", {})
      await self.refresh_tools()
      self._is_connected = True
      logger.info(
        "Connected to MCP server. Discovered %d tools.", len(self._tools_cache)
      )

  async def disconnect(self) -> None:
    """Closes connections and terminates subprocess if running."""
    async with self._lock:
      self._is_connected = False
      if self._reader_task and not self._reader_task.done():
        self._reader_task.cancel()

      if self._process:
        try:
          if self._process.stdin:
            self._process.stdin.close()
          self._process.terminate()
          await asyncio.wait_for(self._process.wait(), timeout=3.0)
        except (TimeoutError, ProcessLookupError):
          self._process.kill()
        self._process = None

  async def _listen_stdout(self) -> None:
    """Reads JSON-RPC messages line-by-line from the subprocess stdout."""
    if not self._process or not self._process.stdout:
      return

    try:
      while True:
        line = await self._process.stdout.readline()
        if not line:
          break

        line_str = line.decode("utf-8").strip()
        if not line_str:
          continue

        try:
          data = json.loads(line_str)
          if "id" in data and data["id"] in self._pending_requests:
            future = self._pending_requests.pop(data["id"])
            if not future.done():
              future.set_result(JSONRPCResponse.model_validate(data))
        except Exception as e:
          logger.warning(
            "Failed to parse MCP server output '%s': %s", line_str, e
          )
    except asyncio.CancelledError:
      pass
    except Exception as e:
      logger.error("Error in MCP stdout listener: %s", e)

  async def _send_request(
    self, method: str, params: dict[str, Any] | None = None
  ) -> JSONRPCResponse:
    """Sends a JSON-RPC request and awaits the corresponding response.

    Args:
      method: JSON-RPC method name.
      params: Optional parameters dict.

    Returns:
      JSONRPCResponse object.

    Raises:
      MCPClientError: On connection failure or timeout.
    """
    if not self._process or not self._process.stdin:
      raise MCPClientError("MCP server is not connected.")

    self._request_id += 1
    req_id = self._request_id
    request = JSONRPCRequest(id=req_id, method=method, params=params)
    loop = asyncio.get_running_loop()
    future: asyncio.Future[JSONRPCResponse] = loop.create_future()
    self._pending_requests[req_id] = future

    payload = request.model_dump_json() + "\n"
    self._process.stdin.write(payload.encode("utf-8"))
    await self._process.stdin.drain()

    try:
      return await asyncio.wait_for(future, timeout=30.0)
    except TimeoutError:
      self._pending_requests.pop(req_id, None)
      raise MCPClientError(
        f"Request timeout for MCP method '{method}' (id={req_id})"
      )

  async def _send_notification(
    self, method: str, params: dict[str, Any] | None = None
  ) -> None:
    """Sends a JSON-RPC notification without awaiting a response."""
    if not self._process or not self._process.stdin:
      return
    notification = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    payload = json.dumps(notification) + "\n"
    self._process.stdin.write(payload.encode("utf-8"))
    await self._process.stdin.drain()

  async def refresh_tools(self) -> list[MCPTool]:
    """Fetches available tools from the server via tools/list.

    Returns:
      List of discovered MCPTool objects.
    """
    response = await self._send_request("tools/list", {})
    if response.error:
      raise MCPClientError(f"Failed to list tools: {response.error}")

    tools_data = response.result.get("tools", []) if response.result else []
    self._tools_cache = [MCPTool.model_validate(t) for t in tools_data]
    return self._tools_cache

  def get_tools(self) -> list[MCPTool]:
    """Returns currently discovered tools from cache."""
    return self._tools_cache

  async def call_tool(
    self, name: str, arguments: dict[str, Any]
  ) -> MCPToolCallResult:
    """Executes a tool on the MCP server via tools/call.

    Args:
      name: Tool identifier.
      arguments: Arguments payload dictionary.

    Returns:
      MCPToolCallResult with structured content or error details.
    """
    response = await self._send_request(
      "tools/call", {"name": name, "arguments": arguments}
    )
    if response.error:
      return MCPToolCallResult(
        content=[
          MCPTextContent(
            text=f"Error executing tool '{name}': {response.error}"
          )
        ],
        isError=True,
      )

    result_data = response.result or {}
    return MCPToolCallResult.model_validate(result_data)
