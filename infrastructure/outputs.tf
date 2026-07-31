output "project_id" {
  value       = var.project_id
  description = "Proyecto GCP."
}

output "region" {
  value       = var.region
  description = "Región."
}

output "service_name" {
  value       = google_cloud_run_v2_service.api_service.name
  description = "Nombre Cloud Run."
}

output "service_url" {
  value       = google_cloud_run_v2_service.api_service.uri
  description = "URL del API (VITE_API_BASE_URL)."
}

output "artifact_registry_repo" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repository_name}"
  description = "Repositorio Docker."
}

output "image_base" {
  value       = local.image_base
  description = "Base de imagen sin tag."
}

output "cloud_run_service_account" {
  value       = google_service_account.cloud_run.email
  description = "SA de runtime."
}

output "cloudsql_connection_name" {
  value       = google_sql_database_instance.main.connection_name
  description = "Connection name Cloud SQL (project:region:instance)."
}

output "database_secret_id" {
  value       = google_secret_manager_secret.database_url.secret_id
  description = "Secret DATABASE_URL."
}

output "firebase_secret_id" {
  value       = google_secret_manager_secret.firebase_credentials.secret_id
  description = "Secret Firebase Admin JSON."
}

output "db_name" {
  value       = var.db_name
  description = "Nombre de la base Postgres."
}

output "db_user" {
  value       = var.db_user
  description = "Usuario Postgres."
}

output "cloudbuild_submit_command" {
  value       = "gcloud builds submit --config=cloudbuild.yaml --project=${var.project_id} --substitutions=_DEPLOY_REGION=${var.region},_AR_REPOSITORY=${var.repository_name},_SERVICE_NAME=${var.service_name}"
  description = "Comando de deploy de la app."
}
