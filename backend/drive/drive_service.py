from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Optional, Any
import os
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
        """
        Listar carpetas en Google Drive
        
        Args:
            parent_id: ID de la carpeta padre (None = raíz)
            max_results: Número máximo de resultados
            
        Returns:
            Lista de carpetas con id, name, parents
        """
        try:
            if not self.service:
                return []
            
            # Query para buscar solo carpetas
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                query += f" and '{parent_id}' in parents"
            
            results = self.service.files().list(
                q=query,
                pageSize=max_results,
                fields="files(id, name, parents, createdTime, modifiedTime)",
                orderBy="name"
            ).execute()
            
            folders = results.get('files', [])
            logger.info(f"Encontradas {len(folders)} carpetas")
            return folders
            
        except HttpError as e:
            logger.error(f"Error listando carpetas: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Error inesperado listando carpetas: {e}", exc_info=True)
            return []
    
    def list_files_in_folder(self, folder_id: str, file_types: Optional[List[str]] = None, recursive: bool = True) -> List[Dict[str, Any]]:
        """
        Listar archivos en una carpeta específica
        
        Args:
            folder_id: ID de la carpeta
            file_types: Lista de tipos MIME a filtrar (ej: ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
            recursive: Si es True, busca también en subcarpetas
            
        Returns:
            Lista de archivos con metadata
        """
        try:
            if not self.service:
                return []
            
            all_files = []
            
            # Primero, obtener todos los archivos directos (no carpetas)
            query = f"'{folder_id}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder'"
            
            logger.debug(f"🔍 Query Drive: {query}")
            
            results = self.service.files().list(
                q=query,
                pageSize=1000,
                fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents)",
                orderBy="name",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"📄 Encontrados {len(files)} archivos directos en carpeta {folder_id}")
            
            # Mostrar los tipos MIME encontrados
            mime_types = set([f.get('mimeType') for f in files])
            logger.debug(f"📋 Tipos MIME encontrados: {mime_types}")
            
            # Filtrar por tipos si se especifican
            if file_types:
                files = [f for f in files if f.get('mimeType') in file_types]
                logger.info(f"✅ Después de filtrar: {len(files)} archivos")
            
            all_files.extend(files)
            
            # Si es recursivo, buscar en subcarpetas
            if recursive:
                subfolder_query = f"'{folder_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
                subfolder_results = self.service.files().list(
                    q=subfolder_query,
                    pageSize=100,
                    fields="files(id, name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                
                subfolders = subfolder_results.get('files', [])
                logger.info(f"📁 Encontradas {len(subfolders)} subcarpetas")
                
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
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtener metadata de un archivo específico
        
        Args:
            file_id: ID del archivo
            
        Returns:
            Diccionario con metadata del archivo
        """
        try:
            if not self.service:
                return None
            
            file = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, createdTime, modifiedTime, parents, webViewLink"
            ).execute()
            
            return file
            
        except HttpError as e:
            logger.error(f"❌ Error obteniendo metadata: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado obteniendo metadata: {e}", exc_info=True)
            return None
    
    def download_file(self, file_id: str) -> Optional[bytes]:
        """
        Descargar contenido de un archivo
        
        Args:
            file_id: ID del archivo
            
        Returns:
            Contenido del archivo en bytes
        """
        try:
            socket.setdefaulttimeout(30)
            if not self.service:
                return None
            
            request = self.service.files().get_media(fileId=file_id)
            file_content = request.execute()
            
            logger.info(f"✅ Archivo descargado: {len(file_content)} bytes")
            return file_content
            
        except socket.timeout as e:
            logger.error(f"❌ Error descargando archivo (Timeout de 30s): {e}")
            return None
        except HttpError as e:
            logger.error(f"❌ Error descargando archivo (HTTP): {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado descargando archivo: {e}", exc_info=True)
            return None
    
    def search_files(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Buscar archivos en Drive
        
        Args:
            query: Nombre o parte del nombre a buscar
            max_results: Número máximo de resultados
            
        Returns:
            Lista de archivos que coinciden con la búsqueda
        """
        try:
            if not self.service:
                return []
            
            search_query = f"name contains '{query}' and trashed=false"
            
            results = self.service.files().list(
                q=search_query,
                pageSize=max_results,
                fields="files(id, name, mimeType, size, parents)",
                orderBy="name"
            ).execute()
            
            files = results.get('files', [])
            logger.info(f"✅ Encontrados {len(files)} archivos para '{query}'")
            return files
            
        except HttpError as e:
            logger.error(f"❌ Error buscando archivos: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"❌ Error inesperado buscando archivos: {e}", exc_info=True)
            return []


    def download_file_thread_safe(self, file_id: str, access_token: str) -> Optional[bytes]:
        """
        Descarga segura para hilos: Crea una instancia nueva del servicio para evitar conflictos SSL.
        """
        try:
            socket.setdefaulttimeout(30)
            # Construir servicio local (aislado del global)
            creds = Credentials(token=access_token)
            local_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            
            request = local_service.files().get_media(fileId=file_id)
            file_content = request.execute()
            
            logger.info(f"✅ Archivo descargado (Thread-Safe): {len(file_content)} bytes")
            return file_content
            
        except socket.timeout as e:
            logger.error(f"❌ Error descarga thread-safe (Timeout de 30s): {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error descarga thread-safe: {e}", exc_info=True)
            return None

    def register_webhook(self, folder_id: str, webhook_url: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Registrar un webhook de notificaciones push para una carpeta en Drive.
        """
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


# Instancia global del servicio
drive_service = DriveService()
