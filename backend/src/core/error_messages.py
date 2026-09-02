"""Central Error Messages and Templates for ArtifactForge."""


class ErrorMessages:
  """Comprehensive centralized error message templates."""

  # Configuration & Environment
  ERR_CONFIG_MISSING_VARS = "Missing required environment variables: {missing}"
  ERR_MISSING_CONFIG_VARS = "Missing required environment variables: {vars}"
  ERR_CONFIG_INVALID = "Invalid configuration value for '{key}': {reason}"
  ERR_PROMPT_FILE_MISSING = "Agent prompt YAML file not found at: {path}"
  ERR_PROMPT_KEY_MISSING = "Missing 'system_instruction' key in YAML at: {path}"

  # Google Drive & Google Docs MCP
  ERR_DRIVE_FOLDER_NOT_FOUND = "Google Drive folder '{folder_id}' not found or inaccessible."
  ERR_DRIVE_FILE_NOT_FOUND = "Google Drive document '{file_id}' was not found in folder '{folder_id}'."
  ERR_DRIVE_PERMISSION_DENIED = "Permission denied accessing Google Drive folder '{folder_id}' for service account: {sa_email}"
  ERR_DRIVE_UNAUTHORIZED_FOLDER = (
    "Security Violation: Access to folder '{requested_folder_id}' is prohibited. "
    "Agent is strictly sandboxed to authorized folder '{allowed_folder_id}'."
  )
  ERR_DRIVE_EXPORT_FAILED = "Failed to export scoping matrix to Google Docs: {reason}"
  ERR_DRIVE_READ_FAILED = "Failed to read content from Google Drive document '{file_id}': {reason}"
  ERR_DRIVE_EMPTY_FOLDER = "The authorized Google Drive folder '{folder_id}' is empty. No SOW or discovery documents found."

  # Discovery Engine & RAG
  ERR_RAG_EMPTY_CORPUS = "No documents found in DataStore '{data_store_id}' for query: '{query}'"
  ERR_RAG_UNEXPECTED_FAILURE = "Vertex AI Search failed on DataStore '{data_store_id}': {error}"
  ERR_DATA_STORE_NOT_FOUND = "Discovery Engine DataStore '{data_store_id}' does not exist in location '{location}'."
  ERR_DATA_STORE_QUERY_FAILED = "Search query against DataStore '{data_store_id}' failed: {reason}"

  # Multi-Tenancy & Zero-Leakage AST
  ERR_TENANT_MISMATCH = "Tenant '{requested}' does not match active security context '{active}'."
  ERR_TENANT_ID_REQUIRED = "Client tenant ID is required for multi-tenant isolation."
  ERR_TENANT_LEAKAGE_DETECTED = (
    "Zero-Leakage Security Violation: Cross-tenant entity '{entity}' detected in response for client '{client_id}'."
  )
  ERR_UNAUTHORIZED_TENANT_ACCESS = (
    "Caller '{caller}' is not authorized to access tenant data for '{target_tenant}'."
  )

  # A2A Protocol
  ERR_A2A_INVALID_PAYLOAD = "Invalid A2A request payload: {reason}"
  ERR_A2A_EXECUTION_FAILED = "A2A task execution failed: {reason}"
  ERR_A2A_METHOD_NOT_SUPPORTED = "A2A method '{method}' is not supported by agent '{agent_name}'."
  ERR_A2A_SCHEMA_VALIDATION_FAILED = "A2A response schema validation failed: {reason}"

  # Agent & Specialist Execution
  ERR_PLANNER_FAILED = "PlannerAgent failed to generate execution plan: {reason}"
  ERR_EXECUTOR_FAILED = "ExecutorAgent failed to synthesize structured actions: {reason}"
  ERR_SPECIALIST_NOT_FOUND = "Specialist sub-agent '{specialist_name}' is not registered."
  ERR_SPECIALIST_EXECUTION_FAILED = "Specialist sub-agent '{specialist_name}' failed turn execution: {reason}"
  ERR_TRIAGE_ROUTING_FAILED = "Triage agent failed to route user intent: {reason}"

  # Guardrails & Model Safety
  ERR_GUARDRAIL_VIOLATION = "Guardrail violation: {reason}"
  ERR_PROMPT_INJECTION_DETECTED = "Prompt injection attempt detected and blocked: {pattern}"
  ERR_PII_LEAKAGE_DETECTED = "Sensitive PII entity '{entity_type}' detected in generation output."
  ERR_VERTEX_GENERATION_FAILED = "Vertex AI model '{model_name}' generation failed: {reason}"
