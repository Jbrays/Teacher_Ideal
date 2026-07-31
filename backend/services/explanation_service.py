"""
Servicio puro y determinista de generación de explicaciones XAI.

No accede a base de datos ni utiliza modelos de lenguaje. Recibe los
matches atómicos y las brechas pre-computadas y produce un texto
legible para el usuario siguiendo reglas fijas.
"""

import random
from typing import List

class ExplanationService:
    """Genera explicaciones XAI deterministas y objetivas a partir de pares atómicos."""

    @staticmethod
    def generate(matches: List[dict], brechas: List[dict]) -> str:
        """
        Genera un reporte de compatibilidad en lenguaje natural objetivo.

        Args:
            matches: Lista de dicts con curso_entidad, docente_entidad y score.
            brechas: Lista de dicts con curso_nodo_name/curso_nodo_id.

        Returns:
            Texto explicativo estructurado y sobrio.
        """
        lines = []
        if not matches:
            lines.append("Sin evidencia de compatibilidad directa registrada en el perfil.")
            return "\n".join(lines)

        for m in matches[:8]:
            score = m.get("score", 0.0)
            curso = m.get("curso_entidad", "Requisito del curso")
            docente = m.get("docente_entidad", "Perfil del docente")

            if score >= 0.9:
                opciones = [
                    f"• Conocimiento directo en {docente} acredita cobertura para el temario de {curso}.",
                    f"• Formación en {docente} responde al requisito de {curso}."
                ]
            elif score >= 0.65:
                opciones = [
                    f"• Conocimiento en {docente} resulta compatible para abordar los contenidos de {curso}.",
                    f"• Experiencia en {docente} otorga una base adecuada para impartir {curso}."
                ]
            else:
                opciones = [
                    f"• Fundamentos en {docente} proporcionan una base teórica aceptable para {curso}.",
                    f"• Existen nociones en {docente} que pueden adaptarse parcialmente a {curso}."
                ]

            lines.append(random.choice(opciones))

        if brechas:
            lines.append("")
            lines.append("Brechas identificadas:")
            for b in brechas[:5]:
                nombre = b.get("curso_nodo_name", b.get("curso_nodo_id", "Requisito"))
                opciones_brechas = [
                    f"• No se identificaron antecedentes directos en el perfil para cubrir {nombre}.",
                    f"• Falta evidencia técnica comprobable respecto a {nombre}."
                ]
                lines.append(random.choice(opciones_brechas))

        return "\n".join(lines)
