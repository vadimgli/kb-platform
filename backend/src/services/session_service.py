"""Firestore session storage service for ArtifactForge multi-turn sessions."""

from collections import OrderedDict
import logging
import time
from typing import Any

try:
  from google.api_core.exceptions import GoogleAPICallError
  from google.auth.exceptions import GoogleAuthError
  from google.cloud import firestore
except ImportError:
  firestore = None
  GoogleAPICallError = Exception
  GoogleAuthError = Exception

from src.core.config import config

logger = logging.getLogger("artifactforge.session_service")


class FirestoreExternalSessionService:
  """Manages multi-turn conversation sessions using Cloud Firestore."""

  def __init__(self, collection_name: str = "artifactforge_sessions") -> None:
    """Initializes Firestore session client."""
    self.collection_name = collection_name
    self.project_id = config.gcp_project_id
    self._client: Any = None
    self._in_memory_store: OrderedDict[str, dict[str, Any]] = OrderedDict()
    self._max_in_memory_sessions = 500

  def _get_client(self) -> Any:
    """Lazy-loads google.cloud.firestore client."""
    if self._client is None:
      if firestore is None:
        logger.info(
          "Firestore library unavailable; using in-memory session store."
        )
        self._client = False
      else:
        try:
          self._client = firestore.Client(project=self.project_id)
        except (GoogleAPICallError, GoogleAuthError, Exception) as err:
          logger.info(
            "Firestore client unavailable (%s); using in-memory session store.",
            err,
          )
          self._client = False
    return self._client if self._client is not False else None

  def _set_in_memory_session(
    self, session_id: str, session_data: dict[str, Any]
  ) -> None:
    """Stores session data in LRU in-memory store."""
    if session_id in self._in_memory_store:
      self._in_memory_store.move_to_end(session_id)
    self._in_memory_store[session_id] = session_data
    if len(self._in_memory_store) > self._max_in_memory_sessions:
      self._in_memory_store.popitem(last=False)

  def get_session(
    self,
    session_id: str,
    user_id: str | None = None,
  ) -> dict[str, Any]:
    """Retrieves session state from Firestore."""
    client = self._get_client()
    if client is None:
      existing = self._in_memory_store.get(session_id)
      if existing:
        self._in_memory_store.move_to_end(session_id)
        return existing
      new_session = {
        "session_id": session_id,
        "user_id": user_id,
        "turns": [],
        "metadata": {},
      }
      self._set_in_memory_session(session_id, new_session)
      return new_session

    try:
      doc_ref = client.collection(self.collection_name).document(session_id)
      doc = doc_ref.get()
      if doc.exists:
        data = doc.to_dict() or {}
        logger.info("Found existing session in Firestore: %s", session_id)
        return data

      new_session = {
        "session_id": session_id,
        "user_id": user_id,
        "turns": [],
        "metadata": {},
      }
      doc_ref.set(new_session)
      logger.info(
        "Initialized new session in Firestore: %s for user: %s",
        session_id,
        user_id,
      )
      return new_session
    except (GoogleAPICallError, GoogleAuthError, Exception) as err:
      logger.warning(
        "Firestore get_session error (%s); falling back to in-memory.", err
      )
      existing = self._in_memory_store.get(session_id)
      if existing:
        self._in_memory_store.move_to_end(session_id)
        return existing
      fallback_session = {
        "session_id": session_id,
        "user_id": user_id,
        "turns": [],
        "metadata": {},
      }
      self._set_in_memory_session(session_id, fallback_session)
      return fallback_session

  def save_session(
    self,
    session_id: str,
    session_data: dict[str, Any],
    user_id: str | None = None,
  ) -> None:
    """Persists updated conversation turn history to Firestore."""
    if user_id and not session_data.get("user_id"):
      session_data["user_id"] = user_id

    client = self._get_client()
    if client is None:
      self._set_in_memory_session(session_id, session_data)
      return

    try:
      doc_ref = client.collection(self.collection_name).document(session_id)
      doc_ref.set(session_data, merge=True)
      logger.info("Persisted turn history to Firestore: %s", session_id)
    except (GoogleAPICallError, GoogleAuthError, Exception) as err:
      logger.warning(
        "Firestore save_session error (%s); updating in-memory store.", err
      )
      self._set_in_memory_session(session_id, session_data)

  def add_turn_to_session(
    self,
    session_id: str,
    turn_data: dict[str, Any],
    user_id: str | None = None,
  ) -> dict[str, Any]:
    """Appends a new turn to a session and updates session metrics."""
    session = self.get_session(session_id=session_id, user_id=user_id)
    turns: list[dict[str, Any]] = session.setdefault("turns", [])
    turns.append(turn_data)

    metadata: dict[str, Any] = session.setdefault("metadata", {})
    now_ts = int(time.time())
    start_ts = metadata.get("created_at_ts", now_ts)
    metadata["created_at_ts"] = start_ts
    metadata["last_updated_ts"] = now_ts
    metadata["session_length_seconds"] = max(0, now_ts - start_ts)
    metadata["turn_count"] = len(turns)

    self.save_session(
      session_id=session_id, session_data=session, user_id=user_id
    )
    return session
