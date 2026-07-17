terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Referencia a secretos ya existentes
# Como vimos en cloudbuild.yaml, los secretos se llaman 'database-url' y 'firebase-credentials-json'
data "google_secret_manager_secret" "database_url" {
  secret_id = var.db_secret_name
}

data "google_secret_manager_secret" "firebase_credentials" {
  secret_id = var.firebase_secret_name
}

# 2. Artifact Registry
resource "google_artifact_registry_repository" "docker_repo" {
  repository_id = var.repository_name
  format        = "DOCKER"
  location      = var.region
  description   = "Docker repository para Vektora API"
}

# 3. Servicio de Cloud Run
resource "google_cloud_run_v2_service" "api_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello" # Imagen placeholder, Cloud Build la actualizara

      resources {
        limits = {
          cpu    = "2"
          memory = "8Gi"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      # Conectar Secretos
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "FIREBASE_CREDENTIALS_JSON"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.firebase_credentials.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 5
        tcp_socket {
          port = 8080
        }
      }
    }

    scaling {
      max_instance_count = 20
    }
    
    max_instance_request_concurrency = 80
    timeout                          = "3600s"
  }
  
  # Ignorar la imagen durante la ejecucion de Terraform,
  # porque Cloud Build sera quien empuje el nuevo Docker tag real.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }
}

# 4. Politica IAM (Hacer el backend publico)
resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.api_service.location
  project  = google_cloud_run_v2_service.api_service.project
  service  = google_cloud_run_v2_service.api_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 5. Base de Datos Firestore para notificaciones en tiempo real
resource "google_project_service" "firestore_api" {
  project            = var.project_id
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}
