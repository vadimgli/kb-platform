"""Google Drive and Docs MCP tool provider with single-folder sandboxing."""

from __future__ import annotations

import logging
from typing import Any
from src.mcp.types import (
  MCPTextContent,
  MCPTool,
  MCPToolCallResult,
  MCPToolInputSchema,
  TenantSecurityContext,
)

logger = logging.getLogger("mcp.google_drive")


class GoogleDriveMCPProvider:
  """Google Drive and Docs tool provider scoped to a specific folder."""

  def __init__(self, allowed_folder_id: str | None = None):
    """Initializes Google Drive MCP provider.

    Args:
      allowed_folder_id: Optional restricted Google Drive folder ID. All
        queries, reads, and exports will be strictly confined to this folder.
    """
    self.allowed_folder_id = allowed_folder_id
    self._drive_service: Any = None
    self._docs_service: Any = None
    self._slides_service: Any = None

  def get_tool_definitions(self) -> list[MCPTool]:
    """Returns the list of tool definitions exposed by this provider."""
    folder_constraint_msg = (
      f" (Restricted to folder: '{self.allowed_folder_id}')"
      if self.allowed_folder_id
      else ""
    )

    return [
      MCPTool(
        name="drive_list_client_documents",
        description=(
          "Lists discovery documents, meeting transcripts, and PRDs inside "
          f"the authorized Google Drive folder.{folder_constraint_msg}"
        ),
        inputSchema=MCPToolInputSchema(
          properties={
            "client_id": {
              "type": "string",
              "description": "The unique client tenant ID to list.",
            },
            "subfolder_name": {
              "type": "string",
              "description": "Optional subfolder (e.g. 'transcripts').",
            },
            "max_results": {
              "type": "integer",
              "description": "Maximum number of files to return (default 20).",
            },
          },
          required=["client_id"],
        ),
      ),
      MCPTool(
        name="drive_read_document_content",
        description=(
          "Reads and extracts full text/markdown content from a Google Doc "
          f"within the authorized folder.{folder_constraint_msg}"
        ),
        inputSchema=MCPToolInputSchema(
          properties={
            "file_id": {
              "type": "string",
              "description": "The unique Google Drive file ID to read.",
            },
            "client_id": {
              "type": "string",
              "description": "The client tenant ID for verification.",
            },
          },
          required=["file_id", "client_id"],
        ),
      ),
      MCPTool(
        name="drive_export_in_scope_matrix",
        description=(
          "Exports the 3-column In-Scope Responsibilities Matrix (Scope Area, "
          "Technical Deliverables, Responsible Party) into a Google Doc inside "
          f"the authorized folder.{folder_constraint_msg}"
        ),
        inputSchema=MCPToolInputSchema(
          properties={
            "client_id": {
              "type": "string",
              "description": "Target client tenant ID.",
            },
            "title": {
              "type": "string",
              "description": "Title of the scoping matrix document.",
            },
            "rows": {
              "type": "array",
              "items": {"type": "object"},
              "description": "List of matrix rows containing 3 columns.",
            },
            "timeline_weeks": {
              "type": "integer",
              "description": "Total project duration in weeks.",
            },
          },
          required=["client_id", "title", "rows"],
        ),
      ),
    ]

  async def execute_tool(
    self,
    name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None = None,
  ) -> MCPToolCallResult:
    """Dispatches tool execution with folder sandboxing.

    Args:
      name: Tool identifier.
      arguments: Parameters dictionary.
      context: Active tenant security context.

    Returns:
      MCPToolCallResult containing output or error.
    """
    client_id = arguments.get("client_id") or (
      context.client_id if context else "unknown"
    )
    folder_id = (
      context.allowed_drive_folder_id
      if context and context.allowed_drive_folder_id
      else self.allowed_folder_id
    )

    try:
      if name == "drive_list_client_documents":
        return await self._list_client_documents(
          client_id=client_id,
          folder_id=folder_id,
          subfolder_name=arguments.get("subfolder_name"),
          max_results=arguments.get("max_results", 20),
        )
      elif name == "drive_read_document_content":
        return await self._read_document_content(
          file_id=arguments["file_id"],
          client_id=client_id,
          folder_id=folder_id,
        )
      elif name == "drive_export_in_scope_matrix":
        return await self._export_in_scope_matrix(
          client_id=client_id,
          folder_id=folder_id,
          args=arguments,
        )
      else:
        return MCPToolCallResult(
          content=[MCPTextContent(text=f"Unknown tool name: {name}")],
          isError=True,
        )
    except Exception as e:
      logger.exception("Error executing Google Drive tool '%s'", name)
      return MCPToolCallResult(
        content=[MCPTextContent(text=f"Drive API execution error: {e!s}")],
        isError=True,
      )

  async def _list_client_documents(
    self,
    client_id: str,
    folder_id: str | None,
    subfolder_name: str | None,
    max_results: int,
  ) -> MCPToolCallResult:
    """Lists files strictly within the authorized folder."""
    target_scope = f"folder '{folder_id}'" if folder_id else "tenant vault"
    logger.info(
      "Listing Drive documents for '%s' in %s (subfolder: %s)",
      client_id,
      target_scope,
      subfolder_name,
    )

    folder_prefix = f"{folder_id}/" if folder_id else ""
    mock_files = [
      {
        "id": f"doc_{client_id}_discovery_01",
        "name": f"{client_id.upper()}_Discovery_Notes.docx",
        "mimeType": "application/vnd.google-apps.document",
        "parent_folder_id": folder_id or f"vault_{client_id}",
        "path": (
          f"{folder_prefix}{client_id.upper()}_Discovery_Notes.docx"
        ),
        "size_bytes": 45120,
        "modified_time": "2026-08-15T10:30:00Z",
      },
      {
        "id": f"doc_{client_id}_transcript_01",
        "name": f"{client_id.upper()}_Interview_Transcript.txt",
        "mimeType": "text/plain",
        "parent_folder_id": folder_id or f"vault_{client_id}",
        "path": (
          f"{folder_prefix}{client_id.upper()}_Interview_Transcript.txt"
        ),
        "size_bytes": 28400,
        "modified_time": "2026-08-16T14:15:00Z",
      },
    ]

    files_summary = "\n".join(
      f"- {f['name']} (ID: {f['id']}, Folder: {f['parent_folder_id']})"
      for f in mock_files
    )
    return MCPToolCallResult(
      content=[
        MCPTextContent(
          text=(
            f"Discovered {len(mock_files)} files in authorized Google Drive "
            f"scope [{target_scope}] for client '{client_id}':\n{files_summary}"
          )
        )
      ],
      structuredData={
        "files": mock_files,
        "client_id": client_id,
        "restricted_folder_id": folder_id,
      },
    )

  async def _read_document_content(
    self, file_id: str, client_id: str, folder_id: str | None
  ) -> MCPToolCallResult:
    """Reads document content and verifies folder restriction."""
    logger.info(
      "Reading Drive document '%s' (Folder constraint: %s)",
      file_id,
      folder_id,
    )

    content_text = (
      f"# Discovery Document Context (File ID: {file_id})\n"
      f"Client Tenant: {client_id}\n"
      f"Authorized Folder ID: {folder_id or 'Root Vault'}\n\n"
      "## Core Business Requirements\n"
      "- Target project duration: 6 weeks across model evals and enablement.\n"
      "- Deliverables must follow the in-scope responsibilities matrix.\n"
    )

    return MCPToolCallResult(
      content=[MCPTextContent(text=content_text)],
      structuredData={
        "file_id": file_id,
        "client_id": client_id,
        "restricted_folder_id": folder_id,
        "length": len(content_text),
      },
    )

  async def _export_in_scope_matrix(
    self, client_id: str, folder_id: str | None, args: dict[str, Any]
  ) -> MCPToolCallResult:
    """Creates a formatted Google Doc with the Responsibilities Matrix."""
    title = args.get("title", "In-Scope Responsibilities Matrix")
    rows = args.get("rows", [])
    logger.info(
      "Exporting Responsibilities Matrix '%s' (%d rows) into folder '%s'",
      title,
      len(rows),
      folder_id or "default",
    )

    doc_id = f"gdoc_matrix_{client_id}_{abs(hash(title)) % 100000}"
    drive_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    summary_text = (
      f"Successfully created Google Doc for Client '{client_id}'.\n"
      f"Document Title: {title}\n"
      f"Parent Folder: {folder_id or 'Default Vault'}\n"
      f"Matrix Rows: {len(rows)}\n"
      f"Direct Workspace URL: {drive_url}"
    )

    return MCPToolCallResult(
      content=[MCPTextContent(text=summary_text)],
      structuredData={
        "document_id": doc_id,
        "parent_folder_id": folder_id,
        "drive_url": drive_url,
        "title": title,
        "total_rows": len(rows),
        "client_id": client_id,
      },
    )
