from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, Boolean, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .db_session import Base


class Colaborador(Base):
    __tablename__ = "colaboradores"
    
    id = Column(Integer, primary_key=True, index=True)
    propietario_email = Column(String, nullable=False, index=True)
    invitado_email = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('propietario_email', 'invitado_email', name='uq_colaboracion'),
    )

    def __repr__(self):
        return f"<Colaborador(propietario='{self.propietario_email}', invitado='{self.invitado_email}')>"

class Docente(Base):
    __tablename__ = "docentes"
    
    id = Column(Integer, primary_key=True, index=True)
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    grado = Column(String, nullable=True)
    perfil_tecnico = Column(JSON, default=list)
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
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    drive_file_id = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False, index=True)
    ciclo = Column(Integer, nullable=True, default=1, index=True)
    perfil_tecnico = Column(JSON, default=list)
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
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    nombre_docente = Column(String, nullable=False, index=True)
    nombre_curso = Column(String, nullable=False, index=True)
    ultima_vez = Column(String, nullable=False)

    __table_args__ = (
        Index('idx_historial_docente_curso', 'nombre_docente', 'nombre_curso'),
    )

    def __repr__(self):
        return f"<Historial(nombre_docente='{self.nombre_docente}', curso='{self.nombre_curso}')>"


class Recomendacion(Base):
    __tablename__ = "recomendaciones"
    
    id = Column(Integer, primary_key=True, index=True)
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
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
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    curso_id = Column(Integer, ForeignKey("cursos.id", ondelete="CASCADE"), nullable=False)
    docente_id = Column(Integer, ForeignKey("docentes.id", ondelete="CASCADE"), nullable=False)
    score_combinado = Column(Float, nullable=False)
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


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    usuario_email = Column(String, nullable=False, index=True)
    accion = Column(String, nullable=False)
    detalles = Column(Text, nullable=True)
    fecha_hora = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AuditLog(usuario='{self.usuario_email}', accion='{self.accion}')>"

class WebhookLog(Base):
    __tablename__ = "webhook_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    propietario_email = Column(String, nullable=False, index=True, server_default="legacy@upao.edu.pe")
    drive_file_id = Column(String, nullable=False, index=True)
    evento_tipo = Column(String, nullable=False) # CREATE, UPDATE, DELETE
    entidad = Column(String, nullable=False)     # CV, SILABO, HORARIO
    status = Column(String, nullable=False)      # SUCCESS, FAILED
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<WebhookLog(id={self.id}, evento='{self.evento_tipo}', status='{self.status}')>"


class UserDriveToken(Base):
    """
    Tokens OAuth de Google Drive por usuario.
    El access_token se renueva con refresh_token mientras el usuario no revoque acceso.
    """
    __tablename__ = "user_drive_tokens"

    email = Column(String, primary_key=True, index=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<UserDriveToken(email='{self.email}', expiry={self.token_expiry})>"


class Nodo(Base):
    """
    Catálogo de nodos de la taxonomía compartida. Se sincroniza con
    backend/taxonomy/taxonomy.json; los ids son estables y no se regeneran.
    """
    __tablename__ = "nodos"

    id = Column(String, primary_key=True, index=True)
    parent_id = Column(String, ForeignKey("nodos.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    node_type = Column(String, nullable=False)  # root | branch | leaf
    aliases = Column(JSON, default=list)
    domain = Column(String, nullable=True)
    source = Column(String, nullable=True, index=True)
    source_version = Column(String, nullable=True)
    external_id = Column(Text, nullable=True)
    external_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    kind = Column(String, nullable=False, default="concept", index=True)
    labels = Column(JSON, default=dict)
    embedding_enabled = Column(Boolean, nullable=False, default=True)
    source_attributes = Column(JSON, default=dict)
    version = Column(String, default="1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)

    children = relationship("Nodo", backref="parent", remote_side=[id])

    def __repr__(self):
        return f"<Nodo(id='{self.id}', name='{self.name}')>"


class NodoRelacion(Base):
    """Arista tipada y trazable entre dos nodos del catálogo."""

    __tablename__ = "nodo_relaciones"

    id = Column(Integer, primary_key=True, index=True)
    source_nodo_id = Column(
        String,
        ForeignKey("nodos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_nodo_id = Column(
        String,
        ForeignKey("nodos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type = Column(String, nullable=False, index=True)
    weight = Column(Float, nullable=False, default=0.0)
    directed = Column(Boolean, nullable=False, default=False)
    source = Column(String, nullable=False)
    source_version = Column(String, nullable=True)
    external_id = Column(Text, nullable=True)
    provenance = Column(JSON, default=dict)
    version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_nodo = relationship("Nodo", foreign_keys=[source_nodo_id])
    target_nodo = relationship("Nodo", foreign_keys=[target_nodo_id])

    __table_args__ = (
        UniqueConstraint(
            "source_nodo_id",
            "target_nodo_id",
            "relation_type",
            "source",
            name="uq_nodo_relacion",
        ),
        Index(
            "idx_nodo_relacion_pair",
            "source_nodo_id",
            "target_nodo_id",
        ),
    )


class DocenteNodo(Base):
    """
    Perfil técnico normalizado de un docente. Cada fila es un nodo de la
    taxonomía que el docente domina, con su peso acumulado y las evidencias
    textuales originales que lo sustentan.
    """
    __tablename__ = "docente_nodos"

    id = Column(Integer, primary_key=True, index=True)
    docente_id = Column(Integer, ForeignKey("docentes.id", ondelete="CASCADE"), nullable=False)
    nodo_id = Column(String, ForeignKey("nodos.id", ondelete="CASCADE"), nullable=False)
    peso = Column(Float, nullable=False, default=1.0)
    evidencias = Column(JSON, default=list)
    explicito = Column(Boolean, default=True)
    recencia = Column(String, nullable=True)
    version = Column(String, default="1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    docente = relationship("Docente")
    nodo = relationship("Nodo")

    __table_args__ = (
        UniqueConstraint("docente_id", "nodo_id", name="uq_docente_nodo"),
        Index("idx_docente_nodo_docente", "docente_id"),
        Index("idx_docente_nodo_nodo", "nodo_id"),
    )

    def __repr__(self):
        return f"<DocenteNodo(docente_id={self.docente_id}, nodo_id='{self.nodo_id}', peso={self.peso})>"


class CursoNodo(Base):
    """
    Requisitos técnicos de un curso expresados como nodos de la taxonomía.
    El peso_centralidad refleja cuántas semanas del temario tocan ese nodo.
    """
    __tablename__ = "curso_nodos"

    id = Column(Integer, primary_key=True, index=True)
    curso_id = Column(Integer, ForeignKey("cursos.id", ondelete="CASCADE"), nullable=False)
    nodo_id = Column(String, ForeignKey("nodos.id", ondelete="CASCADE"), nullable=False)
    peso_centralidad = Column(Float, nullable=False, default=1.0)
    semanas = Column(JSON, default=list)
    evidencias = Column(JSON, default=list)
    version = Column(String, default="1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    curso = relationship("Curso")
    nodo = relationship("Nodo")

    __table_args__ = (
        UniqueConstraint("curso_id", "nodo_id", name="uq_curso_nodo"),
        Index("idx_curso_nodo_curso", "curso_id"),
        Index("idx_curso_nodo_nodo", "nodo_id"),
    )

    def __repr__(self):
        return f"<CursoNodo(curso_id={self.curso_id}, nodo_id='{self.nodo_id}', centralidad={self.peso_centralidad})>"
