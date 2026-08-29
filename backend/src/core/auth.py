"""Argolis IAP authentication dependency for operator identity capture."""

from fastapi import Header, Request

from src.core.logging_config import get_logger

logger = get_logger("artifactforge.auth")


def get_authenticated_user_id(
  request: Request,
  x_goog_authenticated_user_email: str | None = Header(
    None, alias="X-Goog-Authenticated-User-Email"
  ),
) -> str | None:
  """Extracts authenticated operator email from Google Cloud IAP header.

  In Argolis Cloud Run deployments behind IAP, headers are formatted as:
  'accounts.google.com:vadimg@altostrat.com'.
  During local development or automated pytest execution, falls back cleanly
  to the request body 'user_id' field.

  Args:
    x_goog_authenticated_user_email: Injected IAP header string.
    request: Incoming FastAPI request instance.

  Returns:
    Cleaned operator email string (e.g., 'vadimg@altostrat.com') or None.
  """
  if x_goog_authenticated_user_email:
    email = x_goog_authenticated_user_email.split(":")[-1].strip().lower()
    logger.info("Verified Argolis IAP operator identity: %s", email)
    return email

  if (
    request
    and hasattr(request, "state")
    and getattr(request.state, "user_id", None)
  ):
    return request.state.user_id

  logger.debug(
    "No IAP identity header detected; operating in unauthenticated mode."
  )
  return None
