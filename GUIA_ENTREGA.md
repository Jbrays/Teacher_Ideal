# Guía de entrega y despliegue

Documento para que la persona o equipo que reciba este proyecto pueda ponerlo en producción sin tener que adivinar la configuración.

> **Resumen:** la primera vez hay que crear a mano los recursos de GCP y GitHub. A partir de ese momento, cada `git push` a `main` despliega automáticamente backend y frontend.

---

## 1. Requisitos previos

- Cuenta de Google Cloud con un proyecto creado.
- Cuenta de GitHub con permisos de administrador sobre el repositorio.
- CLIs instaladas localmente:
  - `gcloud` (Google Cloud SDK)
  - `gh` (GitHub CLI)
  - `firebase` (Firebase CLI) — solo si se va a configurar Hosting manualmente.
- Tener acceso de **Owner** o **Editor** en el proyecto de GCP.

---

## 2. Variables que debes personalizar

Antes de ejecutar comandos, define estos valores:

| Variable | Valor sugerido / actual | Descripción |
|---|---|---|
| `PROJECT_ID` | `semilleros-493300` | ID del proyecto de GCP. |
| `PROJECT_NUMBER` | `121734839794` | Número del proyecto de GCP. |
| `REGION` | `us-central1` | Región de Cloud Run y Artifact Registry. |
| `SERVICE_NAME` | `vektora` | Nombre del servicio en Cloud Run. |
| `AR_REPO` | `teacher-ideal` | Nombre del repositorio en Artifact Registry. |
| `GITHUB_OWNER` | `Jbrays` | Dueño del repo en GitHub. |
| `GITHUB_REPO` | `Teacher_Ideal` | Nombre del repo en GitHub. |
| `ADMIN_EMAIL` | `jsantillana3@upao.edu.pe` | Email con permiso de admin en `/api/admin/*`. |

---

## 3. Configurar GCP

### 3.1 Iniciar sesión y seleccionar proyecto

```bash
gcloud auth login
gcloud config set project ${PROJECT_ID}
```

### 3.2 Habilitar APIs necesarias

```bash
gcloud services enable run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  firebase.googleapis.com \
  firebasehosting.googleapis.com
```

### 3.3 Crear repositorio en Artifact Registry

```bash
gcloud artifacts repositories create ${AR_REPO} \
  --repository-format=docker \
  --location=${REGION} \
  --description="Imágenes Docker del backend"
```

### 3.4 Crear secretos en Secret Manager

Necesitas dos secretos. Los valores deben ser los correctos para tu entorno.

```bash
# DATABASE_URL: URL completa de PostgreSQL (incluyendo sslmode y channel_binding)
echo -n "postgresql://..." | gcloud secrets create database-url --data-file=-

# FIREBASE_CREDENTIALS_JSON: contenido del JSON de la service account de Firebase
gcloud secrets create firebase-credentials-json --data-file=./firebase-credentials.json
```

> **Importante:** no subas nunca esos valores al repositorio. `cloudbuild.yaml` solo referencia los secretos por nombre.

### 3.5 Asignar permisos IAM

```bash
# Cloud Build necesita subir imágenes, leer secrets y deployar Cloud Run
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Cloud Run necesita leer los secrets en runtime
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 3.6 No crear el servicio de Cloud Run manualmente

**No ejecutes `gcloud run deploy` para crear `vektora`.** El servicio se creará automáticamente con la configuración correcta durante el primer `git push`, gracias a `cloudbuild.yaml`.

Crearlo a mano antes de tiempo solo dejaría un "cascarón" con una imagen anterior, lo cual no es deseable cuando se entrega el proyecto.

> El `cloudbuild.yaml` incluye un paso adicional para conceder acceso público (`allUsers` como `roles/run.invoker`), porque `--allow-unauthenticated` no siempre aplica la política IAM de forma confiable durante el deploy.

---

## 4. Configurar Cloud Build

### 4.1 Conectar el repositorio de GitHub

Ve a la consola de GCP:

```
Cloud Build > Triggers > Connect repository
```

Selecciona GitHub, autoriza la aplicación y elige el repositorio.

### 4.2 Crear el trigger

Una vez conectado el repo, crea un trigger con estas características:

- **Name:** `deploy-${SERVICE_NAME}`
- **Event:** Push to a branch
- **Branch:** `^main$`
- **Configuration:** Cloud Build configuration file (`cloudbuild.yaml`)
- **Location:** Repository root

Si ya existe un trigger anterior, puedes actualizarlo para que apunte al `cloudbuild.yaml` actual.

---

## 5. Configurar GitHub

### 5.1 Instalar los secrets del frontend

Inicia sesión con `gh` y ejecuta:

```bash
gh auth login
gh secret set VITE_FIREBASE_API_KEY --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_API_KEY"
gh secret set VITE_FIREBASE_AUTH_DOMAIN --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_PROJECT_ID.firebaseapp.com"
gh secret set VITE_FIREBASE_PROJECT_ID --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_PROJECT_ID"
gh secret set VITE_FIREBASE_STORAGE_BUCKET --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_PROJECT_ID.firebasestorage.app"
gh secret set VITE_FIREBASE_MESSAGING_SENDER_ID --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_SENDER_ID"
gh secret set VITE_FIREBASE_APP_ID --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "TU_APP_ID"
```

> `VITE_API_BASE_URL` se configura **después del primer deploy**, una vez que sepas la URL real de Cloud Run.

### 5.2 Configurar el secret de Firebase Hosting

El workflow usa `FirebaseExtended/action-hosting-deploy`, que requiere una service account con permisos de Firebase Hosting Admin.

```bash
# 1. Asignar permiso a la service account existente de Firebase
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:firebase-adminsdk-fbsvc@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/firebasehosting.admin"

