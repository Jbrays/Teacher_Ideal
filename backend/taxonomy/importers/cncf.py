"""Importadores del CNCF Cloud Native Glossary y Landscape."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

import yaml


GLOSSARY_SOURCE = "cncf_glossary"
LANDSCAPE_SOURCE = "cncf_landscape"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def _frontmatter(document: str) -> tuple[dict, str]:
    if not document.startswith("---"):
        return {}, document
    parts = document.split("---", 2)
    if len(parts) < 3:
        return {}, document
    return yaml.safe_load(parts[1]) or {}, parts[2].strip()


def _plain_first_paragraph(body: str) -> str | None:
    paragraphs = re.split(r"\n\s*\n", body)
    paragraph = next(
        (
            part.strip()
            for part in paragraphs
            if part.strip() and not part.lstrip().startswith("#")
        ),
        "",
    )
    paragraph = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", paragraph)
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    return paragraph or None


def _title_aliases(title: str) -> list[str]:
    """Deriva formas oficiales abreviadas de ``Concept name (ACRONYM)``."""
    match = re.fullmatch(
        r"\s*(.+?)\s*\(([A-Za-z][A-Za-z0-9+.-]{1,15})\)\s*",
        title,
    )
    if not match:
        return []
    return list(dict.fromkeys((match.group(1).strip(), match.group(2).strip())))


def import_cncf_glossary(
    archive_path: str | Path,
    source_version: str,
) -> tuple[dict, list[dict]]:
    with zipfile.ZipFile(archive_path) as archive:
        english_files = {
            Path(name).name: name
            for name in archive.namelist()
            if "/content/en/" in name
            and name.endswith(".md")
            and not Path(name).name.startswith("_")
        }
        spanish_files = {
            Path(name).name: name
            for name in archive.namelist()
            if "/content/es/" in name
            and name.endswith(".md")
            and not Path(name).name.startswith("_")
        }

        entries: dict[str, dict] = {}
        bodies: dict[str, str] = {}
        for filename, member in english_files.items():
            slug = Path(filename).stem
            metadata, body = _frontmatter(
                archive.read(member).decode("utf-8", errors="replace")
            )
            if str(metadata.get("status", "")).casefold() not in {
                "completed",
                "complete",
            }:
                continue
            title = str(metadata.get("title") or slug.replace("-", " ")).strip()
            spanish_title = ""
            spanish_member = spanish_files.get(filename)
            if spanish_member:
                spanish_metadata, _spanish_body = _frontmatter(
                    archive.read(spanish_member).decode("utf-8", errors="replace")
                )
                spanish_title = str(spanish_metadata.get("title") or "").strip()
            entries[slug] = {
                "title": title,
                "spanish_title": spanish_title,
                "description": _plain_first_paragraph(body),
                "tags": [
                    str(tag).strip()
                    for tag in metadata.get("tags", [])
                    if str(tag).strip()
                ],
            }
            bodies[slug] = body

    children = []
    for slug, entry in sorted(entries.items(), key=lambda item: item[1]["title"].casefold()):
        aliases = [
            *_title_aliases(entry["title"]),
            *([entry["spanish_title"]] if entry["spanish_title"] else []),
        ]
        aliases = [
            alias
            for alias in dict.fromkeys(aliases)
            if alias.casefold() != entry["title"].casefold()
        ]
        children.append(
            {
                "id": f"cncf.glossary.{_slug(slug)}",
                "name": entry["title"],
                "type": "leaf",
                "kind": "concept",
                "aliases": aliases,
                "labels": {
                    language: label
                    for language, label in {
                        "en": entry["title"],
                        "es": entry["spanish_title"],
                    }.items()
                    if label
                },
                "source": GLOSSARY_SOURCE,
                "source_version": source_version,
                "external_id": slug,
                "external_url": f"https://glossary.cncf.io/{slug}/",
                "description": entry["description"],
                "embedding_enabled": True,
                "attributes": {"tags": entry["tags"]},
                "children": [],
            }
        )

    relations = []
    seen: set[tuple[str, str]] = set()
    for slug, body in bodies.items():
        for linked_slug in re.findall(r"\]\(/(?:en/)?([^/#)]+)/?\)", body):
            if linked_slug not in entries or linked_slug == slug:
                continue
            pair = tuple(sorted((slug, linked_slug)))
            if pair in seen:
                continue
            seen.add(pair)
            relations.append(
                {
                    "source_id": f"cncf.glossary.{_slug(slug)}",
                    "target_id": f"cncf.glossary.{_slug(linked_slug)}",
                    "relation_type": "related_to",
                    "weight": 0.52,
                    "directed": False,
                    "source": GLOSSARY_SOURCE,
                    "source_version": source_version,
                    "external_id": "markdown_link",
                    "provenance": {
                        "source_page": slug,
                        "target_page": linked_slug,
                    },
                }
            )

    root = {
        "id": GLOSSARY_SOURCE,
        "name": "CNCF Cloud Native Glossary",
        "type": "root",
        "kind": "root",
        "aliases": ["Cloud Native Glossary"],
        "source": GLOSSARY_SOURCE,
        "source_version": source_version,
        "external_id": source_version,
        "external_url": "https://glossary.cncf.io/",
        "description": "CNCF reference vocabulary for cloud-native concepts.",
        "embedding_enabled": False,
        "children": children,
    }
    return root, relations


def import_cncf_landscape(
    yaml_path: str | Path,
    source_version: str,
) -> dict:
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    categories = []
    for category_entry in data.get("landscape", []):
        category_name = str(category_entry.get("name") or "").strip()
        if not category_name:
            continue
        category_slug = _slug(category_name)
        subcategories = []
        for subcategory_entry in category_entry.get("subcategories") or []:
            subcategory_name = str(subcategory_entry.get("name") or "").strip()
            if not subcategory_name:
                continue
            subcategory_slug = _slug(subcategory_name)
            items = []
            for item_entry in subcategory_entry.get("items") or []:
                name = str(item_entry.get("name") or "").strip()
                if not name:
                    continue
                item_slug = _slug(name)
                item_identity = str(
                    item_entry.get("repo_url")
                    or item_entry.get("homepage_url")
                    or name
                )
                identity_hash = hashlib.sha1(
                    item_identity.encode("utf-8")
                ).hexdigest()[:8]
                items.append(
                    {
                        "id": (
                            f"cncf.landscape.{category_slug}."
                            f"{subcategory_slug}.{item_slug}.{identity_hash}"
                        ),
                        "name": name,
                        "type": "leaf",
                        "kind": "technology",
                        "aliases": [],
                        "labels": {"en": name},
                        "source": LANDSCAPE_SOURCE,
                        "source_version": source_version,
                        "external_id": item_entry.get("repo_url")
                        or item_entry.get("homepage_url")
                        or name,
                        "external_url": item_entry.get("homepage_url"),
                        "description": item_entry.get("description"),
                        "embedding_enabled": False,
                        "hierarchy_weight": 0.70,
                        "attributes": {
                            "repo_url": item_entry.get("repo_url"),
                            "project_status": item_entry.get("project"),
                            "open_source": item_entry.get("open_source"),
                            "second_path": item_entry.get("second_path") or [],
                        },
                        "children": [],
                    }
                )
            items.sort(key=lambda item: item["name"].casefold())
            subcategories.append(
                {
                    "id": f"cncf.landscape.{category_slug}.{subcategory_slug}",
                    "name": subcategory_name,
                    "type": "branch" if items else "leaf",
                    "kind": "group",
                    "aliases": [],
                    "labels": {"en": subcategory_name},
                    "source": LANDSCAPE_SOURCE,
                    "source_version": source_version,
                    "external_id": f"{category_name}/{subcategory_name}",
                    "description": None,
                    "embedding_enabled": False,
                    "children": items,
                }
            )
        subcategories.sort(key=lambda item: item["name"].casefold())
        categories.append(
            {
                "id": f"cncf.landscape.{category_slug}",
                "name": category_name,
                "type": "branch" if subcategories else "leaf",
                "kind": "group",
                "aliases": [],
                "labels": {"en": category_name},
                "source": LANDSCAPE_SOURCE,
                "source_version": source_version,
                "external_id": category_name,
                "description": None,
                "embedding_enabled": False,
                "children": subcategories,
            }
        )

    categories.sort(key=lambda item: item["name"].casefold())
    return {
        "id": LANDSCAPE_SOURCE,
        "name": "CNCF Cloud Native Landscape",
        "type": "root",
        "kind": "root",
        "aliases": ["CNCF Landscape"],
        "source": LANDSCAPE_SOURCE,
        "source_version": source_version,
        "external_id": source_version,
        "external_url": "https://landscape.cncf.io/",
        "description": "CNCF categorization of cloud-native products and projects.",
        "embedding_enabled": False,
        "children": categories,
    }
