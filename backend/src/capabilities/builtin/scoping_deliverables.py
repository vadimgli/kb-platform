"""Scoping Deliverables capability module."""

from __future__ import annotations

from typing import Any
from src.capabilities.base import (
  BaseCapability,
  CapabilityCategory,
  ExportTarget,
)
from src.models.schemas import ScopingDeliverableItem, ScopingDeliverables


class ScopingDeliverablesCapability(BaseCapability):
  """Capability for generating structured In-Scope Scoping Deliverables."""

  def __init__(self) -> None:
    self.capability_id = "scoping_deliverables"
    self.name = "scoping_deliverables"
    self.category = CapabilityCategory.SCOPING_DELIVERABLES
    self.description = (
      "Synthesizes 3-column in-scope responsibilities matrix (Scope Area, "
      "Technical Deliverables, Responsible Party) with zero cross-tenant "
      "leakage."
    )
    self.export_target = ExportTarget.GOOGLE_DOC
    self.response_schema = ScopingDeliverables

  @property
  def structural_skeleton(self) -> str:
    """Returns abstract 3-column structural skeleton with 0% client facts."""
    return (
      "# IN-SCOPE DELIVERABLES STRUCTURAL SKELETON (ABSTRACT GRAMMAR)\n"
      "Column 1: Project Scope Area (e.g. Model Evals, Optimization)\n"
      "Column 2: Technical Deliverables (bulleted list of concrete items)\n"
      "Column 3: Responsible Party (Google FDE, Google FDE & Client)\n"
      "\n"
      "Scope 1: Model Evals & Monitoring Setup\n"
      "  * Technical Deliverables: Evals report across Gemini models; tracing\n"
      "  * Responsible Party: Google FDE Team\n"
      "\n"
      "Scope 2: Algorithm & Workflow Optimization\n"
      "  * Technical Deliverables: Skill iterations, loss analysis, memory\n"
      "  * Responsible Party: Google FDE Team\n"
      "\n"
      "Scope 3: Productization in Target Environment\n"
      "  * Technical Deliverables: Deploy headless agents; telemetry\n"
      "  * Responsible Party: Google FDE Team\n"
      "\n"
      "Scope 4: Asset Handover & Enablement\n"
      "  * Technical Deliverables: Final presentation; knowledge transfer\n"
      "  * Responsible Party: Google FDE Team & Client Technical Team\n"
      "\n"
      "Scope 5: Compute Scaling & Expansion\n"
      "  * Technical Deliverables: Scaling GCP quotas, tuning, roadmap\n"
      "  * Responsible Party: Google FDE Team & Client Infrastructure Team\n"
    )

  def build_prompt_context(
    self,
    client_id: str,
    query: str,
    context_snippets: list[dict[str, Any]],
  ) -> str:
    """Builds the grounding prompt context for structural infilling."""
    snippets_text = "\n".join(
      f"- {s.get('snippet', '')}" for s in context_snippets if s.get("snippet")
    )
    return (
      f"Target Client ID: {client_id}\n"
      f"User Query: {query}\n"
      f"Grounding Notes:\n{snippets_text}\n"
      f"\n{self.structural_skeleton}"
    )

  def format_for_export(
    self,
    data: ScopingDeliverables,
  ) -> dict[str, Any]:
    """Formats scoping deliverables for Google Drive / Google Docs export."""
    return {
      "title": data.title,
      "client_id": data.client_id,
      "timeline_weeks": data.timeline_weeks,
      "headers": [
        "Project Scope Area",
        "Technical Deliverables",
        "Responsible Party",
      ],
      "rows": [
        {
          "project_scope_area": item.project_scope_area,
          "technical_deliverables": item.technical_deliverables,
          "responsible_party": item.responsible_party,
        }
        for item in data.items
      ],
    }


# Backward compatibility alias
InScopeMatrixCapability = ScopingDeliverablesCapability
