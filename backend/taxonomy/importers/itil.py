"""
Importador de ITIL 4 Practices.

ITIL es propiedad de AXELOS/PeopleCert y no existe una taxonomía estructurada
oficial abierta. Esta implementación construye un sub-árbol ligero a partir de
la lista pública de las 34 prácticas de ITIL 4, agrupadas en sus tres categorías.

Fuentes de referencia:
- https://www.proactivanet.com/blog/itil/34-practicas-de-itil-4-publicacion-completada/
- https://www.manageengine.com/products/service-desk/itsm/what-is-itil-4-management-practices.html
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List


ITIL_PRACTICES: Dict[str, List[str]] = {
    "General management practices": [
        "Architecture management",
        "Continual improvement",
        "Information security management",
        "Knowledge management",
        "Measurement and reporting",
        "Organizational change management",
        "Portfolio management",
        "Project management",
        "Relationship management",
        "Risk management",
        "Service financial management",
        "Strategy management",
        "Supplier management",
        "Workforce and talent management",
    ],
    "Service management practices": [
        "Availability management",
        "Business analysis",
        "Capacity and performance management",
        "Change enablement",
        "Incident management",
        "IT asset management",
        "Monitoring and event management",
        "Problem management",
        "Release management",
        "Service catalogue management",
        "Service configuration management",
        "Service continuity management",
        "Service design",
        "Service desk",
        "Service level management",
        "Service request management",
        "Service validation and testing",
    ],
    "Technical management practices": [
        "Deployment management",
        "Infrastructure and platform management",
        "Software development and management",
    ],
}


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def _build_practice_node(practice_name: str) -> Dict:
    return {
        "id": f"itil.{_slugify(practice_name)}",
        "name": practice_name,
        "type": "leaf",
        "aliases": [],
        "source": "itil_4",
        "external_id": _slugify(practice_name),
        "description": None,
        "children": [],
    }


def _build_category_node(category_name: str, practices: List[str]) -> Dict:
    children = [_build_practice_node(p) for p in practices]
    return {
        "id": f"itil.{_slugify(category_name)}",
        "name": category_name,
        "type": "branch",
        "aliases": [],
        "source": "itil_4",
        "external_id": None,
        "description": None,
        "children": children,
    }


def import_itil_taxonomy() -> Dict:
    """
    Construye el sub-árbol ITIL 4 y devuelve un nodo raíz listo para insertar
    en la taxonomía unificada.
    """
    children = [
        _build_category_node(category, practices)
        for category, practices in ITIL_PRACTICES.items()
    ]

    return {
        "id": "itil_4",
        "name": "ITIL 4 Management Practices",
        "type": "root",
        "aliases": ["ITIL", "ITIL 4", "Information Technology Infrastructure Library"],
        "source": "itil_4",
        "external_id": "itil4",
        "description": "Prácticas de gestión de servicios de TI según ITIL 4.",
        "children": children,
    }


if __name__ == "__main__":
    import json

    root = import_itil_taxonomy()

    out_path = Path(__file__).parent.parent / "data" / "processed" / "itil_taxonomy.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent=2)

    total_practices = sum(len(p) for p in ITIL_PRACTICES.values())
    print(f"ITIL 4 importado: {total_practices} prácticas en {len(ITIL_PRACTICES)} categorías.")
