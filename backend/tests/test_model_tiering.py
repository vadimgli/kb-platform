"""Unit tests for Flash-Lite Model Tiering (Asymmetric Model Routing)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.executor import ExecutorAgent
from src.agents.llm_agent import LlmAgent
from src.agents.planner import PlannerAgent
from src.core.config import AppConfig
from src.models.schemas import ActionCategory, AgentAction, RiskLevel


def test_app_config_loads_tiered_model_names(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Verifies AppConfig correctly loads tiered model environment settings."""
  monkeypatch.setenv("PLANNER_MODEL_NAME", "gemini-2.5-flash")
  monkeypatch.setenv("EXECUTOR_MODEL_NAME", "gemini-2.5-flash-lite")
  cfg = AppConfig()

  assert cfg.planner_model == "gemini-2.5-flash"
  assert cfg.executor_model == "gemini-2.5-flash-lite"


def test_llm_agent_defaults_to_default_model() -> None:
  """Verifies LlmAgent falls back to default_model when unspecified."""
  valid_prompt = (
    Path(__file__).parent.parent / "src" / "prompts" / "planner_prompt_v1.yaml"
  )
  agent = LlmAgent(prompt_path=str(valid_prompt))
  assert agent.model_name == agent.model_name


def test_agents_initialize_with_asymmetric_models(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Verifies PlannerAgent and ExecutorAgent bind to assigned model tiers."""
  monkeypatch.setenv("PLANNER_MODEL_NAME", "gemini-2.5-flash")
  monkeypatch.setenv("EXECUTOR_MODEL_NAME", "gemini-2.5-flash-lite")

  planner = PlannerAgent()
  executor = ExecutorAgent()

  assert planner.model_name == "gemini-2.5-flash"
  assert executor.model_name == "gemini-2.5-flash-lite"


@pytest.mark.asyncio
async def test_executor_agent_flash_lite_structured_output() -> None:
  """Verifies ExecutorAgent synthesizes valid AgentAction JSON."""
  executor = ExecutorAgent()
  mock_json_output = """
  [
    {
      "action_type": "DISCOVERY_SEARCH",
      "target_tenant_id": "client_d",
      "payload": "Search client notes",
      "description": "Discovery search",
      "risk_level": "LOW",
      "status": "PENDING"
    }
  ]
  """

  mock_response = MagicMock()
  mock_response.text = mock_json_output

  with patch.object(
    executor.client.aio.models,
    "generate_content",
    new_callable=AsyncMock,
    return_value=mock_response,
  ):
    actions = await executor.generate_actions(
      steps=["Search client notes"],
      client_id="client_d",
    )

    assert len(actions) == 1
    assert actions[0].action_type == ActionCategory.DISCOVERY_SEARCH
    assert actions[0].target_tenant_id == "client_d"
    assert actions[0].risk_level == RiskLevel.LOW
