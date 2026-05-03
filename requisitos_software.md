# Requisitos del Software: Sistema de Recomendación Docente (Teacher Ideal)

Este documento detalla los requisitos funcionales y no funcionales del sistema, identificados a partir de la implementación final desplegada en producción.

---

## 1. Requisitos Funcionales (RF)

Los requisitos funcionales describen lo que el sistema debe hacer y cómo debe comportarse ante entradas específicas.

### RF-01: Autenticación mediante Google
**Descripción:** El sistema debe permitir al usuario iniciar sesión exclusivamente mediante su cuenta institucional o personal de Google, utilizando Firebase Authentication.
**Tipo:** Funcional
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema debe presentar un botón visible de "Iniciar sesión con Google".
- El sistema debe solicitar y obtener permisos (`drive.readonly`) a través de la ventana de consentimiento de OAuth.
- El sistema debe redirigir al usuario al panel principal una vez que el inicio de sesión es exitoso.

### RF-02: Selección de Orígenes de Datos en Google Drive
**Descripción:** El sistema debe permitir al usuario seleccionar tres carpetas fuente desde su Google Drive (incluyendo unidades compartidas/Shared Drives) usando la API nativa de Google Picker.
**Tipo:** Funcional
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema debe abrir la interfaz nativa de Google Picker.
- El usuario debe poder seleccionar carpetas para: CVs, Sílabos y Horarios.
- El sistema debe almacenar temporalmente los IDs de estas carpetas en memoria o localStorage para su posterior procesamiento.

### RF-03: Procesamiento Automatizado de CVs (PDF)
**Descripción:** El sistema debe escanear de manera recursiva (incluyendo subcarpetas) documentos en formato PDF dentro de la carpeta asignada para CVs, extraer su texto y analizar su contenido semántico mediante IA.
**Tipo:** Funcional
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema debe descargar los archivos PDF de forma segura (Thread-Safe).
- El sistema debe extraer la información personal (nombre, email), grado académico, habilidades y metodologías usando el modelo Gemini de Vertex AI.
- El sistema debe alertar al usuario si la carpeta seleccionada está vacía o no contiene archivos PDF.
- El sistema debe persistir el perfil estructurado del docente en la base de datos relacional.

### RF-04: Procesamiento Automatizado de Sílabos (DOCX)
**Descripción:** El sistema debe buscar recursivamente archivos Word (.docx) en la carpeta de Sílabos para extraer la información estructural de las asignaturas universitarias.
**Tipo:** Funcional
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema debe extraer el código, nombre, ciclo académico, sumilla y temas clave de cada documento Word.
- El sistema debe saltar automáticamente aquellos archivos que ya han sido procesados previamente en la base de datos.
- El sistema debe agrupar y guardar los cursos detectados para alimentar la malla curricular.

### RF-05: Procesamiento Automatizado de Horarios (PDF)
**Descripción:** El sistema debe escanear la carpeta de Horarios para extraer el historial de carga académica de los docentes.
**Tipo:** Funcional
**Prioridad:** Media
**Criterios de Aceptación:**
- El sistema debe identificar a los docentes mencionados y vincularlos con los cursos que dictaron.
- El sistema debe guardar estos registros históricos en la base de datos para influenciar futuras recomendaciones.

### RF-06: Visualización de Malla Curricular
**Descripción:** El sistema debe mostrar una interfaz interactiva donde los cursos detectados se listen agrupados según su ciclo académico correspondiente.
**Tipo:** Funcional
**Prioridad:** Media
**Criterios de Aceptación:**
- El usuario debe poder ver pestañas o listas separadas para los ciclos (ej. Ciclo 1 al Ciclo 10).
- Cada ciclo debe mostrar los cursos pertenecientes al mismo con su código y título.

### RF-07: Motor de Recomendación y Emparejamiento (Matching)
**Descripción:** El sistema debe recomendar a los docentes más idóneos para dictar un curso específico basándose en la coincidencia semántica entre el contenido del curso (sílabo) y el perfil del docente (CV).
**Tipo:** Funcional
**Prioridad:** Crítica
**Criterios de Aceptación:**
- El usuario debe poder hacer clic en un curso específico para ver sus candidatos.
- El sistema debe calcular un score de afinidad para cada docente de la base de datos.
- El sistema debe presentar una tabla/lista de candidatos ordenada de mayor a menor afinidad.

---

## 2. Requisitos No Funcionales (RNF)

Los requisitos no funcionales describen los atributos de calidad, rendimiento y restricciones tecnológicas del sistema.

