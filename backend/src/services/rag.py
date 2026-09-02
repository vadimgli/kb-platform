"""RAG retrieval service using Vertex AI Search & Discovery Engine."""

import logging
from typing import Any

from google.api_core import exceptions as g_exc
from google.api_core import retry as retry_lib
from google.cloud import discoveryengine_v1 as discoveryengine

from src.core.config import config
from src.core.exceptions import RAGRetrievalError

logger = logging.getLogger("artifactforge.rag")


def _should_retry_rag(exc: Exception) -> bool:
  """Predicate for retryable Google API errors in Vertex AI Search."""
  return isinstance(
    exc,
    (
      g_exc.DeadlineExceeded,
      g_exc.ServiceUnavailable,
      g_exc.InternalServerError,
      g_exc.TooManyRequests,
      g_exc.ResourceExhausted,
      g_exc.Aborted,
    ),
  )


class VertexRAGService:
  """Service for retrieving snippets from Vertex AI Search."""

  def __init__(self) -> None:
    """Initializes the Vertex AI Search client."""
    self.project_id = config.gcp_project_id
    self.location = config.gcp_location
    self.data_store_id = config.data_store_id
    self._client: discoveryengine.SearchServiceClient | None = None

  @property
  def client(self) -> discoveryengine.SearchServiceClient:
    """Lazy initialization of the SearchServiceClient."""
    if self._client is None:
      self._client = discoveryengine.SearchServiceClient()
    return self._client

  def search_documentation(
    self, query: str, page_size: int = 3
  ) -> list[dict[str, Any]]:
    """Queries Vertex AI Search for relevant documentation snippets.

    Args:
      query: The scoping query or requirements search string.
      page_size: Maximum number of documentation snippets to return.

    Returns:
      List of dictionary objects containing 'title', 'snippet', 'gcs_uri', and
      'link'.
    """
    logger.info(
      "Querying Vertex AI Search DataStore '%s' for: '%s'",
      self.data_store_id,
      query,
    )

    try:
      serving_config = self.client.serving_config_path(
        project=self.project_id,
        location=self.location,
        data_store=self.data_store_id,
        serving_config="default_config",
      )

      snippet_spec = (
        discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
          max_snippet_count=1,
          return_snippet=True,
        )
      )
      summary_spec = (
        discoveryengine.SearchRequest.ContentSearchSpec.SummarySpec(
          summary_result_count=page_size,
          include_citations=True,
        )
      )

      request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=page_size,
        content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
          snippet_spec=snippet_spec,
          summary_spec=summary_spec,
        ),
      )

      response = self.client.search(
        request=request,
        timeout=2.0,
        retry=retry_lib.Retry(predicate=_should_retry_rag, deadline=2.0),
      )

      results: list[dict[str, Any]] = []
      for result in response.results:
        doc = result.document
        title = (
          doc.struct_data.get("title")
          if hasattr(doc, "struct_data") and doc.struct_data
          else "GCP Documentation"
        )
        snippet = ""
        if hasattr(doc, "derived_struct_data") and doc.derived_struct_data:
          snippets = doc.derived_struct_data.get("snippets", [])
          if snippets:
            snippet = snippets[0].get("snippet", "")

        gcs_uri = (
          doc.struct_data.get("gcs_uri")
          if hasattr(doc, "struct_data") and doc.struct_data
          else ""
        )
        link = (
          doc.struct_data.get("link")
          if hasattr(doc, "struct_data") and doc.struct_data
          else config.default_k8s_docs_url
        )

        results.append(
          {
            "title": title or config.default_doc_title,
            "snippet": snippet or "Relevant GCP documentation snippet.",
            "gcs_uri": gcs_uri,
            "link": link or config.default_k8s_docs_url,
          }
        )

      return results

    except Exception as err:
      logger.error("Vertex AI Search query failure on DataStore '%s': %s", self.data_store_id, err)
      raise RAGRetrievalError(
        ErrorMessages.ERR_RAG_UNEXPECTED_FAILURE.format(
          data_store_id=self.data_store_id,
          error=str(err),
        ),
        details={"data_store_id": self.data_store_id, "query": query, "error": str(err)},
      ) from err

  # Backward compatibility alias
  search_k8s_documentation = search_documentation


rag_service = VertexRAGService()
