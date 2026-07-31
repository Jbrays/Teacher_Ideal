"""
Dependencias comunes de los routers FastAPI.

Incluye autenticación con Firebase y resolución de workspaces multi-tenant.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.auth.firebase import firebase_auth
from backend.database.db_session import get_db


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Dependencia que valida el token JWT de Firebase."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    try:
        token = authorization.replace("Bearer ", "")
        user_info = firebase_auth.verify_token(token)
        if not user_info:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error interno de autenticación: {str(e)}")


def get_current_user_email(user: dict = Depends(get_current_user)) -> str:
    return user.get("email", "").strip().lower()


def get_user_workspaces(db: Session = Depends(get_db), email: str = Depends(get_current_user_email)) -> list[str]:
    """Devuelve la lista de correos dueños a cuyos datos este usuario tiene acceso (incluyéndose a sí mismo)."""
    from backend.database.models import Colaborador
    workspaces = [email]
    colaboraciones = db.query(Colaborador).filter(Colaborador.invitado_email == email).all()
    for colab in colaboraciones:
        workspaces.append(colab.propietario_email)
    return workspaces
