"""Router de autenticación y tokens de Google Drive."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_current_user_email
from backend.auth.firebase import firebase_auth
from backend.database.db_session import get_db
from backend.models.schemas import UserLogin, UserResponse, AuthResponse
from backend.services import drive_token_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class DriveCodeRequest(BaseModel):
  """Authorization code de Google Identity Services (offline)."""
  code: str = Field(..., min_length=10)


class DriveAccessTokenRequest(BaseModel):
  """Access token de corto plazo (y refresh opcional)."""
  access_token: str
  refresh_token: Optional[str] = None
  expires_in: int = 3600


@router.post("/verify", response_model=AuthResponse)
async def verify_token(login_data: UserLogin):
  try:
    user_info = firebase_auth.verify_token(login_data.token)
    if user_info:
      user_response = UserResponse(
        uid=user_info["uid"],
        email=user_info["email"],
        name=user_info.get("name"),
        picture=user_info.get("picture"),
        email_verified=user_info.get("email_verified", False),
      )
      return AuthResponse(success=True, user=user_response, message="Token verificado")
    return AuthResponse(success=False, message="Token inválido o expirado")
  except Exception as e:
    raise HTTPException(status_code=400, detail=f"Error verificando token: {str(e)}")


@router.get("/user/{uid}", response_model=UserResponse)
async def get_user_info(uid: str):
  try:
    user_info = firebase_auth.get_user(uid)
    if not user_info:
      raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserResponse(
      uid=user_info["uid"],
      email=user_info["email"],
      name=user_info.get("name"),
      picture=user_info.get("picture"),
      email_verified=user_info.get("email_verified", False),
    )
  except Exception as e:
    raise HTTPException(status_code=400, detail=f"Error obteniendo usuario: {str(e)}")


@router.post("/drive/code")
async def save_drive_authorization_code(
  body: DriveCodeRequest,
  email: str = Depends(get_current_user_email),
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
):
  """
  Intercambia el authorization code (GIS) por access+refresh token y los persiste.
  Así el backend puede renovar Drive sin que el usuario vuelva a entrar.
  """
  try:
    row = drive_token_service.exchange_authorization_code(db, email, body.code)
    return {
      "success": True,
      "email": email,
      "has_refresh_token": bool(row.refresh_token),
      "message": "Tokens de Drive guardados",
    }
  except Exception as e:
    logger.error("Error guardando code Drive para %s: %s", email, e, exc_info=True)
    raise HTTPException(status_code=400, detail=str(e))


@router.post("/drive/token")
async def save_drive_access_token(
  body: DriveAccessTokenRequest,
  email: str = Depends(get_current_user_email),
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
):
  """Guarda/actualiza access_token (y refresh si viene). Usado en keepalive del frontend."""
  try:
    row = drive_token_service.upsert_tokens(
      db,
      email=email,
      access_token=body.access_token,
      refresh_token=body.refresh_token,
      expires_in=body.expires_in,
    )
    return {
      "success": True,
      "email": email,
      "has_refresh_token": bool(row.refresh_token),
    }
  except Exception as e:
    raise HTTPException(status_code=400, detail=str(e))


@router.delete("/drive/token")
async def revoke_drive_tokens(
  email: str = Depends(get_current_user_email),
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
):
  """Borra tokens de Drive al cerrar sesión."""
  drive_token_service.delete_tokens(db, email)
  return {"success": True}
