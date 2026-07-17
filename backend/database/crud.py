import logging
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from typing import List, Optional

logger = logging.getLogger(__name__)
from backend.database.models import (
    Docente, Curso, Historial, Recomendacion, WebhookLog, RecomendacionCache,
    Nodo, DocenteNodo, CursoNodo,
)
from datetime import datetime, timedelta
import json
import os


def _apply_workspaces(query, model, workspaces):
    if workspaces is not None:
        query = query.filter(model.propietario_email.in_(workspaces))
    return query


def create_docente(db: Session, drive_file_id: str, nombre: str, propietario_email: str = "legacy@upao.edu.pe", **kwargs) -> Docente:
    docente = Docente(drive_file_id=drive_file_id, nombre=nombre, propietario_email=propietario_email, **kwargs)
    db.add(docente)
    db.commit()
    db.refresh(docente)
    return docente

def get_docente_by_id(db: Session, docente_id: int) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.id == docente_id).first()

def get_docente_by_drive_id(db: Session, drive_file_id: str) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.drive_file_id == drive_file_id).first()

def get_all_docentes(db: Session, skip: int = 0, limit: int = 100, workspaces: Optional[List[str]] = None) -> List[Docente]:
    query = db.query(Docente)
    query = _apply_workspaces(query, Docente, workspaces)
    return query.offset(skip).limit(limit).all()

def update_docente(db: Session, docente_id: int, **kwargs) -> Optional[Docente]:
    docente = get_docente_by_id(db, docente_id)
    if docente:
        for key, value in kwargs.items():
            setattr(docente, key, value)
        docente.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(docente)
    return docente

def delete_docente(db: Session, docente_id: int) -> bool:
    docente = get_docente_by_id(db, docente_id)
    if docente:
        db.delete(docente)
        db.commit()
        return True
    return False


def create_curso(db: Session, drive_file_id: str, nombre: str, ciclo: int, propietario_email: str = "legacy@upao.edu.pe", **kwargs) -> Curso:
    curso = Curso(drive_file_id=drive_file_id, nombre=nombre, ciclo=ciclo, propietario_email=propietario_email, **kwargs)
    db.add(curso)
    db.commit()
    db.refresh(curso)
    return curso

def get_curso_by_id(db: Session, curso_id: int) -> Optional[Curso]:
    return db.query(Curso).filter(Curso.id == curso_id).first()

def get_curso(db: Session, curso_id: int) -> Optional[Curso]:
    return get_curso_by_id(db, curso_id)

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

def update_curso(db: Session, curso_id: int, **kwargs) -> Optional[Curso]:
    curso = get_curso_by_id(db, curso_id)
    if curso:
        for key, value in kwargs.items():
            setattr(curso, key, value)
        curso.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(curso)
    return curso


def upsert_historial(db: Session, nombre_docente: str, nombre_curso: str, periodo: str, propietario_email: str = "legacy@upao.edu.pe") -> Historial:
    historial = db.query(Historial).filter(
        Historial.nombre_docente == nombre_docente,
        Historial.nombre_curso == nombre_curso
    ).first()
    
    if historial:
        historial.ultima_vez = periodo
    else:
        historial = Historial(
            nombre_docente=nombre_docente,
            nombre_curso=nombre_curso,
            ultima_vez=periodo,
            propietario_email=propietario_email,
        )
        db.add(historial)
        
    db.commit()
    db.refresh(historial)
    return historial

def get_all_historiales(db: Session, workspaces: Optional[List[str]] = None) -> List[Historial]:
    query = db.query(Historial)
    query = _apply_workspaces(query, Historial, workspaces)
    return query.all()


def create_recomendacion(db: Session, curso_id: int, docente_id: int, score: float, confidence: float, explanations: list, propietario_email: str = "legacy@upao.edu.pe") -> Recomendacion:
    recomendacion = Recomendacion(curso_id=curso_id, docente_id=docente_id, score=score, confidence=confidence, explanations=explanations, propietario_email=propietario_email)
    db.add(recomendacion)
    db.commit()
    db.refresh(recomendacion)
    return recomendacion

def get_recomendaciones_by_curso(db: Session, curso_id: int, limit: int = 10, workspaces: Optional[List[str]] = None) -> List[Recomendacion]:
    query = db.query(Recomendacion).filter(Recomendacion.curso_id == curso_id, Recomendacion.is_valid == True)
    query = _apply_workspaces(query, Recomendacion, workspaces)
    return query.order_by(Recomendacion.score.desc()).limit(limit).all()

