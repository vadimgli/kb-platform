"""Tier 3 Isolated Research Worker Tool for ArtifactForge."""

from typing import Any
from src.core.logging_config import get_logger
from src.mcp.servers.google_drive import GoogleDriveMCPProvider
from src.services.rag import VertexRAGService

logger = get_logger("artifactforge.tools.research")


class ResearchAgentTool:
  """Sandboxed research tool querying RAG and sandboxed Drive folders."""

  def __init__(
    self,
    rag_service: VertexRAGService | None = None,
    drive_provider: GoogleDriveMCPProvider | None = None,
  ) -> None:
    self.rag_service = rag_service or VertexRAGService()
    self.drive_provider = drive_provider or GoogleDriveMCPProvider()

  async def execute_research(
    self,
    query: str,
    client_id: str,
    allowed_folder_id: str | None = None,
  ) -> list[str]:
    """Retrieves grounded findings strictly bounded to the active tenant."""
    logger.info("Executing deep research for client '%s'", client_id)
    findings: list[str] = []

    # 1. Query Vertex AI Search RAG
    try:
      rag_snippets = self.rag_service.search_k8s_documentation(
        query=query, page_size=3
      )
      for s in rag_snippets:
        if s.get("snippet"):
          findings.append(f"Grounding Note: {s['snippet']}")
    except Exception as err:
      logger.warning("RAG research fallback note: %s", err)

    # 2. Query Sandboxed Google Drive MCP provider
    try:
      files_res = await self.drive_provider.list_client_documents(
        client_id=client_id,
        folder_id=allowed_folder_id,
      )
      for f in files_res.get("files", [])[:3]:
        content_res = await self.drive_provider.read_document_content(
          file_id=f["id"],
          client_id=client_id,
        )
        body = content_res.get("content", "")
        if body:
          findings.append(f"Drive [{f.get('name', 'doc')}]: {body}")
    except Exception as err:
      logger.warning("Drive research fallback note: %s", err)

    if not findings:
      findings.append(
        "Standard Engagement Scope: ML Evals, Pipeline Optimization, "
        "Productization in Vertex AI, Enablement & Handover."
      )

    return findings
