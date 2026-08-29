"""Enterprise Safety Guardrails and Tenant Isolation Interceptors."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.core.exceptions import GuardrailValidationError
from src.models.schemas import (
  ActionCategory,
  AgentAction,
  ExecutionPlan,
  RiskLevel,
)

logger = logging.getLogger("artifactforge.guardrails")

# Forbidden destructive actions & patterns
FORBIDDEN_DESTRUCTIVE_KEYWORDS = {
  "DELETE_VAULT",
  "PURGE_BUCKET",
  "DESTROY_INFRASTRUCTURE",
  "REVOKE_ALL_PERMISSIONS",
  "FORCE_OVERWRITE_ALL",
  "DROP_TABLE",
  "DELETE_FROM",
}

# Forbidden sharing or public access modifications
FORBIDDEN_PERMISSIONS_PATTERNS = [
  re.compile(r"role\s*=\s*reader.*type\s*=\s*anyone", re.IGNORECASE),
  re.compile(r"type\s*=\s*anyone", re.IGNORECASE),
  re.compile(r"allUsers|allAuthenticatedUsers", re.IGNORECASE),
  re.compile(r"public_access\s*=\s*true", re.IGNORECASE),
]

# Multi-tenant boundary regex pattern (matches foreign vault paths)
CROSS_TENANT_PATH_PATTERN = re.compile(
  r"gs://(?:[a-zA-Z0-9_\.\-]+-)?vaults/([a-zA-Z0-9_\-]+)/", re.IGNORECASE
)

# Allowed Read-Only Action Categories
READ_ONLY_ACTIONS = {
  ActionCategory.DISCOVERY_SEARCH,
  ActionCategory.LEAKAGE_AUDIT_SCREEN,
  ActionCategory.NOTIFY_OPERATOR,
}

# Permitted Safe Write Action Categories
SAFE_MUTATING_ACTIONS = {
  ActionCategory.FACT_INFILL_GENERATE,
  ActionCategory.DRIVE_EXPORT,
  ActionCategory.DRIVE_MATRIX_EXPORT,
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
  modified = False

  for pattern, replacement in CREDENTIAL_PATTERNS:
    if pattern.search(sanitized):
      sanitized = pattern.sub(replacement, sanitized)
      modified = True

  return sanitized, modified


def classify_action_risk(action: AgentAction) -> RiskLevel:
  """Evaluates risk classification for synthesized agent actions.

  Args:
    action: AgentAction to evaluate.

  Returns:
    RiskLevel (LOW, MEDIUM, HIGH).
  """
  if action.action_type in READ_ONLY_ACTIONS:
    return RiskLevel.LOW

  if action.action_type == ActionCategory.FACT_INFILL_GENERATE:
    return RiskLevel.MEDIUM

  if action.action_type in (
    ActionCategory.DRIVE_EXPORT,
    ActionCategory.DRIVE_MATRIX_EXPORT,
  ):
    payload_lower = action.payload.lower()
    if (
      "anyone" in payload_lower
      or "allusers" in payload_lower
      or "delete" in payload_lower
    ):
      return RiskLevel.HIGH
    return RiskLevel.LOW

  return RiskLevel.LOW


def verify_action_safety(
  action: AgentAction | str, allowed_tenant_id: str | None = None
) -> tuple[bool, str | None]:
  """Applies AST and regex guardrails to verify action safety.

  Args:
    action: The AgentAction or command string to validate.
    allowed_tenant_id: The client tenant ID authorized for current session.

  Returns:
    Tuple of (is_safe: bool, violation_reason: str | None).
  """
  if isinstance(action, str):
    text = action
    action_tenant = None
  else:
    text = f"{action.action_type} {action.description} {action.payload}"
    action_tenant = action.target_tenant_id

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


def sanitize_and_verify_commands(
  plan_or_actions: ExecutionPlan | list[AgentAction] | None = None,
  allowed_tenant_id: str = "",
  actions: list[AgentAction] | None = None,
  plan: ExecutionPlan | None = None,
) -> Any:
  """Re-verifies actions through safety guardrails.

  Args:
    plan_or_actions: The ExecutionPlan or list of AgentAction objects.
    allowed_tenant_id: Authorized tenant ID when list passed.
    actions: Optional explicit actions keyword argument.
    plan: Optional explicit plan keyword argument.

  Returns:
    Sanitized plan (or tuple of actions, high_risk_flagged, overridden).
  """
  target = plan_or_actions or actions or plan
  if isinstance(target, ExecutionPlan):
    plan_obj = target
    tenant_id = plan_obj.target_tenant_id
    for act in plan_obj.actions:
      is_safe, violation_reason = verify_action_safety(
        action=act, allowed_tenant_id=tenant_id
      )
      if not is_safe:
        raise GuardrailValidationError(
          f"Action '{act.description}' failed safety verification: "
          f"{violation_reason}"
        )
      act.risk_level = classify_action_risk(act)
      sanitized_payload, _ = sanitize_user_prompt_with_dlp_and_model_armor(
        act.payload
      )
      act.payload = sanitized_payload
    return plan_obj

  action_list = target if isinstance(target, list) else []
  sanitized_list: list[AgentAction] = []
  high_risk = False
  for act in action_list:
    is_safe, violation_reason = verify_action_safety(
      action=act, allowed_tenant_id=allowed_tenant_id
    )
    if not is_safe:
      raise GuardrailValidationError(
        f"Action '{act.description}' failed safety verification: "
        f"{violation_reason}"
      )
    act.risk_level = classify_action_risk(act)
    if act.risk_level == RiskLevel.HIGH:
      high_risk = True
    sanitized_payload, _ = sanitize_user_prompt_with_dlp_and_model_armor(
      act.payload
    )
    act.payload = sanitized_payload
    sanitized_list.append(act)

  return sanitized_list, high_risk, False
