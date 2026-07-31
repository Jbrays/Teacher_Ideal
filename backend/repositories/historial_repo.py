"""
Repositorio de historial docente. Encapsula el acceso a la tabla `historiales`.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.database.models import Historial
from backend.database.crud import _apply_workspaces

logger = logging.getLogger(__name__)


class HistorialRepository:
    """Acceso al historial de cursos dictados por docentes."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self, workspaces: Optional[List[str]] = None) -> List[Historial]:
        query = self.db.query(Historial)
        query = _apply_workspaces(query, Historial, workspaces)
        return query.all()

    def upsert(
        self,
        nombre_docente: str,
        nombre_curso: str,
        periodo: str,
        propietario_email: str = "legacy@upao.edu.pe",
    ) -> Historial:
        historial = (
            self.db.query(Historial)
            .filter(
                Historial.nombre_docente == nombre_docente,
                Historial.nombre_curso == nombre_curso,
            )
            .first()
        )
        if historial:
            if periodo > historial.ultima_vez:
                historial.ultima_vez = periodo
        else:
            historial = Historial(
                nombre_docente=nombre_docente,
                nombre_curso=nombre_curso,
                ultima_vez=periodo,
                propietario_email=propietario_email,
            )
            self.db.add(historial)
        self.db.flush()
        return historial
