"""Normalización y validación de términos técnicos bilingües.

Este módulo es la compuerta entre la salida probabilística del LLM y la data
procesada que se persiste. No traduce: valida que cada par represente el mismo
concepto y utiliza las etiquetas versionadas de la taxonomía.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional


_MAX_TERM_LENGTH = 160
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")
_WHITESPACE = re.compile(r"\s+")
_KEY_SEPARATORS = re.compile(r"[^a-z0-9+#.]+")

# Indicadores suficientemente específicos para detectar que `termino_en`
# contiene español. No pretende ser un detector general de idioma.
_SPANISH_TECHNICAL_WORDS = {
    "administracion",
    "almacenamiento",
    "analisis",
    "aprendizaje",
    "arquitectura",
    "automatizacion",
    "bases",
    "calculo",
    "calidad",
    "ciencia",
    "computacion",
    "contenedores",
    "datos",
    "desarrollo",
    "deteccion",
    "diseno",
    "empresarial",
    "gestion",
    "herramienta",
    "informacion",
    "infraestructura",
    "inteligencia",
    "lenguaje",
    "metodologia",
    "modelado",
    "nube",
    "operativo",
    "operativos",
    "plataforma",
    "procesos",
    "programacion",
    "redes",
    "seguridad",
    "sistema",
    "sistemas",
    "visualizacion",
}

_GENERIC_ENGLISH_CATEGORIES = (
    "cloud computing platform",
    "container platform",
    "database management system",
    "development framework",
    "learning management platform",
    "learning management system",
    "programming language",
    "software development methodology",
    "version control system",
    "video conferencing platform",
)


def _clean_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHARACTERS.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip(" \t\r\n,;:")


def _ascii_words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.findall(r"[a-z0-9+#.]+", normalized)


def _lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii").lower()
    normalized = _KEY_SEPARATORS.sub(" ", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


@dataclass(frozen=True)
class NormalizedTechnicalTerm:
    """Par técnico listo para persistencia y resolución taxonómica."""

    es: str
    en: str
    raw_es: str
    context: str = ""
    source_section: str = ""
    explicit: bool = True

    def as_profile_item(self) -> dict[str, str]:
        return {"es": self.es, "en": self.en}

    def as_resolver_item(self) -> dict[str, Any]:
        return {
            "termino": self.es,
            "termino_en": self.en,
            "contexto": self.context,
            "seccion": self.source_section,
            "explicito": self.explicit,
        }


@dataclass(frozen=True)
class RejectedTechnicalTerm:
    term: str
    reason: str


@dataclass
class TechnicalTermResult:
    accepted: list[NormalizedTechnicalTerm] = field(default_factory=list)
    rejected: list[RejectedTechnicalTerm] = field(default_factory=list)

    @property
    def profile(self) -> list[dict[str, str]]:
        return [term.as_profile_item() for term in self.accepted]


class TechnicalTermNormalizer:
    """Valida, canoniza y deduplica menciones técnicas."""

    @staticmethod
    def _looks_spanish(value: str) -> bool:
        words = set(_ascii_words(value))
        return bool(words & _SPANISH_TECHNICAL_WORDS)

    @staticmethod
    def _looks_like_proper_name(
        value: str,
        canonical_lookup: Optional[Mapping[str, str]] = None,
    ) -> bool:
        key = _lookup_key(value)
        if canonical_lookup and key in canonical_lookup:
            return True
        if TechnicalTermNormalizer._looks_spanish(value):
            return False

        words = value.split()
        if len(words) == 1:
            return bool(re.search(r"[A-Z0-9+#.]", value))
        if any(
            token.isupper()
            or bool(re.search(r"\d|[+#.]", token))
            or (any(c.isupper() for c in token[1:]) and any(c.islower() for c in token))
            for token in words
        ):
            return True
        return len(words) <= 5 and all(
            not token[0].isalpha() or token[0].isupper()
            for token in words
            if token
        )

    @staticmethod
    def _is_generic_definition(value: str) -> bool:
        key = _lookup_key(value)
        return any(key == category or key.startswith(f"{category} ") for category in _GENERIC_ENGLISH_CATEGORIES)

    @classmethod
    def normalize_one(
        cls,
        item: Mapping[str, Any],
        canonical_lookup: Optional[Mapping[str, str]] = None,
    ) -> tuple[Optional[NormalizedTechnicalTerm], Optional[str]]:
        raw_es = _clean_label(
            item.get("termino")
            or item.get("es")
            or item.get("mention")
            or item.get("term")
        )
        raw_en = _clean_label(
            item.get("termino_en")
            or item.get("en")
            or item.get("term_en")
        )

        if not raw_es:
            return None, "termino_es_vacio"
        if len(raw_es) > _MAX_TERM_LENGTH:
            return None, "termino_es_demasiado_largo"

        raw_es_key = _lookup_key(raw_es)
        raw_en_key = _lookup_key(raw_en) if raw_en else ""
        canonical_lookup = canonical_lookup or {}
        canonical_es = canonical_lookup.get(raw_es_key)
        canonical_en = canonical_lookup.get(raw_en_key) if raw_en else None

        if (
            canonical_es
            and canonical_en
            and _lookup_key(canonical_es) != _lookup_key(canonical_en)
        ):
            return None, "aliases_bilingues_en_conflicto"

        canonical = canonical_es or canonical_en
        if canonical:
            # Productos, lenguajes y estándares conservan una sola grafía
            # canónica en ambos campos (p. ej. ZOOM -> Zoom). Los conceptos
            # traducibles mantienen la etiqueta española original.
            raw_words = set(_ascii_words(raw_es))
            canonical_words = _ascii_words(canonical)
            compact_identifier_in_spanish_label = (
                len(canonical_words) == 1
                and canonical_words[0] in raw_words
            )
            term_es = (
                canonical
                if (
                    not cls._looks_spanish(raw_es)
                    and cls._looks_like_proper_name(canonical)
                )
                or compact_identifier_in_spanish_label
                else raw_es
            )
            term_en = canonical
        else:
            term_es, term_en = raw_es, raw_en

            if not term_en:
                if cls._looks_like_proper_name(term_es, canonical_lookup):
                    term_en = term_es
                else:
                    return None, "traduccion_ingles_faltante"

            if len(term_en) > _MAX_TERM_LENGTH:
                return None, "termino_en_demasiado_largo"

            if cls._looks_spanish(term_en):
                if cls._looks_like_proper_name(term_es, canonical_lookup):
                    term_en = term_es
                else:
                    return None, "termino_en_no_esta_en_ingles"

            if cls._looks_like_proper_name(
                term_es, canonical_lookup
            ) and cls._is_generic_definition(term_en):
                term_en = term_es

            if _lookup_key(term_es) == _lookup_key(term_en) and cls._looks_spanish(term_es):
                return None, "concepto_espanol_sin_traducir"

        context = _clean_label(item.get("contexto") or item.get("context") or "")
        source_section = _clean_label(item.get("seccion") or item.get("source_section") or "")
        explicit = bool(item.get("explicito", item.get("explicit", True)))

        return (
            NormalizedTechnicalTerm(
                es=term_es,
                en=term_en,
                raw_es=raw_es,
                context=context,
                source_section=source_section,
                explicit=explicit,
            ),
            None,
        )

    @classmethod
    def normalize_many(
        cls,
        items: Iterable[Mapping[str, Any]],
        canonical_lookup: Optional[Mapping[str, str]] = None,
    ) -> TechnicalTermResult:
        result = TechnicalTermResult()
        seen_node_queries: set[str] = set()

        for item in items:
            if not isinstance(item, Mapping):
                result.rejected.append(
                    RejectedTechnicalTerm(term=str(item), reason="elemento_no_es_objeto")
                )
                continue

            normalized, reason = cls.normalize_one(
                item,
                canonical_lookup=canonical_lookup,
            )
            if normalized is None:
                raw_term = _clean_label(
                    item.get("termino")
                    or item.get("es")
                    or item.get("mention")
                    or item.get("term")
                )
                result.rejected.append(
                    RejectedTechnicalTerm(term=raw_term, reason=reason or "termino_invalido")
                )
                continue

            key = _lookup_key(normalized.en)
            if key in seen_node_queries:
                continue
            seen_node_queries.add(key)
            result.accepted.append(normalized)

        return result
