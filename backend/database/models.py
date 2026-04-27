from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .db_session import Base


class Docente(Base):
    __tablename__ = "docentes"
    
    id = Column(Integer, primary_key=True, index=True)
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    areas = Column(JSON, default=list)
    grado = Column(String, nullable=True)
    herramientas = Column(JSON, default=list)
    lenguajes = Column(JSON, default=list)
    metodologias = Column(JSON, default=list)
    contenidos = Column(JSON, default=list)
    cv_text = Column(Text, nullable=True)
    embedding_version = Column(String, default="v1.0")
    embedding_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    historiales = relationship("Historial", back_populates="docente")
    recomendaciones_cache = relationship("RecomendacionCache", back_populates="docente")

    def __repr__(self):
        return f"<Docente(id={self.id}, nombre='{self.nombre}')>"


class Curso(Base):
    __tablename__ = "cursos"
    
    id = Column(Integer, primary_key=True, index=True)
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    codigo = Column(String, nullable=True)
    ciclo = Column(Integer, nullable=True, default=1, index=True)
    descripcion = Column(Text, nullable=True)
    objetivos = Column(JSON, default=list)
    syllabus_text = Column(Text, nullable=True)
    areas = Column(JSON, default=list)
    herramientas = Column(JSON, default=list)
    lenguajes = Column(JSON, default=list)
    metodologias = Column(JSON, default=list)
    contenidos = Column(JSON, default=list)
    embedding_version = Column(String, default="v1.0")
    embedding_hash = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    historiales = relationship("Historial", back_populates="curso")
    recomendaciones = relationship("Recomendacion", back_populates="curso")
    recomendaciones_cache = relationship("RecomendacionCache", back_populates="curso")

    def __repr__(self):
        return f"<Curso(id={self.id}, nombre='{self.nombre}', ciclo={self.ciclo})>"


class Historial(Base):
    __tablename__ = "historiales"
    
    id = Column(Integer, primary_key=True, index=True)
    docente_id = Column(Integer, ForeignKey("docentes.id"), nullable=False)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    periodo = Column(String, nullable=False)
    resultado = Column(String, nullable=True)
    veces = Column(Integer, default=1)
    ultima_vez = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    docente = relationship("Docente", back_populates="historiales")
    curso = relationship("Curso", back_populates="historiales")

    __table_args__ = (
        Index('idx_historial_docente_curso', 'docente_id', 'curso_id'),
    )

    def __repr__(self):
        return f"<Historial(docente_id={self.docente_id}, curso_id={self.curso_id}, periodo='{self.periodo}')>"


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
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    docente_id = Column(Integer, ForeignKey("docentes.id"), nullable=False)
    score_combinado = Column(Float, nullable=False)
    score_historico = Column(Float, default=0.0)
    score_semantico = Column(Float, nullable=False)
    evidencias = Column(JSON, default=list)
    shap_explanations = Column(JSON, default=dict)
    ranking_position = Column(Integer, nullable=False)
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
        return f"<RecomendacionCache(curso_id={self.curso_id}, docente_id={self.docente_id}, rank={self.ranking_position}, score={self.score_combinado:.2f})>"


class Procesamiento(Base):
    __tablename__ = "procesamientos"
    
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(String, nullable=False)
    folder_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    files_processed = Column(Integer, default=0)
    files_total = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Procesamiento(id={self.id}, type='{self.type}', status='{self.status}')>"
