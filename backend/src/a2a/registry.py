"""Agent2Agent (A2A) Client Registry for remote agent discovery."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

try:
  from a2a import ClientFactory
except ImportError:
  ClientFactory = None

from src.a2a.types import A2AMessage, A2ATask, AgentCard

logger = logging.getLogger("a2a.registry")


class A2ARegistry:
  """Discovers and orchestrates remote agents conforming to the A2A protocol."""

  def __init__(self, timeout_seconds: float = 30.0):
    """Initializes A2A Registry.

    Args:
      timeout_seconds: HTTP request timeout in seconds.
    """
    self._registered_cards: dict[str, AgentCard] = {}
    self._clients: dict[str, Any] = {}
    self._timeout = timeout_seconds
    self._http_client = httpx.AsyncClient(timeout=timeout_seconds)

  async def close(self) -> None:
    """Closes underlying HTTP clients."""
    await self._http_client.aclose()

  async def register_remote_agent(
    self,
    agent_url: str,
    custom_name: str | None = None,
  ) -> AgentCard:
    """Discovers a remote agent by resolving its /.well-known/agent-card.json.

    Args:
      agent_url: Base URL of remote agent (e.g. 'http://pricing-service:8001').
      custom_name: Optional local alias for the agent.

    Returns:
      Resolved AgentCard instance.

    Raises:
      RuntimeError: If the remote agent cannot be reached or returns an error.
    """
    card_url = f"{agent_url.rstrip('/')}/.well-known/agent-card.json"
    logger.info("Resolving remote A2A Agent Card from: %s", card_url)

    if ClientFactory:
      try:
        client = await ClientFactory.connect(agent_url)
        card_data = await client.get_card()
        card = (
          card_data
          if isinstance(card_data, AgentCard)
          else AgentCard.model_validate(card_data)
        )
        self._clients[card.name] = client
      except Exception as err:
        logger.warning(
          "ClientFactory connection failed (%s); using HTTP fallback", err
        )
        card = await self._fetch_card_http(card_url)
    else:
      card = await self._fetch_card_http(card_url)

    key = custom_name or card.name
    self._registered_cards[key] = card
    logger.info(
      "Registered A2A agent '%s' (v%s) with %d skills.",
      card.name,
      card.version,
      len(card.skills),
    )
    return card

  async def _fetch_card_http(self, card_url: str) -> AgentCard:
    """Direct HTTP fallback for fetching Agent Card."""
    response = await self._http_client.get(card_url)
    if response.status_code != 200:
      raise RuntimeError(
        f"Failed to fetch Agent Card from {card_url} "
        f"(HTTP {response.status_code})"
      )
    return AgentCard.model_validate(response.json())

  def get_card(self, agent_name: str) -> AgentCard | None:
    """Returns the AgentCard for a registered agent name."""
    return self._registered_cards.get(agent_name)

  def list_agents(self) -> list[AgentCard]:
    """Returns all registered agent cards."""
    return list(self._registered_cards.values())

  def find_agents_by_skill(self, skill_id: str) -> list[AgentCard]:
    """Finds all agents offering a specific skill ID."""
    matched: list[AgentCard] = []
    for card in self._registered_cards.values():
      if any(s.id == skill_id for s in card.skills):
        matched.append(card)
    return matched

  async def send_message_to_agent(
    self,
    agent_name: str,
    message: A2AMessage,
  ) -> A2AMessage:
    """Sends an A2A message to a registered remote agent.

    Args:
      agent_name: Name or alias of target agent.
      message: Outbound A2AMessage payload.

    Returns:
      Inbound response A2AMessage.

    Raises:
      KeyError: If agent_name is not registered.
      RuntimeError: If the remote agent call fails.
    """
    card = self._registered_cards.get(agent_name)
    if not card:
      raise KeyError(f"Agent '{agent_name}' is not registered in A2A Registry")

    endpoint = f"{card.url.rstrip('/')}/a2a/v1/message"
    logger.info(
      "Sending A2A message %s to agent '%s' at %s",
      message.id,
      agent_name,
      endpoint,
    )

    response = await self._http_client.post(
      endpoint,
      json=message.model_dump(mode="json"),
    )
    if response.status_code != 200:
      raise RuntimeError(
        f"A2A communication with '{agent_name}' failed "
        f"(HTTP {response.status_code}): {response.text}"
      )

    return A2AMessage.model_validate(response.json())

  async def send_message(self, agent_name: str, content: str):
    """Sends a text message to a target agent and yields the result.

    Args:
      agent_name: Target agent identifier.
      content: Prompt or message string.

    Yields:
      Content string chunks from the agent.
    """
    msg = A2AMessage(role="user", content=content)
    res = await self.send_message_to_agent(agent_name, msg)
    yield res.content

  async def fan_out_query(
    self,
    skill_id: str | None = None,
    query_text: str | None = None,
    targets: list[str] | None = None,
    content: str | None = None,
    context: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    """Queries target agents in parallel and gathers results.

    Args:
      skill_id: Optional skill identifier.
      query_text: Optional prompt string.
      targets: Optional list of target agent names.
      content: Optional prompt string alias.
      context: Context dictionary passed in task.

    Returns:
      Dict mapping agent names to their responses.
    """
    query = content or query_text or ""
    if targets:
      target_names = targets
    elif skill_id:
      target_names = [c.name for c in self.find_agents_by_skill(skill_id)]
    else:
      target_names = list(self._registered_cards.keys())

    if not target_names:
      logger.warning("No A2A agents found for query")
      return {}

    async def _query_single(agent_name: str) -> tuple[str, str]:
      chunks = []
      gen = self.send_message(agent_name, query)
      if hasattr(gen, "__aiter__"):
        async for chunk in gen:
          chunks.append(chunk)
      elif asyncio.iscoroutine(gen):
        res = await gen
        chunks.append(str(res))
      return agent_name, "".join(chunks)

    tasks = [_query_single(name) for name in target_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, Any] = {}
    for res in results:
      if isinstance(res, tuple):
        name, output = res
        out[name] = output
      elif isinstance(res, Exception):
        logger.error("Fan-out query task encountered error: %s", res)

    return out
