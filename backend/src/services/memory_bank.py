"""MemoryBankService for Vertex AI institutional cluster memory."""

from functools import lru_cache
from typing import Any

import vertexai

from src.core.config import config
from src.core.logging_config import get_logger

logger = get_logger("k8s-copilot.memory_bank")


class MemoryBankService:
  """Manages Vertex AI Agent Platform Memory Bank for institutional memory.

  Uses circuit-breaker exception handling so that if the Beta agent_engines
  API is unavailable in a region, it gracefully degrades to standard RAG.
  """

  def __init__(self) -> None:
    """Initializes MemoryBankService configuration and rules."""
    self.project_id = config.gcp_project_id
    self.location = config.gcp_location
    self._client = None
    self._memory_bank_resource_name: str | None = None

    self.memory_bank_config: dict[str, Any] = {
      "generation_config": {
        "model": (
          f"projects/{self.project_id}/locations/{self.location}"
          "/publishers/google/models/gemini-2.5-flash"
        )
      },
      "similarity_search_config": {
        "embedding_model": (
          f"projects/{self.project_id}/locations/{self.location}"
          "/publishers/google/models/text-embedding-005"
        )
      },
      "ttl_config": {"memory_revision_default_ttl": f"{365 * 24 * 60 * 60}s"},
      "customization_configs": [
        {
          "memory_topics": [
            {"managed_memory_topic": "USER_PERSONAL_INFO"},
            {"managed_memory_topic": "USER_PREFERENCES"},
            {"managed_memory_topic": "KEY_CONVERSATION_DETAILS"},
            {"managed_memory_topic": "EXPLICIT_INSTRUCTIONS"},
            {"custom_memory_topic": "CLUSTER_QUIRKS_AND_RUNBOOKS"},
          ],
          "consolidation_config": {"revisions_per_candidate_count": 1},
          "generate_memories_examples": [],
          "enable_third_person_memories": False,
        }
      ],
      "disable_memory_revisions": False,
    }

  def _get_client(self) -> Any:
    """Lazy-loads vertexai.Client when needed."""
    if self._client is None:
      try:
        vertexai.init(project=self.project_id, location=self.location)
        self._client = vertexai.Client(
          project=self.project_id, location=self.location
        )
      except Exception as e:  # noqa: BLE001
        logger.warning(
          "Vertex AI Client initialization failed for Memory Bank;"
          f" gracefully degrading: {e}"
        )
        self._client = None
    return self._client

  def initialize_memory_bank(self) -> str | None:
    """Creates or registers a Memory Bank instance with configured rules."""
    client = self._get_client()
    if client is None or not hasattr(client, "agent_engines"):
      return None

    try:
      memory_bank = client.agent_engines.create(
        config={"context_spec": {"memory_bank_config": self.memory_bank_config}}
      )
      self._memory_bank_resource_name = getattr(
        memory_bank, "api_resource_name", str(memory_bank)
      )
      logger.info(
        "Successfully initialized Vertex AI Memory Bank:"
        f" {self._memory_bank_resource_name}"
      )
      return self._memory_bank_resource_name
    except Exception as e:  # noqa: BLE001
      logger.warning(
        f"Memory Bank instance creation failed; degrading gracefully: {e}"
      )
      return None

  @lru_cache(maxsize=128)  # noqa: B019
  def retrieve_relevant_memories(
    self,
    query: str,
    namespace: str | None = None,
    user_id: str | None = None,
    as_hybrid: bool = False,
  ) -> str | tuple[str, str]:
    """Retrieves institutional cluster memories relevant to the incident query.

    Args:
      query: Diagnostic prompt query from operator.
      namespace: Optional Kubernetes namespace context.
      user_id: Optional authenticated operator email/ID for personal memory
        scope.
      as_hybrid: If True, returns a tuple (system_memories, dialogue_memories)
        separating stable user profile/preferences from episodic runbooks.

    Returns:
      Formatted text string of relevant historical cluster memories (or tuple of
      strings when as_hybrid=True), or empty string/tuple if unavailable.
    """
    if not self._memory_bank_resource_name:
      return ("", "") if as_hybrid else ""

    client = self._get_client()
    if client is None or not hasattr(client, "agent_engines"):
      logger.info(
        "Memory Bank client unavailable; skipping institutional memory lookup."
      )
      return ("", "") if as_hybrid else ""

    try:
      search_query = (
        f"Namespace: {namespace} | Query: {query}" if namespace else query
      )
      retrieve_kwargs: dict[str, Any] = {
        "name": self._memory_bank_resource_name,
        "scope": {
          "user_id": user_id or "default_user",
          "app_name": "vadimglinskiy-k8s",
        },
        "similarity_search_params": {
          "search_query": search_query,
          "top_k": 3,
        },
      }
      memories = client.agent_engines.memories.retrieve(**retrieve_kwargs)
      if not memories:
        return ("", "") if as_hybrid else ""

      system_lines: list[str] = []
      dialogue_lines: list[str] = []
      formatted_lines: list[str] = []
      for idx, mem in enumerate(memories, 1):
        content = getattr(mem, "content", getattr(mem, "fact", str(mem)))
        formatted_lines.append(f"{idx}. {content}")
        topics = [str(t).upper() for t in getattr(mem, "topics", [])]
        is_global = any(
          topic in ("USER_PERSONAL_INFO", "USER_PREFERENCES")
          for topic in topics
        ) or any(
          k in content.lower()
          for k in ("prefer", "always", "require", "never", "team")
        )
        target_list = system_lines if is_global else dialogue_lines
        target_list.append(f"- {content}")

      if not as_hybrid:
        return "\n".join(formatted_lines)

      system_str = "\n".join(system_lines) if system_lines else ""
      dialogue_str = "\n".join(dialogue_lines) if dialogue_lines else ""
      return system_str, dialogue_str

    except Exception as e:  # noqa: BLE001
      logger.warning(
        f"Memory Bank retrieval error; degrading to RAG-only context: {e}"
      )
      return ("", "") if as_hybrid else ""

  def generate_memory(
    self,
    session_context: str,
    user_id: str | None = None,
    topic_tag: str | None = None,
  ) -> bool:
    """Consolidates new institutional memory from a completed session.

    Args:
      session_context: Natural language summary of resolved incident.
      user_id: Optional authenticated operator email/ID for personal memory
        scope.
      topic_tag: Optional diagnostic topic tag (e.g. 'Pod_OOMKilled') for
        metadata consolidation.

    Returns:
      True if memory generation succeeded, False otherwise.
    """
    if not self._memory_bank_resource_name:
      return False

    client = self._get_client()
    if client is None or not hasattr(client, "agent_engines"):
      return False

    try:
      generate_kwargs: dict[str, Any] = {
        "name": self._memory_bank_resource_name,
        "direct_contents_source": {
          "contents": [{"role": "user", "parts": [{"text": session_context}]}]
        },
      }
      if user_id:
        generate_kwargs["scope"] = {
          "user_id": user_id,
          "app_name": "vadimglinskiy-k8s",
        }
      if topic_tag:
        generate_kwargs["config"] = {
          "metadata": {
            "topic_tag": {"string_value": topic_tag},
          },
          "metadata_merge_strategy": "MERGE",
        }
      client.agent_engines.memories.generate(**generate_kwargs)
      logger.info(
        "Successfully generated and consolidated new Memory Bank fact."
      )
      return True
    except Exception as e:  # noqa: BLE001
      logger.warning(
        f"Memory Bank generation failed; skipping persistence: {e}"
      )
      return False
