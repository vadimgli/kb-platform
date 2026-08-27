"""Pytest configuration and global environment variable setup."""

import os
from pathlib import Path


def _sync_env_from_template() -> None:
  """Populates environment variables strictly from root .env.example template.

  No hardcoded fallback values are permitted; all configuration must derive
  from a single authoritative template source.
  """
  root_dir = Path(__file__).resolve().parent.parent.parent
  template_path = root_dir / ".env.example"

  if not template_path.exists():
    raise FileNotFoundError(
      f"Required configuration template missing at path: '{template_path}'"
    )

  with open(template_path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if line and not line.startswith("#") and "=" in line:
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if val and key not in os.environ:
          os.environ[key] = val


_sync_env_from_template()
