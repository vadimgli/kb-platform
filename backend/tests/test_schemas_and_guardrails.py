"""Unit tests for domain schemas and safety guardrails."""

import unittest

from src.models.guardrails import (
  classify_action_risk,
  sanitize_user_prompt_with_dlp_and_model_armor,
  verify_action_safety,
)
from src.models.schemas import (
  ActionCategory,
  AgentAction,
  AgentQueryRequest,
  InScopeResponsibilitiesMatrix,
  ResponsibilityMatrixItem,
  RiskLevel,
)


class TestSchemasAndGuardrails(unittest.TestCase):
  """Test suite covering matrix schemas, risk classification, and guardrails."""

  def test_in_scope_matrix_schema_validation(self):
    """Verifies valid InScopeResponsibilitiesMatrix instantiation."""
    matrix = InScopeResponsibilitiesMatrix(
      title="In-Scope Responsibilities Matrix",
      client_id="client_d",
      rows=[
        ResponsibilityMatrixItem(
          project_scope_area="Model Evals Setup",
          technical_deliverables=[
            "Evaluation report for Gemini versions",
            "End-to-end tracing and monitoring",
          ],
          responsible_party="Google FDE Team",
        ),
        ResponsibilityMatrixItem(
          project_scope_area="Asset Handover & Enablement",
          technical_deliverables=[
            "Final presentation and knowledge transfer",
            "Transition to production",
          ],
          responsible_party="Google FDE Team & Client Technical Team",
        ),
      ],
      timeline_weeks=6,
    )
    self.assertEqual(matrix.client_id, "client_d")
    self.assertEqual(len(matrix.rows), 2)
    self.assertEqual(matrix.rows[0].responsible_party, "Google FDE Team")

  def test_agent_query_request(self):
    """Tests AgentQueryRequest instantiation."""
    req = AgentQueryRequest(
      query="Generate an in-scope responsibilities matrix for our project",
      client_id="client_d",
    )
    self.assertEqual(req.client_id, "client_d")

  def test_risk_classification(self):
    """Verifies risk classification for low, medium, and high risk actions."""
    low_action = AgentAction(
      action_type=ActionCategory.DISCOVERY_SEARCH,
      target_tenant_id="client_d",
      payload="Search discovery notes for requirements",
      description="Find requirements",
    )
    self.assertEqual(classify_action_risk(low_action), RiskLevel.LOW)

    med_action = AgentAction(
      action_type=ActionCategory.FACT_INFILL_GENERATE,
      target_tenant_id="client_d",
      payload="Infill responsibilities matrix",
      description="Create matrix deliverable",
    )
    self.assertEqual(classify_action_risk(med_action), RiskLevel.MEDIUM)

    high_action = AgentAction(
      action_type=ActionCategory.DRIVE_EXPORT,
      target_tenant_id="client_d",
      payload="UPDATE_PERMISSIONS role=reader type=anyone",
      description="Make document public",
    )
    self.assertEqual(classify_action_risk(high_action), RiskLevel.HIGH)

  def test_verify_action_safety_destructive_blocked(self):
    """Verifies that destructive actions are blocked immediately."""
    destructive_action = AgentAction(
      action_type=ActionCategory.FACT_INFILL_GENERATE,
      target_tenant_id="client_d",
      payload="DELETE_VAULT client_d",
      description="Attempting to purge vault",
    )
    is_safe, reason = verify_action_safety(
      destructive_action, allowed_tenant_id="client_d"
    )
    self.assertFalse(is_safe)
    self.assertIn("Forbidden destructive operation", reason)

  def test_verify_action_safety_cross_tenant_leakage_blocked(self):
    """Verifies that cross-tenant access is blocked."""
    leaked_action = AgentAction(
      action_type=ActionCategory.DISCOVERY_SEARCH,
      target_tenant_id="client_b",
      payload="Read notes from gs://vaults/client_b/notes.txt",
      description="Reading foreign notes",
    )
    is_safe, reason = verify_action_safety(
      leaked_action, allowed_tenant_id="client_d"
    )
    self.assertFalse(is_safe)
    self.assertIn("Tenant Boundary Violation", reason)

  def test_dlp_and_model_armor_sanitization(self):
    """Verifies that credentials and emails are scrubbed."""
    mock_key = "AIza" + "Sy" + "MockKeyForTesting1234567890abcdef"
    raw = (
      f"My API key is {mock_key} and email is "
      "test@example.com"
    )
    sanitized, modified = sanitize_user_prompt_with_dlp_and_model_armor(raw)
    self.assertTrue(modified)
    self.assertNotIn("AIza", sanitized)
    self.assertIn("[REDACTED_API_KEY]", sanitized)
    self.assertIn("[REDACTED_EMAIL]", sanitized)


if __name__ == "__main__":
  unittest.main()
