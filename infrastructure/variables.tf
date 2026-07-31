variable "project_id" {
  type        = string
  description = "ID del proyecto GCP (único valor típico al migrar/vender)."
}

variable "region" {
  type        = string
  description = "Región de Artifact Registry, Cloud Run y Cloud SQL."
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  description = "Nombre del servicio Cloud Run."
  default     = "vektora"
}

variable "repository_name" {
  type        = string
  description = "ID del repositorio Docker en Artifact Registry."
  default     = "teacher-ideal"
}

variable "db_secret_name" {
  type        = string
  description = "Secret Manager: DATABASE_URL."
  default     = "database-url"
}

variable "firebase_secret_name" {
  type        = string
  description = "Secret Manager: JSON Firebase Admin / SA."
  default     = "firebase-credentials-json"
}

variable "db_instance_name" {
  type        = string
  description = "Nombre de la instancia Cloud SQL."
  default     = "vektora-db"
}

variable "db_name" {
  type        = string
  description = "Nombre de la base de datos Postgres."
  default     = "vektora"
}

variable "db_user" {
  type        = string
  description = "Usuario de la base de datos."
  default     = "vektora"
}

variable "db_tier" {
  type        = string
  description = "Tier Cloud SQL. Free trial: db-f1-micro."
  default     = "db-f1-micro"
}

variable "db_disk_size_gb" {
  type        = number
  description = "Disco SSD Cloud SQL (GB)."
  default     = 10
}

variable "cloud_run_cpu" {
  type        = string
  description = "CPU del contenedor Cloud Run."
  default     = "2"
}

variable "cloud_run_memory" {
  type        = string
  description = "Memoria del contenedor Cloud Run."
  default     = "8Gi"
}

variable "cloud_run_max_instances" {
  type        = number
  description = "Máx. instancias. Free trial: 1–5."
  default     = 2
}

variable "cloud_run_min_instances" {
  type        = number
  description = "Mín. instancias (0 = scale to zero)."
  default     = 0
}

variable "cloud_run_concurrency" {
  type        = number
  description = "Concurrencia por instancia."
  default     = 80
}

variable "cloud_run_timeout" {
  type        = string
  description = "Timeout de request Cloud Run."
  default     = "3600s"
}

variable "public_invoker" {
  type        = bool
  description = "API pública (allUsers invoker)."
  default     = true
}

variable "enable_firestore" {
  type        = bool
  description = "Habilitar API Firestore."
  default     = true
}

variable "gemini_model_name" {
  type        = string
  description = "Modelo Gemini (env GEMINI_MODEL_NAME). Debe coincidir con backend/core/config.py."
  # Valor del código de la app (config.py + schedule_service.py), no inventar IDs.
  default     = "gemini-3.1-flash-lite"
}

variable "gemini_location" {
  type        = string
  description = "Location Vertex/Gemini (env GOOGLE_CLOUD_LOCATION). El código default es global."
  default     = "global"
}

variable "cors_origins" {
  type        = string
  description = "Orígenes CORS extra (separados por coma). El frontend Firebase se añade al desplegar."
  default     = ""
}
