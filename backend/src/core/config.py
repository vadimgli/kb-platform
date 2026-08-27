"""Central configuration module for ArtifactForge."""

import os
from dataclasses import dataclass, field

from src.core.error_messages import ErrorMessages


def _load_dotenv() -> None:
  """Loads environment variables from local .env file into os.environ."""
  for path in [
    os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
    os.path.join(os.getcwd(), ".env"),
  ]:
    if os.path.exists(path):
      with open(path, encoding="utf-8") as f:
        for line in f:
          line = line.strip()
          if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()


@dataclass(frozen=True)
class AppConfig:
  """Central configuration loaded from environment variables."""

  # GCP Infrastructure Settings
  gcp_project_id: str = field(
    default_factory=lambda: os.getenv("GCP_PROJECT_ID", "")
  )
  gcp_location: str = field(
    default_factory=lambda: os.getenv("GCP_LOCATION", "")
  )
  data_store_id: str = field(
    default_factory=lambda: os.getenv("DATA_STORE_ID", "")
  )

  # Gemini Model Selection
  default_model: str = field(
    default_factory=lambda: os.getenv("DEFAULT_MODEL_NAME", "")
  )
  lightweight_model: str = field(
    default_factory=lambda: os.getenv("LIGHTWEIGHT_MODEL_NAME", "")
  )

  # Asymmetric Model Tiering settings
  planner_model: str = field(
    default_factory=lambda: os.getenv(
      "PLANNER_MODEL_NAME",
      os.getenv("DEFAULT_MODEL_NAME", "gemini-2.5-flash"),
    )
  )
  executor_model: str = field(
    default_factory=lambda: os.getenv(
      "EXECUTOR_MODEL_NAME",
      os.getenv("LIGHTWEIGHT_MODEL_NAME", "gemini-2.5-flash-lite"),
    )
  )

  # Grounding Links & Documentation Settings
  default_k8s_docs_url: str = field(
    default_factory=lambda: os.getenv("DEFAULT_K8S_DOCS_URL", "")
  )
  default_doc_title: str = field(
    default_factory=lambda: os.getenv("DEFAULT_DOC_TITLE", "")
  )

  # Security & CORS Settings
  cors_allowed_origins: str = field(
    default_factory=lambda: os.getenv("CORS_ALLOWED_ORIGINS", "")
  )

  @property
  def cors_origins_list(self) -> list[str]:
    """Returns parsed list of CORS allowed origin strings."""
    return [
      origin.strip()
      for origin in self.cors_allowed_origins.split(",")
      if origin.strip()
    ]

  def __post_init__(self) -> None:
    """Validates that configuration variables are provided in environment."""
    required_vars = {
      "GCP_PROJECT_ID": self.gcp_project_id,
      "GCP_LOCATION": self.gcp_location,
      "DATA_STORE_ID": self.data_store_id,
      "DEFAULT_MODEL_NAME": self.default_model,
      "LIGHTWEIGHT_MODEL_NAME": self.lightweight_model,
      "DEFAULT_K8S_DOCS_URL": self.default_k8s_docs_url,
      "DEFAULT_DOC_TITLE": self.default_doc_title,
      "CORS_ALLOWED_ORIGINS": self.cors_allowed_origins,
    }
    missing = [name for name, val in required_vars.items() if not val]
    if missing:
      raise ValueError(
        ErrorMessages.ERR_MISSING_CONFIG_VARS.format(
          vars=", ".join(sorted(missing))
        )
      )


config = AppConfig()