# 2. Crear clave JSON
gcloud iam service-accounts keys create firebase-sa-key.json \
  --iam-account=firebase-adminsdk-fbsvc@${PROJECT_ID}.iam.gserviceaccount.com

# 3. Subir a GitHub secrets
gh secret set FIREBASE_SERVICE_ACCOUNT --repo ${GITHUB_OWNER}/${GITHUB_REPO} < firebase-sa-key.json

# 4. Eliminar el archivo local inmediatamente
rm firebase-sa-key.json
```

---

## 6. Primer deploy

Una vez todo configurado:

```bash
git add .
git commit -m "Configuración de despliegue automático"
git push origin main
```

Verifica:

1. En **Cloud Build** que el build del backend termine sin errores.
2. En **Cloud Run** que el servicio `${SERVICE_NAME}` tenga una nueva revisión.
3. En **GitHub Actions** que el workflow de frontend termine correctamente.
4. En **Firebase Hosting** que el sitio se haya actualizado.

---

## 7. Post-deploy

### 7.1 Actualizar la URL del backend

Después del primer `git push`, obtén la URL real del servicio:

```bash
gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)'
```

Actualiza el secret `VITE_API_BASE_URL` en GitHub:

```bash
gh secret set VITE_API_BASE_URL --repo ${GITHUB_OWNER}/${GITHUB_REPO} --body "URL_OBTENIDA"
```

Luego haz un pequeño cambio en el frontend (por ejemplo, un espacio en cualquier archivo de `frontend_taller/src`) y haz `git push` para redeployar el frontend con la URL correcta.

### 7.2 Eliminar el servicio antiguo (si aplica)

Si antes existía un servicio llamado `teacher-ideal` u otro nombre, y ya confirmaste que `vektora` funciona:

```bash
gcloud run services delete teacher-ideal --region=${REGION}
```

### 7.3 Reprocesar datos

Si la base de datos fue truncada o es nueva, entra a la aplicación y vuelve a vincular las carpetas de Google Drive (CVs, sílabos y horarios) para que el backend regenere los embeddings.

---

## 8. Troubleshooting rápido

| Síntoma | Posible causa | Solución |
|---|---|---|
| Cloud Build falla al hacer push | Falta permiso `artifactregistry.writer` o `run.admin` | Revisar sección 3.5 |
| Cloud Run no lee los secrets | Falta `secretmanager.secretAccessor` para la compute SA | Revisar sección 3.5 |
| Frontend no conecta con backend | `VITE_API_BASE_URL` incorrecta | Actualizar el secret y redeployar frontend |
| Firebase Hosting deploy falla | `FIREBASE_SERVICE_ACCOUNT` mal formada o sin permisos | Revisar sección 5.2 |

---

## 9. Checklist final

- [ ] Proyecto de GCP creado y APIs habilitadas.
- [ ] Artifact Registry creado.
- [ ] Secrets `database-url` y `firebase-credentials-json` creados.
- [ ] Permisos IAM asignados a Cloud Build y Cloud Run.
- [ ] Trigger de Cloud Build conectado a GitHub y apuntando a `cloudbuild.yaml`.
- [ ] Secrets de GitHub configurados.
- [ ] Service account de Firebase con rol Hosting Admin y clave en `FIREBASE_SERVICE_ACCOUNT`.
- [ ] Primer `git push` exitoso (crea el servicio `vektora`).
- [ ] URL del backend obtenida y actualizada en `VITE_API_BASE_URL`.
- [ ] Segundo push mínimo en frontend para aplicar la URL correcta.
