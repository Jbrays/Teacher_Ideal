from sqlalchemy.orm import Session
from typing import List, Optional
from backend.database.models import Docente, Curso, Historial, Recomendacion, WebhookLog, RecomendacionCache
from datetime import datetime, timedelta


def create_docente(db: Session, drive_file_id: str, nombre: str, **kwargs) -> Docente:
    docente = Docente(drive_file_id=drive_file_id, nombre=nombre, **kwargs)
    db.add(docente)
    db.commit()
    db.refresh(docente)
    return docente

def get_docente_by_id(db: Session, docente_id: int) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.id == docente_id).first()

def get_docente_by_drive_id(db: Session, drive_file_id: str) -> Optional[Docente]:
    return db.query(Docente).filter(Docente.drive_file_id == drive_file_id).first()

def get_all_docentes(db: Session, skip: int = 0, limit: int = 100) -> List[Docente]:
    return db.query(Docente).offset(skip).limit(limit).all()

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


def create_curso(db: Session, drive_file_id: str, nombre: str, ciclo: int, **kwargs) -> Curso:
    curso = Curso(drive_file_id=drive_file_id, nombre=nombre, ciclo=ciclo, **kwargs)
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

def get_cursos_by_ciclo(db: Session, ciclo: int) -> List[Curso]:
    return db.query(Curso).filter(Curso.ciclo == ciclo).all()

def get_all_cursos(db: Session, skip: int = 0, limit: int = 100) -> List[Curso]:
    return db.query(Curso).offset(skip).limit(limit).all()

def get_all_ciclos(db: Session) -> List[int]:
    ciclos = db.query(Curso.ciclo).distinct().order_by(Curso.ciclo).all()
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


def upsert_historial(db: Session, nombre_docente: str, nombre_curso: str, periodo: str) -> Historial:
    historial = db.query(Historial).filter(
        Historial.nombre_docente == nombre_docente,
        Historial.nombre_curso == nombre_curso
    ).first()
    
    if historial:
        historial.veces += 1
        historial.ultima_vez = periodo
    else:
        historial = Historial(
            nombre_docente=nombre_docente,
            nombre_curso=nombre_curso,
            veces=1,
            ultima_vez=periodo
        )
        db.add(historial)
        
    db.commit()
    db.refresh(historial)
    return historial

def get_all_historiales(db: Session) -> List[Historial]:
    return db.query(Historial).all()


def create_recomendacion(db: Session, curso_id: int, docente_id: int, score: float, confidence: float, explanations: list) -> Recomendacion:
    recomendacion = Recomendacion(curso_id=curso_id, docente_id=docente_id, score=score, confidence=confidence, explanations=explanations)
    db.add(recomendacion)
    db.commit()
    db.refresh(recomendacion)
    return recomendacion

def get_recomendaciones_by_curso(db: Session, curso_id: int, limit: int = 10) -> List[Recomendacion]:
    return db.query(Recomendacion).filter(Recomendacion.curso_id == curso_id, Recomendacion.is_valid == True).order_by(Recomendacion.score.desc()).limit(limit).all()

def invalidate_recomendaciones_by_curso(db: Session, curso_id: int):
    db.query(Recomendacion).filter(Recomendacion.curso_id == curso_id).update({"is_valid": False})
    db.commit()


def create_webhook_log(db: Session, drive_file_id: str, evento_tipo: str, entidad: str, status: str, error_message: str = None) -> WebhookLog:
    log = WebhookLog(
        drive_file_id=drive_file_id,
        evento_tipo=evento_tipo,
        entidad=entidad,
        status=status,
        error_message=error_message
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

def get_active_processing_count(db: Session) -> int:
    return db.query(WebhookLog).filter(WebhookLog.status.in_(["received", "processing"])).count()


def get_recomendaciones_cache(db: Session, curso_id: int, max_age_days: Optional[int] = 7) -> Optional[List[RecomendacionCache]]:
    query = db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id)
    if max_age_days is not None:
        fecha_limite = datetime.utcnow() - timedelta(days=max_age_days)
        query = query.filter(RecomendacionCache.fecha_generada >= fecha_limite)
    cache = query.order_by(RecomendacionCache.score_combinado.desc()).all()
    return cache if cache else None

def save_recomendaciones_cache(db: Session, curso_id: int, recommendations: List[dict], version_algoritmo: str = "sbert_v1.0") -> None:
    try:
        db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id).delete()
        for idx, rec in enumerate(recommendations):
            cache_entry = RecomendacionCache(
                curso_id=curso_id,
                docente_id=rec['docente_id'],
                score_combinado=rec.get('score_combinado', 0.0),
                score_est=rec.get('score_est', 0.0),
                score_tac=rec.get('score_tac', 0.0),
                evidencias=rec.get('evidencias', []),
                shap_explanations=rec.get('shap_explanations', {}),
                version_algoritmo=version_algoritmo,
                fecha_generada=datetime.utcnow()
            )
            db.add(cache_entry)
        db.commit()
    except Exception:
        db.rollback()
        raise

def clear_recomendaciones_cache(db: Session, curso_id: Optional[int] = None) -> int:
    query = db.query(RecomendacionCache)
    if curso_id:
        query = query.filter(RecomendacionCache.curso_id == curso_id)
    count = query.count()
    query.delete()
    db.commit()
    return count

def delete_recomendaciones_cache_by_docente(db: Session, docente_id: int) -> int:
    count = db.query(RecomendacionCache).filter(RecomendacionCache.docente_id == docente_id).delete()
    db.commit()
    return count

def delete_recomendaciones_cache_by_curso(db: Session, curso_id: int) -> int:
    count = db.query(RecomendacionCache).filter(RecomendacionCache.curso_id == curso_id).delete()
    db.commit()
    return count

def get_cache_stats(db: Session) -> dict:
    total_cache = db.query(RecomendacionCache).count()
    cursos_con_cache = db.query(RecomendacionCache.curso_id).distinct().count()
    oldest = db.query(RecomendacionCache).order_by(RecomendacionCache.fecha_generada.asc()).first()
    newest = db.query(RecomendacionCache).order_by(RecomendacionCache.fecha_generada.desc()).first()
    return {
        'total_entradas': total_cache,
        'cursos_con_cache': cursos_con_cache,
        'fecha_mas_antigua': oldest.fecha_generada if oldest else None,
        'fecha_mas_reciente': newest.fecha_generada if newest else None
    }
