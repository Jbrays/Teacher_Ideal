"""
Repositorio de cursos. Encapsula el acceso a la tabla `cursos`
y a sus nodos asociados (`curso_nodos`).
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.database.models import Curso, CursoNodo
from backend.database.crud import _apply_workspaces

logger = logging.getLogger(__name__)


class CursoRepository:
    """Acceso a datos de cursos y sus requisitos de nodos."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, curso_id: int) -> Optional[Curso]:
        return self.db.query(Curso).filter(Curso.id == curso_id).first()

    def get_by_drive_id(self, drive_file_id: str) -> Optional[Curso]:
        return self.db.query(Curso).filter(Curso.drive_file_id == drive_file_id).first()

    def get_all(self, skip: int = 0, limit: int = 100, workspaces: Optional[List[str]] = None) -> List[Curso]:
        query = self.db.query(Curso)
        query = _apply_workspaces(query, Curso, workspaces)
        return query.offset(skip).limit(limit).all()

    def get_or_create(
        self,
        drive_file_id: str,
        nombre: str,
        ciclo: int = 1,
        propietario_email: str = "legacy@upao.edu.pe",
    ) -> Curso:
        curso = self.get_by_drive_id(drive_file_id)
        if curso:
            return curso
        curso = Curso(
            drive_file_id=drive_file_id,
            nombre=nombre,
            ciclo=ciclo,
            propietario_email=propietario_email,
        )
        self.db.add(curso)
        self.db.flush()
        return curso

    def update_profile(
        self,
        curso_id: int,
        nombre: Optional[str] = None,
        ciclo: Optional[int] = None,
        perfil_tecnico: Optional[list] = None,
    ) -> Optional[Curso]:
        curso = self.get_by_id(curso_id)
        if not curso:
            return None
        if nombre:
            curso.nombre = nombre
        if ciclo is not None:
            curso.ciclo = ciclo
        if perfil_tecnico is not None:
            curso.perfil_tecnico = perfil_tecnico
        self.db.commit()
        self.db.refresh(curso)
        return curso

    def delete_nodos(self, curso_id: int) -> int:
        """Elimina todos los nodos asociados a un curso. Devuelve cantidad eliminada."""
        count = self.db.query(CursoNodo).filter(CursoNodo.curso_id == curso_id).delete()
        return count

    def get_nodos(self, curso_id: int) -> List[CursoNodo]:
        return (
            self.db.query(CursoNodo)
            .filter(CursoNodo.curso_id == curso_id)
            .all()
        )
