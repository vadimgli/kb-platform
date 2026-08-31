provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

# 1. Enable Core Google Cloud APIs
locals {
  services_to_enable = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "firestore.googleapis.com",
    "bigquery.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "iap.googleapis.com",
    "compute.googleapis.com"
  ]
}

resource "google_project_service" "enabled_services" {
  for_each           = toset(locals.services_to_enable)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# 2. Artifact Registry Repository
resource "google_artifact_registry_repository" "artifactforge_repo" {
  provider      = google
  project       = var.project_id
  location      = var.region
  repository_id = "artifactforge-repo"
  description   = "ArtifactForge Multi-Agent Docker Repository"
  format        = "DOCKER"

  depends_on = [google_project_service.enabled_services]
}

# 3. Document Grounding Corpus Cloud Storage Bucket
resource "google_storage_bucket" "docs_corpus" {
  name                        = "${var.project_id}-docs-corpus"
  project                     = var.project_id
  location                    = "US"
  force_destroy               = false
  uniform_bucket_level_access = true

  depends_on = [google_project_service.enabled_services]
}

# 4. BigQuery Telemetry Dataset & Metrics Table
resource "google_bigquery_dataset" "telemetry_dataset" {
  project                     = var.project_id
  dataset_id                  = "telemetry_logs"
  friendly_name               = "ArtifactForge Query & Evaluation Telemetry"
  description                 = "Telemetry data sink for evaluation metrics, latency, and token cost calculation"
  location                    = "US"
  default_table_expiration_ms = 31536000000

  depends_on = [google_project_service.enabled_services]
}

resource "google_bigquery_table" "query_metrics" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.telemetry_dataset.dataset_id
  table_id   = "query_metrics"

  schema = jsonencode([
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "session_id", type = "STRING", mode = "REQUIRED" },
    { name = "client_id", type = "STRING", mode = "NULLABLE" },
    { name = "query", type = "STRING", mode = "NULLABLE" },
    { name = "query_length", type = "INT64", mode = "NULLABLE" },
    { name = "latency_ms", type = "INT64", mode = "NULLABLE" },
    { name = "prompt_tokens", type = "INT64", mode = "NULLABLE" },
    { name = "completion_tokens", type = "INT64", mode = "NULLABLE" },
    { name = "cached_tokens", type = "INT64", mode = "NULLABLE" },
    { name = "estimated_cost_usd", type = "FLOAT64", mode = "NULLABLE" },
    { name = "high_risk_flagged", type = "BOOLEAN", mode = "NULLABLE" },
    { name = "user_rating", type = "INT64", mode = "NULLABLE" },
    { name = "model_version", type = "STRING", mode = "NULLABLE" },
    { name = "prompt_template_version", type = "STRING", mode = "NULLABLE" }
  ])
}

# 5. Secret Manager Configuration
resource "google_secret_manager_secret" "workspace_oauth_secret" {
  project   = var.project_id
  secret_id = "workspace-oauth-client-secret"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled_services]
}

# 6. Runtime Service Account & IAM Role Bindings
resource "google_service_account" "runtime_sa" {
  project      = var.project_id
  account_id   = "artifactforge-sa"
  display_name = "ArtifactForge Runtime Service Account"

  depends_on = [google_project_service.enabled_services]
}

locals {
  runtime_sa_roles = [
    "roles/aiplatform.user",
    "roles/discoveryengine.viewer",
    "roles/datastore.user",
    "roles/bigquery.dataEditor",
    "roles/secretmanager.secretAccessor",
    "roles/dlp.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter"
  ]
}

resource "google_project_iam_member" "runtime_sa_bindings" {
  for_each = toset(locals.runtime_sa_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime_sa.email}"
}

# 7. Cloud Run Serverless Multi-Agent Service (Ingress restricted to Load Balancer)
resource "google_cloud_run_service" "artifactforge_api" {
  name     = "artifactforge-api"
  project  = var.project_id
  location = var.region

  template {
    metadata {
      annotations = {
        "run.googleapis.com/ingress"        = "internal-and-cloud-load-balancing"
        "autoscaling.knative.dev/minScale"  = "1"
        "autoscaling.knative.dev/maxScale"  = "10"
        "run.googleapis.com/cpu-throttling" = "false"
      }
    }

    spec {
      service_account_name = google_service_account.runtime_sa.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.artifactforge_repo.repository_id}/artifactforge-api:${var.image_tag}"

        ports {
          container_port = 8000
        }

        resources {
          limits = {
            cpu    = "2000m"
            memory = "2Gi"
          }
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "GCP_LOCATION"
          value = var.region
        }
        env {
          name  = "DATA_STORE_ID"
          value = var.data_store_id
        }
        env {
          name  = "DEFAULT_MODEL_NAME"
          value = "gemini-2.5-flash"
        }
        env {
          name  = "LIGHTWEIGHT_MODEL_NAME"
          value = "gemini-2.5-flash-lite"
        }
        env {
          name  = "PLANNER_MODEL_NAME"
          value = "gemini-2.5-flash"
        }
        env {
          name  = "EXECUTOR_MODEL_NAME"
          value = "gemini-2.5-flash-lite"
        }
        env {
          name  = "CORS_ALLOWED_ORIGINS"
          value = "http://localhost:5173,http://localhost:3000,https://*.altostrat.com,https://*.run.app"
        }
        env {
          name  = "GCS_CORPUS_BUCKET"
          value = google_storage_bucket.docs_corpus.name
        }

        liveness_probe {
          initial_delay_seconds = 5
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 3
          http_get {
            path = "/healthz"
          }
        }

        startup_probe {
          initial_delay_seconds = 10
          timeout_seconds       = 3
          period_seconds        = 10
          failure_threshold     = 5
          http_get {
            path = "/readyz"
          }
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_project_iam_member.runtime_sa_bindings,
    google_artifact_registry_repository.artifactforge_repo
  ]
}

# 8. Cloud Build and Service Account Ingress IAM
resource "google_cloud_run_service_iam_member" "cloudbuild_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloud_run_service.artifactforge_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

resource "google_cloud_run_service_iam_member" "sa_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloud_run_service.artifactforge_api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime_sa.email}"
}
