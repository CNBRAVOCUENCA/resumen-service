"""Cliente para el proveedor de IA (Gemini) vía su API REST.

Se define una interfaz mínima (`LLMClient`) para poder inyectar una
implementación falsa en los tests, sin llamar a la API real ni gastar
cuota. `GeminiClient` es la implementación concreta que habla con la API
de Google Generative Language.

Las solicitudes de generación son POST y no tienen clave de idempotencia.
Se ejecutan una sola vez: repetir una solicitud con resultado ambiguo podría
duplicar generación/costos.
"""

from typing import Protocol

import httpx

from App.exceptions import LLMError, LLMNotConfiguredError


class LLMClient(Protocol):
    """Interfaz mínima que debe cumplir cualquier cliente de IA."""

    async def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Implementación real que realiza una llamada HTTP por solicitud."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMNotConfiguredError("Falta GEMINI_API_KEY para llamar al proveedor de IA")

        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        # La clave va en un header y no en la URL: las URLs quedan registradas en
        # los logs (httpx, proxies), y así la clave nunca aparece en ellos.
        headers = {"x-goog-api-key": self.api_key}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http_client:
                response = await http_client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"No se pudo contactar al proveedor de IA: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(
                f"El proveedor de IA respondió {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Respuesta inesperada del proveedor de IA: {exc}") from exc
