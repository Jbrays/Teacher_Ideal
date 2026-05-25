# Flujo Core del Sistema: Sistema Inteligente de Asignación Docente

Este documento describe el flujo principal de ejecución del sistema, explicando el viaje de la información desde que interactúa con la plataforma hasta que se generan las recomendaciones finales.

## 1. ¿Cómo se procesan los documentos?

El procesamiento de documentos es **asíncrono y dirigido por eventos (Event-Driven)**:

1. **Ingesta (Google Drive):** El administrador o usuario sube documentos (CVs en PDF, Sílabos en DOCX u Horarios Históricos en PDF) a una carpeta configurada en Google Drive.
2. **Webhook:** Google Drive envía una notificación (POST) al endpoint `/api/webhooks/drive` de FastAPI informando que un archivo fue creado o modificado.
3. **Delegación a Hilo Secundario:** El backend registra el evento en la BD (`WebhookLog`) e inmediatamente devuelve una respuesta `200 OK` a Google, encolando el procesamiento real mediante `BackgroundTasks` para evitar saturación (timeouts).
4. **Descarga Segura:** En el hilo secundario (procesador central asíncrono), se descarga el archivo usando un candado (`threading.Lock()`) para evitar problemas de concurrencia al leer de Drive.
5. **Enrutamiento:** Dependiendo del formato y de la carpeta/tipo de documento inferido, se envía al `pdf_processor` (para docentes), `docx_processor` (para cursos) o `schedule_processor` (para horarios).

## 2. ¿Cuándo interviene el LLM?

El LLM (**Gemini 3.1 Flash Lite** de Vertex AI) interviene en la etapa inicial de **Extracción de Entidades y Normalización**, justo después de que se descarga o lee el documento crudo:

- **En CVs de Docentes (`pdf_processor.py`):** Se le envía el PDF (como archivo multimodal) con un prompt estricto. El LLM extrae el nombre, grado académico, crea un `perfil_sintetico` (resumen denso de habilidades) y extrae `entidades_clave` (lista de tecnologías y competencias).
- **En Sílabos (`docx_processor.py`):** Se extrae el texto usando `python-docx` y se envía al LLM para que entienda la estructura de la UPAO. Devuelve código, nombre, resumen para la suma, entidades y otro `perfil_sintetico`.
- **En Horarios (`schedule_processor.py`):** El PDF es largo, por lo que se extrae el texto y se agrupa por lotes de 5 páginas (Batching). Se envía cada lote al LLM para que analice la tabla desestructurada y extraiga pares estrictos de `[Código de Curso, Nombre de Docente]`. Aquí el LLM tiene lógica de reintentos escalonados para no exceder las cuotas de API (`429 Too Many Requests`).

## 3. ¿Qué se almacena y dónde?

El sistema utiliza una arquitectura de **Almacenamiento Híbrido** (SQL + Caché L2 en Sistema de Archivos):

### En la Base de Datos Relacional (SQLite/PostgreSQL)
- **Metadatos y Texto Estructurado:** En las tablas `docentes` y `cursos` se guarda la información normalizada (nombre, código, perfil sintético devuelto por el LLM, json de entidades clave). También guardan un *hash* del texto para control de caché.
- **Relaciones Históricas:** En la tabla `historiales` se guarda el cruce (Docente_ID, Curso_ID, Semestre) y cuántas veces se repite esa asignación (experiencia).
- **Caché y Logs:** Tabla `recomendaciones_cache` para devolver rápidamente resultados sin recalcular todo, y `webhook_logs` para auditar integraciones con Drive.

### En el Sistema de Archivos Local (`backend/data/embeddings/`)
- **Vectores Semánticos (Embeddings L2 Cache):** Cada vez que un texto sintético es codificado por el modelo semántico, el vector matemático (Numpy Array) se serializa usando `pickle` y se guarda en un archivo `.pkl` (ej: `docente_14.pkl`). Esto previene volver a codificar textos que no han cambiado (validado por su *hash*).

## 4. ¿Cómo funciona el motor de recomendación internamente?

El `RecommendationEngine` une la información histórica con la semántica:

1. **Obtención de Embeddings:** Toma el perfil sintético del curso objetivo y los perfiles de *todos* los docentes de la base de datos. Pide al `embeddings_manager` sus representaciones vectoriales. Si el vector no existe o el texto cambió, utiliza el modelo **SBERT (BAAI/bge-m3)** para generarlo al vuelo y guardarlo en el archivo `.pkl`.
2. **Cálculo de Similitud (Fuerza Bruta Vectorial):** Calcula la **Similitud del Coseno** matemática entre el vector del curso y la matriz de todos los vectores de docentes. Esto resulta en el **Score Semántico** (qué tanto sus perfiles teóricos se alinean).
3. **Cálculo de Experiencia (Historial):** Consulta la base de datos para ver cuántas veces cada docente ha enseñado este curso específico. Asigna un **Score Histórico**, normalizando la cantidad enseñada frente a un umbral "Veterano" predefinido (ej: 8 veces enseñado = 100% de Score Histórico).
4. **Agregación Final:** Calcula el **Score Combinado** aplicando una fórmula de pesos: `(Score Histórico * 0.40) + (Score Semántico * 0.60)`.
5. **Generación de Evidencias:** Calcula la intersección simple de `entidades_clave` entre curso y docente para generar una evidencia rápida y legible (ej: "Ambos mencionan Python y SQL").
6. **Ordenamiento:** Ordena todos los candidatos de mayor a menor según el Score Combinado y se queda con los `Top_K`.

## 5. ¿En qué momento y cómo interviene SHAP en el proceso?

SHAP (SHapley Additive exPlanations) interviene en el **paso final de la recomendación**, después de haber seleccionado el `Top_K` pero antes de devolver los resultados al Frontend (y de guardar en caché). Su propósito es darle explicabilidad a un modelo "caja negra".

**¿Cómo lo hace?**
1. **Creación del Dataset en caliente:** Agrupa los Top resultados y forma un dataset *Ad Hoc* donde las columnas (features) son: `score_semantico`, `score_historico` y la `cantidad de entidades que hicieron match`, y la variable objetivo es el `score_combinado`.
2. **Entrenamiento Explícito:** Utiliza un modelo secundario local (`ExplanationModel`, un ensamble de árboles como RandomForest) y lo entrena muy rápido con este mini-dataset para sobreajustarlo a la fórmula matemática actual.
3. **Cálculo de Shapley Values:** Aplica el estimador SHAP al modelo entrenado. Este algoritmo de teoría de juegos desglosa el `score_combinado` final de CADA docente, indicando qué porcentaje matemático exacto fue empujado por su experiencia (historial), cuánto por su perfil semántico y cuánto por los keywords (entidades).

## 6. ¿Qué le llega finalmente al frontend?

Una vez completado el motor (o extraído de la caché), el backend expone un JSON estructurado vía el endpoint REST `/api/recommend/docentes/{curso_id}`. 

Lo que el cliente (Vue/Pinia) recibe es una lista de objetos enriquecidos con:
- **Datos Personales:** `docente_id`, `nombre`, `email`, `grado`.
- **Métricas Clave:** `score_combinado`, `score_historico`, `score_semantico` (escalados de 0 a 100).
- **Justificaciones:** 
  - `evidencias`: Un arreglo con las palabras clave (`entidades_clave`) exactas que se interceptaron.
  - `shap_explanations`: Un diccionario detallando el peso que tuvo cada factor para lograr el score final.
- **Trazabilidad:** Una bandera booleana `from_cache` para saber si este cálculo fue generado al momento o reciclado.
