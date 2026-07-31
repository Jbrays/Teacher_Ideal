"""Router de estado del sistema."""

import logging
import sys
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.db_session import get_db
from backend.database import crud
from backend.database.models import Docente
from backend.auth.firebase import firebase_auth
from backend.drive.drive_service import drive_service
from backend.models.schemas import SystemStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])


@router.get("/status", response_model=SystemStatus)
async def api_status(db: Session = Depends(get_db)):
  db_ok = False
  try:
    db.query(Docente).first()
    db_ok = True
  except Exception:
    db_ok = False
  return SystemStatus(
    status="running",
    version="1.0.0",
    features=["Firebase Auth", "Drive Integration", "NER Processing", "SBERT Recommendations", "Schedule Analysis"],
    firebase_connected=firebase_auth.app is not None,
    drive_connected=drive_service.service is not None,
    database_connected=db_ok,
    python_version=sys.version,
  )


@router.get("/system/status")
async def get_system_status(db: Session = Depends(get_db)):
  count = crud.get_active_processing_count(db)
  return {"is_processing": count > 0, "pending_count": count}
