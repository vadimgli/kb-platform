"""Unit tests for MemoryBankService institutional memory integration."""

from unittest.mock import MagicMock, patch

from src.services.memory_bank import MemoryBankService


def test_initialize_memory_bank_success() -> None:
  """Tests successful Memory Bank instance creation with configured rules."""
  service = MemoryBankService()
  mock_client = MagicMock()
  mock_bank = MagicMock()
  mock_bank.api_resource_name = (
    "projects/test-proj/locations/us-central1/memoryBanks/mb-123"
  )
  mock_client.agent_engines.create.return_value = mock_bank

  with patch.object(service, "_get_client", return_value=mock_client):
    resource_name = service.initialize_memory_bank()
    assert (
      resource_name
      == "projects/test-proj/locations/us-central1/memoryBanks/mb-123"
    )
    mock_client.agent_engines.create.assert_called_once_with(
      config={
        "context_spec": {"memory_bank_config": service.memory_bank_config}
      }
    )


def test_retrieve_relevant_memories_graceful_degradation() -> None:
  """Tests that memory retrieval returns empty string when client is None."""
  service = MemoryBankService()
  with patch.object(service, "_get_client", return_value=None):
    result = service.retrieve_relevant_memories(
      "Pod payment-pod crashing", namespace="production"
    )
    assert result == ""


def test_retrieve_relevant_memories_success() -> None:
  """Tests successful institutional memory retrieval and formatting."""
  service = MemoryBankService()
  service._memory_bank_resource_name = "test-gcp-project"
  mock_client = MagicMock()
  mock_memory_1 = MagicMock()
  mock_memory_1.content = "Pod payment-pod requires 512Mi memory limits."
  mock_memory_2 = MagicMock()
  mock_memory_2.content = "Always check Istio sidecar proxy logs first."
  mock_client.agent_engines.memories.retrieve.return_value = [
    mock_memory_1,
    mock_memory_2,
  ]

  with patch.object(service, "_get_client", return_value=mock_client):
    result = service.retrieve_relevant_memories(
      "Pod payment-pod crashing", namespace="production"
    )
    assert "1. Pod payment-pod requires 512Mi memory limits." in result
    assert "2. Always check Istio sidecar proxy logs first." in result


def test_generate_memory_success() -> None:
  """Tests successful memory generation and consolidation."""
  service = MemoryBankService()
  service._memory_bank_resource_name = "test-gcp-project"
  mock_client = MagicMock()

  with patch.object(service, "_get_client", return_value=mock_client):
    success = service.generate_memory(
      "Resolved OOMKilled crash on payment-pod by increasing limit to 512Mi."
    )
    assert success is True
    mock_client.agent_engines.memories.generate.assert_called_once_with(
      name="test-gcp-project",
      direct_contents_source={
        "contents": [
          {
            "role": "user",
            "parts": [
              {
                "text": (
                  "Resolved OOMKilled crash on payment-pod by increasing limit"
                  " to 512Mi."
                )
              }
            ],
          }
        ]
      },
    )


def test_user_scoped_memory_bank_retrieval_and_generation() -> None:
  """Tests user_id scope propagation in Memory Bank retrieval and generation."""
  service = MemoryBankService()
  service._memory_bank_resource_name = "test-gcp-project"
  mock_client = MagicMock()
  mock_client.agent_engines.memories.retrieve.return_value = []

  with patch.object(service, "_get_client", return_value=mock_client):
    service.retrieve_relevant_memories(
      "Pod crash", namespace="default", user_id="vadimg@google.com"
    )
    mock_client.agent_engines.memories.retrieve.assert_called_once_with(
      name="test-gcp-project",
      scope={
        "user_id": "vadimg@google.com",
        "app_name": "vadimglinskiy-k8s",
      },
      similarity_search_params={
        "search_query": "Namespace: default | Query: Pod crash",
        "top_k": 3,
      },
    )

    service.generate_memory(
      "Resolved crash",
      user_id="vadimg@google.com",
      topic_tag="Pod_OOMKilled",
    )
    mock_client.agent_engines.memories.generate.assert_called_once_with(
      name="test-gcp-project",
      direct_contents_source={
        "contents": [{"role": "user", "parts": [{"text": "Resolved crash"}]}]
      },
      scope={
        "user_id": "vadimg@google.com",
        "app_name": "vadimglinskiy-k8s",
      },
      config={
        "metadata": {
          "topic_tag": {"string_value": "Pod_OOMKilled"},
        },
        "metadata_merge_strategy": "MERGE",
      },
    )


def test_retrieve_relevant_memories_as_hybrid() -> None:
  """Tests hybrid memory retrieval partitioning into system and dialogue."""
  service = MemoryBankService()
  service._memory_bank_resource_name = "test-gcp-project"
  mock_client = MagicMock()

  mock_global = MagicMock()
  mock_global.content = "Operator vadimg prefers json output."
  mock_global.topics = ["USER_PREFERENCES"]

  mock_episodic = MagicMock()
  mock_episodic.content = "Istio ingress pod needs restart on 502."
  mock_episodic.topics = ["KEY_CONVERSATION_DETAILS"]

  mock_client.agent_engines.memories.retrieve.return_value = [
    mock_global,
    mock_episodic,
  ]

  with patch.object(service, "_get_client", return_value=mock_client):
    result = service.retrieve_relevant_memories(
      "Ingress 502", namespace="prod", as_hybrid=True
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    system_mem, dialogue_mem = result
    assert "Operator vadimg prefers json output." in system_mem
    assert "Istio ingress pod needs restart on 502." in dialogue_mem
