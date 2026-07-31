"""
Gestión de tokens OAuth de Google Drive por usuario.

- Guarda access_token + refresh_token en DB
- Renueva access_token automáticamente antes de descargar archivos
- La sesión de Drive dura hasta que el usuario revoque acceso o cierre sesión
  (al cerrar sesión se borran los tokens)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from backend.database.models import UserDriveToken

logger = logging.getLogger(__name__)


def _client_id() -> str:
  return (
    os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    or os.environ.get("GOOGLE_OAUTH_CLIENT_ID_PUBLIC")
    or ""
  ).strip()


def _client_secret() -> str:
  return (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def upsert_tokens(
  db: Session,
  email: str,
  access_token: str,
  refresh_token: Optional[str] = None,
  expires_in: int = 3600,
) -> UserDriveToken:
  email = (email or "").strip().lower()
  if not email or not access_token:
    raise ValueError("email y access_token son requeridos")

  row = db.query(UserDriveToken).filter(UserDriveToken.email == email).first()
  expiry = datetime.utcnow() + timedelta(seconds=max(60, int(expires_in) - 120))

  if row:
    row.access_token = access_token
    if refresh_token:
      # Solo sobrescribe si viene uno nuevo (Google a veces no reenvía refresh_token)
      row.refresh_token = refresh_token
    row.token_expiry = expiry
    row.updated_at = datetime.utcnow()
  else:
    row = UserDriveToken(
      email=email,
      access_token=access_token,
      refresh_token=refresh_token,
      token_expiry=expiry,
    )
    db.add(row)

  db.commit()
  db.refresh(row)
  logger.info("Tokens Drive guardados para %s (refresh=%s)", email, bool(row.refresh_token))
  return row


def exchange_authorization_code(db: Session, email: str, code: str) -> UserDriveToken:
  """Intercambia authorization code (GIS popup / postmessage) por tokens offline."""
  client_id = _client_id()
  client_secret = _client_secret()
  if not client_id or not client_secret:
    raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID/SECRET no configurados en el backend")

  resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
      "code": code,
      "client_id": client_id,
      "client_secret": client_secret,
      "redirect_uri": "postmessage",
      "grant_type": "authorization_code",
    },
    timeout=30,
  )
  if not resp.ok:
    logger.error("Error intercambiando code OAuth: %s %s", resp.status_code, resp.text[:500])
    raise RuntimeError(f"No se pudo intercambiar el código OAuth de Drive ({resp.status_code})")

  data = resp.json()
  access = data.get("access_token")
  if not access:
    raise RuntimeError("Respuesta OAuth sin access_token")

  return upsert_tokens(
    db,
    email=email,
    access_token=access,
    refresh_token=data.get("refresh_token"),
    expires_in=int(data.get("expires_in") or 3600),
  )


def _refresh_access_token(refresh_token: str) -> dict:
  client_id = _client_id()
  client_secret = _client_secret()
  if not client_id or not client_secret:
    raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID/SECRET no configurados")

  resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
      "client_id": client_id,
      "client_secret": client_secret,
      "refresh_token": refresh_token,
      "grant_type": "refresh_token",
    },
    timeout=30,
  )
  if not resp.ok:
    logger.error("Error refrescando access_token Drive: %s %s", resp.status_code, resp.text[:500])
    raise RuntimeError(f"Refresh de token Drive falló ({resp.status_code})")
  return resp.json()


def get_valid_access_token(
  db: Session,
  email: str,
  *,
  force_refresh: bool = False,
) -> Optional[str]:
  """
  Devuelve un access_token usable.
  Si está por caducar (o force_refresh=True) y hay refresh_token, renueva automáticamente.
  Con refresh_token la sesión de Drive sobrevive horas/días sin el usuario presente.
  """
  email = (email or "").strip().lower()
  if not email:
    return None

  row = db.query(UserDriveToken).filter(UserDriveToken.email == email).first()
  if not row:
    return None

  now = datetime.utcnow()
  needs_refresh = force_refresh
  if not needs_refresh:
    if not row.token_expiry or row.token_expiry <= now + timedelta(minutes=2):
      needs_refresh = True

  if not needs_refresh:
    return row.access_token

  if not row.refresh_token:
    logger.warning(
      "Token Drive de %s caducado/sin margen y no hay refresh_token. "
      "El usuario debe volver a autorizar Drive (login offline).",
      email,
    )
    return row.access_token if not force_refresh else None

  try:
    data = _refresh_access_token(row.refresh_token)
    access = data.get("access_token")
    if not access:
      return row.access_token if not force_refresh else None
    row.access_token = access
    row.token_expiry = now + timedelta(seconds=max(60, int(data.get("expires_in") or 3600) - 120))
    # Google no siempre devuelve refresh_token en el refresh
    if data.get("refresh_token"):
      row.refresh_token = data["refresh_token"]
    row.updated_at = now
    db.commit()
    logger.info("Access token Drive renovado para %s (force=%s)", email, force_refresh)
    return row.access_token
  except Exception as e:
    logger.error("No se pudo renovar token Drive de %s: %s", email, e, exc_info=True)
    return row.access_token if not force_refresh else None


def delete_tokens(db: Session, email: str) -> None:
  email = (email or "").strip().lower()
  if not email:
    return
  db.query(UserDriveToken).filter(UserDriveToken.email == email).delete()
  db.commit()
  logger.info("Tokens Drive eliminados para %s", email)
