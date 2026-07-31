"""Prompts centralizados para extracción de CVs y sílabos."""

from backend.llm.prompts.cv import prompt_cv_unificado, prompt_validacion_inferencias
from backend.llm.prompts.syllabus import prompt_directo_silabo

__all__ = [
    "prompt_cv_unificado",
    "prompt_validacion_inferencias",
    "prompt_directo_silabo",
]