def invalidate_recomendaciones_by_curso(db: Session, curso_id: int, workspaces: Optional[List[str]] = None):
    query = db.query(Recomendacion).filter(Recomendacion.curso_id == curso_id)
    query = _apply_workspaces(query, Recomendacion, workspaces)
    query.update({"is_valid": False})
    db.commit()


def create_webhook_log(db: Session, drive_file_id: str, evento_tipo: str, entidad: str, status: str, error_message: str = None, propietario_email: str = "legacy@upao.edu.pe") -> WebhookLog:
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

def update_webhook_log_status(db: Session, drive_file_id: str, status: str) -> Optional[WebhookLog]:
    log = db.query(WebhookLog).filter(WebhookLog.drive_file_id == drive_file_id).order_by(WebhookLog.timestamp.desc()).first()
    if log:
        log.status = status
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
    from datetime import datetime, timedelta
    umbral = datetime.utcnow() - timedelta(minutes=15)
    query = db.query(WebhookLog).filter(
        or_(
            WebhookLog.status == "received",
            and_(WebhookLog.status == "processing", WebhookLog.updated_at >= umbral)
        )
    )
    query = _apply_workspaces(query, WebhookLog, workspaces)
    return query.count()


def get_recomendaciones_cache(db: Session, curso_id: int, max_age_days: Optional[int] = 7, workspaces: Optional[List[str]] = None) -> Optional[List[RecomendacionCache]]:
    query = db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id)
    query = _apply_workspaces(query, RecomendacionCache, workspaces)
    if max_age_days is not None:
        fecha_limite = datetime.utcnow() - timedelta(days=max_age_days)
        query = query.filter(RecomendacionCache.fecha_generada >= fecha_limite)
    cache = query.order_by(RecomendacionCache.score_combinado.desc()).all()
    return cache if cache else None

def save_recomendaciones_cache(db: Session, curso_id: int, recommendations: List[dict], version_algoritmo: str = "sbert_v1.0", propietario_email: str = "legacy@upao.edu.pe") -> None:
    try:
        db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id).delete()
        for idx, rec in enumerate(recommendations):
            cache_entry = RecomendacionCache(
                curso_id=curso_id,
                docente_id=rec['docente_id'],
                score_combinado=rec.get('score_combinado', 0.0),
                shap_explanations=rec.get('shap_explanations', {}),
                version_algoritmo=version_algoritmo,
                fecha_generada=datetime.utcnow(),
                propietario_email=propietario_email,
            )
            db.add(cache_entry)
        db.commit()
    except Exception:
        db.rollback()
        raise

def delete_recomendaciones_cache_by_docente(db: Session, docente_id: int) -> int:
    count = db.query(RecomendacionCache).filter(RecomendacionCache.docente_id == docente_id).delete()
    db.commit()
    return count

def delete_recomendaciones_cache_by_curso(db: Session, curso_id: int) -> int:
    count = db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id).delete()
    db.commit()
    return count

def get_cache_stats(db: Session, workspaces: Optional[List[str]] = None) -> dict:
    query = db.query(RecomendacionCache)
    query = _apply_workspaces(query, RecomendacionCache, workspaces)
    total_cache = query.count()
    query_cursos = db.query(RecomendacionCache.curso_id)
    query_cursos = _apply_workspaces(query_cursos, RecomendacionCache, workspaces) if workspaces else query_cursos
    cursos_con_cache = query_cursos.distinct().count()
    query_oldest = db.query(RecomendacionCache)
    query_oldest = _apply_workspaces(query_oldest, RecomendacionCache, workspaces) if workspaces else query_oldest
    oldest = query_oldest.order_by(RecomendacionCache.fecha_generada.asc()).first()
    query_newest = db.query(RecomendacionCache)
    query_newest = _apply_workspaces(query_newest, RecomendacionCache, workspaces) if workspaces else query_newest
    newest = query_newest.order_by(RecomendacionCache.fecha_generada.desc()).first()
    return {
        'total_entradas': total_cache,
        'cursos_con_cache': cursos_con_cache,
        'fecha_mas_antigua': oldest.fecha_generada if oldest else None,
        'fecha_mas_reciente': newest.fecha_generada if newest else None
    }


