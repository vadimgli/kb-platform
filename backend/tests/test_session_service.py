"""Unit tests for Firestore and in-memory session history storage."""

from unittest.mock import MagicMock, patch

from src.services.session_service import FirestoreExternalSessionService


def test_session_service_in_memory_fallback() -> None:
  """Tests in-memory session CRUD when Firestore is unavailable."""
  service = FirestoreExternalSessionService()

  with patch.object(service, "_get_client", return_value=None):
    session = service.get_session("test-session-1", user_id="test-user")
    assert session["session_id"] == "test-session-1"
    assert session["user_id"] == "test-user"
    assert session["turns"] == []

    turn_data = {
      "query": "CrashLoopBackOff in pod",
      "summary": "Investigate logs",
      "deliverables": None,
      "actions": [],
    }
    updated_session = service.add_turn_to_session(
      session_id="test-session-1",
      turn_data=turn_data,
      user_id="test-user",
    )

    assert len(updated_session["turns"]) == 1
    assert updated_session["metadata"]["turn_count"] == 1

    fetched = service.get_session("test-session-1")
    assert len(fetched["turns"]) == 1


def test_session_service_firestore_new_session_and_error_handling() -> None:
  """Tests new session initialization in Firestore service."""
  service = FirestoreExternalSessionService()
  mock_client = MagicMock()

  mock_doc_not_exists = MagicMock()
  mock_doc_not_exists.exists = False
  mock_client.collection.return_value.document.return_value.get.return_value = (
    mock_doc_not_exists
  )

  with patch.object(service, "_get_client", return_value=mock_client):
    session = service.get_session("new-session-id", user_id="user@google.com")
    assert session["session_id"] == "new-session-id"
    assert session["user_id"] == "user@google.com"
    mock_doc = mock_client.collection.return_value.document.return_value
    mock_doc.set.assert_called_once()

  # Test save_session with active Firestore client
  mock_save_client = MagicMock()
  with patch.object(service, "_get_client", return_value=mock_save_client):
    service.save_session(
      "save-session-id", {"data": 123}, user_id="user@google.com"
    )
    save_doc = mock_save_client.collection.return_value.document.return_value
    save_doc.set.assert_called_once_with(
      {"data": 123, "user_id": "user@google.com"}, merge=True
    )

  # Test Firestore get_session exception fallback
  mock_err_client = MagicMock()
  mock_err_client.collection.side_effect = RuntimeError("Firestore Error")
  with patch.object(service, "_get_client", return_value=mock_err_client):
    fallback_session = service.get_session(
      "err-session-id", user_id="user@google.com"
    )
    assert fallback_session["session_id"] == "err-session-id"
