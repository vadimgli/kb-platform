"""Central Agent Registry for managing local ADK and remote A2A agents."""

from __future__ import annotations

import logging
from typing import Any
from src.a2a.types import AgentCard, AgentSkill
from src.agents.executor import ExecutorAgent
from src.agents.llm_agent import LlmAgent
from src.agents.planner import PlannerAgent
from src.agents.specialists.scoping import ScopingSpecialistSubAgent
from src.agents.triage import PrimaryTriageAgent
from src.capabilities.registry import capability_registry

logger = logging.getLogger("artifactforge.agent_registry")


class AgentRegistry:
  """Registers and orchestrates local ADK agents and remote A2A agents."""

  def __init__(self) -> None:
    self._agents: dict[str, LlmAgent] = {}
    self._skills_map: dict[str, list[AgentSkill]] = {}

  def register_agent(
    self,
    name: str,
    agent: LlmAgent,
    skills: list[AgentSkill] | None = None,
  ) -> None:
    """Registers a local ADK agent with its declared skills.

    Args:
      name: Unique agent identifier.
      agent: Initialized LlmAgent instance.
      skills: Optional list of declared AgentSkill descriptors.
    """
    self._agents[name] = agent
    self._skills_map[name] = skills or []
    logger.info(
      "Registered agent '%s' with %d skills.", name, len(skills or [])
    )

  def get_agent(self, name: str) -> LlmAgent | None:
    """Retrieves an agent by its unique identifier."""
    return self._agents.get(name)

  def find_agent_by_skill(self, skill_id: str) -> LlmAgent | None:
    """Finds an agent advertising a matching skill ID."""
    for name, skills in self._skills_map.items():
      if any(s.id == skill_id for s in skills):
        return self._agents[name]
    return None

  def list_agents(self) -> dict[str, LlmAgent]:
    """Returns all registered agent instances."""
    return dict(self._agents)

  def export_agent_card(self, base_url: str) -> AgentCard:
    """Compiles registered capabilities into an A2A Agent Card."""
    skills = capability_registry.export_as_a2a_skills()
    return AgentCard(
      name="artifactforge_platform",
      description=(
        "Enterprise 3-Tier Multi-Agent Platform for In-Scope Responsibilities "
        "Matrix and Zero-Leakage Deliverable Generation."
      ),
      url=base_url,
      version="1.0.0",
      skills=skills,
    )


# Global singleton instance with default agents registered
agent_registry = AgentRegistry()
agent_registry.register_agent("planner", PlannerAgent())
agent_registry.register_agent("executor", ExecutorAgent())
agent_registry.register_agent(
  "scoping_specialist", ScopingSpecialistSubAgent()
)
agent_registry.register_agent("triage", PrimaryTriageAgent())
