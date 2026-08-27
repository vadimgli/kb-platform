"""Scoping Deliverables Capability Module."""

from __future__ import annotations

from typing import Any
from src.capabilities.base import (
  BaseCapability,
  CapabilityCategory,
  ExportTarget,
)
from src.models.schemas import ScopingDeliverables


class ScopingDeliverablesCapability(BaseCapability):
  """Capability for generating the In-Scope Scoping Deliverables list."""

  capability_id = "scoping_deliverables"
  name = "In-Scope Scoping Deliverables"
  description = (
    "Generates a constrained list of bulleted deliverables grouped by Scope "
    "Area with assigned Responsible Parties."
  )
  category = CapabilityCategory.DELIVERABLE
  export_target = ExportTarget.GOOGLE_DOC
  response_schema = ScopingDeliverables

  structural_skeleton = (
    "# Scoping Deliverables Grammar Structure:\n"
    "- Project Scope Area 1: Model Evals & Monitoring Setup\n"
    "  * Technical Deliverables: Evals report across Gemini models; end-to-end tracing\n"
    "  * Responsible Party: Google FDE Team\n"
    "- Project Scope Area 2: Algorithm & Workflow Optimization\n"
    "  * Technical Deliverables: Skill iterations, loss analysis, memory layers\n"
    "  * Responsible Party: Google FDE Team\n"
    "- Project Scope Area 3: Productization in Target Environment\n"
    "  * Technical Deliverables: Deploy headless agents; telemetry; promote to Gold\n"
    "  * Responsible Party: Google FDE Team\n"
    "- Project Scope Area 4: Asset Handover & Enablement\n"
    "  * Technical Deliverables: Final presentation; knowledge transfer; cooldown\n"
    "  * Responsible Party: Google FDE Team & Client Technical Team\n"
    "- Project Scope Area 5: Compute Scaling & Expansion\n"
    "  * Technical Deliverables: Scaling GCP quotas, tuning, and expansion roadmap\n"
    "  * Responsible Party: Google FDE Team\n"
  )

  def build_prompt_context(
    self,
    client_id: str,
    query: str,
    context_snippets: list[dict[str, Any]],
  ) -> str:
    """Constructs prompt grounding the learned skeleton with client facts."""
    return (
      f"Target Tenant Client: {client_id}\n"
      f"User Query: {query}\n"
      f"Discovered Client Notes & Context:\n{context_snippets}\n\n"
      f"Structural Grammar Skeleton to Infill:\n{self.structural_skeleton}"
    )

