"""Tier 3 Zero-Leakage Audit Tool for ArtifactForge."""

import re
from typing import Any
from src.core.logging_config import get_logger
from src.models.schemas import ScopingDeliverables

logger = get_logger("artifactforge.tools.audit")


class ZeroLeakageAuditTool:
  """Verifies zero cross-tenant contamination and structural compliance."""

  def __init__(self) -> None:
    self.forbidden_patterns = [
      re.compile(r"gs://vaults/(?!{client_id})[a-zA-Z0-9_-]+", re.IGNORECASE),
      re.compile(r"\bclient_[a-zA-Z0-9_-]+\b", re.IGNORECASE),
      re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"),
      re.compile(r"DROP\s+TABLE|DELETE\s+FROM", re.IGNORECASE),
    ]

  def audit_deliverables(
    self,
    deliverables: ScopingDeliverables,
    allowed_client_id: str,
  ) -> tuple[bool, list[str]]:
    """Evaluates deliverables matrix for foreign data leakage."""
    violations: list[str] = []

    # Check client ID consistency
    if deliverables.client_id != allowed_client_id:
      violations.append(
        f"Tenant Mismatch: matrix client '{deliverables.client_id}' "
        f"does not match authorized client '{allowed_client_id}'."
      )

    # Convert entire matrix text to string for inspection
    all_text = (
      f"{deliverables.title} "
      + " ".join(
        f"{item.project_scope_area} {' '.join(item.technical_deliverables)} "
        f"{item.responsible_party}"
        for item in deliverables.items
      )
    )

    # Check for foreign client identifiers
    for match in re.finditer(r"\bclient_([a-zA-Z0-9_-]+)\b", all_text):
      found_client = match.group(0).lower()
      if found_client != allowed_client_id.lower():
        violations.append(
          f"Foreign Client Leakage: Detected foreign tenant '{found_client}' "
          f"in deliverables."
        )

    # Check for vault leakage
    for match in re.finditer(r"gs://[a-zA-Z0-9_\.\-]+", all_text):
      uri = match.group(0)
      if allowed_client_id not in uri:
        violations.append(
          f"Vault Boundary Violation: Foreign storage path '{uri}' detected."
        )

    is_clean = len(violations) == 0
    if not is_clean:
      logger.warning("Zero-leakage audit failed: %s", violations)
    else:
      logger.info("Zero-leakage audit passed for '%s'", allowed_client_id)

    return is_clean, violations
