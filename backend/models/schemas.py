from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class UserLogin(BaseModel):
    token: str

class UserResponse(BaseModel):
    uid: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    email_verified: bool = False

class AuthResponse(BaseModel):
    success: bool
    user: Optional[UserResponse] = None
    message: str

class SystemStatus(BaseModel):
    status: str
    version: str
    python_version: str
    features: List[str]
    firebase_connected: bool = False
    drive_connected: bool = False
    database_connected: bool = False

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None

class DriveFolder(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    mime_type: str = "application/vnd.google-apps.folder"

class DriveFile(BaseModel):
    id: str
    name: str
    mime_type: str
    size: Optional[int] = None
    folder_path: str
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None

class FolderSelection(BaseModel):
    folder_type: str
    folder_id: str
    folder_name: str

class FileScanResponse(BaseModel):
    success: bool
    files_found: int
    files: List[DriveFile]
    message: str

class ProcessingStatus(BaseModel):
    status: str
    progress: int
    message: str
    files_processed: int = 0
    total_files: int = 0

class Docente(BaseModel):
    id: int
    drive_file_id: str
    nombre: str
    email: Optional[str] = None
    grado: Optional[str] = None
    areas: List[str] = []
    herramientas: List[str] = []
    lenguajes: List[str] = []
    metodologias: List[str] = []
    model_config = ConfigDict(from_attributes=True)

class Curso(BaseModel):
    id: int
    drive_file_id: str
    nombre: str
    codigo: Optional[str] = None
    ciclo: int
    descripcion: Optional[str] = None
    areas: List[str] = []
    herramientas: List[str] = []
    lenguajes: List[str] = []
    metodologias: List[str] = []
    model_config = ConfigDict(from_attributes=True)

class EvidenciasXAI(BaseModel):
    areas: List[str] = []
    lenguajes: List[str] = []
    herramientas: List[str] = []
    metodologias: List[str] = []

class DocenteRecommendation(BaseModel):
    docente_id: int
    nombre: str
    email: Optional[str] = None
    grado: Optional[str] = None
    score_combinado: float
    score_historico: float
    score_semantico: float
    evidencias: EvidenciasXAI
    shap_explanations: Dict = {}
    from_cache: bool
    areas: List[str] = []
    herramientas: List[str] = []
    lenguajes: List[str] = []
    metodologias: List[str] = []

class RecommendationResponse(BaseModel):
    success: bool
    curso_id: int
    curso_nombre: str
    total_recommendations: int
    recommendations: List[DocenteRecommendation]
