from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Optional, Any
import socket
import logging

logger = logging.getLogger(__name__)


class DriveService:
    """Servicio para interactuar con Google Drive API"""

    def __init__(self):
        self.service = None

    def build_service(self, access_token: str):
        """
        Construir servicio de Drive con el token de acceso del usuario

        Args:
            access_token: Token de acceso OAuth2 del usuario
        """
        try:
            credentials = Credentials(token=access_token)
            self.service = build('drive', 'v3', credentials=credentials)
            return True
        except Exception as e:
            logger.error(f"Error construyendo servicio Drive: {e}", exc_info=True)
            return False

    def list_folders(self, parent_id: Optional[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """Listar carpetas en Google Drive"""
        try:
            if not self.service:
                return []

            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, parents)",
                orderBy="name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            return results.get('files', [])

        except HttpError as e:
            logger.error(f"❌ Error listando carpetas (HTTP): {e}")
            raise Exception(f"Error de permisos o conexión con Drive: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado listando carpetas: {e}", exc_info=True)
            raise Exception(f"Error inesperado al leer Drive: {e}")

    def list_files_in_folder(self, folder_id: str, file_types: Optional[List[str]] = None, recursive: bool = True) -> List[Dict[str, Any]]:
        """Listar archivos en una carpeta de Drive (opcionalmente recursivo)."""
        try:
            if not self.service:
                return []

            all_files: List[Dict[str, Any]] = []

            query = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
            if file_types:
                mime_q = " or ".join([f"mimeType='{m}'" for m in file_types])
                query = f"'{folder_id}' in parents and trashed=false and ({mime_q})"

            page_token = None
            while True:
                results = self.service.files().list(
                    q=query,
                    pageSize=1000,
                    fields="nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, parents)",
                    orderBy="name",
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
                all_files.extend(results.get('files', []))
                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            if recursive:
                folder_query = f"'{folder_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
                subfolders = self.service.files().list(
                    q=folder_query,
                    pageSize=1000,
                    fields="files(id, name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute().get('files', [])

                for subfolder in subfolders:
                    logger.debug(f"  📁 Buscando en subcarpeta: {subfolder['name']}")
                    subfolder_files = self.list_files_in_folder(subfolder['id'], file_types, recursive=True)
                    all_files.extend(subfolder_files)

            logger.info(f"✅ Total: {len(all_files)} archivos encontrados")
            return all_files

        except HttpError as e:
            logger.error(f"❌ Error listando archivos (HTTP): {e}")
            raise Exception(f"Error de permisos o conexión con Drive: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado listando archivos: {e}", exc_info=True)
            raise Exception(f"Error inesperado al leer Drive: {e}")

    def download_file_thread_safe(self, file_id: str, access_token: str) -> Optional[bytes]:
        """
        Descarga segura para hilos. No intenta refresh localmente:
        el access_token debe venir ya renovado de drive_token_service.
        """
        try:
            socket.setdefaulttimeout(60)
            # expiry lejos en el futuro para que la librería no intente refresh sin refresh_token
            creds = Credentials(token=access_token)
            local_service = build('drive', 'v3', credentials=creds, cache_discovery=False)

            request = local_service.files().get_media(fileId=file_id)
            file_content = request.execute()

            logger.info(f"✅ Archivo descargado (Thread-Safe): {len(file_content)} bytes")
            return file_content

        except socket.timeout as e:
            logger.error(f"❌ Error descarga thread-safe (Timeout): {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error descarga thread-safe: {e}", exc_info=True)
            return None

    def register_webhook(self, folder_id: str, webhook_url: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """Registrar un webhook de notificaciones push para una carpeta en Drive."""
        try:
            if not self.service:
                return None

            body = {
                "id": channel_id,
                "type": "web_hook",
                "address": webhook_url
            }

            response = self.service.files().watch(
                fileId=folder_id,
                body=body
            ).execute()

            logger.info(f"✅ Webhook registrado para carpeta {folder_id}: {response}")
            return response

        except HttpError as e:
            logger.error(f"❌ Error registrando webhook: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado registrando webhook: {e}", exc_info=True)
            return None


drive_service = DriveService()
