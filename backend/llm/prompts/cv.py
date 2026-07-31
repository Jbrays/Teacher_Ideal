"""Prompts para extracción de información de CVs de docentes."""

def prompt_cv_unificado(texto_cv: str) -> str:
    """Prompt unificado para extracción de herramientas e inferencia conceptual de un CV."""
    return f"""
Eres un experto en extracción de información técnica a partir de currículums. Tu objetivo es leer el documento y estructurar el conocimiento del profesional separando las herramientas exactas de las disciplinas teóricas inferidas.

<instrucciones>
1. DATOS PERSONALES: Extrae únicamente el nombre completo y el grado académico.
2. HERRAMIENTAS TECNOLOGICAS: Extrae de forma estrictamente literal únicamente software, lenguajes de programación, plataformas, productos, estándares o herramientas con nombre propio mencionados en el documento. Queda absolutamente prohibido inferir o suponer el uso de cualquier herramienta. Un proceso, servicio empresarial, actividad, metodología o área de conocimiento no es una herramienta aunque se implemente mediante software. Por ejemplo, "facturación electrónica", "gestión de proyectos", "desarrollo de software" y "comercio electrónico" pertenecen a DOMINIOS CONCEPTUALES; sólo un producto nombrado como "SAP", "Visual Studio" o "Oracle Database" pertenece a HERRAMIENTAS TECNOLOGICAS. Registra la oración exacta del documento que sirve como respaldo textual en el campo contexto.
3. DOMINIOS CONCEPTUALES: Extrae áreas de conocimiento, procesos técnicos, metodologías o disciplinas fundamentales aplicando dos reglas de origen excluyentes. Primera regla de origen: extrae inferencias derivadas directamente de las responsabilidades de la experiencia laboral, los proyectos ejecutados y la docencia impartida. Segunda regla de origen: si el documento declara títulos universitarios de naturaleza formal o fundacional, estás OBLIGADO a inferir y desglosar como dominios conceptuales las disciplinas teóricas pilares que conforman la base curricular ineludible de dicho grado académico. Tienes terminantemente prohibido realizar este tipo de expansión o inferir conocimientos para títulos pertenecientes a ingenierías de amplio espectro, carreras administrativas o disciplinas tecnológicas orientadas a la gestión. Si el dominio conceptual está escrito textualmente en el documento, establécelo con explicito en true y pon el motivo de inferencia en null. Si el dominio no está escrito textualmente, pero lo estás deduciendo lógicamente de la educación formal o de las responsabilidades descritas, establécelo en false y redacta la justificación en el motivo de inferencia.
4. CONTEXTUALIZACION OBLIGATORIA: Los términos extraídos deben tener sentido técnico por sí solos, incluso al leerse fuera de este documento. Ante conceptos sueltos, genéricos o ambiguos como seguridad, instalación, tipos o fundamentos, debes enriquecer el resultado combinándolo con la tecnología, la teoría central o el dominio de la experiencia. El objetivo es asegurar que cada término sea universalmente comprensible sin depender de leer el currículum original.
5. CONTRATO BILINGUE OBLIGATORIO:
   - "termino" debe ser el nombre técnico canónico en español.
   - "termino_en" debe ser el equivalente técnico exacto del mismo concepto en inglés.
   - Está prohibido colocar en "termino_en" una definición, explicación, categoría o descripción del término.
   - Si el término es el nombre propio de una tecnología, producto, lenguaje, sigla o estándar, conserva su nombre oficial en ambos campos. Ejemplos: Python/Python, Zoom/Zoom, PostgreSQL/PostgreSQL, ISO/IEC 27001/ISO/IEC 27001.
   - Para conceptos traducibles usa equivalencia semántica directa. Ejemplos: "Inteligencia artificial"/"Artificial intelligence", "Gestión de bases de datos"/"Database management".
   - Ejemplos prohibidos: "Python"/"Lenguaje de programación", "Zoom"/"Plataforma de videoconferencias", "Docker"/"Plataforma de contenedores".
   - No conviertas una plataforma en una capacidad que el documento no demuestre. Por ejemplo, "Android" sólo puede convertirse en "Desarrollo de aplicaciones Android"/"Android application development" si el documento demuestra explícitamente desarrollo de aplicaciones.
6. CALIDAD DE SALIDA: No repitas conceptos con diferencias de mayúsculas, puntuación, abreviaturas o versiones. Devuelve únicamente términos suficientemente específicos y profesionalmente útiles.
</instrucciones>

<formato_salida>
Debes responder estricta y únicamente con un objeto JSON válido con esta estructura exacta:
{{
  "nombre": "string",
  "grado": "string",
  "herramientas_tecnologicas": [
    {{
      "termino": "string",
      "termino_en": "string",
      "contexto": "string"
    }}
  ],
  "dominios_conceptuales": [
    {{
      "termino": "string",
      "termino_en": "string",
      "contexto": "string",
      "explicito": true,
      "motivo_inferencia": null
    }}
  ]
}}
</formato_salida>

<documento>
{texto_cv}
</documento>
"""

def prompt_validacion_inferencias(cursos_str: str, inferencias_str: str) -> str:
    """Prompt para validar inferencias de un CV usando LLM as a Judge."""
    return f"""
Eres un Director Académico experto en perfiles profesionales. Tu tarea es auditar habilidades deducidas sobre la capacidad de un docente, comparándolas contra el historial real de los cursos que dicta en la actualidad.

REGLA DE VALIDACIÓN FUNDAMENTAL:
No evalúes si el curso y la habilidad pertenecen a la misma categoría teórica o comparten jerga lingüística. Tu único criterio para aprobar una deducción es responder afirmativamente a la premisa de solapamiento práctico. Un conocimiento solo es válido si es razonable y profesionalmente coherente esperar que alguien capacitado para enseñar la lista de cursos dictados posea la destreza técnica u operativa para ejecutar la habilidad deducida en el mundo real.

<instrucciones>
Recibirás una lista de cursos dictados y una lista de habilidades deducidas. 
Para CADA habilidad deducida, evalúa el solapamiento práctico. 
Atención especial: Elimina estableciendo el campo es_valida en false cualquier habilidad de naturaleza puramente técnica u operativa si el curso que dicta el docente es estrictamente de nivel estratégico, gerencial o de políticas.
</instrucciones>

<formato_salida>
Debes responder estricta y únicamente con una lista JSON válida de objetos:
[
  {{
    "habilidad": "nombre de la habilidad",
    "analisis": "breve explicacion del nivel tecnico vs gerencial y el solapamiento",
    "es_valida": true
  }}
]
</formato_salida>

<cursos_dictados>
{cursos_str}
</cursos_dictados>

<habilidades_deducidas>
{inferencias_str}
</habilidades_deducidas>
"""