# ═══════════════════════════════════════════════════════════════
# Nodos de taxonomía (perfiles docentes y requisitos de cursos)
# ═══════════════════════════════════════════════════════════════


def sync_nodos_from_taxonomy(db: Session, taxonomy_path: Optional[str] = None) -> int:
    """
    Sincroniza la tabla `nodos` con el contenido de `taxonomy.json`.
    Inserta o actualiza nodos según su id estable. No borra nodos que ya no
    existan en el JSON para no romper referencias históricas.
    """
    if taxonomy_path is None:
        taxonomy_path = os.path.join(
            os.path.dirname(__file__), "..", "taxonomy", "taxonomy.json"
        )

    with open(taxonomy_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def _walk(nodes, parent_id=None):
        for node_data in nodes:
            yield node_data, parent_id
            yield from _walk(node_data.get("children", []), parent_id=node_data["id"])

    count = 0
    for node_data, parent_id in _walk(data.get("roots", [])):
        nodo = db.query(Nodo).filter(Nodo.id == node_data["id"]).first()
        if nodo:
            nodo.parent_id = parent_id
            nodo.name = node_data["name"]
            nodo.node_type = node_data.get("type", "leaf")
            nodo.aliases = node_data.get("aliases", [])
            nodo.domain = node_data.get("domain")
        else:
            nodo = Nodo(
                id=node_data["id"],
                parent_id=parent_id,
                name=node_data["name"],
                node_type=node_data.get("type", "leaf"),
                aliases=node_data.get("aliases", []),
                domain=node_data.get("domain"),
            )
            db.add(nodo)
        count += 1

    db.commit()
    return count


def get_nodo_by_id(db: Session, nodo_id: str) -> Optional[Nodo]:
    return db.query(Nodo).filter(Nodo.id == nodo_id).first()


def get_all_nodos(db: Session) -> List[Nodo]:
    return db.query(Nodo).all()


# ═══════════════════════════════════════════════════════════════
# DocenteNodo
# ═══════════════════════════════════════════════════════════════


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
    dn = db.query(DocenteNodo).filter(
        DocenteNodo.docente_id == docente_id,
        DocenteNodo.nodo_id == nodo_id,
    ).first()

    if dn:
        # Acumula evidencias nuevas y recalcula peso como suma simple.
        # El motor de matching normalizará internamente.
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

    db.commit()
    db.refresh(dn)
    return dn


def get_docente_nodos(db: Session, docente_id: int) -> List[DocenteNodo]:
    return db.query(DocenteNodo).filter(DocenteNodo.docente_id == docente_id).all()


def delete_docente_nodos_by_docente(db: Session, docente_id: int) -> int:
    count = db.query(DocenteNodo).filter(DocenteNodo.docente_id == docente_id).delete()
    db.commit()
    return count


# ═══════════════════════════════════════════════════════════════
# CursoNodo
# ═══════════════════════════════════════════════════════════════


def upsert_curso_nodo(
    db: Session,
    curso_id: int,
    nodo_id: str,
    peso_centralidad: float,
    semanas: List[int],
    evidencias: List[dict],
    version: str = "1.0.0",
) -> CursoNodo:
    cn = db.query(CursoNodo).filter(
        CursoNodo.curso_id == curso_id,
        CursoNodo.nodo_id == nodo_id,
    ).first()

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

    db.commit()
    db.refresh(cn)
    return cn


def get_curso_nodos(db: Session, curso_id: int) -> List[CursoNodo]:
    return db.query(CursoNodo).filter(CursoNodo.curso_id == curso_id).all()


def delete_curso_nodos_by_curso(db: Session, curso_id: int) -> int:
    count = db.query(CursoNodo).filter(CursoNodo.curso_id == curso_id).delete()
    db.commit()
    return count

def create_audit_log(db: Session, usuario_email: str, accion: str, detalles: str = "") -> None:
    from backend.database.models import AuditLog
    try:
        log_entry = AuditLog(
            usuario_email=usuario_email,
            accion=accion,
            detalles=detalles
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error creando registro de auditoria: {e}", exc_info=True)

def add_colaborador(db: Session, propietario_email: str, invitado_email: str):
    from backend.database.models import Colaborador
    existing = db.query(Colaborador).filter(
        Colaborador.propietario_email == propietario_email,
        Colaborador.invitado_email == invitado_email
    ).first()
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
        Colaborador.invitado_email == invitado_email
    ).delete()
    db.commit()
    return True
