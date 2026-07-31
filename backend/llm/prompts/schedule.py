"""Prompts para extracción de información de horarios."""

def prompt_horarios(batch_text: str) -> str:
    """Prompt para extracción de asignaciones de un bloque de páginas de horarios."""
    return f"""
Eres un experto extractor de datos a partir de horarios universitarios. Tu objetivo es leer el documento y estructurar la información de asignación docente de manera consolidada.

<instrucciones>
1. PERIODO ACADEMICO: El período académico se encuentra en el encabezado del documento. Captúralo una sola vez y aplícalo a todos los registros que extraigas. El período debe ser el código numérico o romano del ciclo académico.
2. EXTRACCION DE ASIGNACIONES: Por cada fila del horario, identifica el nombre exacto del curso y el nombre completo del docente.
3. REGLAS DE CONSOLIDACION: Un mismo curso puede aparecer en múltiples líneas para el mismo docente debido a diferentes secciones. Debes consolidar estas apariciones en un único registro por cada combinación única de docente y curso.
4. REGLAS DE EXCLUSION: Ignora completamente cualquier fila donde el docente asignado sea la palabra STAFF. No extraigas ni incluyas datos operativos adicionales como el NRC, la sección, el aula, la hora o los créditos.
</instrucciones>

<formato_salida>
Debes responder estricta y únicamente con una lista JSON válida, sin etiquetas previas, con esta estructura exacta:
[
  {{
    "nombre_docente": "string",
    "curso": "string",
    "periodo": "string"
  }}
]
</formato_salida>

<documento>
{batch_text}
</documento>
"""
