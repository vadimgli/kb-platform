"""Unit tests for Zero-Leakage Structural Transfer of Scoping Deliverables."""

import unittest
from src.capabilities.builtin.scoping_deliverables import (
  ScopingDeliverablesCapability,
)
from src.models.guardrails import verify_action_safety
from src.models.schemas import (
  ScopingDeliverableItem,
  ScopingDeliverables,
)


class TestZeroLeakageDeliverablesTransfer(unittest.TestCase):
  """Verifies structural grammar transfer without cross-tenant fact leakage."""

  def test_structural_grammar_skeleton_defined(self):
    """Verifies that the deliverable structure is defined abstractly."""
    capability = ScopingDeliverablesCapability()
    self.assertEqual(capability.capability_id, "scoping_deliverables")
    self.assertIn("Project Scope Area", capability.structural_skeleton)
    self.assertIn("Technical Deliverables", capability.structural_skeleton)
    self.assertIn("Responsible Party", capability.structural_skeleton)

  def test_infilled_deliverables_for_client_b_contains_zero_leakage(self):
    """Tests that Client B deliverables have zero facts from past Client A."""
    confidential_project_a_terms = [
      "JPMC",
      "Block Trading",
      "Atlas Alpha",
      "Atlas Gold",
    ]

    client_b_deliverables = ScopingDeliverables(
      title="In-Scope Scoping Deliverables",
      client_id="client_healthcare",
      items=[
        ScopingDeliverableItem(
          project_scope_area="Clinical Diagnostic Model Evals",
          technical_deliverables=[
            "Evaluation report for Gemini 2.5 Flash on EHR data",
            "FHIR pipeline end-to-end tracing and monitoring",
          ],
          responsible_party="Google FDE Team",
        ),
        ScopingDeliverableItem(
          project_scope_area="EMR Environment Productization",
          technical_deliverables=[
            "Deploy HIPAA-compliant headless agents to Staging",
            "Promote solution to Clinical Production Dev environment",
          ],
          responsible_party="Google FDE Team",
        ),
        ScopingDeliverableItem(
          project_scope_area="Clinical Asset Handover & Enablement",
          technical_deliverables=[
            "Final clinical staff presentation and knowledge transfer",
            "Transition to hospital IT operations team",
          ],
          responsible_party="Google FDE Team & Hospital IT Technical team",
        ),
      ],
      timeline_weeks=6,
    )

    self.assertEqual(len(client_b_deliverables.items), 3)
    for item in client_b_deliverables.items:
      self.assertTrue(bool(item.project_scope_area))
      self.assertTrue(len(item.technical_deliverables) > 0)
      self.assertTrue(bool(item.responsible_party))

    dump = client_b_deliverables.model_dump_json()
    for forbidden_term in confidential_project_a_terms:
      self.assertNotIn(
        forbidden_term.lower(),
        dump.lower(),
        f"Leakage detected! Term '{forbidden_term}' found in Client B output.",
      )

  def test_guardrail_blocks_foreign_client_id_in_payload(self):
    """Verifies that guardrail blocks foreign client vault references."""
    payload = "Export deliverables to gs://vaults/client_jpmc/scope.docx"
    is_safe, reason = verify_action_safety(
      action=payload, allowed_tenant_id="client_healthcare"
    )
    self.assertFalse(is_safe)
    self.assertIn("Cross-Tenant Data Leakage Blocked", reason)


if __name__ == "__main__":
  unittest.main()
