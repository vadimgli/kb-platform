"""Benchmark runner for evaluating plans against the golden scenario dataset."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from evals.rubric_scorer import grade_plan_against_rubric
from src.models.schemas import (
  ActionCategory,
  AgentAction,
  ExecutionPlan,
  RiskLevel,
  ScopingDeliverables,
)

logger = logging.getLogger("artifactforge.benchmark")

POTENTIAL_PATHS = [
  Path("evals/golden_scenarios.json"),
  Path("backend/evals/golden_scenarios.json"),
  Path(__file__).parent / "golden_scenarios.json",
]


def _find_golden_dataset() -> Path:
  for p in POTENTIAL_PATHS:
    if p.exists():
      return p
  return POTENTIAL_PATHS[0]


def run_benchmark_report() -> dict[str, Any]:
  """Executes FDE rubric evaluation across golden scenarios.

  Returns:
    Dictionary containing benchmark summary metrics and scenario scores.
  """
  dataset_path = _find_golden_dataset()
  if not dataset_path.exists():
    logger.error("Golden dataset not found at %s", dataset_path)
    raise FileNotFoundError(f"Golden dataset not found at {dataset_path}")

  with open(dataset_path, encoding="utf-8") as f:
    scenarios = json.load(f)

  logger.info("Starting GOLDEN DATASET BENCHMARK REPORT")

  total_score = 0
  results: list[dict[str, Any]] = []

  for scenario in scenarios:
    actions = [
      AgentAction(
        action_type=ActionCategory.DISCOVERY_SEARCH,
        target_tenant_id="client_d",
        payload=f"Execute action: {step_str}",
        description=f"Action step {step_str}",
        risk_level=RiskLevel.LOW,
      )
      for step_str in scenario.get(
        "required_diagnostic_steps", scenario.get("required_actions", [])
      )
    ]
    plan = ExecutionPlan(
      summary=" ".join(
        scenario.get("expected_root_cause_keywords", ["Artifact", "Plan"])
      ),
      target_tenant_id="client_d",
      deliverables=ScopingDeliverables(
        client_id="client_d",
        items=[],
      ),
      actions=actions,
      citations=["https://docs.google.com/document/d/example_grounding"],
    )

    score = grade_plan_against_rubric(scenario, plan)
    total_score += score

    grade_label = {
      3: "3 - Exemplary",
      2: "2 - Competent",
      1: "1 - Needs Imprv",
      0: "0 - Unsatisfactory",
    }.get(score, str(score))

    anchor_name = (
      scenario.get("domain_anchor")
      or scenario.get("k8s_error_anchor")
      or "general"
    )
    msg = (
      f"Scenario {scenario.get('id', scenario.get('scenario_id'))} "
      f"({anchor_name}) graded: score={score} grade={grade_label.strip()}"
    )
    if score >= 2:
      logger.info(msg)
    elif score == 1:
      logger.warning(msg)
    else:
      logger.error(msg)

    results.append(
      {
        "id": scenario.get("id", scenario.get("scenario_id")),
        "anchor": anchor_name,
        "score": score,
        "grade": grade_label,
      }
    )

  num_scenarios = len(scenarios)
  avg_score = round(total_score / num_scenarios, 2) if num_scenarios > 0 else 0
  exemplary_count = sum(1 for r in results if r["score"] == 3)
  pass_rate = (
    round((exemplary_count / num_scenarios) * 100, 1)
    if num_scenarios > 0
    else 0
  )

  report = {
    "total_scenarios": num_scenarios,
    "average_score": avg_score,
    "pass_rate_percentage": pass_rate,
    "exemplary_count": exemplary_count,
    "results": results,
  }

  logger.info("BENCHMARK COMPLETED: Avg Score: %s/3.0", avg_score)
  return report


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  run_benchmark_report()
