from typing import List, Optional

from pydantic import BaseModel, ConfigDict


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
    python_version: Optional[str] = None
    features: List[str]
    firebase_connected: bool = False
    drive_connected: bool = False
    database_connected: bool = False


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
    temas: List[str] = []
    descripcion: Optional[str] = None
    areas: List[str] = []
    herramientas: List[str] = []
    lenguajes: List[str] = []
    metodologias: List[str] = []
    model_config = ConfigDict(from_attributes=True)