### RNF-01: Arquitectura Serverless y Contenedores
**Descripción:** El backend del sistema debe operar como una API REST aislada, desplegada en Google Cloud Run y el frontend alojado como Single Page Application en Firebase Hosting.
**Tipo:** No Funcional (Arquitectura)
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema backend debe estar correctamente contenedorizado en Docker.
- El servicio en la nube debe escalar su infraestructura automáticamente según la demanda de la red.

### RNF-02: Tolerancia a Fallos y Concurrencia Transaccional
**Descripción:** El sistema debe garantizar la integridad de las transacciones hacia la base de datos remota (Neon PostgreSQL) incluso durante la extracción simultánea masiva de múltiples archivos.
**Tipo:** No Funcional (Confiabilidad)
**Prioridad:** Crítica
**Criterios de Aceptación:**
- El sistema debe implementar bloqueos asíncronos (`asyncio.Lock()`) a nivel de código para evitar colisiones de conexión de SQLAlchemy (`concurrent operations are not permitted`).

### RNF-03: Procesamiento Asíncrono de IA
**Descripción:** El sistema debe procesar múltiples documentos descargados en paralelo para minimizar los tiempos de respuesta, respetando las cuotas de red.
**Tipo:** No Funcional (Rendimiento)
**Prioridad:** Media
**Criterios de Aceptación:**
- El sistema debe usar semáforos asíncronos (`asyncio.Semaphore()`) para analizar simultáneamente al menos 2 archivos de Google Drive sin saturar los Rate Limits de la API de Vertex AI.

### RNF-04: Seguridad y Validación de Sesiones
**Descripción:** El sistema debe proteger sus endpoints impidiendo el procesamiento de datos si no se envían tokens de autorización legítimos.
**Tipo:** No Funcional (Seguridad)
**Prioridad:** Alta
**Criterios de Aceptación:**
- El frontend debe adjuntar la cabecera `X-Drive-Token` en las peticiones HTTP seguras.
- El backend debe rechazar peticiones y devolver un código HTTP 401 Unauthorized si el token expira o es inexistente.

### RNF-05: Adopción de IA Estable en Producción
**Descripción:** El sistema debe utilizar los modelos fundacionales de Google Cloud de disponibilidad general (GA) recomendados para la fecha del despliegue en producción.
**Tipo:** No Funcional (Estandarización)
**Prioridad:** Alta
**Criterios de Aceptación:**
- El sistema debe instanciar y consumir específicamente el modelo `gemini-2.5-flash` en la región `us-central1` para garantizar la estabilidad de las extracciones estructuradas (JSON).

---

## 3. Requisitos Complementarios (Futuras Mejoras)

Estos requisitos adicionales no forman parte de la versión inicial desplegada, pero se sugieren como mejoras estratégicas para escalar la funcionalidad y robustez del sistema en futuras iteraciones.

### RF-08: Exportación de Resultados de Recomendación
**Descripción:** El sistema debe permitir al administrador exportar el listado de docentes recomendados para un curso específico en formatos estándar (PDF y Excel/CSV).
**Tipo:** Funcional
**Prioridad:** Baja
**Criterios de Aceptación:**
- Debe existir un botón de "Exportar a Excel" y "Exportar a PDF" en la vista de resultados.
- El archivo generado debe incluir el nombre del curso, los nombres de los docentes recomendados y su respectivo score de afinidad.

### RF-09: Filtrado Avanzado por Disponibilidad (Horarios)
**Descripción:** El sistema debe permitir cruzar las recomendaciones semánticas con la disponibilidad horaria real del docente (extraída previamente de sus horarios históricos).
**Tipo:** Funcional
**Prioridad:** Media
**Criterios de Aceptación:**
- El sistema debe ofrecer un filtro que descarte automáticamente a los docentes que tienen cruce de horarios con las horas programadas para el curso a dictar.

### RF-10: Sistema de Retroalimentación de Recomendaciones (RLHF)
**Descripción:** El sistema debe permitir al usuario aceptar o rechazar a un docente recomendado, para utilizar esta decisión y mejorar futuras predicciones.
**Tipo:** Funcional
**Prioridad:** Baja
**Criterios de Aceptación:**
- Cada recomendación debe tener opciones de "Aprobar" o "Descartar".
- Esta decisión debe registrarse en la base de datos para afinar el algoritmo de matching en futuras búsquedas.

### RNF-06: Trazabilidad y Auditoría de Procesamientos
**Descripción:** El sistema debe mantener un registro (log) de qué usuario inició un procesamiento masivo de archivos, cuándo ocurrió y si fue exitoso o fallido.
**Tipo:** No Funcional (Seguridad/Auditoría)
**Prioridad:** Media
**Criterios de Aceptación:**
- La base de datos debe almacenar el email del usuario autenticado que disparó los endpoints de procesamiento de Drive y un timestamp de la acción.

