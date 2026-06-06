import os
import chromadb
import logging
from typing import Dict, Optional, Callable, List
from pathlib import Path
import numpy as np
from sqlalchemy.orm import Session
from backend.database.models import Docente, Curso
import hashlib

logger = logging.getLogger(__name__)

# Configuración de ChromaDB (usamos /tmp/ porque Cloud Run tiene el resto del disco en solo-lectura)
BASE_DIR = Path("/tmp/chroma_db")
BASE_DIR.mkdir(parents=True, exist_ok=True)

class EmbeddingsManager:
    def __init__(self):
        try:
            self.client = chromadb.PersistentClient(path=str(BASE_DIR))
            # Usar distancia Coseno en la base de datos
            self.docentes_collection = self.client.get_or_create_collection(name="docentes", metadata={"hnsw:space": "cosine"})
            self.cursos_collection = self.client.get_or_create_collection(name="cursos", metadata={"hnsw:space": "cosine"})
            self.entidades_collection = self.client.get_or_create_collection(name="entidades_global", metadata={"hnsw:space": "cosine"})
        except Exception as e:
            logger.error(f"Error inicializando ChromaDB: {e}")
            self.client = None

    def _generate_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def get_or_create_embedding(self, db_item: (Docente | Curso), text_generator: Callable, embedding_generator: Callable) -> np.ndarray:
        if not self.client:
            raise Exception("ChromaDB no está inicializado")
            
        is_docente = isinstance(db_item, Docente)
        collection = self.docentes_collection if is_docente else self.cursos_collection
        item_id = f"docente_{db_item.id}" if is_docente else f"curso_{db_item.id}"
        
        current_text = text_generator(db_item)
        current_hash = self._generate_hash(current_text)
        
        # Intentar obtener de ChromaDB
        try:
            result = collection.get(ids=[item_id], include=["embeddings", "metadatas"])
            if result and result["metadatas"] and len(result["metadatas"]) > 0:
                cached_hash = result["metadatas"][0].get("hash")
                if cached_hash == current_hash and result["embeddings"] and len(result["embeddings"]) > 0:
                    # Devolver como numpy array 2D para ser compatible con la API existente
                    vector = np.array(result["embeddings"][0])
                    if vector.ndim == 1:
                        vector = vector.reshape(1, -1)
                    return vector
        except Exception as e:
            logger.error(f"Error consultando ChromaDB para {item_id}: {e}")

        # Si no existe o el hash cambió, generar nuevo embedding
        new_vector = embedding_generator(current_text)
        
        # Aplanar el vector para ChromaDB si es 2D (SBERT devuelve 2D)
        flat_vector = new_vector.flatten().tolist()
        
        # Guardar en ChromaDB
        try:
            # Upsert inserta o actualiza
            collection.upsert(
                ids=[item_id],
                embeddings=[flat_vector],
                metadatas=[{"hash": current_hash, "text_preview": current_text[:100]}],
                documents=[current_text]
            )
        except Exception as e:
            logger.error(f"Error guardando en ChromaDB para {item_id}: {e}")
            
        db_item.embedding_hash = current_hash
        return new_vector

    def get_entity_embeddings(self, entities: List[str], embedding_generator: Callable) -> Dict[str, np.ndarray]:
        if not self.client:
            raise Exception("ChromaDB no está inicializado")
        
        if not entities:
            return {}
            
        entities = [e.strip() for e in entities if e.strip()]
        if not entities:
            return {}
            
        entity_ids = [self._generate_hash(e) for e in entities]
        result_map = {}
        missing_entities = []
        missing_ids = []
        
        try:
            result = self.entidades_collection.get(ids=entity_ids, include=["embeddings"])
            if result and result.get("embeddings"):
                for i, doc_id in enumerate(result["ids"]):
                    try:
                        idx = entity_ids.index(doc_id)
                        ent = entities[idx]
                        vec = np.array(result["embeddings"][i])
                        if vec.ndim == 1:
                            vec = vec.reshape(1, -1)
                        result_map[ent] = vec
                    except ValueError:
                        pass
        except Exception as e:
            logger.error(f"Error consultando ChromaDB entidades: {e}")
            
        for ent, ent_id in zip(entities, entity_ids):
            if ent not in result_map:
                missing_entities.append(ent)
                missing_ids.append(ent_id)
                
        if missing_entities:
            for ent, ent_id in zip(missing_entities, missing_ids):
                vec = embedding_generator(ent)
                result_map[ent] = vec
                
                flat_vec = vec.flatten().tolist()
                try:
                    self.entidades_collection.upsert(
                        ids=[ent_id],
                        embeddings=[flat_vec],
                        documents=[ent]
                    )
                except Exception as e:
                    logger.error(f"Error guardando entidad en ChromaDB: {e}")
                    
        return result_map

    def get_all_docente_embeddings(self, db: Session, docentes: List[Docente], text_generator: Callable, embedding_generator: Callable) -> Dict[int, np.ndarray]:
        embeddings_map = {}
        needs_commit = False
        for docente in docentes:
            try:
                vector = self.get_or_create_embedding(
                    db_item=docente,
                    text_generator=text_generator,
                    embedding_generator=embedding_generator
                )
                embeddings_map[docente.id] = vector
                if not docente.embedding_hash:
                    needs_commit = True
            except Exception as e:
                logger.error(f"Error generando embedding para docente {docente.id}: {e}")
                
        if needs_commit:
            try:
                db.commit()
            except Exception:
                db.rollback()
        return embeddings_map

    def delete_docente_embedding(self, docente_id: int):
        if not self.client:
            return
        try:
            self.docentes_collection.delete(ids=[f"docente_{docente_id}"])
            logger.info(f"Vector semántico del docente {docente_id} destruido exitosamente de ChromaDB.")
        except Exception as e:
            logger.error(f"Error destruyendo vector del docente {docente_id}: {e}")

    def clear_cache(self, item_type: str = "all") -> int:
        count = 0
        try:
            if item_type in ["all", "docentes"] and self.client:
                # Una forma simple es borrar y recrear
                self.client.delete_collection("docentes")
                self.docentes_collection = self.client.get_or_create_collection(name="docentes", metadata={"hnsw:space": "cosine"})
                count += 1
            if item_type in ["all", "cursos"] and self.client:
                self.client.delete_collection("cursos")
                self.cursos_collection = self.client.get_or_create_collection(name="cursos", metadata={"hnsw:space": "cosine"})
                count += 1
        except Exception as e:
            logger.error(f"Error limpiando colecciones: {e}")
        return count

embeddings_manager = EmbeddingsManager()
