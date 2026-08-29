"""Tier 3 Google Drive Export Tool for ArtifactForge."""

from typing import Any
from src.core.logging_config import get_logger
from src.mcp.servers.google_drive import GoogleDriveMCPProvider
from src.models.schemas import ScopingDeliverables

logger = get_logger("artifactforge.tools.drive")


class GoogleDriveExportTool:
  """Sandboxed exporter for formatting deliverables into Google Docs."""

  def __init__(
    self, drive_provider: GoogleDriveMCPProvider | None = None
  ) -> None:
    self.drive_provider = drive_provider or GoogleDriveMCPProvider()

  async def export_matrix_to_doc(
    self,
    deliverables: ScopingDeliverables,
    allowed_folder_id: str | None = None,
  ) -> dict[str, Any]:
    """Exports structured 3-column deliverables table to Google Docs."""
    logger.info(
      "Exporting deliverables matrix to Google Drive for client '%s'",
      deliverables.client_id,
    )

    rows_payload = [
      {
        "project_scope_area": item.project_scope_area,
        "technical_deliverables": item.technical_deliverables,
        "responsible_party": item.responsible_party,
      }
      for item in deliverables.items
    ]

    result = await self.drive_provider.drive_export_in_scope_matrix(
      client_id=deliverables.client_id,
      title=deliverables.title,
      rows=rows_payload,
      folder_id=allowed_folder_id,
      timeline_weeks=deliverables.timeline_weeks,
    )

    return result