### RNF-07: Accesibilidad Web (WCAG)
**Descripción:** El frontend del sistema debe cumplir con los estándares básicos de accesibilidad web (WCAG 2.1 Nivel AA) para asegurar su uso por personas con discapacidades visuales.
**Tipo:** No Funcional (Usabilidad)
**Prioridad:** Baja
**Criterios de Aceptación:**
- Todos los botones e imágenes deben tener atributos `aria-label` o `alt`.
- La interfaz debe soportar navegación completa utilizando únicamente el teclado.

### RF-11: Configuración Interactiva y Sincronización Autónoma (Webhooks)
**Descripción:** El sistema opera bajo un modelo orientado a eventos (Webhooks). El usuario interactúa con la interfaz únicamente para vincular la carpeta de origen en Google Drive (Configuración Inicial), tras lo cual el sistema opera de manera autónoma en segundo plano para mantener la información sincronizada.
**Tipo:** Funcional (Interfaz y Backend)
**Prioridad:** Alta
**Criterios de Aceptación:**
- **Retroalimentación Visual:** Tras la selección de una carpeta mediante Google Picker, la interfaz de usuario debe mostrar de forma estática el nombre de la carpeta seleccionada junto con un indicador visual de estado (ej. "Webhook Activo").
- **Acciones de Vinculación:** El sistema debe contar con una acción denominada "Sincronizar y Vincular". Su ejecución debe registrar la suscripción del Webhook en la API de Google Cloud y realizar un escaneo inicial (Initial Pull) del contenido existente.
- **Prevención de Errores:** Una vez confirmada la vinculación y activado el Webhook, los controles de sincronización manual deben deshabilitarse o desaparecer. El sistema solo debe ofrecer opciones para "Desvincular" o "Cambiar Carpeta".
- **Autonomía de Procesamiento:** El backend debe disponer de un endpoint público preparado para recibir eventos push desde Google Drive, desencadenando automáticamente el procesamiento, actualización o eliminación en cascada de los registros correspondientes sin intervención manual.

### RF-12: Extracción Determinista de Horarios
**Descripción:** El sistema vincula la información de carga académica (horarios) a los docentes y cursos utilizando exclusivamente claves primarias y códigos institucionales exactos.
**Tipo:** Funcional
**Prioridad:** Alta
**Criterios de Aceptación:**
- El procesamiento de horarios debe extraer el identificador único del docente (ID_DOC) y el código institucional del curso directamente del documento.
- La inserción de datos en la tabla de historiales debe realizarse condicionada a una coincidencia exacta de estos códigos institucionales.

### RF-13: Procesamiento Unificado de Lenguaje Natural
**Descripción:** El sistema centraliza la comprensión semántica y la extracción de entidades estructuradas en un único Modelo de Lenguaje Grande (LLM), garantizando homogeneidad en el procesamiento.
**Tipo:** Funcional (Arquitectura)
**Prioridad:** Alta
**Criterios de Aceptación:**
- El LLM debe procesar el texto fuente y retornar un objeto JSON estructurado que contenga tanto el perfil sintético unificado como el vector de entidades tecnológicas clave.
- El sistema debe operar de forma independiente, sin requerir bibliotecas secundarias de procesamiento de lenguaje natural o diccionarios estáticos de palabras clave.

### RNF-08: Motor Vectorial de Alta Capacidad de Contexto
**Descripción:** El motor de representación semántica (Embeddings) procesa documentos extensos en su totalidad para asegurar que ninguna sección de la trayectoria del docente sea omitida en el cálculo de afinidad.
**Tipo:** No Funcional (Precisión Algorítmica)
**Prioridad:** Crítica
**Criterios de Aceptación:**
- El modelo vectorial implementado debe poseer una ventana de contexto de al menos 8,192 tokens.
- La ejecución del modelo debe configurarse con precisión de coma flotante de 16 bits (float16) para asegurar un uso eficiente de los recursos de memoria RAM.

### RNF-09: Actualización Dirigida de Caché
**Descripción:** El sistema mantiene el rendimiento y la escalabilidad al recalcular las recomendaciones almacenadas en caché aplicando actualizaciones granulares exclusivas sobre los registros alterados.
**Tipo:** No Funcional (Rendimiento)
**Prioridad:** Alta
**Criterios de Aceptación:**
- Frente a un evento de actualización o inserción, el sistema debe ejecutar sentencias de borrado (DELETE) dirigidas únicamente al identificador específico del docente o curso modificado en la tabla de caché.
- El sistema debe preservar el resto de los registros no afectados dentro de la caché durante las operaciones de actualización individual.
