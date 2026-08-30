variable "project_id" {
  description = "Google Cloud Project ID for deployment"
  type        = string
  default     = "kb-agent-fsi-vadimg"
}

variable "region" {
  description = "Google Cloud Region"
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Container image tag (e.g. git commit SHA or latest)"
  type        = string
  default     = "latest"
}

variable "data_store_id" {
  description = "Vertex AI Search Datastore ID for document grounding"
  type        = string
  default     = "kb-datastore-dev"
}

variable "enable_dlp_redaction" {
  description = "Flag enabling Cloud DLP PII & credential redaction"
  type        = bool
  default     = true
}

variable "internal_user_domain" {
  description = "Internal Google Workspace domain authorized for IAP SSO access"
  type        = string
  default     = "altostrat.com"
}

variable "iap_oauth_client_id" {
  description = "OAuth 2.0 Client ID for Identity-Aware Proxy"
  type        = string
  default     = ""
}

variable "iap_oauth_client_secret" {
  description = "OAuth 2.0 Client Secret for Identity-Aware Proxy"
  type        = string
  default     = ""
  sensitive   = true
}
