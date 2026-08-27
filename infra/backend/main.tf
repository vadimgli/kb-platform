provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {}

resource "google_storage_bucket" "docs_corpus" {
  name                        = "${var.project_id}-docs-corpus"
  location                    = "US"
  force_destroy               = false
  uniform_bucket_level_access = true
}

resource "google_bigquery_dataset" "telemetry_dataset" {
  dataset_id                  = "k8s_copilot_telemetry"
  friendly_name               = "Kubernetes Troubleshooting Copilot Telemetry"
  description                 = "Telemetry data sink for evaluation metrics and operator feedback"
  location                    = "US"
  default_table_expiration_ms = 31536000000
}

resource "google_bigquery_table" "query_metrics" {
  dataset_id = google_bigquery_dataset.telemetry_dataset.dataset_id
  table_id   = "query_metrics"

  schema = jsonencode([
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "session_id", type = "STRING", mode = "REQUIRED" },
    { name = "query", type = "STRING", mode = "NULLABLE" },
    { name = "latency_ms", type = "INT64", mode = "NULLABLE" },
    { name = "high_risk_flagged", type = "BOOLEAN", mode = "NULLABLE" },
    { name = "user_rating", type = "INT64", mode = "NULLABLE" }
  ])
}

resource "google_service_account" "runtime_sa" {
  account_id   = "k8s-copilot-sa"
  display_name = "Kubernetes Troubleshooting Copilot Runtime Service Account"
}

resource "google_project_iam_member" "aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime_sa.email}"
}

resource "google_project_iam_member" "discoveryengine_viewer" {
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
  member  = "serviceAccount:${google_service_account.runtime_sa.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.runtime_sa.email}"
}

resource "google_cloud_run_service" "copilot_backend" {
  name     = "k8s-troubleshooting-copilot"
  location = var.region

  template {
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale"  = "2"
        "autoscaling.knative.dev/maxScale"  = "10"
        "run.googleapis.com/cpu-throttling" = "false"
      }
    }

    spec {
      service_account_name = google_service_account.runtime_sa.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/copilot/backend:${var.image_tag}"

        ports {
          container_port = 8000
        }

        resources {
          limits = {
            cpu    = "4000m"
            memory = "4Gi"
          }
        }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_LOCATION"
        value = "global"
      }
      env {
        name  = "DATA_STORE_ID"
        value = "k8s-docs-corpus-dev"
      }
      env {
        name  = "DEFAULT_MODEL_NAME"
        value = "gemini-3.5-flash"
      }
      env {
        name  = "LIGHTWEIGHT_MODEL_NAME"
        value = "gemini-3.5-flash-lite"
      }
      env {
        name  = "EXECUTOR_MODEL_NAME"
        value = "gemini-3.5-flash-lite"
      }
      env {
        name  = "PLANNER_MODEL_NAME"
        value = "gemini-3.5-flash"
      }
      env {
        name  = "DEFAULT_K8S_DOCS_URL"
        value = "https://kubernetes.io/docs/"
      }
      env {
        name  = "DEFAULT_DOC_TITLE"
        value = "Kubernetes Documentation"
      }
      env {
        name  = "CORS_ALLOWED_ORIGINS"
        value = "http://localhost:5173,http://localhost:3000,*"
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
}

resource "google_cloud_run_service_iam_member" "ci_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloud_run_service.copilot_backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_cloud_run_service_iam_member" "cloudbuild_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloud_run_service.copilot_backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

resource "google_cloud_run_service_iam_member" "sa_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloud_run_service.copilot_backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime_sa.email}"
}
