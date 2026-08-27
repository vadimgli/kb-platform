"""Action Safety Guardrails, DLP Redaction, and Zero-Leakage Policy.

Enforces:
1. Multi-tenant isolation: Blocks any cross-tenant file reads or writes.
2. Destructive action blocking: Forbids deletion and purging of client data.
3. Model Armor / DLP Redaction: Scrubs API keys, passwords, and PII.
4. Risk classification (LOW, MEDIUM, HIGH) via deterministic analysis.
"""

from __future__ import annotations

import logging
import re

from src.core.exceptions import GuardrailValidationError
from src.models.schemas import (
  AgentAction,
  ExecutionPlan,
  RiskLevel,
)

logger = logging.getLogger("artifactforge.guardrails")

# ---------------------------------------------------------------------------
# Forbidden Patterns & Rules
# ---------------------------------------------------------------------------

# Forbidden destructive verbs & commands
FORBIDDEN_DESTRUCTIVE_KEYWORDS = {
  "DELETE_VAULT",
  "PURGE_CLIENT_DATA",
  "DROP_DATABASE",
  "DESTROY_WORKSPACE",
  "UNLINK_TENANT",
  "RMDIR",
  "RM -RF",
  "FORMAT_DISK",
  "SHUTDOWN",
}

# Forbidden public exposure / exfiltration patterns
FORBIDDEN_PERMISSIONS_PATTERNS = [
  re.compile(
    r"(?i)role\s*[:=]\s*['\"]?(reader|writer)['\"]?"
    r"\s*,\s*type\s*[:=]\s*['\"]?anyone['\"]?"
  ),
  re.compile(r"(?i)make_public"),
  re.compile(r"(?i)share_outside_domain"),
  re.compile(r"(?i)allow_unauthenticated"),
]

# Cross-tenant exfiltration regex patterns (referencing other client vaults)
CROSS_TENANT_PATH_PATTERN = re.compile(
  r"(?:gs://|drive/|vaults/|client_vaults/)(client_[a-zA-Z0-9_\-]+)",
  re.IGNORECASE,
)

# High-risk actions that modify external resources
HIGH_RISK_KEYWORDS = {
  "UPDATE_PERMISSIONS",
  "EXPORT_WORKSPACE",
  "DELETE",
  "OVERWRITE_FILE",
  "CALENDAR_SYNC",
  "CREATE_SHAREABLE_LINK",
}

# Medium-risk actions that create artifacts or write documents
MEDIUM_RISK_KEYWORDS = {
  "DRIVE_FILE_WRITE",
  "CREATE_DOCUMENT",
  "FACT_INFILL_GENERATE",
  "APPEND_RECORD",
  "INVOKE_SUBAGENT",
}

# Credential & PII Scrubbing Patterns
CREDENTIAL_PATTERNS = [
  (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{15,}"),
    "[REDACTED_BEARER_TOKEN]",
  ),
  (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_API_KEY]"),
  (re.compile(r"ghp_[0-9a-zA-Z]{36}"), "[REDACTED_GITHUB_TOKEN]"),
  (re.compile(r"ya29\.[0-9A-Za-z-_]+"), "[REDACTED_OAUTH_TOKEN]"),
  (
    re.compile(
      r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"
      r"[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
    ),
    "[REDACTED_PRIVATE_KEY]",
  ),
  (
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]+['\"]"),
    "password='[REDACTED_PASSWORD]'",
  ),
  (
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "[REDACTED_EMAIL]",
  ),
]


def sanitize_user_prompt_with_dlp_and_model_armor(
  prompt: str,
) -> tuple[str, bool]:
  """Sanitizes PII, credentials, and API keys before logging or processing.

  Args:
    prompt: Raw user input text.

  Returns:
    Tuple of (sanitized_prompt, was_modified).
  """
  sanitized = prompt
  for pattern, replacement in CREDENTIAL_PATTERNS:
    sanitized = pattern.sub(replacement, sanitized)
  return sanitized, sanitized != prompt


