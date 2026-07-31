# Infraestructura Vektora (IaC)

Todo el backend en GCP se define aquí con **Terraform**.  
La **aplicación** (imagen Docker) se construye y publica con **Cloud Build** (`/cloudbuild.yaml`).

## Idea de portabilidad

| Qué cambia al migrar / vender | Dónde |
|---|---|
| Cuenta Google / billing | `gcloud auth login` + billing del proyecto destino |
| Proyecto GCP | `project_id` en `terraform.tfvars` |
| Región / nombres | variables opcionales en `terraform.tfvars` |
| Secretos (DB, Firebase) | se crean vacíos; los **valores** se cargan a mano en el destino |
| Código de la app | el mismo repo; `gcloud builds submit` |

No hardcodear IDs de proyecto viejos en Terraform ni en `cloudbuild.yaml`.

## Flujo en un proyecto nuevo

```bash
# 0. Cuenta y proyecto destino
gcloud auth login
gcloud config set project TU_PROJECT_ID

# 1. Variables locales (no se commitean)
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# editar project_id=TU_PROJECT_ID

# 2. Crear APIs, Cloud SQL, secrets, Artifact Registry, Cloud Run, IAM
#    (usa token de usuario: export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token))
terraform init
terraform apply

# 3. Firebase Auth / Hosting (una vez por proyecto; ToS de Firebase en consola)
#    https://console.firebase.google.com/ → Add project → usar el mismo project_id
#    Habilitar Google Sign-In; crear app Web; copiar config a frontend .env / GitHub Secrets
#    firebase login   # misma cuenta dueña del proyecto
#    firebase projects:addfirebase TU_PROJECT_ID   # si no se hizo desde consola

# 4. Construir y desplegar la app (imagen Docker + update Cloud Run)
cd ..
gcloud builds submit --config=cloudbuild.yaml --project=TU_PROJECT_ID

# 5. URL del API → VITE_API_BASE_URL del frontend
cd infrastructure && terraform output service_url
```

Parámetros de producto (modelos, tier SQL, max instances, CORS) van en `variables.tf` / `terraform.tfvars`.

## Qué crea Terraform

- APIs necesarias (Run, Build, Artifact Registry, Secret Manager, AI Platform, …)
- Secretos `database-url` y `firebase-credentials-json` (sin versiones)
- Artifact Registry Docker
- Service Account de Cloud Run + permisos (secretos, Vertex, logs)
- Permisos del SA de Cloud Build (deploy, push imágenes)
- Servicio Cloud Run (imagen placeholder hasta el primer build)
- IAM público opcional (`roles/run.invoker` → `allUsers`)

## Qué NO debe ir en el repo

- `terraform.tfvars` (solo el `.example`)
- `terraform.tfstate*` (estado local o remoto privado)
- JSON de Firebase / connection strings

## Frontend

El hosting (Firebase) usa secrets de GitHub Actions; el `projectId` de Firebase debe ser el del comprador/entorno destino (ver workflow).
