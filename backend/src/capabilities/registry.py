"""Central registry for managing pluggable enterprise capabilities."""

from __future__ import annotations

import logging
from src.a2a.types import AgentSkill
from src.capabilities.base import BaseCapability
from src.capabilities.builtin.scoping_deliverables import (
  ScopingDeliverablesCapability,
)

logger = logging.getLogger("artifactforge.capabilities")


class CapabilityRegistry:
  """Registers, discovers, and retrieves pluggable capabilities."""

  def __init__(self):
    self._capabilities: dict[str, BaseCapability] = {}

  def register(self, capability: BaseCapability) -> None:
    """Registers a capability plugin.

    Args:
      capability: An instance of BaseCapability.
    """
    self._capabilities[capability.capability_id] = capability
    logger.info(
      "Registered capability '%s' [%s]",
      capability.name,
      capability.capability_id,
    )

  def get(self, capability_id: str) -> BaseCapability | None:
    """Retrieves capability by ID."""
    return self._capabilities.get(capability_id)

  def list_all(self) -> list[BaseCapability]:
    """Returns all registered capabilities."""
    return list(self._capabilities.values())

  def export_as_a2a_skills(self) -> list[AgentSkill]:
    """Converts all registered capabilities into A2A AgentSkill descriptors."""
    return [
      AgentSkill(
        id=cap.capability_id,
        name=cap.name,
        description=cap.description,
        tags=[cap.category.value],
      )
      for cap in self._capabilities.values()
    ]


# Global singleton with the single primary capability registered
capability_registry = CapabilityRegistry()
capability_registry.register(ScopingDeliverablesCapability())
