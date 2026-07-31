"""Importador exact-only del léxico O*NET 30.3 Software Skills."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


SOURCE_ID = "onet_30_3"
SOURCE_VERSION = "30.3"


def _key(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return " ".join(normalized.split())


def _node_id(name: str) -> str:
    key = _key(name)
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:70] or "technology"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"onet.tech.{slug}.{digest}"


def import_onet_software_skills(json_path: str | Path) -> dict:
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in payload.get("row", []):
        name = str(row.get("workplace_example") or "").strip()
        if name:
            grouped[_key(name)].append(row)

    children = []
    for normalized_name, rows in grouped.items():
        names = sorted(
            {str(row["workplace_example"]).strip() for row in rows},
            key=lambda value: (len(value), value.casefold()),
        )
        name = names[0]
        aliases = [candidate for candidate in names[1:] if candidate != name]
        categories = sorted(
            {
                str(row.get("element_name") or "").strip()
                for row in rows
                if str(row.get("element_name") or "").strip()
            }
        )
        occupation_codes = sorted(
            {
                str(row.get("onetsoc_code") or "").strip()
                for row in rows
                if str(row.get("onetsoc_code") or "").strip()
            }
        )
        in_demand_codes = sorted(
            {
                str(row.get("onetsoc_code") or "").strip()
                for row in rows
                if row.get("in_demand") == "Y"
            }
        )
        children.append(
            {
                "id": _node_id(name),
                "name": name,
                "type": "leaf",
                "kind": "technology",
                "aliases": aliases,
                "labels": {"en": name},
                "source": SOURCE_ID,
                "source_version": SOURCE_VERSION,
                "external_id": normalized_name,
                "external_url": "https://www.onetonline.org/search/tech/",
                "description": None,
                # O*NET se usa como léxico de identidad. Sus categorías UNSPSC
                # no participan en la resolución semántica por embeddings.
                "embedding_enabled": False,
                "attributes": {
                    "onet_categories": categories,
                    "occupation_codes": occupation_codes,
                    "occupation_count": len(occupation_codes),
                    "in_demand_occupation_codes": in_demand_codes,
                    "hot_technology": any(
                        row.get("hot_technology") == "Y" for row in rows
                    ),
                },
                "children": [],
            }
        )

    children.sort(key=lambda node: node["name"].casefold())
    return {
        "id": SOURCE_ID,
        "name": "O*NET 30.3 Software Skills",
        "type": "root",
        "kind": "root",
        "aliases": ["O*NET Software Skills"],
        "source": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "external_id": "software_skills",
        "external_url": "https://www.onetcenter.org/database.html",
        "description": (
            "Technology identity lexicon and occupation evidence. O*NET product "
            "categories are retained as metadata, not semantic parent nodes."
        ),
        "embedding_enabled": False,
        "children": children,
    }
