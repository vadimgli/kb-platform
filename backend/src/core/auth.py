"""Argolis IAP authentication dependency for operator identity capture."""

from __future__ import annotations

from fastapi import Header, Request
from google.auth import jwt as google_jwt

from src.core.logging_config import get_logger

logger = get_logger("artifactforge.auth")
IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"


def get_authenticated_user_id(
  request: Request,
  x_goog_iap_jwt_assertion: str | None = Header(
    None, alias="X-Goog-IAP-JWT-Assertion"
  ),
  x_goog_authenticated_user_email: str | None = Header(
    None, alias="X-Goog-Authenticated-User-Email"
  ),
) -> str | None:
  """Extracts and verifies operator identity from Google Cloud IAP headers.

  In Google Cloud IAP environments, Google cryptographically signs the
  'X-Goog-IAP-JWT-Assertion' header. If present, this token is verified
  against Google's public JWK certificates. In local development or mock test
  environments, falls back to 'X-Goog-Authenticated-User-Email' or the request
  body state.

  Args:
    request: Incoming FastAPI request instance.
    x_goog_iap_jwt_assertion: Cryptographically signed JWT token from IAP.
    x_goog_authenticated_user_email: Plain-text identity header from IAP.

  Returns:
    Verified operator email string (e.g., 'vadimg@altostrat.com') or None.
  """
  # 1. Primary path: Verify cryptographic IAP JWT Assertion
  if x_goog_iap_jwt_assertion:
    try:
      decoded_claims = google_jwt.decode(
        x_goog_iap_jwt_assertion,
        certs_url=IAP_CERTS_URL,
      )
      email = decoded_claims.get("email")
      if email:
        cleaned_email = email.strip().lower()
        logger.info("Cryptographically verified IAP JWT: %s", cleaned_email)
        return cleaned_email
    except Exception as exc:
      logger.warning(
        "IAP JWT signature verification failed: %s; checking fallback header",
        exc,
      )

  # 2. Secondary path: Parse verified IAP email header
  if x_goog_authenticated_user_email:
    email = x_goog_authenticated_user_email.split(":")[-1].strip().lower()
    logger.info("Verified IAP operator identity header: %s", email)
    return email

  # 3. Local/Dev fallback: Request state user_id
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
