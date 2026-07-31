"""Estado global para el procesamiento en segundo plano."""
import threading
import concurrent.futures

memoria_tareas = {}
folder_tokens = {}
folder_propietarios = {}
canal_a_entidad = {}
background_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
drive_download_lock = threading.Lock()
