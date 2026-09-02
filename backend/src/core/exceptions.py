"""Custom typed exception hierarchy for ArtifactForge."""

from __future__ import annotations
from typing import Any


class CopilotError(Exception):
  """Base exception class for all ArtifactForge errors."""

  def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
    """Initializes CopilotError with message and optional details context.

    Args:
      message: Human-readable error description.
      details: Optional dictionary containing error metadata.
    """
    super().__init__(message)
    self.message = message
    self.details = details or {}


# Configuration Errors
class ConfigurationError(CopilotError):
  """Raised when required configuration or prompt files are missing or invalid."""


# Google Drive & MCP Errors
class GoogleDriveError(CopilotError):
  """Base exception for Google Drive & Docs MCP provider errors."""


class DriveFolderNotFoundError(GoogleDriveError):
  """Raised when the authorized Google Drive folder cannot be found or accessed."""


class DriveFileNotFoundError(GoogleDriveError):
  """Raised when a specific document is missing in the authorized folder."""


class DrivePermissionDeniedError(GoogleDriveError):
  """Raised when caller or service account lacks Drive API permissions."""


class DriveUnauthorizedFolderError(GoogleDriveError):
  """Raised when an attempt is made to access a folder outside the authorized sandbox."""


class DriveExportError(GoogleDriveError):
  """Raised when exporting a scoping matrix to Google Docs fails."""


# Discovery Engine & RAG Errors
class RAGRetrievalError(CopilotError):
  """Raised when Vertex AI Search / Discovery Engine retrieval fails."""


class DataStoreNotFoundError(RAGRetrievalError):
  """Raised when the requested Discovery Engine data store does not exist."""


class DataStoreQueryError(RAGRetrievalError):
  """Raised when querying the Discovery Engine search API fails."""


# Multi-Tenancy & Zero-Leakage Errors
class TenantSecurityError(CopilotError):
  """Raised when multi-tenant boundary checks fail."""


class ZeroLeakageViolationError(TenantSecurityError):
  """Raised when AST analysis detects cross-tenant data leakage."""


# Agent & Execution Errors
class PlannerExecutionError(CopilotError):
  """Raised when PlannerAgent fails to generate a valid strategy or matrix."""


class ExecutorExecutionError(CopilotError):
  """Raised when ExecutorAgent fails to generate valid structured actions."""


class SpecialistExecutionError(CopilotError):
  """Raised when a specialist sub-agent fails during turn execution."""


class TriageRoutingError(CopilotError):
  """Raised when triage routing fails to resolve an appropriate agent."""


class A2AProtocolError(CopilotError):
  """Raised when incoming A2A payloads or protocol handshakes fail validation."""


class GuardrailValidationError(CopilotError):
  """Raised when guardrail validation fails or violates safety contracts."""
