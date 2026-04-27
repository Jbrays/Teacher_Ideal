import os
import pickle
import numpy as np
import hashlib
from typing import Dict, Optional, Callable, List
from pathlib import Path
from sqlalchemy.orm import Session
from backend.database.models import Docente, Curso

BASE_DIR = Path("backend/data/embeddings")
DOCENTES_DIR = BASE_DIR / "docentes"
CURSOS_DIR = BASE_DIR / "cursos"
DOCENTES_DIR.mkdir(parents=True, exist_ok=True)
CURSOS_DIR.mkdir(parents=True, exist_ok=True)


class EmbeddingsManager:
    def __init__(self):
        self.docentes_dir = DOCENTES_DIR
        self.cursos_dir = CURSOS_DIR

    def _generate_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _get_item_path(self, db_item: (Docente | Curso)) -> Path:
        if isinstance(db_item, Docente):
            return self.docentes_dir / f"docente_{db_item.id}.pkl"
        elif isinstance(db_item, Curso):
            return self.cursos_dir / f"curso_{db_item.id}.pkl"
        else:
            raise TypeError("El item debe ser un objeto Docente o Curso")

    def _load_embedding(self, path: Path) -> Optional[Dict]:
        if not path.exists():
            return None
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            return None

    def _save_embedding(self, path: Path, data: Dict):
        try:
            with open(path, 'wb') as f:
                pickle.dump(data, f)
        except Exception:
            pass

    def get_or_create_embedding(self, db_item: (Docente | Curso), text_generator: Callable, embedding_generator: Callable) -> np.ndarray:
        path = self._get_item_path(db_item)
        cached_data = self._load_embedding(path)
        current_text = text_generator(db_item)
        current_hash = self._generate_hash(current_text)
        if cached_data and cached_data.get('hash') == current_hash:
            return cached_data.get('vector')
        new_vector = embedding_generator(current_text)
        new_data = {'vector': new_vector, 'hash': current_hash, 'text_preview': current_text[:150]}
        self._save_embedding(path, new_data)
        db_item.embedding_hash = current_hash
        return new_vector

    def get_all_docente_embeddings(self, db: Session, docentes: List[Docente], text_generator: Callable, embedding_generator: Callable) -> Dict[int, np.ndarray]:
        embeddings_map = {}
        needs_commit = False
        for docente in docentes:
            vector = self.get_or_create_embedding(
                db_item=docente,
                text_generator=text_generator,
                embedding_generator=embedding_generator
            )
            embeddings_map[docente.id] = vector
            if not docente.embedding_hash:
                needs_commit = True
        if needs_commit:
            try:
                db.commit()
            except Exception:
                db.rollback()
        return embeddings_map

    def clear_cache(self, item_type: str = "all") -> int:
        count = 0
        if item_type in ["all", "docentes"]:
            for f in self.docentes_dir.glob("*.pkl"):
                os.remove(f)
                count += 1
        if item_type in ["all", "cursos"]:
            for f in self.cursos_dir.glob("*.pkl"):
                os.remove(f)
                count += 1
        return count


embeddings_manager = EmbeddingsManager()
