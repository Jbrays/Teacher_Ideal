import logging
from sqlalchemy.orm import Session

from backend.database import crud
from backend.repositories.curso_repo import CursoRepository
from backend.repositories.docente_repo import DocenteRepository
from backend.repositories.nodo_repo import NodoRepository
from backend.taxonomy.resolver import TaxonomyResolver
from backend.taxonomy.catalog import get_taxonomy
from backend.core.config import settings

logger = logging.getLogger(__name__)

class TaxonomyService:
    """
    Servicio encargado de leer el `perfil_tecnico` puro de docentes y cursos
    desde la base de datos, mapearlos contra el arbol de conocimientos oficial,
    y poblar las tablas relacionales (`docente_nodos`, `curso_nodos`).
    """
    def __init__(self, db: Session):
        self.db = db
        self.curso_repo = CursoRepository(db)
        self.docente_repo = DocenteRepository(db)
        self.nodo_repo = NodoRepository(db)
        self.resolver = TaxonomyResolver(
            get_taxonomy(settings.taxonomy_path),
            auto_create_nodes=False,
        )

    def process_curso(self, curso_id: int) -> int:
        """
        Lee el perfil tecnico del curso, resuelve los terminos y guarda los nodos.
        """
        curso = self.curso_repo.get_by_id(curso_id)
        if not curso:
            logger.error(f"Curso {curso_id} no encontrado para taxonomia.")
            return 0

        perfil_tecnico = curso.perfil_tecnico
        if not perfil_tecnico:
            logger.info(f"Curso {curso_id} no tiene perfil tecnico.")
            return 0

        logger.info(f"Procesando taxonomia para curso: {curso.nombre}")
        
        # Preparar formato para el resolver
        menciones_a_resolver = []
        for item in perfil_tecnico:
            menciones_a_resolver.append({
                "termino": item.get("es", ""),
                "termino_en": item.get("en", ""),
                "explicito": True # Por defecto en cursos
            })

        self.nodo_repo.sync_from_taxonomy(str(settings.taxonomy_path))
        resultado = self.resolver.resolve_many(menciones_a_resolver)
        menciones_resueltas = resultado.resolved
        if resultado.unresolved:
            logger.warning(
                "Curso %s: %s términos no se asociaron por falta de coincidencia confiable: %s",
                curso_id,
                len(resultado.unresolved),
                ", ".join(resultado.unresolved[:20]),
            )
        
        # Agrupar por nodo y guardar
        from collections import defaultdict
        nodos_agrupados = defaultdict(list)
        for rm in menciones_resueltas:
            if not self.nodo_repo.get_by_id(rm.node_id):
                logger.error(
                    "Se rechazó el nodo %s porque no existe en el catálogo persistido.",
                    rm.node_id,
                )
                continue
            nodos_agrupados[rm.node_id].append(rm)

        self.curso_repo.delete_nodos(curso_id)
        guardados = 0
        
        for nodo_id, rms in nodos_agrupados.items():
            evidencias = []
            for rm in rms:
                evidencias.append({
                    "termino": rm.raw_mention,
                    "explicito": rm.explicit
                })
            
            # Peso por defecto para cursos (podria venir de un WeightStrategy)
            peso = 1.0 
            
            crud.upsert_curso_nodo(
                db=self.db,
                curso_id=curso_id,
                nodo_id=nodo_id,
                peso_centralidad=peso,
                semanas=[], # Ya no trabajamos semanas aca
                evidencias=evidencias,
                version="1.0.0",
            )
            guardados += 1

        self.db.commit()
        logger.info(f"Taxonomia de curso {curso_id} completada. {guardados} nodos guardados.")
        return guardados

    def process_docente(self, docente_id: int) -> int:
        """
        Lee el perfil tecnico del docente, resuelve los terminos y guarda los nodos.
        """
        docente = self.docente_repo.get_by_id(docente_id)
        if not docente:
            logger.error(f"Docente {docente_id} no encontrado para taxonomia.")
            return 0

        perfil_tecnico = docente.perfil_tecnico
        if not perfil_tecnico:
            logger.info(f"Docente {docente_id} no tiene perfil tecnico.")
            return 0

        logger.info(f"Procesando taxonomia para docente: {docente.nombre}")
        
        menciones_a_resolver = []
        for item in perfil_tecnico:
            menciones_a_resolver.append({
                "termino": item.get("es", ""),
                "termino_en": item.get("en", ""),
                "explicito": item.get("explicito", True)
            })

        self.nodo_repo.sync_from_taxonomy(str(settings.taxonomy_path))
        resultado = self.resolver.resolve_many(menciones_a_resolver)
        menciones_resueltas = resultado.resolved
        if resultado.unresolved:
            logger.warning(
                "Docente %s: %s términos no se asociaron por falta de coincidencia confiable: %s",
                docente_id,
                len(resultado.unresolved),
                ", ".join(resultado.unresolved[:20]),
            )
        
        from collections import defaultdict
        nodos_agrupados = defaultdict(list)
        for rm in menciones_resueltas:
            if not self.nodo_repo.get_by_id(rm.node_id):
                logger.error(
                    "Se rechazó el nodo %s porque no existe en el catálogo persistido.",
                    rm.node_id,
                )
                continue
            nodos_agrupados[rm.node_id].append(rm)

        self.docente_repo.delete_nodos(docente_id)
        guardados = 0
        
        for nodo_id, rms in nodos_agrupados.items():
            evidencias = []
            for rm in rms:
                evidencias.append({
                    "termino": rm.raw_mention,
                    "explicito": rm.explicit
                })
            
            explicito = any(rm.explicit for rm in rms)
            peso = 1.0 # Default base weight
            
            crud.upsert_docente_nodo(
                db=self.db,
                docente_id=docente_id,
                nodo_id=nodo_id,
                peso=peso,
                evidencias=evidencias,
                explicito=explicito,
                recencia=None,
                version="1.0.0",
            )
            guardados += 1

        self.db.commit()
        logger.info(f"Taxonomia de docente {docente_id} completada. {guardados} nodos guardados.")
        return guardados
