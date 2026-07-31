# Análisis de código sin uso — Teacher_Ideal / Vektora

## Archivos completos que puedes eliminar

### Routers no montados en `main.py`
- `backend/api/routers/admin.py`
- `backend/api/routers/ws.py`

### Scripts huérfanos en `backend/`
- `backend/query_silvia.py`
- `backend/test_schedule_extraction.py`

### Backup
- `backend/taxonomy/taxonomy.json.bak`

### Scripts en `backend/scripts/` (8)
- `backend/scripts/analyze_icsi522.py`
- `backend/scripts/build_taxonomy_embeddings.py`
- `backend/scripts/diagnose_resolver.py`
- `backend/scripts/test_validator_end_to_end.py`
- `backend/scripts/verify_end_to_end.py`
- `backend/scripts/verify_end_to_end_real_cvs.py`
- `backend/scripts/verify_matching.py`
- `backend/scripts/verify_resolver.py`

### Scripts en `scripts/` (4)
- `scripts/procesar_reales_icsi521.py`
- `scripts/procesar_todos_cursos.py`
- `scripts/reset_database.py`
- `scripts/verificar_icsi521.py`

### Archivo completo de clase nunca usada
- `backend/services/node_matching_engine.py` — la clase `NodeMatchingEngine` no se importa en ningún archivo productivo

---

## Imports que puedes eliminar de cada archivo

| Archivo | Línea | Import |
|---|---|---|
| `backend/test_schedule_extraction.py` | 1 | `os` |
| `backend/core/ws_manager.py` | 2 | `Dict` |
| `backend/api/routers/auth.py` | 7 | `get_current_user` |
| `backend/api/routers/docentes.py` | 4 | `Optional` |
| `backend/api/routers/docentes.py` | 8 | `get_current_user_email` |
| `backend/api/routers/drive.py` | 7 | `get_current_user` |
| `backend/api/routers/recommendations.py` | 6 | `Optional` |
| `backend/api/routers/recommendations.py` | 12 | `get_current_user_email` |
| `backend/api/routers/colaboradores.py` | 8 | `get_user_workspaces` |
| `backend/drive/drive_service.py` | 5 | `os` |
| `backend/models/schemas.py` | 1 | `EmailStr` |
| `backend/models/schemas.py` | 4 | `sys` |
| `backend/services/curso_service.py` | 8 | `asyncio` |
| `backend/services/curso_service.py` | 10 | `defaultdict` |
| `backend/services/curso_service.py` | 18 | `settings` |
| `backend/services/curso_service.py` | 19 | `crud` |
| `backend/services/curso_service.py` | 30 | `TaxonomyResolver` |
| `backend/services/docente_service.py` | 8 | `asyncio` |
| `backend/services/docente_service.py` | 18 | `settings` |
| `backend/services/docente_service.py` | 31 | `TaxonomyResolver` |
| `backend/services/schedule_service.py` | 4 | `BytesIO` |
| `backend/services/schedule_service.py` | 21 | `Historial` |
| `backend/services/taxonomy_service.py` | 2 | `json` |
| `backend/services/taxonomy_service.py` | 3 | `List, Dict, Any` |
| `backend/services/explanation_service.py` | 13 | `List` (duplicado) |
| `backend/services/node_matching_engine.py` | 26 | `Curso` |
| `backend/taxonomy/resolver.py` | 5 | `re` |
| `backend/repositories/nodo_repo.py` | 7 | `os` |

---

## Esquemas Pydantic (clases) que puedes eliminar de `backend/models/schemas.py`

- `ErrorResponse` (línea 30)
- `DriveFolder` (línea 35)
- `DriveFile` (línea 41)
- `FolderSelection` (línea 50)
- `FileScanResponse` (línea 55)
- `ProcessingStatus` (línea 61)
- `EvidenciasXAI` (línea 94)
- `DocenteRecommendation` (línea 100)
- `RecommendationResponse` (línea 116)

Los schemas `Docente` y `Curso` se quedan — son usados como type hints aunque no como response_model.

---

## Funciones y métodos que puedes eliminar

| Archivo | Elemento | Línea |
|---|---|---|
| `backend/api/deps.py` | `require_admin` | 36 |
| `backend/services/entity_utils.py` | `limpiar_entidades` | 182 |
| `backend/llm/prompts/explanation.py` | `prompt_explicacion_matches` | 6 |
| `backend/llm/prompts/explanation.py` | `prompt_explicacion_matches_batch` | 75 |
| `backend/core/config.py` | `Settings.cors_origins_list` | 55 |
| `backend/core/config.py` | `Settings.resolve_firebase_credentials` | 60 |
| `backend/auth/firebase.py` | `FirebaseAuth.create_custom_token` | 94 |
| `backend/drive/drive_service.py` | `DriveService.get_file_metadata` | 146 |
| `backend/drive/drive_service.py` | `DriveService.download_file` | 174 |
| `backend/drive/drive_service.py` | `DriveService.search_files` | 205 |
| `backend/llm/client.py` | `GeminiClient.generate_pro_json` | 154 |
| `backend/llm/client.py` | `GeminiClient.generate_text` | 171 |
| `backend/services/taxonomy_embedder.py` | `TaxonomyEmbedder.encode_passage` | 201 |
| `backend/services/taxonomy_embedder.py` | `TaxonomyEmbedder.get_node_vector` | 242 |
| `backend/services/taxonomy_embedder.py` | `PASSAGE_INSTRUCTION` | 42 |
| `backend/services/matching_service.py` | `MatchingService._generate_xai_from_matches` | 236 |
| `backend/domain/filters/syllabus_filter.py` | `SyllabusFilter.filter_text` | 30 |
| `backend/domain/filters/syllabus_filter.py` | `SyllabusFilter.stats` | 49 |
| `backend/domain/weighting/teacher_weight.py` | `UniformTeacherWeightStrategy` | 27 |
| `backend/domain/weighting/course_weight.py` | `FrequencyWeightStrategy` | 42 |
| `backend/core/ws_manager.py` | `ConnectionManager.broadcast` | 23 |

