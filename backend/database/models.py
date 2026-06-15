from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .db_session import Base


class Docente(Base):
    __tablename__ = "docentes"
    
    id = Column(Integer, primary_key=True, index=True)
    id_upao = Column(String, unique=True, index=True, nullable=True) # ID extraído de los horarios
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    grado = Column(String, nullable=True)
    entidades_clave = Column(JSON, default=list) # Reemplaza a las 5 columnas anteriores
    competencias_tecnicas = Column(Text, nullable=True) # Reemplaza a perfil_sintetico/cv_text
    embedding_version = Column(String, default="v1.0")
    embedding_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recomendaciones_cache = relationship("RecomendacionCache", back_populates="docente", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Docente(id={self.id}, nombre='{self.nombre}')>"


class Curso(Base):
    __tablename__ = "cursos"
    
    id = Column(Integer, primary_key=True, index=True)
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    codigo = Column(String, nullable=True)
    ciclo = Column(Integer, nullable=True, default=1, index=True)
    temas = Column(JSON, default=list)  # Temas semanales extraídos del sílabo
    embedding_version = Column(String, default="v1.0")
    embedding_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recomendaciones = relationship("Recomendacion", back_populates="curso", cascade="all, delete-orphan")
    recomendaciones_cache = relationship("RecomendacionCache", back_populates="curso", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Curso(id={self.id}, nombre='{self.nombre}', ciclo={self.ciclo})>"


class Historial(Base):
    __tablename__ = "historiales"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre_docente = Column(String, nullable=False, index=True)
    nombre_curso = Column(String, nullable=False, index=True)
    veces = Column(Integer, default=1)
    ultima_vez = Column(String, nullable=False)

    __table_args__ = (
        Index('idx_historial_docente_curso', 'nombre_docente', 'nombre_curso'),
    )

    def __repr__(self):
        return f"<Historial(nombre_docente='{self.nombre_docente}', curso='{self.nombre_curso}', veces={self.veces})>"


class Recomendacion(Base):
    __tablename__ = "recomendaciones"
    
    id = Column(Integer, primary_key=True, index=True)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    docente_id = Column(Integer, ForeignKey("docentes.id"), nullable=False)
    score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    explanations = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_valid = Column(Boolean, default=True)
    curso = relationship("Curso", back_populates="recomendaciones")
    docente = relationship("Docente")

    def __repr__(self):
        return f"<Recomendacion(curso_id={self.curso_id}, docente_id={self.docente_id}, score={self.score})>"


class RecomendacionCache(Base):
    __tablename__ = "recomendaciones_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    curso_id = Column(Integer, ForeignKey("cursos.id", ondelete="CASCADE"), nullable=False)
    docente_id = Column(Integer, ForeignKey("docentes.id", ondelete="CASCADE"), nullable=False)
    score_combinado = Column(Float, nullable=False)
    score_est = Column(Float, nullable=False, default=0.0)
    score_tac = Column(Float, nullable=False, default=0.0)
    evidencias = Column(JSON, default=list)
    shap_explanations = Column(JSON, default=dict)
    version_algoritmo = Column(String(50), default="sbert_v1.1")
    embed_version = Column(String(50), default="v1.1")
    fecha_generada = Column(DateTime, default=datetime.utcnow, nullable=False)
    curso = relationship("Curso", back_populates="recomendaciones_cache")
    docente = relationship("Docente", back_populates="recomendaciones_cache")

    __table_args__ = (
        Index('idx_recomendacion_curso', 'curso_id'),
        Index('idx_recomendacion_curso_fecha', 'curso_id', 'fecha_generada'),
        Index('idx_recomendacion_docente', 'docente_id'),
    )

    def __repr__(self):
        return f"<RecomendacionCache(curso_id={self.curso_id}, docente_id={self.docente_id}, score={self.score_combinado:.2f})>"


class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    drive_file_id = Column(String, nullable=False, index=True)
    evento_tipo = Column(String, nullable=False) # CREATE, UPDATE, DELETE
    entidad = Column(String, nullable=False)     # CV, SILABO, HORARIO
    status = Column(String, nullable=False)      # SUCCESS, FAILED
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WebhookLog(id={self.id}, evento='{self.evento_tipo}', status='{self.status}')>"
