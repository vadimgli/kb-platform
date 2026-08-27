output "backend_url" {
  description = "Cloud Run backend service URL"
  value       = google_cloud_run_service.copilot_backend.status[0].url
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository ID"
  value       = "copilot"
}

output "docs_bucket_name" {
  description = "GCS bucket storing Kubernetes documentation corpus"
  value       = google_storage_bucket.docs_corpus.name
}
