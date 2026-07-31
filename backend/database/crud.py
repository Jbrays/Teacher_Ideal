import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.database.models import (
    Curso,
    CursoNodo,
    Docente,
    DocenteNodo,
    Historial,
    RecomendacionCache,
    WebhookLog,
)

logger = logging.getLogger(__name__)


def _apply_workspaces(query, model, workspaces):
    if workspaces is not None:
        query = query.filter(model.propietario_email.in_(workspaces))
    return query


def get_docente_by_id(db: Session, docente_id: int) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.id == docente_id).first()


def get_docente_by_drive_id(db: Session, drive_file_id: str) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.drive_file_id == drive_file_id).first()


def get_all_docentes(db: Session, skip: int = 0, limit: int = 100, workspaces: Optional[List[str]] = None) -> List[Docente]:
    query = db.query(Docente)
    query = _apply_workspaces(query, Docente, workspaces)
    return query.offset(skip).limit(limit).all()


def delete_docente(db: Session, docente_id: int) -> bool:
    docente = get_docente_by_id(db, docente_id)
    if docente:
        db.delete(docente)
        db.commit()
        return True
    return False


def get_curso_by_id(db: Session, curso_id: int) -> Optional[Curso]:
    return db.query(Curso).filter(Curso.id == curso_id).first()


def get_curso_by_drive_id(db: Session, drive_file_id: str) -> Optional[Curso]:
    return db.query(Curso).filter(Curso.drive_file_id == drive_file_id).first()


def get_cursos_by_ciclo(db: Session, ciclo: int, workspaces: Optional[List[str]] = None) -> List[Curso]:
    query = db.query(Curso).filter(Curso.ciclo == ciclo)
    query = _apply_workspaces(query, Curso, workspaces)
    return query.all()


def get_all_cursos(db: Session, skip: int = 0, limit: int = 100, workspaces: Optional[List[str]] = None) -> List[Curso]:
    query = db.query(Curso)
    query = _apply_workspaces(query, Curso, workspaces)
    return query.offset(skip).limit(limit).all()


def get_all_ciclos(db: Session, workspaces: Optional[List[str]] = None) -> List[int]:
    query = db.query(Curso.ciclo)
    if workspaces is not None:
        query = query.filter(Curso.propietario_email.in_(workspaces))
    ciclos = query.distinct().order_by(Curso.ciclo).all()
    return [c[0] for c in ciclos]


def get_all_historiales(db: Session, workspaces: Optional[List[str]] = None) -> List[Historial]:
    query = db.query(Historial)
    query = _apply_workspaces(query, Historial, workspaces)
    return query.all()


def create_webhook_log(
    db: Session,
    drive_file_id: str,
    evento_tipo: str,
    entidad: str,
    status: str,
    error_message: str = None,
    propietario_email: str = "legacy@upao.edu.pe",
) -> WebhookLog:
    log = WebhookLog(
        drive_file_id=drive_file_id,
        evento_tipo=evento_tipo,
        entidad=entidad,
        status=status,
        error_message=error_message,
        propietario_email=propietario_email,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def update_webhook_log_status_by_id(db: Session, log_id: int, status: str) -> Optional[WebhookLog]:
    log = db.query(WebhookLog).filter(WebhookLog.id == log_id).first()
    if log:
        log.status = status
        db.commit()
        db.refresh(log)
    return log


def get_active_processing_count(db: Session, workspaces: Optional[List[str]] = None) -> int:
    umbral = datetime.utcnow() - timedelta(minutes=15)
    query = db.query(WebhookLog).filter(
        or_(
            WebhookLog.status == "received",
            and_(WebhookLog.status == "processing", WebhookLog.updated_at >= umbral),
        )
    )
    query = _apply_workspaces(query, WebhookLog, workspaces)
    return query.count()


def get_recomendaciones_cache(
    db: Session,
    curso_id: int,
    max_age_days: Optional[int] = 7,
    workspaces: Optional[List[str]] = None,
) -> Optional[List[RecomendacionCache]]:
    query = db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id)
    query = _apply_workspaces(query, RecomendacionCache, workspaces)
    if max_age_days is not None:
        fecha_limite = datetime.utcnow() - timedelta(days=max_age_days)
        query = query.filter(RecomendacionCache.fecha_generada >= fecha_limite)
    cache = query.order_by(RecomendacionCache.score_combinado.desc()).all()
    return cache if cache else None


