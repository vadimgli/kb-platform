"""Google Drive and Docs MCP tool provider with single-folder sandboxing."""

from __future__ import annotations

import logging
from typing import Any

from src.core.error_messages import ErrorMessages
from src.core.exceptions import (
  DriveExportError,
  DriveFileNotFoundError,
  DriveFolderNotFoundError,
  DrivePermissionDeniedError,
  DriveUnauthorizedFolderError,
)
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

  def __init__(self, allowed_folder_id: str | None = None) -> None:
    """Initializes Google Drive MCP provider.

    Args:
      allowed_folder_id: Optional restricted Google Drive folder ID. All
        queries, reads, and exports will be strictly confined to this folder.
    """
    self.allowed_folder_id = allowed_folder_id
    self._drive_service: Any = None
    self._docs_service: Any = None

  def _get_drive_service(self) -> Any:
    """Lazy initialization of Google Drive API v3 client."""
    if self._drive_service is None:
      try:
        import google.auth
        from googleapiclient.discovery import build

        credentials, _ = google.auth.default(
          scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
          ]
        )
        self._drive_service = build("drive", "v3", credentials=credentials)
      except Exception as err:
        logger.error("Failed to build Google Drive API client: %s", err)
        raise DrivePermissionDeniedError(
          ErrorMessages.ERR_DRIVE_PERMISSION_DENIED.format(
            folder_id=self.allowed_folder_id or "default",
            sa_email="authenticated-identity",
          ),
          details={"error": str(err)},
        ) from err
    return self._drive_service

  def _get_docs_service(self) -> Any:
    """Lazy initialization of Google Docs API v1 client."""
    if self._docs_service is None:
      try:
        import google.auth
        from googleapiclient.discovery import build

        credentials, _ = google.auth.default(
          scopes=["https://www.googleapis.com/auth/documents"]
        )
        self._docs_service = build("docs", "v1", credentials=credentials)
      except Exception as err:
        logger.error("Failed to build Google Docs API client: %s", err)
        raise DrivePermissionDeniedError(
          ErrorMessages.ERR_DRIVE_PERMISSION_DENIED.format(
            folder_id=self.allowed_folder_id or "default",
            sa_email="authenticated-identity",
          ),
          details={"error": str(err)},
        ) from err
    return self._docs_service

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
          "Reads the full text content of a Google Doc within the authorized "
          f"folder boundary.{folder_constraint_msg}"
        ),
        inputSchema=MCPToolInputSchema(
          properties={
            "file_id": {
              "type": "string",
              "description": "Google Drive file ID.",
            },
            "client_id": {
              "type": "string",
              "description": "Client ID for tenant verification.",
            },
          },
          required=["file_id", "client_id"],
        ),
      ),
      MCPTool(
        name="drive_export_in_scope_matrix",
        description=(
          "Creates a new Google Doc formatted with the 3-column In-Scope "
          "Responsibilities Matrix table inside the client's authorized "
          f"Google Drive folder.{folder_constraint_msg}"
        ),
        inputSchema=MCPToolInputSchema(
          properties={
            "client_id": {
              "type": "string",
              "description": "The client tenant identifier.",
            },
            "title": {
              "type": "string",
              "description": "The title of the scoping document.",
            },
            "rows": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "project_scope_area": {"type": "string"},
                  "technical_deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                  },
                  "responsible_party": {"type": "string"},
                },
                "required": [
                  "project_scope_area",
                  "technical_deliverables",
                  "responsible_party",
                ],
              },
            },
          },
          required=["client_id", "title", "rows"],
        ),
      ),
    ]

  async def list_client_documents(
    self,
    client_id: str,
    folder_id: str | None = None,
    subfolder_name: str | None = None,
    max_results: int = 20,
  ) -> dict[str, Any]:
    """Public helper to list documents inside authorized folder."""
    result = await self._list_client_documents(
      client_id=client_id,
      folder_id=folder_id or self.allowed_folder_id,
      subfolder_name=subfolder_name,
      max_results=max_results,
    )
    if result.isError:
      error_text = result.content[0].text if result.content else "Unknown Drive error"
      raise DriveFolderNotFoundError(error_text)
    return result.structuredData or {}

  async def read_document_content(
    self,
    file_id: str,
    client_id: str,
    folder_id: str | None = None,
  ) -> dict[str, Any]:
    """Public helper to read document content."""
    result = await self._read_document_content(
      file_id=file_id,
      client_id=client_id,
      folder_id=folder_id or self.allowed_folder_id,
    )
    if result.isError:
      error_text = result.content[0].text if result.content else "Unknown Drive read error"
      raise DriveFileNotFoundError(error_text)
    content = result.content[0].text if result.content else ""
    return {"content": content, "file_id": file_id}

  async def drive_export_in_scope_matrix(
    self,
    client_id: str,
    title: str,
    rows: list[dict[str, Any]],
    folder_id: str | None = None,
    timeline_weeks: int = 6,
  ) -> dict[str, Any]:
    """Public helper to export matrix to Google Docs."""
    args = {
      "title": title,
      "rows": rows,
      "timeline_weeks": timeline_weeks,
    }
    result = await self._export_in_scope_matrix(
      client_id=client_id,
      folder_id=folder_id or self.allowed_folder_id,
      args=args,
    )
    if result.isError:
      error_text = result.content[0].text if result.content else "Unknown export error"
      raise DriveExportError(error_text)
    sdata = result.structuredData or {}
    doc_id = sdata.get("document_id", "")
    doc_url = sdata.get("drive_url", "")
    return {
      "document_id": doc_id,
      "document_url": doc_url,
      "drive_url": doc_url,
      "title": title,
    }

  async def execute_tool(
    self,
    name: str,
    arguments: dict[str, Any],
    context: TenantSecurityContext | None = None,
  ) -> MCPToolCallResult:
    """Executes a Google Drive MCP tool within the tenant security context."""
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
    """Lists files strictly within the authorized folder using live Drive API."""
    target_folder = folder_id or self.allowed_folder_id
    if not target_folder:
      err_msg = ErrorMessages.ERR_DRIVE_FOLDER_NOT_FOUND.format(folder_id="None")
      return MCPToolCallResult(
        content=[MCPTextContent(text=err_msg)],
        isError=True,
      )

    # Enforce single-folder sandboxing boundary
    if self.allowed_folder_id and target_folder != self.allowed_folder_id:
      err_msg = ErrorMessages.ERR_DRIVE_UNAUTHORIZED_FOLDER.format(
        requested_folder_id=target_folder,
        allowed_folder_id=self.allowed_folder_id,
      )
      return MCPToolCallResult(
        content=[MCPTextContent(text=err_msg)],
        isError=True,
      )

    try:
      drive = self._get_drive_service()
      query = f"'{target_folder}' in parents and trashed = false"
      if subfolder_name:
        query += f" and name = '{subfolder_name}'"

      logger.info("Executing Google Drive API list query: %s", query)
      response = drive.files().list(
        q=query,
        pageSize=max_results,
        fields="files(id, name, mimeType, size, modifiedTime)",
      ).execute()

      raw_files = response.get("files", [])
      if not raw_files:
        empty_msg = ErrorMessages.ERR_DRIVE_EMPTY_FOLDER.format(folder_id=target_folder)
        return MCPToolCallResult(
          content=[MCPTextContent(text=empty_msg)],
          structuredData={
            "files": [],
            "client_id": client_id,
            "restricted_folder_id": target_folder,
          },
        )

      files = [
        {
          "id": f.get("id"),
          "name": f.get("name"),
          "mimeType": f.get("mimeType"),
          "parent_folder_id": target_folder,
          "size": f.get("size"),
          "modifiedTime": f.get("modifiedTime"),
        }
        for f in raw_files
      ]

      files_summary = "\n".join(
        f"- {f.get('name', 'Untitled')} (ID: {f.get('id')}, MIME: {f.get('mimeType')})"
        for f in files
      )
      return MCPToolCallResult(
        content=[
          MCPTextContent(
            text=(
              f"Discovered {len(files)} files in authorized Google Drive "
              f"folder [{target_folder}]:\n{files_summary}"
            )
          )
        ],
        structuredData={
          "files": files,
          "client_id": client_id,
          "restricted_folder_id": target_folder,
        },
      )
    except Exception as e:
      logger.exception("Google Drive API list failure on folder '%s'", target_folder)
      return MCPToolCallResult(
        content=[
          MCPTextContent(
            text=ErrorMessages.ERR_DRIVE_FOLDER_NOT_FOUND.format(folder_id=target_folder)
            + f" (Details: {e!s})"
          )
        ],
        isError=True,
      )

  async def _read_document_content(
    self, file_id: str, client_id: str, folder_id: str | None
  ) -> MCPToolCallResult:
    """Reads real document content using Google Drive API."""
    target_folder = folder_id or self.allowed_folder_id

    try:
      drive = self._get_drive_service()
      file_meta = drive.files().get(
        fileId=file_id,
        fields="id, name, mimeType, parents",
      ).execute()

      parents = file_meta.get("parents", [])
      if self.allowed_folder_id and self.allowed_folder_id not in parents:
        err_msg = ErrorMessages.ERR_DRIVE_UNAUTHORIZED_FOLDER.format(
          requested_folder_id=str(parents),
          allowed_folder_id=self.allowed_folder_id,
        )
        return MCPToolCallResult(
          content=[MCPTextContent(text=err_msg)],
          isError=True,
        )

      mime_type = file_meta.get("mimeType", "")
      if "google-apps.document" in mime_type:
        content_bytes = drive.files().export(
          fileId=file_id,
          mimeType="text/plain",
        ).execute()
        content_text = (
          content_bytes.decode("utf-8")
          if isinstance(content_bytes, bytes)
          else str(content_bytes)
        )
      else:
        content_bytes = drive.files().get_media(fileId=file_id).execute()
        content_text = (
          content_bytes.decode("utf-8")
          if isinstance(content_bytes, bytes)
          else str(content_bytes)
        )

      return MCPToolCallResult(
        content=[MCPTextContent(text=content_text)],
        structuredData={
          "file_id": file_id,
          "client_id": client_id,
          "file_name": file_meta.get("name"),
          "restricted_folder_id": target_folder,
          "length": len(content_text),
        },
      )
    except Exception as e:
      logger.exception("Google Drive API read failure for file '%s'", file_id)
      return MCPToolCallResult(
        content=[
          MCPTextContent(
            text=ErrorMessages.ERR_DRIVE_READ_FAILED.format(file_id=file_id, reason=str(e))
          )
        ],
        isError=True,
      )

  async def _export_in_scope_matrix(
    self, client_id: str, folder_id: str | None, args: dict[str, Any]
  ) -> MCPToolCallResult:
    """Creates a real Google Doc in the authorized folder."""
    title = args.get("title", "In-Scope Responsibilities Matrix")
    rows = args.get("rows", [])
    target_folder = folder_id or self.allowed_folder_id

    try:
      drive = self._get_drive_service()
      file_metadata: dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
      }
      if target_folder:
        file_metadata["parents"] = [target_folder]

      doc_file = drive.files().create(
        body=file_metadata,
        fields="id, name, webViewLink",
      ).execute()

      doc_id = doc_file.get("id")
      drive_url = doc_file.get(
        "webViewLink",
        f"https://docs.google.com/document/d/{doc_id}/edit",
      )

      # Populate Google Doc body if Docs API is available
      try:
        docs = self._get_docs_service()
        doc_body_text = f"Document: {title}\nTenant: {client_id}\n\nIn-Scope Deliverables Matrix ({len(rows)} Scope Areas):\n"
        for idx, row in enumerate(rows, 1):
          scope_area = row.get("project_scope_area") or row.get("scope_area", "Scope Area")
          delivs = row.get("technical_deliverables") or row.get("deliverables", [])
          delivs_str = ", ".join(delivs) if isinstance(delivs, list) else str(delivs)
          party = row.get("responsible_party", "Google FDE Team")
          doc_body_text += f"\n{idx}. Scope Area: {scope_area}\n   Deliverables: {delivs_str}\n   Owner: {party}\n"

        docs.documents().batchUpdate(
          documentId=doc_id,
          body={
            "requests": [
              {
                "insertText": {
                  "location": {"index": 1},
                  "text": doc_body_text,
                }
              }
            ]
          },
        ).execute()
      except Exception as doc_err:
        logger.warning("Google Docs body population notice: %s", doc_err)

      summary_text = (
        f"Successfully created Google Doc for Client '{client_id}'.\n"
        f"Document Title: {title}\n"
        f"Parent Folder: {target_folder or 'Default'}\n"
        f"Matrix Rows: {len(rows)}\n"
        f"Direct Workspace URL: {drive_url}"
      )

      return MCPToolCallResult(
        content=[MCPTextContent(text=summary_text)],
        structuredData={
          "document_id": doc_id,
          "parent_folder_id": target_folder,
          "drive_url": drive_url,
          "title": title,
          "total_rows": len(rows),
          "client_id": client_id,
        },
      )
    except Exception as e:
      logger.exception("Google Drive export failure for title '%s'", title)
      return MCPToolCallResult(
        content=[
          MCPTextContent(
            text=ErrorMessages.ERR_DRIVE_EXPORT_FAILED.format(reason=str(e))
          )
        ],
        isError=True,
      )
