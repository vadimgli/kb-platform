"""Structured JSON logging for Cloud Logging and OpenTelemetry."""

import json
import logging
import sys
import traceback
from typing import Any

try:
  from opentelemetry import trace
except ImportError:
  trace = None  # type: ignore[assignment]


class StructuredJSONFormatter(logging.Formatter):
  """JSON formatter for GCP Cloud Logging compatibility."""

  def format(self, record: logging.LogRecord) -> str:
    """Formats log record into a structured JSON string.

    Args:
      record: The logging LogRecord instance.

    Returns:
      JSON formatted log record string.
    """
    log_entry: dict[str, Any] = {
      "timestamp": self.formatTime(record, self.datefmt),
      "severity": record.levelname,
      "logger": record.name,
      "message": record.getMessage(),
      "module": record.module,
      "function": record.funcName,
      "line": record.lineno,
    }

    try:
      if trace:
        current_span = trace.get_current_span()
        if current_span and hasattr(current_span, "get_span_context"):
          span_ctx = current_span.get_span_context()
          if span_ctx and span_ctx.is_valid:
            trace_id_str = trace.format_trace_id(span_ctx.trace_id)
            log_entry["logging.googleapis.com/trace"] = (
              f"projects/unknown/traces/{trace_id_str}"
            )
            log_entry["logging.googleapis.com/spanId"] = (
              trace.format_span_id(span_ctx.span_id)
            )
            log_entry["logging.googleapis.com/trace_sampled"] = (
              span_ctx.trace_flags.sampled
            )
    except Exception:
      pass

    if record.exc_info:
      log_entry["exception"] = "".join(
        traceback.format_exception(*record.exc_info)
      )

    return json.dumps(log_entry)


def setup_logging(level: int = logging.INFO) -> None:
  """Configures root logger with StructuredJSONFormatter on stdout."""
  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(StructuredJSONFormatter())
  root_logger = logging.getLogger()
  root_logger.setLevel(level)
  root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
  """Returns a configured logger instance."""
  return logging.getLogger(name)
