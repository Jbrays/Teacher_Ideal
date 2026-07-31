# =============================================================================
# Vektora — infraestructura portable (IaC)
# Migrar/vender: cambiar project_id en terraform.tfvars + secretos de negocio
# (Firebase web config del comprador). El resto se recrea con apply + build.
# =============================================================================

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  apis = compact([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "sqladmin.googleapis.com",
    "servicenetworking.googleapis.com",
    "firebase.googleapis.com",
    "identitytoolkit.googleapis.com",
    "drive.googleapis.com", # listar/descargar CVs, sílabos y horarios del usuario
    var.enable_firestore ? "firestore.googleapis.com" : "",
  ])

  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"
  image_base        = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_name}/${var.service_name}"

  cloudsql_connection = google_sql_database_instance.main.connection_name

  # URL para Cloud Run vía socket Unix de Cloud SQL
  database_url = "postgresql://${var.db_user}:${urlencode(random_password.db.result)}@/${var.db_name}?host=/cloudsql/${local.cloudsql_connection}"
}

# -----------------------------------------------------------------------------
# APIs
# -----------------------------------------------------------------------------
resource "google_project_service" "required" {
  for_each = toset(local.apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Artifact Registry
# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "docker_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_name
  format        = "DOCKER"
  description   = "Imágenes Docker de Vektora API"

  depends_on = [google_project_service.required]
}

# -----------------------------------------------------------------------------
# Cloud SQL (Postgres)
# -----------------------------------------------------------------------------
resource "random_password" "db" {
  length  = 24
  special = false
}

resource "google_sql_database_instance" "main" {
  name             = var.db_instance_name
  project          = var.project_id
  region           = var.region
  database_version = "POSTGRES_15"

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_size         = var.db_disk_size_gb
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = true
      # Cloud Run usa el conector Cloud SQL (socket), no IP pública de la app.
    }

    backup_configuration {
      enabled = false
    }
  }

  deletion_protection = false

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "app" {
  name     = var.db_name
  project  = var.project_id
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = var.db_user
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

# -----------------------------------------------------------------------------
# Secrets
# -----------------------------------------------------------------------------
resource "google_secret_manager_secret" "database_url" {
  secret_id = var.db_secret_name
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = local.database_url

  depends_on = [
    google_sql_database.app,
    google_sql_user.app,
  ]
}

resource "google_secret_manager_secret" "firebase_credentials" {
  secret_id = var.firebase_secret_name
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

# -----------------------------------------------------------------------------
# Runtime SA (Cloud Run) + clave para Firebase Admin SDK
# -----------------------------------------------------------------------------
resource "google_service_account" "cloud_run" {
  project      = var.project_id
  account_id   = "${var.service_name}-run"
  display_name = "Vektora Cloud Run runtime"
}

resource "google_service_account_key" "cloud_run" {
  service_account_id = google_service_account.cloud_run.name
}

resource "google_secret_manager_secret_version" "firebase_credentials" {
  secret      = google_secret_manager_secret.firebase_credentials.id
  secret_data = base64decode(google_service_account_key.cloud_run.private_key)
}

resource "google_secret_manager_secret_iam_member" "run_db_secret" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "run_firebase_secret" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.firebase_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "run_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "run_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "run_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "run_firebase_admin" {
  project = var.project_id
  role    = "roles/firebase.admin"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_project_iam_member" "run_datastore_user" {
  count   = var.enable_firestore ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# -----------------------------------------------------------------------------
# Cloud Build SA permissions
# -----------------------------------------------------------------------------
data "google_project" "current" {
  project_id = var.project_id
}

locals {
  cloud_build_sa = "${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

resource "google_project_iam_member" "cloudbuild_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${local.cloud_build_sa}"
}

resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${local.cloud_build_sa}"
}

resource "google_project_iam_member" "cloudbuild_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${local.cloud_build_sa}"
}

resource "google_project_iam_member" "cloudbuild_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.cloud_build_sa}"
}

resource "google_project_iam_member" "cloudbuild_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.cloud_build_sa}"
}

# -----------------------------------------------------------------------------
# Cloud Run
# -----------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "api_service" {
  name     = var.service_name
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    max_instance_request_concurrency = var.cloud_run_concurrency
    timeout                          = var.cloud_run_timeout

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = local.placeholder_image

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }

      ports {
        container_port = 8080
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        # Location de Vertex/Gemini (puede ser "global"; no forzar region de Cloud Run).
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.gemini_location
      }

      env {
        name  = "GEMINI_MODEL_NAME"
        value = var.gemini_model_name
      }

      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "FIREBASE_CREDENTIALS_JSON"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.firebase_credentials.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 240
        period_seconds        = 240
        failure_threshold     = 1
        tcp_socket {
          port = 8080
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.firebase_credentials,
    google_secret_manager_secret_iam_member.run_db_secret,
    google_secret_manager_secret_iam_member.run_firebase_secret,
    google_project_iam_member.run_cloudsql_client,
    google_artifact_registry_repository.docker_repo,
  ]
}

resource "google_cloud_run_service_iam_member" "public_access" {
  count = var.public_invoker ? 1 : 0

  location = google_cloud_run_v2_service.api_service.location
  project  = google_cloud_run_v2_service.api_service.project
  service  = google_cloud_run_v2_service.api_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
