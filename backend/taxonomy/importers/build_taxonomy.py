"""Construye el catálogo unificado, versionado y reproducible."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from backend.taxonomy.importers.acm_ccs import import_acm_ccs_taxonomy
from backend.taxonomy.importers.cncf import (
    import_cncf_glossary,
    import_cncf_landscape,
)
from backend.taxonomy.importers.cso import import_cso_taxonomy
from backend.taxonomy.importers.download_sources import download_sources
from backend.taxonomy.importers.esco import import_esco_digital_taxonomy
from backend.taxonomy.importers.itil import import_itil_taxonomy
from backend.taxonomy.importers.onet import import_onet_software_skills
from backend.taxonomy.importers.sfia import import_sfia_taxonomy
from backend.taxonomy.models import SOURCE_PRIORITY, Taxonomy


CATALOG_VERSION = "3.0.0"
TAXONOMY_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = PROJECT_DIR / ".cache" / "taxonomy_sources"
SOURCE_MANIFEST = TAXONOMY_DIR / "sources.json"


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    normalized = re.sub(r"[^a-z0-9+#.]+", " ", normalized)
    return " ".join(normalized.split())


def _walk_dict(nodes: list[dict]):
    for node in nodes:
        yield node
        yield from _walk_dict(node.get("children", []))


def _apply_source_defaults(
    root: dict,
    source_version: str,
) -> None:
    for node in _walk_dict([root]):
        node.setdefault("source_version", source_version)
        node.setdefault("kind", "root" if node.get("type") == "root" else "concept")
        node.setdefault("labels", {"en": node.get("name", "")})
        node.setdefault("embedding_enabled", node.get("type") != "root")
        node.setdefault("attributes", {})
        node.setdefault("children", [])


def _build_exact_label_crosswalks(roots: list[dict]) -> list[dict]:
    """
    Enlaza etiquetas oficiales idénticas entre fuentes.

    Una coincidencia entre nombres/labels canónicos se considera equivalencia.
    Si una fuente sólo expone el término como alias, se conserva como una
    relación semántica más débil: un alias puede ser un nombre alternativo,
    pero también un producto citado como ejemplo de un concepto general.

    Sólo se crea una arista cuando la etiqueta identifica un único nodo dentro
    de cada fuente participante. No hay listas de términos ni reglas por
    tecnología: el crosswalk se deriva de los datos versionados.
    """
    labels: dict[str, dict[str, dict[str, dict]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for node in _walk_dict(roots):
        if (
            node.get("type") == "root"
            or node.get("kind") in {"root", "group"}
            or node.get("source") == "auto"
        ):
            continue
        canonical_labels = [
            node.get("name", ""),
            *(node.get("labels") or {}).values(),
        ]
        labelled_values = [
            *((label, True) for label in canonical_labels),
            *((label, False) for label in node.get("aliases", [])),
        ]
        for label, canonical in labelled_values:
            key = _normalize(str(label))
            if not key or key.isdigit():
                continue
            source = str(node.get("source") or "")
            existing = labels[key][source].get(node["id"])
            if existing is None:
                labels[key][source][node["id"]] = {
                    "node": node,
                    "canonical": canonical,
                }
            elif canonical:
                existing["canonical"] = True

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for label, by_source in labels.items():
        unique_matches = []
        for nodes in by_source.values():
            canonical_nodes = [
                match for match in nodes.values() if match["canonical"]
            ]
            if len(canonical_nodes) == 1:
                # Un alias genérico de otro nodo de la misma fuente no vuelve
                # ambiguo a un nombre canónico exacto (p. ej. SQL o MySQL).
                unique_matches.append(canonical_nodes[0])
            elif not canonical_nodes and len(nodes) == 1:
                unique_matches.append(next(iter(nodes.values())))
        if len(label) < 4:
            # Los acrónimos y lenguajes cortos sólo se cruzan cuando ambas
            # fuentes los declaran como nombre canónico. Un alias corto puede
            # ser homónimo de otro concepto (p. ej. NOC).
            unique_matches = [
                match for match in unique_matches if match["canonical"]
            ]
        if len(unique_matches) < 2:
            continue
        unique_matches.sort(
            key=lambda match: (
                SOURCE_PRIORITY.get(
                    str(match["node"].get("source") or ""),
                    999,
                ),
                match["node"]["id"],
            )
        )
        canonical_matches = [
            match for match in unique_matches if match["canonical"]
        ]
        alias_matches = [
            match for match in unique_matches if not match["canonical"]
        ]
        anchor = canonical_matches[0] if canonical_matches else unique_matches[0]
        targets: list[tuple[dict, bool]] = [
            *((match, True) for match in canonical_matches if match is not anchor),
            *((match, False) for match in alias_matches if match is not anchor),
        ]
        if not canonical_matches:
            targets = [
                (match, False)
                for match in unique_matches
                if match is not anchor
            ]

        for target, both_canonical in targets:
            anchor_node = anchor["node"]
            target_node = target["node"]
            relation_type = "exact_label_match" if both_canonical else (
                "official_alias_reference"
            )
            pair = (
                *sorted((anchor_node["id"], target_node["id"])),
                relation_type,
            )
            if pair in seen:
                continue
            seen.add(pair)
            relations.append(
                {
                    "source_id": anchor_node["id"],
                    "target_id": target_node["id"],
                    "relation_type": relation_type,
                    "weight": 0.97 if both_canonical else 0.78,
                    "directed": False,
                    "source": "generated_crosswalk",
                    "source_version": CATALOG_VERSION,
                    "external_id": label,
                    "provenance": {
                        "method": (
                            "normalized_exact_canonical_label"
                            if both_canonical
                            else "normalized_exact_official_alias"
                        ),
                        "label": label,
                        "left_source": anchor_node.get("source"),
                        "right_source": target_node.get("source"),
                        "left_is_canonical": anchor["canonical"],
                        "right_is_canonical": target["canonical"],
                    },
                }
            )
    return relations


def _source_metadata(manifest: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for source in manifest.values():
        source_id = source["source_id"]
        current = grouped.setdefault(
            source_id,
            {
                "id": source_id,
                "version": source["version"],
                "license": source["license"],
                "urls": [],
            },
        )
        current["urls"].append(source["url"])
    return [
        {
            "id": "itil_4",
            "version": "4",
            "license": "Reference names only; ITIL is a PeopleCert trademark",
            "urls": ["https://www.peoplecert.org/"],
        },
        *sorted(grouped.values(), key=lambda item: item["id"]),
    ]


def _verify_bundled_source(path: str | Path, source: dict, key: str) -> None:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != source["sha256"]:
        raise ValueError(
            f"Checksum inválido para {key}: {actual}; "
            f"se esperaba {source['sha256']}"
        )


def build_unified_taxonomy(
    acm_xml_path: str | Path,
    sfia_json_path: str | Path,
    output_path: str | Path,
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
) -> Taxonomy:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_dir = Path(source_dir)

    def source_path(key: str) -> Path:
        path = source_dir / manifest[key]["filename"]
        if not path.exists():
            raise FileNotFoundError(
                f"Falta la fuente {key}: {path}. Ejecute "
                "`python -m backend.taxonomy.importers.download_sources`."
            )
        return path

    _verify_bundled_source(acm_xml_path, manifest["acm"], "acm")
    _verify_bundled_source(sfia_json_path, manifest["sfia"], "sfia")
    acm_root = import_acm_ccs_taxonomy(acm_xml_path)
    sfia_root = import_sfia_taxonomy(sfia_json_path)
    itil_root = import_itil_taxonomy()
    _apply_source_defaults(acm_root, "2012")
    _apply_source_defaults(sfia_root, "9")
    _apply_source_defaults(itil_root, "4")

    esco_root, esco_relations = import_esco_digital_taxonomy(
        source_path("esco_en"),
        source_path("esco_es"),
    )
    cso_root, cso_relations = import_cso_taxonomy(source_path("cso"))
    glossary_root, glossary_relations = import_cncf_glossary(
        source_path("cncf_glossary"),
        manifest["cncf_glossary"]["version"],
    )
    landscape_root = import_cncf_landscape(
        source_path("cncf_landscape"),
        manifest["cncf_landscape"]["version"],
    )
    onet_root = import_onet_software_skills(source_path("onet"))

    roots = [
        acm_root,
        sfia_root,
        itil_root,
        esco_root,
        cso_root,
        glossary_root,
        landscape_root,
        onet_root,
    ]
    relations = [
        *esco_relations,
        *cso_relations,
        *glossary_relations,
        *_build_exact_label_crosswalks(roots),
    ]
    unified = {
        "version": CATALOG_VERSION,
        "description": (
            "Versioned multi-source catalog. Source hierarchies remain "
            "traceable and typed relations connect equivalent or related nodes."
        ),
        "sources": _source_metadata(manifest),
        "roots": roots,
        "relations": relations,
    }

    raw_ids = [node["id"] for node in _walk_dict(roots)]
    duplicate_ids = sorted(
        node_id for node_id, count in Counter(raw_ids).items() if count > 1
    )
    if duplicate_ids:
        raise ValueError(f"IDs de nodos duplicados: {duplicate_ids[:20]}")

    valid_ids = set(raw_ids)
    invalid_relations = [
        relation
        for relation in relations
        if relation["source_id"] not in valid_ids
        or relation["target_id"] not in valid_ids
    ]
    if invalid_relations:
        raise ValueError(
            f"Relaciones con nodos inexistentes: {invalid_relations[:5]}"
        )

    taxonomy = Taxonomy.from_dict(unified)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(unified, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return taxonomy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=TAXONOMY_DIR / "taxonomy.json",
    )
    args = parser.parse_args()

    if args.download:
        download_sources(destination=args.source_dir)

    raw_dir = TAXONOMY_DIR / "data" / "raw"
    taxonomy = build_unified_taxonomy(
        acm_xml_path=raw_dir / "acm_ccs_2012.xml",
        sfia_json_path=raw_dir / "sfia_9.json",
        output_path=args.output,
        source_dir=args.source_dir,
    )
    by_source: dict[str, int] = defaultdict(int)
    for node in taxonomy.all_nodes():
        by_source[node.source or "unknown"] += 1
    print(f"Taxonomía generada en: {args.output}")
    print(f"Nodos: {len(taxonomy.all_nodes())}")
    print(f"Relaciones: {len(taxonomy.relations)}")
    print(f"Por fuente: {dict(sorted(by_source.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
