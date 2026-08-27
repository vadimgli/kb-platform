variable "project_id" {
  description = "Google Cloud Project ID for staging"
  type        = string
  default     = "fde-k8s-sandbox-dev-vadimg"
}

variable "region" {
  description = "Google Cloud Region"
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Container image tag"
  type        = string
  default     = "latest"
}
