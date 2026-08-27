"""Unit tests for central application configuration and model settings."""

import os
import pytest

from src.core.config import AppConfig, config


def test_default_config_model_versions() -> None:
  """Tests default model version assignments loaded from environment."""
  assert config.default_model == os.getenv("DEFAULT_MODEL_NAME")
  assert config.lightweight_model == os.getenv("LIGHTWEIGHT_MODEL_NAME")
  expected_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
  ]
  assert config.cors_origins_list == expected_origins


def test_config_env_override(monkeypatch) -> None:
  """Tests environment variable overrides for model selection."""
  monkeypatch.setenv("DEFAULT_MODEL_NAME", "custom-model-3.6")
  monkeypatch.setenv("LIGHTWEIGHT_MODEL_NAME", "custom-model-3.5")

  custom_config = AppConfig()
  assert custom_config.default_model == "custom-model-3.6"
  assert custom_config.lightweight_model == "custom-model-3.5"


def test_config_missing_model_env_raises_error(monkeypatch) -> None:
  """Tests that missing DEFAULT_MODEL_NAME raises ValueError."""
  monkeypatch.setenv("DEFAULT_MODEL_NAME", "")
  with pytest.raises(ValueError) as exc_info:
    AppConfig()
  assert "DEFAULT_MODEL_NAME" in str(exc_info.value)
