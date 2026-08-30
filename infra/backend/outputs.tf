output "backend_url" {
  description = "Cloud Run backend service URL"
  value       = google_cloud_run_service.artifactforge_api.status[0].url
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository ID"
  value       = google_artifact_registry_repository.artifactforge_repo.id
}

output "docs_bucket_name" {
  description = "GCS bucket storing discovery documentation corpus"
  value       = google_storage_bucket.docs_corpus.name
}

output "telemetry_dataset_id" {
  description = "BigQuery dataset ID for query telemetry metrics"
  value       = google_bigquery_dataset.telemetry_dataset.dataset_id
}

output "runtime_service_account_email" {
  description = "Runtime service account email used by Cloud Run"
  value       = google_service_account.runtime_sa.email
}
