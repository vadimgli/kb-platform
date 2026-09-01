"""ADK PlannerAgent for In-Scope Responsibilities Matrix planning."""

from __future__ import annotations

import logging
from typing import Any

from google.genai import types

from src.agents.llm_agent import LlmAgent
from src.core.config import config
from src.models.schemas import (
  AgentQueryRequest,
  ExecutionPlan,
  InScopeResponsibilitiesMatrix,
  ResponsibilityMatrixItem,
)

logger = logging.getLogger("artifactforge.planner")


class PlannerAgent(LlmAgent):
  """Plans and infills the In-Scope Responsibilities Matrix."""

  def __init__(
    self,
    prompt_path: str = "src/prompts/planner_prompt_v1.yaml",
    model_name: str | None = None,
  ) -> None:
    super().__init__(
      prompt_path=prompt_path,
      model_name=model_name or config.planner_model or "gemini-2.5-flash",
    )

  async def generate_plan(
    self,
    query: str | AgentQueryRequest,
    client_id: str = "default",
    context_snippets: list[dict[str, Any]] | None = None,
    image_bytes: bytes | None = None,
  ) -> ExecutionPlan:
    """Generates an ExecutionPlan with the In-Scope Responsibilities Matrix.

    Args:
      query: User prompt, scoping requirements, or request object.
      client_id: Mandatory client tenant ID for zero-leakage grounding.
      context_snippets: Grounding snippets from discovery notes.
      image_bytes: Optional screenshot or diagram image data.

    Returns:
      Validated Pydantic ExecutionPlan instance.
    """
    if isinstance(query, AgentQueryRequest):
      raw_query = query.query
      client_id = query.client_id or client_id
    else:
      raw_query = str(query)

    logger.info(
      "Generating scoping matrix for tenant '%s' using %s",
      client_id,
      self.model_name,
    )

    contents: list[Any] = [
      f"Target Tenant Client ID: {client_id}",
      f"User Query / Scoping Requirements:\n{raw_query}",
      f"Grounded Discovery Notes (CONFIDENTIAL - CLIENT {client_id} ONLY):\n"
      f"{context_snippets or []}",
    ]

    if image_bytes:
      contents.append(
        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
      )

    response = await self.client.aio.models.generate_content(
      model=self.model_name,
      contents=contents,
      config=types.GenerateContentConfig(
        system_instruction=self.system_instruction,
        temperature=0.1,
        response_mime_type="application/json",
        response_schema=ExecutionPlan,
      ),
    )

    plan = ExecutionPlan.model_validate_json(response.text)
    plan.target_tenant_id = client_id
    if plan.matrix:
      plan.matrix.client_id = client_id
    return plan

  async def converse(
    self,
    query: str,
    client_id: str = "default",
  ) -> str:
    """Answers general and Google Drive folder questions conversationally with real enterprise context."""
    folder_id = config.allowed_drive_folder_id or "1IIxHSQLgvUSTwBpuZXDvTcUTWIBCWxHn"
    
    # Check for real files via GoogleDriveMCPProvider
    files_context = ""
    try:
      from src.mcp.servers.google_drive import GoogleDriveMCPProvider
      drive_provider = GoogleDriveMCPProvider(allowed_folder_id=folder_id)
      doc_list = await drive_provider.list_client_documents(client_id=client_id, folder_id=folder_id)
      files = doc_list.get("files", [])
      if files:
        file_summaries = [f"- {f.get('name', 'Untitled')} (ID: {f.get('id', '')})" for f in files]
        files_context = f"\nReal files found in authorized folder ({folder_id}):\n" + "\n".join(file_summaries)
      else:
        files_context = f"\nAuthorized folder ({folder_id}) currently contains no uploaded documents."
    except Exception as e:
      logger.warning("Could not list live Drive files: %s", e)
      files_context = f"\nAuthorized Google Drive Folder ID: {folder_id}"

    system_prompt = (
      "You are the Enterprise Assistant for ArtifactForge integrated within Gemini Enterprise.\n"
      f"You have Model Context Protocol (MCP) access to the authorized client Google Drive folder (ID: {folder_id}).\n"
      f"{files_context}\n\n"
      "Guidelines:\n"
      "1. If the user asks about the folder or files, report the actual files found above. Never invent fake client names or fake document titles.\n"
      "2. If no files are in the folder, inform the user and offer to generate an in-scope deliverables matrix based on their prompt requirements.\n"
      "3. Answer general technical, cloud architecture, and project management questions accurately and helpfully.\n"
      "4. If the user provides scoping requirements, offer to synthesize a 3-column In-Scope Responsibilities Matrix and export it to Google Docs."
    )
    response = await self.client.aio.models.generate_content(
      model=self.model_name,
      contents=[query],
      config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.2,
      ),
    )
    return response.text or f"I am your Gemini Enterprise assistant with access to Google Drive folder {folder_id}. How can I assist you?"



