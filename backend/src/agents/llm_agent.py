"""Base Google ADK LlmAgent class for prompt and client management."""

from __future__ import annotations

import os
from typing import Any

import yaml
from google import genai

try:
  from google.adk.agents import LlmAgent as BaseADKLlmAgent
except ImportError:

  class BaseADKLlmAgent:
    pass


from src.core.config import config
from src.core.error_messages import ErrorMessages
from src.core.logging_config import get_logger

logger = get_logger("artifactforge.agent")


class LlmAgent(BaseADKLlmAgent):
  """Base Google ADK LlmAgent class for Gemini API and YAML prompts."""

  def __init__(
    self,
    prompt_path: str,
    model_name: str | None = None,
    **kwargs: Any,
  ) -> None:
    """Initializes LlmAgent with model tier and prompt instructions.

    Args:
      prompt_path: Path to versioned YAML prompt file.
      model_name: Optional Vertex AI model name (e.g. 'gemini-2.5-flash').
      **kwargs: Extra arguments passed to base ADK agent.
    """
    super().__init__(**kwargs)
    self.model_name = model_name or config.default_model
    self.prompt_path = prompt_path
    self.system_instruction = self._load_system_instruction()
    self._client: genai.Client | None = None

  def _load_system_instruction(self) -> str:
    """Loads prompt instructions from versioned YAML template.

    Returns:
      System instruction text.

    Raises:
      FileNotFoundError: If prompt YAML file is missing.
      ValueError: If 'system_instruction' key is missing in YAML.
    """
    resolved_path = self.prompt_path
    if not os.path.exists(resolved_path):
      candidates = [
        os.path.join(
          os.path.dirname(os.path.dirname(__file__)),
          "prompts",
          os.path.basename(self.prompt_path),
        ),
        os.path.join("backend", self.prompt_path),
        os.path.join(os.getcwd(), "backend", self.prompt_path),
        os.path.join(os.getcwd(), self.prompt_path),
      ]
      for c in candidates:
        if os.path.exists(c):
          resolved_path = c
          break

    if not os.path.exists(resolved_path):
      logger.error(
        "Agent prompt YAML not found: %s (resolved: %s)",
        self.prompt_path,
        resolved_path,
      )
      raise FileNotFoundError(
        ErrorMessages.ERR_PROMPT_FILE_MISSING.format(path=self.prompt_path)
      )

    with open(resolved_path, encoding="utf-8") as f:
      data = yaml.safe_load(f)
      instruction = data.get("system_instruction")
      if not instruction:
        logger.error("Missing 'system_instruction' in: %s", self.prompt_path)
        raise ValueError(
          ErrorMessages.ERR_PROMPT_KEY_MISSING.format(path=self.prompt_path)
        )
      return instruction

  @property
  def client(self) -> genai.Client:
    """Lazy initialization of the Gemini API Client in Vertex AI mode.

    Returns:
      Initialized genai.Client instance authenticated via Google Cloud IAM.
    """
    if self._client is None:
      self._client = genai.Client(
        vertexai=True,
        project=config.gcp_project_id,
        location=config.gcp_location,
      )
    return self._client
