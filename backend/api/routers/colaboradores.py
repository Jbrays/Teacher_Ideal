"""Router de gestion de colaboradores (invitaciones multi-tenant)."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_email
from backend.database.db_session import get_db
from backend.database import crud

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/colaboradores", tags=["colaboradores"])


class InviteRequest(BaseModel):
    invitado_email: str


@router.post("")
async def add_colaborador(
    req: InviteRequest,
    db: Session = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    if req.invitado_email.strip().lower() == email:
        raise HTTPException(status_code=400, detail="No puedes invitarte a ti mismo")
    crud.add_colaborador(db, propietario_email=email, invitado_email=req.invitado_email.strip().lower())
    return {"success": True, "message": f"Colaborador {req.invitado_email} agregado"}


@router.get("")
async def list_colaboradores(
    db: Session = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    colaboradores = crud.get_colaboradores(db, propietario_email=email)
    return {
        "success": True,
        "colaboradores": [
            {"id": c.id, "invitado_email": c.invitado_email, "created_at": c.created_at}
            for c in colaboradores
        ],
    }


@router.delete("/{invitado_email}")
async def remove_colaborador(
    invitado_email: str,
    db: Session = Depends(get_db),
    email: str = Depends(get_current_user_email),
):
    crud.remove_colaborador(db, propietario_email=email, invitado_email=invitado_email.lower())
    return {"success": True, "message": f"Colaborador {invitado_email} eliminado"}
