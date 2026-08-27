"""Base capability interface and data contracts for pluggable deliverables."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Type
from pydantic import BaseModel


class CapabilityCategory(str, Enum):
  """Classification category of an enterprise capability."""

  DELIVERABLE = "DELIVERABLE"
  AUDIT = "AUDIT"
  ANALYSIS = "ANALYSIS"


class ExportTarget(str, Enum):
  """Target Google Workspace export format."""

  GOOGLE_DOC = "GOOGLE_DOC"
  GOOGLE_SLIDES = "GOOGLE_SLIDES"
  GOOGLE_SHEETS = "GOOGLE_SHEETS"
  MARKDOWN = "MARKDOWN"


class BaseCapability(ABC):
  """Abstract base class for all pluggable enterprise capabilities."""

  capability_id: str
  name: str
  description: str
  category: CapabilityCategory = CapabilityCategory.DELIVERABLE
  export_target: ExportTarget = ExportTarget.GOOGLE_DOC
  response_schema: Type[BaseModel]
  structural_skeleton: str

  @abstractmethod
  def build_prompt_context(
    self,
    client_id: str,
    query: str,
    context_snippets: list[dict[str, Any]],
  ) -> str:
    """Builds the grounding prompt context for structural infilling."""
    pass