---

## Métodos de repositorio que puedes eliminar

| Archivo | Método | Línea |
|---|---|---|
| `backend/repositories/docente_repo.py` | `save_nodos` | 79 |
| `backend/repositories/docente_repo.py` | `delete` | 92 |
| `backend/repositories/curso_repo.py` | `get_by_ciclo` | 34 |
| `backend/repositories/curso_repo.py` | `get_all_ciclos` | 39 |
| `backend/repositories/curso_repo.py` | `save_nodos` | 91 |
| `backend/repositories/curso_repo.py` | `delete` | 104 |
| `backend/repositories/historial_repo.py` | `get_by_docente` | 27 |
| `backend/repositories/historial_repo.py` | `get_by_docente_like` | 32 |
| `backend/repositories/historial_repo.py` | `get_by_periodos` | 37 |
| `backend/repositories/historial_repo.py` | `delete` | 71 |
| `backend/repositories/nodo_repo.py` | `get_by_id` | 24 |
| `backend/repositories/nodo_repo.py` | `get_all` | 27 |
| `backend/repositories/nodo_repo.py` | `bulk_ensure_exist` | 74 |

---

## Funciones de `backend/database/crud.py` que puedes eliminar (19)

- `create_docente` (línea 22)
- `update_docente` (línea 40)
- `create_curso` (línea 59)
- `get_curso` (línea 69)
- `update_curso` (línea 92)
- `upsert_historial` (línea 103)
- `create_recomendacion` (línea 130)
- `get_recomendaciones_by_curso` (línea 137)
- `invalidate_recomendaciones_by_curso` (línea 142)
- `update_webhook_log_status` (línea 163)
- `delete_recomendaciones_cache_by_docente` (línea 220)
- `delete_recomendaciones_cache_by_curso` (línea 225)
- `get_cache_stats` (línea 230)
- `sync_nodos_from_taxonomy` (línea 256)
- `get_nodo_by_id` (línea 300)
- `get_all_nodos` (línea 304)
- `delete_docente_nodos_by_docente` (línea 364)
- `delete_curso_nodos_by_curso` (línea 421)
- `create_audit_log` (línea 426)

---

## Código no usado en frontend

### `src/store/app.js`
- Estado: `data.docentes` (línea 22)
- Getter: `allFoldersSelected` (línea 41)
- Acción: `setFolders` (línea 105)
- Acción: `setData` (línea 117)

### `src/services/api.js`
- Export: `wsURL` (línea 14)

### `src/router/index.js`
- Parámetro: `from` en `beforeEach` (línea 42)

### `src/views/HomeView.vue`
- Import: `onUnmounted` (línea 76)
- Variable: `pollingInterval` (línea 88)
- Función: `checkSystemStatus` (línea 90)

### `src/views/RecomendacionesView.vue`
- `rankColor` (línea 155)
- `circleStyle` (línea 162)
- `getSortedShapValues` (línea 253)
- `formatFeatureName` (línea 265)

### `src/views/SettingsView.vue`
- Variable: `webhookActive` (línea 269)
- Función: `handleClearDatabase` (línea 395)
- Props de `folderList`: `icon` y `optional` (línea 287)

---

## Dependencias que puedes eliminar de `requirements.txt`

| Paquete | Nota |
|---|---|
| `anthropic[vertex]` | No se usa. Código usa Gemini, no Claude. |
| `PyPDF2==3.0.1` | Solo usado en scripts huérfanos. El código real usa `pdfplumber`. |
| `requests==2.31.0` | Es transitiva de `firebase-admin` y `google-auth`. Pip la reinstala automáticamente. |
| `aiofiles==23.2.1` | No se usa. |
| `spacy==3.7.2` | No se usa. |
| `es_core_news_lg` | No se usa. Depende de spacy. |
| `thinc` | Transitiva de spacy. |
| `chromadb==0.5.0` | No se usa. |
| `tiktoken==0.5.2` | No se usa. |
| `einops==0.7.0` | No se usa. |
| `transformers_stream_generator` | No se usa. |
| `scipy>=1.11.3` | Es transitiva de `scikit-learn`. Pip la reinstala automáticamente. |
| `PyJWT==2.8.0` | No se usa. Firebase Admin maneja JWT internamente. |
| `pandas==2.1.3` | Solo usado en scripts huérfanos. |

## Dependencias que puedes eliminar de `frontend_taller/package.json`

| Paquete | Nota |
|---|---|
| `baseline-browser-mapping` | No se referencia en ningún archivo `src/`. |
