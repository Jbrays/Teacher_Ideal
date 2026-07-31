"""Router de cursos."""

from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_email, get_user_workspaces
from backend.database.db_session import get_db
from backend.database import crud

router = APIRouter(prefix="/api/cursos", tags=["cursos"])


@router.get("/ciclos")
async def get_ciclos(db: Session = Depends(get_db), email: str = Depends(get_current_user_email), workspaces: list = Depends(get_user_workspaces)):
  ciclos = crud.get_all_ciclos(db, workspaces=workspaces)
  return {"success": True, "ciclos": ciclos}


@router.get("")
async def get_cursos(
  ciclo: Optional[int] = None,
  db: Session = Depends(get_db),
  email: str = Depends(get_current_user_email),
  workspaces: list = Depends(get_user_workspaces),
):
  cursos = crud.get_cursos_by_ciclo(db, ciclo, workspaces=workspaces) if ciclo else crud.get_all_cursos(db, workspaces=workspaces)
  return {
    "success": True,
    "total": len(cursos),
    "cursos": [
      {
        "id": c.id,
        "nombre": c.nombre,
        "ciclo": c.ciclo,
        "perfil_tecnico": c.perfil_tecnico,
      }
      for c in cursos
    ],
  }
