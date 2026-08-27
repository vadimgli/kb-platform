"""Unit tests for domain exceptions and structured JSON logging."""

import json
import logging

from src.core.exceptions import (
  CopilotError,
  ExecutorExecutionError,
  GuardrailValidationError,
  PlannerExecutionError,
  RAGRetrievalError,
)
from src.core.logging_config import StructuredJSONFormatter, get_logger


def test_copilot_exceptions_creation() -> None:
  """Tests instantiation and metadata details for CopilotError hierarchy."""
  err = RAGRetrievalError("RAG query failed", details={"query": "test"})
  assert err.message == "RAG query failed"
  assert err.details == {"query": "test"}
  assert isinstance(err, CopilotError)

  planner_err = PlannerExecutionError("Planning failed")
  assert planner_err.details == {}

  executor_err = ExecutorExecutionError(
    "Executor failed", details={"cmd": "invalid"}
  )
  assert executor_err.details == {"cmd": "invalid"}

  guardrail_err = GuardrailValidationError("Guardrail failed")
  assert guardrail_err.message == "Guardrail failed"


def test_structured_json_formatter() -> None:
  """Tests that log records are formatted as valid JSON with required fields."""
  logger = get_logger("test.copilot")
  formatter = StructuredJSONFormatter()

  record = logging.LogRecord(
    name="test.copilot",
    level=logging.INFO,
    pathname="test.py",
    lineno=10,
    msg="Test incident diagnostic message",
    args=(),
    exc_info=None,
  )

  formatted = formatter.format(record)
  data = json.loads(formatted)

  assert data["severity"] == "INFO"
  assert data["logger"] == "test.copilot"
  assert data["message"] == "Test incident diagnostic message"
  assert "timestamp" in data