def save_recomendaciones_cache(
    db: Session,
    curso_id: int,
    recommendations: List[dict],
    version_algoritmo: str = "sbert_v1.0",
    propietario_email: str = "legacy@upao.edu.pe",
) -> None:
    try:
        db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id).delete()
        for rec in recommendations:
            cache_entry = RecomendacionCache(
                curso_id=curso_id,
                docente_id=rec["docente_id"],
                score_combinado=rec.get("score_combinado", 0.0),
                shap_explanations=rec.get("shap_explanations", {}),
                version_algoritmo=version_algoritmo,
                fecha_generada=datetime.utcnow(),
                propietario_email=propietario_email,
            )
            db.add(cache_entry)
        db.commit()
    except Exception:
        db.rollback()
        raise


def upsert_docente_nodo(
    db: Session,
    docente_id: int,
    nodo_id: str,
    peso: float,
    evidencias: List[dict],
    explicito: bool = True,
    recencia: Optional[str] = None,
    version: str = "1.0.0",
) -> DocenteNodo:
    import json

    dn = (
        db.query(DocenteNodo)
        .filter(
            DocenteNodo.docente_id == docente_id,
            DocenteNodo.nodo_id == nodo_id,
        )
        .first()
    )

    if dn:
        existing = dn.evidencias or []
        seen = {json.dumps(e, sort_keys=True) for e in existing}
        for e in evidencias:
            key = json.dumps(e, sort_keys=True)
            if key not in seen:
                existing.append(e)
                seen.add(key)
        dn.evidencias = existing
        dn.peso = max(dn.peso, peso) + (0.1 * max(0, len(existing) - 1))
        dn.explicito = dn.explicito and explicito
        dn.recencia = recencia or dn.recencia
        dn.version = version
    else:
        dn = DocenteNodo(
            docente_id=docente_id,
            nodo_id=nodo_id,
            peso=peso,
            evidencias=evidencias,
            explicito=explicito,
            recencia=recencia,
            version=version,
        )
        db.add(dn)

    db.flush()
    db.refresh(dn)
    return dn


def upsert_curso_nodo(
    db: Session,
    curso_id: int,
    nodo_id: str,
    peso_centralidad: float,
    semanas: List[int],
    evidencias: List[dict],
    version: str = "1.0.0",
) -> CursoNodo:
    import json

    cn = (
        db.query(CursoNodo)
        .filter(
            CursoNodo.curso_id == curso_id,
            CursoNodo.nodo_id == nodo_id,
        )
        .first()
    )

    if cn:
        existing = cn.evidencias or []
        seen = {json.dumps(e, sort_keys=True) for e in existing}
        for e in evidencias:
            key = json.dumps(e, sort_keys=True)
            if key not in seen:
                existing.append(e)
                seen.add(key)
        cn.evidencias = existing
        cn.semanas = sorted(list(set((cn.semanas or []) + semanas)))
        cn.peso_centralidad = max(cn.peso_centralidad, peso_centralidad)
        cn.version = version
    else:
        cn = CursoNodo(
            curso_id=curso_id,
            nodo_id=nodo_id,
            peso_centralidad=peso_centralidad,
            semanas=sorted(list(set(semanas))),
            evidencias=evidencias,
            version=version,
        )
        db.add(cn)

    db.flush()
    db.refresh(cn)
    return cn


def add_colaborador(db: Session, propietario_email: str, invitado_email: str):
    from backend.database.models import Colaborador

    existing = (
        db.query(Colaborador)
        .filter(
            Colaborador.propietario_email == propietario_email,
            Colaborador.invitado_email == invitado_email,
        )
        .first()
    )
    if not existing:
        colab = Colaborador(propietario_email=propietario_email, invitado_email=invitado_email)
        db.add(colab)
        db.commit()
    return True


def get_colaboradores(db: Session, propietario_email: str):
    from backend.database.models import Colaborador

    return db.query(Colaborador).filter(Colaborador.propietario_email == propietario_email).all()


def remove_colaborador(db: Session, propietario_email: str, invitado_email: str):
    from backend.database.models import Colaborador

    db.query(Colaborador).filter(
        Colaborador.propietario_email == propietario_email,
        Colaborador.invitado_email == invitado_email,
    ).delete()
    db.commit()
    return True
