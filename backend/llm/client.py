"""
Cliente unificado para llamadas a Gemini vía Vertex AI.

Centraliza la inicialización del SDK, reintentos, logging de tiempos y
parseo de respuestas JSON. Ningún otro módulo debe crear su propio cliente
de Gemini directamente.
"""

import asyncio
import json
import logging
import random
import time
from typing import Callable, Optional, TypeVar

from google import genai
from google.genai import types

from backend.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GeminiClient:
    """
    Cliente de Gemini con reintentos automáticos y respuesta JSON estructurada.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        flash_model: Optional[str] = None,
        max_retries: int = 3,
        timeout: float = 120.0,
    ):
        self.project_id = project_id or settings.google_cloud_project
        self.location = (location or settings.google_cloud_location or "global").lower()
        self.flash_model = flash_model or settings.gemini_model_name
        self.max_retries = max_retries
        self.timeout = timeout

        try:
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
            )
            logger.info(
                f"GeminiClient inicializado (project={self.project_id}, "
                f"location={self.location})"
            )
        except Exception as e:
            logger.error(f"Error inicializando GeminiClient: {e}", exc_info=True)
            self.client = None

    def _is_rate_limit(self, exc: Exception) -> bool:
        texto = str(exc)
        return "429" in texto or "RESOURCE_EXHAUSTED" in texto

    async def _generate_with_retries(
        self,
        model_name: str,
        contents: str,
        temperature: float = 0.1,
        response_mime_type: str = "application/json",
        parser: Optional[Callable[[str], T]] = None,
        default_value: Optional[T] = None,
        label: str = "LLM",
    ) -> Optional[T]:
        """
        Llama al modelo con reintentos y parseo opcional.

        parser: función que recibe el texto plano y devuelve el tipo esperado.
        default_value: valor a devolver si falla la llamada o el parseo.
        """
        if not self.client:
            return default_value

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(
                        f"⏳ [{label}] Retry {attempt + 1}/{self.max_retries} en {wait:.1f}s..."
                    )
                    await asyncio.sleep(wait)

                start = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type=response_mime_type,
                            temperature=temperature,
                        ),
                    ),
                    timeout=self.timeout,
                )
                elapsed = time.time() - start
                logger.info(f"⏱️ [{label}] {model_name} tardó: {elapsed:.2f}s")

                text = (response.text or "").strip()
                if not text:
                    return default_value

                if parser:
                    return parser(text)
                return text  # type: ignore[return-value]

            except Exception as e:
                retryable_json_error = isinstance(e, json.JSONDecodeError)
                if (
                    (self._is_rate_limit(e) or retryable_json_error)
                    and attempt < self.max_retries - 1
                ):
                    if retryable_json_error:
                        logger.warning(
                            "[%s] Respuesta JSON inválida; se reintentará la extracción.",
                            label,
                        )
                    continue
                logger.error(
                    f"[{label}] Error en {model_name} (intento {attempt + 1}): {e}",
                    exc_info=True,
                )
                return default_value

        return default_value

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Limpia backticks y parsea JSON."""
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            if error.msg != "Extra data":
                raise

            # Vertex puede añadir accidentalmente un delimitador de cierre
            # duplicado aun usando response_mime_type=application/json. Si el
            # primer valor es íntegro y el remanente sólo contiene cierres,
            # recuperar ese valor es determinista y no oculta texto adicional.
            value, end = json.JSONDecoder().raw_decode(cleaned)
            trailing = cleaned[end:].strip()
            if trailing and all(char in "}]" for char in trailing):
                logger.warning(
                    "Se ignoraron delimitadores JSON de cierre duplicados en la respuesta."
                )
                return value
            raise

    async def generate_flash_lite_json(
        self,
        contents: str,
        temperature: float = 0.1,
        default: Optional[dict] = None,
        label: str = "Flash-Lite",
    ) -> dict:
        """Llama a Gemini Flash-Lite y devuelve un dict parseado de JSON."""
        return await self._generate_with_retries(
            model_name=self.flash_model,
            contents=contents,
            temperature=temperature,
            parser=self._parse_json,
            default_value=default or {},
            label=label,
        )
