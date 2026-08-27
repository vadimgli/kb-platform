"""Unit tests for CapabilityRegistry and AgentRegistry."""

import unittest

from src.agents.planner import PlannerAgent
from src.agents.registry import AgentRegistry
from src.capabilities.builtin.scoping_deliverables import (
  ScopingDeliverablesCapability,
)
from src.capabilities.registry import CapabilityRegistry


class TestRegistries(unittest.TestCase):
  """Test suite covering CapabilityRegistry and AgentRegistry."""

  def test_capability_registry(self):
    """Tests capability registration and A2A skill translation."""
    cap_registry = CapabilityRegistry()
    cap = ScopingDeliverablesCapability()
    cap_registry.register(cap)

    resolved = cap_registry.get("scoping_deliverables")
    self.assertIsNotNone(resolved)
    self.assertEqual(resolved.name, cap.name)

    skills = cap_registry.export_as_a2a_skills()
    self.assertEqual(len(skills), 1)
    self.assertEqual(skills[0].id, "scoping_deliverables")

  def test_agent_registry(self):
    """Tests agent registration, lookup, and A2A card generation."""
    agent_reg = AgentRegistry()
    planner = PlannerAgent()
    agent_reg.register_agent(
      name="planner",
      agent=planner,
    )

    resolved_agent = agent_reg.get_agent("planner")
    self.assertIsNotNone(resolved_agent)

    card = agent_reg.export_agent_card(base_url="http://localhost:8000")
    self.assertEqual(card.name, "artifactforge_platform")
    self.assertGreater(len(card.skills), 0)


if __name__ == "__main__":
  unittest.main()
