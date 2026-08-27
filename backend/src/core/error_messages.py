"""Central Error Messages and Templates for ArtifactForge."""


class ErrorMessages:
  """Centralized error message templates."""

  ERR_PROMPT_FILE_MISSING = "Agent prompt YAML file not found at: {path}"
  ERR_PROMPT_KEY_MISSING = "Missing 'system_instruction' key in YAML at: {path}"
  ERR_CONFIG_MISSING_VARS = "Missing required environment variables: {missing}"
  ERR_MISSING_CONFIG_VARS = "Missing required environment variables: {vars}"
  ERR_RAG_EMPTY_CORPUS = (
    "No documents found in DataStore '{data_store_id}' for query: '{query}'"
  )
  ERR_RAG_UNEXPECTED_FAILURE = (
    "Vertex AI Search failed on DataStore '{data_store_id}': {error}"
  )
  ERR_GUARDRAIL_VIOLATION = "Guardrail violation: {reason}"
  ERR_TENANT_MISMATCH = (
    "Tenant '{requested}' does not match active security context '{active}'"
  )
