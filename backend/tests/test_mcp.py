"""Unit tests for the MCP module, Google Drive provider, and interceptors."""

import unittest
from unittest.mock import MagicMock

from src.mcp.interceptors import (
  ModelArmorScrubbingInterceptor,
  TenantBoundaryInterceptor,
  TenantIsolationError,
)
from src.mcp.servers.google_drive import GoogleDriveMCPProvider
from src.mcp.toolset import MCPToolSet
from src.mcp.types import TenantSecurityContext


class TestMCPModule(unittest.IsolatedAsyncioTestCase):
  """Test suite covering tool discovery, execution, and folder sandboxing."""

  async def test_mcp_toolset_initialization(self):
    """Tests that MCPToolSet registers Google Drive tools on startup."""
    toolset = MCPToolSet()
    await toolset.initialize()

    names = toolset.get_tool_names()
    self.assertIn("drive_list_client_documents", names)
    self.assertIn("drive_read_document_content", names)
    self.assertIn("drive_export_in_scope_matrix", names)

  async def test_mcp_to_genai_declarations(self):
    """Tests schema translation into Google GenAI Tool formats."""
    toolset = MCPToolSet()
    await toolset.initialize()

    decls = toolset.to_genai_function_declarations()
    self.assertEqual(len(decls), 3)

    matrix_decl = next(
      d for d in decls if d["name"] == "drive_export_in_scope_matrix"
    )
    self.assertIsNotNone(matrix_decl["description"])
    self.assertIn("properties", matrix_decl["parameters"])
    self.assertIn("rows", matrix_decl["parameters"]["properties"])

  async def test_google_drive_folder_sandboxing(self):
    """Tests that provider confines operations strictly to allowed folder."""
    provider = GoogleDriveMCPProvider(
      allowed_folder_id="restricted_folder_999"
    )
    mock_drive = MagicMock()
    mock_drive.files().list().execute.return_value = {
      "files": [
        {
          "id": "doc_1",
          "name": "Discovery_Notes.docx",
          "mimeType": "application/vnd.google-apps.document",
        }
      ]
    }
    provider._drive_service = mock_drive
    toolset = MCPToolSet(drive_provider=provider)
    await toolset.initialize()

    context = TenantSecurityContext(
      client_id="client_d",
      allowed_drive_folder_id="restricted_folder_999",
    )

    result = await toolset.execute_tool(
      name="drive_list_client_documents",
      arguments={"client_id": "client_d"},
      context=context,
    )

    self.assertFalse(result.isError)
    self.assertEqual(
      result.structuredData.get("restricted_folder_id"),
      "restricted_folder_999",
    )
    for f in result.structuredData["files"]:
      self.assertEqual(f["parent_folder_id"], "restricted_folder_999")

  async def test_folder_boundary_violation(self):
    """Tests that accessing unauthorized folder raises TenantIsolationError."""
    interceptor = TenantBoundaryInterceptor()
    context = TenantSecurityContext(
      client_id="client_d",
      allowed_drive_folder_id="allowed_folder_1",
    )

    with self.assertRaises(TenantIsolationError) as ctx:
      await interceptor.before_execute(
        tool_name="drive_list_client_documents",
        arguments={"client_id": "client_d", "folder_id": "foreign_folder_2"},
        context=context,
      )

    self.assertIn(
      "is outside the authorized Google Drive folder",
      str(ctx.exception),
    )

  async def test_tenant_boundary_enforcement_violation(self):
    """Tests that cross-tenant access raises TenantIsolationError."""
    toolset = MCPToolSet()
    await toolset.initialize()

    context = TenantSecurityContext(client_id="client_d")

    with self.assertRaises(TenantIsolationError) as ctx:
      await toolset.execute_tool(
        name="drive_read_document_content",
        arguments={"file_id": "doc_123", "client_id": "client_b"},
        context=context,
      )

    self.assertIn(
      "Tenant 'client_b' does not match active security context 'client_d'",
      str(ctx.exception),
    )

  async def test_model_armor_secret_scrubbing(self):
    """Tests that sensitive credentials and API keys are redacted."""
    scrubber = ModelArmorScrubbingInterceptor()

    mock_key = "AIza" + "Sy" + "MockKeyForTesting1234567890abcdef"
    text_with_secret = (
      f"Here is the key: {mock_key} and secret "
      "password='my_super_secret_password'"
    )
    cleaned = scrubber._scrub_text(text_with_secret)

    self.assertNotIn("AIza", cleaned)
    self.assertIn("[REDACTED_SECRET]", cleaned)


if __name__ == "__main__":
  unittest.main()
