"""Router de Google Drive."""

import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from backend.drive.drive_service import drive_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/drive", tags=["drive"])


@router.get("/folders")
async def list_drive_folders(
  parent_id: Optional[str] = None,
  authorization: Optional[str] = Header(None),
):
  if not authorization:
    raise HTTPException(status_code=401, detail="Token requerido")
  try:
    access_token = authorization.replace("Bearer ", "")
    if not drive_service.build_service(access_token):
      raise HTTPException(status_code=500, detail="Error conectando con Drive")
    folders = drive_service.list_folders(parent_id=parent_id)
    return {"success": True, "count": len(folders), "folders": folders}
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error listando carpetas: {str(e)}")


@router.get("/folders/{folder_id}/files")
async def list_folder_files(
  folder_id: str,
  authorization: Optional[str] = Header(None),
):
  if not authorization:
    raise HTTPException(status_code=401, detail="Token de autorización requerido")
  try:
    access_token = authorization.replace("Bearer ", "")
    if not drive_service.build_service(access_token):
      raise HTTPException(status_code=500, detail="Error conectando con Drive")
    file_types = [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    files = drive_service.list_files_in_folder(folder_id, file_types)
    pdf_count = sum(1 for f in files if f["mimeType"] == "application/pdf")
    docx_count = sum(1 for f in files if "wordprocessingml" in f["mimeType"])

    return {
      "success": True,
      "folder_id": folder_id,
      "total_files": len(files),
      "pdf_files": pdf_count,
      "docx_files": docx_count,
      "files": files,
    }
  except Exception as e:
    logger.error(f"Error listando archivos: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error listando archivos: {str(e)}")
