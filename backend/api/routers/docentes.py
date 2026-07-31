"""Router de docentes."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_user_workspaces
from backend.database.db_session import get_db
from backend.database import crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/docentes", tags=["docentes"])


@router.get("")
async def get_docentes(
  skip: int = 0,
  limit: int = 100,
  db: Session = Depends(get_db),
  user: dict = Depends(get_current_user),
  workspaces: list = Depends(get_user_workspaces),
):
  docentes = crud.get_all_docentes(db, skip=skip, limit=limit, workspaces=workspaces)
  return {
    "success": True,
    "total": len(docentes),
    "docentes": [
      {
        "id": d.id,
        "nombre": d.nombre,
        "grado": d.grado,
        "perfil_tecnico": d.perfil_tecnico,
      }
      for d in docentes
    ],
  }


@router.delete("/{docente_id}")
async def delete_docente_endpoint(
  docente_id: int,
  db: Session = Depends(get_db),
  user: dict = Depends(get_current_user),
):
  try:
    docente = crud.get_docente_by_id(db, docente_id)
    if not docente:
      raise HTTPException(status_code=404, detail=f"Docente con ID {docente_id} no encontrado")
    success = crud.delete_docente(db, docente.id)
    if not success:
      raise HTTPException(status_code=500, detail="Error eliminando docente de la base de datos")

    logger.info(f" Docente {docente.nombre} (ID: {docente.id}) eliminado exitosamente.")
    return {"success": True, "message": "Docente eliminado correctamente"}
  except HTTPException:
    raise
  except Exception as e:
    logger.error(f" Error en endpoint delete_docente: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
