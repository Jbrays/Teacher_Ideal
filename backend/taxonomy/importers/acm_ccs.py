"""
Importador de la taxonomía ACM Computing Classification System 2012.

Fuente: XML SKOS oficial de ACM.
URL: https://dl.acm.org/pb-assets/dl_ccs/acm_ccs2012-1626988337597.xml
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional


NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xml": "http://www.w3.org/XML/1998/namespace",
}


def _safe_id(about: str) -> str:
    """Genera un id interno estable a partir del about de SKOS."""
    return f"acm.{about}"


def _parse_concepts(xml_path: str | Path) -> Dict[str, Dict]:
    """Parsea el XML y devuelve un dict {about: concept_data}."""
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    concepts: Dict[str, Dict] = {}

    for concept in root.findall("skos:Concept", NS):
        about = concept.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
        if not about:
            continue

        pref_label = concept.find("skos:prefLabel", NS)
        name = pref_label.text.strip() if pref_label is not None and pref_label.text else about

        alt_labels = [el.text.strip() for el in concept.findall("skos:altLabel", NS) if el.text]

        broader = [
            el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
            for el in concept.findall("skos:broader", NS)
            if el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
        ]
        narrower = [
            el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
            for el in concept.findall("skos:narrower", NS)
            if el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource")
        ]

        is_top = concept.find("skos:topConceptOf", NS) is not None

        concepts[about] = {
            "about": about,
            "name": name,
            "aliases": alt_labels,
            "broader": broader,
            "narrower": narrower,
            "is_top": is_top,
        }

    return concepts


def _build_node_data(
    about: str,
    concepts: Dict[str, Dict],
    visited: Optional[set] = None,
) -> Optional[Dict]:
    """Construye el dict de nodo recursivamente."""
    if visited is None:
        visited = set()

    if about in visited:
        # Protección contra ciclos, aunque ACM CCS no debería tenerlos.
        return None
    visited.add(about)

    concept = concepts.get(about)
    if not concept:
        return None

    children = []
    for child_about in concept.get("narrower", []):
        child_data = _build_node_data(child_about, concepts, visited)
        if child_data:
            children.append(child_data)

    node_type = "leaf" if not children else "branch"

    return {
        "id": _safe_id(about),
        "name": concept["name"],
        "type": node_type,
        "aliases": concept["aliases"],
        "source": "acm_ccs_2012",
        "external_id": about,
        "description": None,
        "children": children,
    }


def import_acm_ccs_taxonomy(xml_path: str | Path) -> Dict:
    """
    Importa ACM CCS 2012 y devuelve un nodo raíz listo para insertar en
    la taxonomía unificada.
    """
    concepts = _parse_concepts(xml_path)

    # Los top concepts son aquellos marcados con topConceptOf O los que no tienen broader.
    top_abouts = [
        about
        for about, concept in concepts.items()
        if concept.get("is_top") or not concept.get("broader")
    ]

    children = []
    for about in top_abouts:
        node = _build_node_data(about, concepts)
        if node:
            children.append(node)

    return {
        "id": "acm_ccs_2012",
        "name": "ACM Computing Classification System 2012",
        "type": "root",
        "aliases": ["ACM CCS", "CCS 2012"],
        "source": "acm_ccs_2012",
        "external_id": "ccs2012",
        "description": "Taxonomía oficial de la ACM para clasificar literatura de computación.",
        "children": children,
    }


if __name__ == "__main__":
    import json

    raw_path = Path(__file__).parent.parent / "data" / "raw" / "acm_ccs_2012.xml"
    root = import_acm_ccs_taxonomy(raw_path)

    out_path = Path(__file__).parent.parent / "data" / "processed" / "acm_ccs_taxonomy.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False, indent=2)

    print(f"ACM CCS importado: {len(root['children'])} ramas principales.")