def classify_action_risk(payload: str | AgentAction) -> RiskLevel:
  """Classifies action risk level based on inspection and action category.

  Args:
    payload: Either an AgentAction instance or raw payload string.

  Returns:
    Evaluated RiskLevel (LOW, MEDIUM, or HIGH).
  """
  if isinstance(payload, AgentAction):
    action_type_str = str(payload.action_type).upper()
    text = f"{action_type_str} {payload.payload}".upper()
  else:
    text = str(payload).upper()

  # Check high-risk criteria
  if any(kw in text for kw in FORBIDDEN_DESTRUCTIVE_KEYWORDS):
    return RiskLevel.HIGH
  if any(kw in text for kw in HIGH_RISK_KEYWORDS):
    return RiskLevel.HIGH
  for pattern in FORBIDDEN_PERMISSIONS_PATTERNS:
    if pattern.search(text):
      return RiskLevel.HIGH

  # Check medium-risk criteria
  if any(kw in text for kw in MEDIUM_RISK_KEYWORDS):
    return RiskLevel.MEDIUM

  return RiskLevel.LOW


def verify_action_safety(
  action: AgentAction | str, allowed_tenant_id: str | None = None
) -> tuple[bool, str | None]:
  """Inspects action against destructive rules and tenant isolation.

  Args:
    action: The AgentAction or raw string to verify.
    allowed_tenant_id: The authenticated tenant context (e.g. 'client_d').

  Returns:
    Tuple of (is_safe: bool, violation_reason: str | None).
  """
  if isinstance(action, AgentAction):
    text = f"{action.action_type} {action.payload}"
    action_tenant = action.target_tenant_id
  else:
    text = str(action)
    action_tenant = allowed_tenant_id

  upper_text = text.upper()

  # 1. Block destructive operations
  for forbidden_kw in FORBIDDEN_DESTRUCTIVE_KEYWORDS:
    if forbidden_kw in upper_text:
      reason = (
        f"Security Violation: Forbidden destructive operation "
        f"'{forbidden_kw}' detected."
      )
      logger.error(reason)
      return False, reason

  # 2. Block public permission mutations
  for pattern in FORBIDDEN_PERMISSIONS_PATTERNS:
    if pattern.search(text):
      reason = (
        "Security Violation: Unauthorized public access or external "
        "domain sharing requested."
      )
      logger.error(reason)
      return False, reason

  # 3. Enforce Multi-Tenant Isolation (Zero Cross-Contamination)
  if allowed_tenant_id:
    # Verify explicit action tenant matching
    if action_tenant and action_tenant != allowed_tenant_id:
      reason = (
        f"Tenant Boundary Violation: Action tenant '{action_tenant}' "
        f"conflicts with active session tenant '{allowed_tenant_id}'."
      )
      logger.error(reason)
      return False, reason

    # Check for hardcoded cross-tenant path references in payload text
    matches = CROSS_TENANT_PATH_PATTERN.findall(text)
    for matched_tenant in matches:
      if matched_tenant.lower() != allowed_tenant_id.lower():
        reason = (
          f"Cross-Tenant Data Leakage Blocked: Detected attempt to access "
          f"vault for foreign tenant '{matched_tenant}' within "
          f"session '{allowed_tenant_id}'."
        )
        logger.error(reason)
        return False, reason

  return True, None


def sanitize_and_verify_commands(plan: ExecutionPlan) -> ExecutionPlan:
  """Re-verifies all actions within an ExecutionPlan through safety guardrails.

  Args:
    plan: The ExecutionPlan to validate.

  Returns:
    The plan with sanitized descriptions and verified risk levels.

  Raises:
    GuardrailValidationError: If any action violates safety rules.
  """
  for action in plan.actions:
    is_safe, violation_reason = verify_action_safety(
      action=action, allowed_tenant_id=plan.target_tenant_id
    )
    if not is_safe:
      raise GuardrailValidationError(
        f"Action '{action.description}' failed safety verification: "
        f"{violation_reason}"
      )

    # Classify and update risk level
    action.risk_level = classify_action_risk(action)

    # Sanitize payload strings
    sanitized_payload, _ = sanitize_user_prompt_with_dlp_and_model_armor(
      action.payload
    )
    action.payload = sanitized_payload

  return plan
