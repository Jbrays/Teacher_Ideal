"""
Repositorio de docentes. Encapsula el acceso a la tabla `docentes`
y a sus nodos asociados (`docente_nodos`).
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.database.models import Docente, DocenteNodo
from backend.database.crud import _apply_workspaces

logger = logging.getLogger(__name__)


class DocenteRepository:
    """Acceso a datos de docentes y sus perfiles de nodos."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, docente_id: int) -> Optional[Docente]:
        return self.db.query(Docente).filter(Docente.id == docente_id).first()

    def get_by_drive_id(self, drive_file_id: str) -> Optional[Docente]:
        return self.db.query(Docente).filter(Docente.drive_file_id == drive_file_id).first()

    def get_all(self, skip: int = 0, limit: int = 100, workspaces: Optional[List[str]] = None) -> List[Docente]:
        query = self.db.query(Docente)
        query = _apply_workspaces(query, Docente, workspaces)
        return query.offset(skip).limit(limit).all()

    def get_or_create(
        self,
        drive_file_id: str,
        nombre: str,
        grado: Optional[str] = None,
        propietario_email: str = "legacy@upao.edu.pe",
    ) -> Docente:
        docente = self.get_by_drive_id(drive_file_id)
        if docente:
            return docente
        docente = Docente(
            drive_file_id=drive_file_id,
            nombre=nombre,
            grado=grado,
            propietario_email=propietario_email,
        )
        self.db.add(docente)
        self.db.flush()
        return docente

    def update_profile(
        self,
        docente_id: int,
        nombre: Optional[str] = None,
        grado: Optional[str] = None,
        perfil_tecnico: Optional[list] = None,
    ) -> Optional[Docente]:
        docente = self.get_by_id(docente_id)
        if not docente:
            return None
        if nombre:
            docente.nombre = nombre
        if grado:
            docente.grado = grado
        if perfil_tecnico is not None:
            docente.perfil_tecnico = perfil_tecnico
        self.db.commit()
        self.db.refresh(docente)
        return docente

    def delete_nodos(self, docente_id: int) -> int:
        """Elimina todos los nodos asociados a un docente. Devuelve cantidad eliminada."""
        count = self.db.query(DocenteNodo).filter(DocenteNodo.docente_id == docente_id).delete()
        return count

    def get_nodos(self, docente_id: int) -> List[DocenteNodo]:
        return (
            self.db.query(DocenteNodo)
            .filter(DocenteNodo.docente_id == docente_id)
            .all()
        )
