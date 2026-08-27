"""Custom exception hierarchy for ArtifactForge."""


class CopilotError(Exception):
  """Base exception class for all ArtifactForge errors."""

  def __init__(self, message: str, details: dict | None = None) -> None:
    """Initializes CopilotError with message and optional details context.

    Args:
      message: Human-readable error description.
      details: Optional dictionary containing error metadata.
    """
    super().__init__(message)
    self.message = message
    self.details = details or {}


class RAGRetrievalError(CopilotError):
  """Raised when Vertex AI Search RAG retrieval fails."""


class PlannerExecutionError(CopilotError):
  """Raised when PlannerAgent fails to generate a strategy."""


class ExecutorExecutionError(CopilotError):
  """Raised when ExecutorAgent fails to generate valid structured actions."""


class GuardrailValidationError(CopilotError):
  """Raised when guardrail validation fails or violates safety contracts."""
