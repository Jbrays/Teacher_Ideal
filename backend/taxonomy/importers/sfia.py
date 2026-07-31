"""
Importador de SFIA 9 (Skills Framework for the Information Age).

Fuente: JSON público redistribuido en GitHub.
URL: https://raw.githubusercontent.com/niwa/sfia-position-description-tool/master/json_source.json

Nota: SFIA es un framework de competencias profesionales. El JSON de NIWA parece
ser una copia/redistribución no oficial; en producción se debe verificar licencia.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict


def _slugify(text: str) -> str:
    """Convierte un nombre en un id tipo snake_case."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def _build_skill_node(category_name: str, subcategory_name: str, skill_name: str, skill_data: Dict[str, Any]) -> Dict:
    """Construye un nodo hoja para un skill SFIA."""
    code = skill_data.get("code", "")
    description = skill_data.get("description", "")
    levels = skill_data.get("levels", {})
    url = skill_data.get("url", "")

    # Construimos una descripción rica que ayude al embedding model.
    level_summary = " ".join([f"Nivel {k}: {v.strip()}" for k, v in sorted(levels.items())])
    full_description = f"{description} {level_summary}".strip()

    return {
        "id": f"sfia.{code}" if code else f"sfia.{_slugify(skill_name)}",
        "name": skill_name,
        "type": "leaf",
        "aliases": [code] if code else [],
        "source": "sfia_9",
        "external_id": code,
        "description": full_description,
        "children": [],
    }


def _build_subcategory_node(category_name: str, subcategory_name: str, skills: Dict[str, Dict]) -> Dict:
    """Construye un nodo rama para una subcategoría SFIA."""
    children = []
    for skill_name, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        children.append(_build_skill_node(category_name, subcategory_name, skill_name, skill_data))

    return {
        "id": f"sfia.{_slugify(category_name)}.{_slugify(subcategory_name)}",
        "name": subcategory_name,
        "type": "branch" if children else "leaf",
        "aliases": [],
        "source": "sfia_9",
        "external_id": None,
        "description": None,
        "children": children,
    }


def _build_category_node(category_name: str, subcategories: Dict[str, Any]) -> Dict:
    """Construye un nodo rama para una categoría SFIA."""
    children = []
    for subcategory_name, skills in subcategories.items():
        if isinstance(skills, dict):
            children.append(_build_subcategory_node(category_name, subcategory_name, skills))

    return {
        "id": f"sfia.{_slugify(category_name)}",
        "name": category_name,
        "type": "branch" if children else "leaf",
        "aliases": [],
        "source": "sfia_9",
        "external_id": None,
        "description": None,
        "children": children,
    }


def import_sfia_taxonomy(json_path: str | Path) -> Dict:
    """
    Importa SFIA 9 desde el JSON público y devuelve un nodo raíz listo para
    insertar en la taxonomía unificada.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    children = []
    for category_name, subcategories in data.items():
        if isinstance(subcategories, dict):
            children.append(_build_category_node(category_name, subcategories))

    return {
        "id": "sfia_9",
        "name": "SFIA 9 - Skills Framework for the Information Age",
        "type": "root",
        "aliases": ["SFIA", "Skills Framework for the Information Age"],
        "source": "sfia_9",
        "external_id": "sfia9",
        "description": "Framework de competencias profesionales para el ámbito digital y tecnológico.",
        "children": children,
    }


if __name__ == "__main__":
    raw_path = Path(__file__).parent.parent / "data" / "raw" / "sfia_9.json"
    root = import_sfia_taxonomy(raw_path)

    out_path = Path(__file__).parent.parent / "data" / "processed" / "sfia_taxonomy.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent=2)

    print(f"SFIA importado: {len(root['children'])} categorías principales.")
