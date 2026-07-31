"""Prompts para extracción de información de sílabos de cursos."""

def prompt_directo_silabo(texto_silabo: str) -> str:
    """Prompt para extracción de un sílabo en JSON estructurado."""
    return f"""
Eres un experto en extracción estructurada de datos académicos. Tu objetivo es analizar el sílabo de un curso y extraer su información general y su contenido técnico semana a semana.

<instrucciones>
1. DATOS GENERALES: Extrae únicamente el nombre oficial de la asignatura y el ciclo de estudios. Tienes permitido corregir errores ortográficos evidentes en el nombre de la asignatura.
2. SEMANAS TÉCNICAS: Recorre el sílabo e identifica las semanas de aprendizaje.
   - INCLUYE ÚNICAMENTE las semanas que contengan el dictado de teoría, metodologías, paradigmas o el uso de herramientas de laboratorio, como software, lenguajes o entornos de trabajo.
   - IGNORA por completo cualquier semana cuyo propósito principal sea administrativo o evaluativo, abarcando actividades como exámenes, prácticas calificadas, feriados, retroalimentación o presentación de proyectos.
3. ESTRUCTURA SEMANAL: Para cada semana técnica extraída, clasifica su contenido en:
   - "teoria": Conceptos y metodologías en español.
   - "teoria_en": Equivalente técnico exacto en inglés de cada elemento de "teoria", respetando el mismo orden y la misma cantidad de elementos.
   - "laboratorio_herramientas": Nombres propios de software, plataformas o lenguajes. Debes mantenerlos en su idioma original e incluir su versión si el texto la menciona, como por ejemplo Oracle 11g o equivalentes.
4. ATOMICIDAD Y CANONIZACIÓN:
   - Cada elemento debe representar UN solo concepto técnico reutilizable, no la redacción de una actividad de clase.
   - Elimina envolturas pedagógicas como "introducción a", "definición de", "características de", "aplicaciones de", "conceptos básicos de", "instalación de" o "práctica de". Conserva únicamente el concepto central. Ejemplo: "Definición, características y aplicaciones de Internet de las cosas" se convierte una sola vez en "Internet de las cosas"/"Internet of Things".
   - Divide enumeraciones que mezclen conceptos independientes. Ejemplo: "clasificación supervisada y no supervisada" produce dos elementos; "HTML, CSS y JavaScript" produce tres herramientas.
   - No repitas el mismo concepto por aparecer en varias semanas. Versiones, fases o actividades de una metodología no deben generar entradas redundantes si todas representan la misma competencia central. Por ejemplo, las fases A-H de TOGAF se representan como "TOGAF" una sola vez, salvo que el sílabo enseñe una técnica independiente con nombre propio.
   - No mezcles una herramienta con la actividad realizada. "Instalación local de Node-RED" se representa como la herramienta "Node-RED"; "servidor embebido con HTML y CSS" debe separar el concepto "servidores web embebidos" de las herramientas "HTML" y "CSS".
5. CONTEXTUALIZACIÓN OBLIGATORIA: Los términos extraídos deben tener sentido técnico por sí solos, incluso al leerse fuera de este documento. Ante conceptos sueltos, genéricos o ambiguos como seguridad, tipos o fundamentos, debes enriquecer el resultado combinándolo con la tecnología, la teoría central o el nombre de la asignatura correspondiente. No vuelvas a introducir verbos o envolturas pedagógicas al contextualizar.
6. CONTRATO BILINGÜE OBLIGATORIO:
   - Cada posición de "teoria_en" debe traducir exclusivamente el concepto ubicado en la misma posición de "teoria".
   - Está prohibido devolver definiciones, explicaciones o categorías en lugar de traducciones.
   - Los nombres propios de tecnologías se conservan: Python/Python, PostgreSQL/PostgreSQL, Docker/Docker.
   - Los conceptos se traducen: "Inteligencia artificial"/"Artificial intelligence", "Base de datos relacional"/"Relational database".
   - "teoria" y "teoria_en" deben tener exactamente la misma longitud.
7. CALIDAD DE SALIDA: No repitas conceptos por diferencias de mayúsculas, puntuación, abreviaturas, semanas o versiones. No conviertas el nombre de una herramienta en una competencia más amplia sin respaldo explícito del sílabo.
</instrucciones>

<formato_salida>
Debes responder estricta y únicamente con un objeto JSON válido con esta estructura exacta:
{{
  "nombre": "string",
  "ciclo": 0,
  "semanas": [
    {{
      "numero": 1,
      "teoria": ["tema conceptual 1", "tema 2"],
      "teoria_en": ["conceptual topic 1", "topic 2"],
      "laboratorio_herramientas": ["Oracle 11g", "Visual Studio Code"]
    }}
  ]
}}
</formato_salida>

<documento>
{texto_silabo}
</documento>
"""
