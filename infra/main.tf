terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  description = "Target Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "Deployment region for Cloud Run"
  type        = string
  default     = "us-central1"
}

variable "container_image" {
  description = "Artifact Registry image URI for the ADK agent service"
  type        = string
}

resource "google_project_service" "required_apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_service_account" "agent_runtime_sa" {
  project      = var.project_id
  account_id   = "consulting-copilot-sa"
  display_name = "Enterprise Consulting Co-Pilot Least-Privilege Runtime SA"
}

resource "google_project_iam_member" "agent_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.agent_runtime_sa.email}"
}

resource "google_cloud_run_v2_service" "consulting_copilot" {
  name     = "enterprise-consulting-copilot"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.agent_runtime_sa.email
    containers {
      image = var.container_image
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = "global"
      }
      env {
        name  = "OTEL_EXPORTER_GCP_TRACE"
        value = "TRUE"
      }
    }
  }
  depends_on = [google_project_service.required_apis]
}
