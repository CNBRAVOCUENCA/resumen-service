"""Cliente para el proveedor de IA (Gemini) vía su API REST.

Se define una interfaz mínima (`LLMClient`) para poder inyectar una
implementación falsa en los tests, sin llamar a la API real ni gastar
cuota. `GeminiClient` es la implementación concreta que habla con la API
de Google Generative Language.

Política de REINTENTOS (patrón Retry), documentada en
orquestador-service/infra/RESILIENCE.md:

- Solo se reintenta cuando hay certeza de que Gemini NO procesó el pedido,
  así no se duplican generaciones ni costos:
  * 429 (cuota/limite) y 503 (modelo saturado): Google rechazó el pedido.
  * Error de conexión (no se pudo abrir la conexión, ConnectError /
    ConnectTimeout): el pedido nunca llegó.
- NO se reintenta un 500, un timeout de lectura ni otros errores: el pedido
  pudo haberse procesado y repetirlo podría duplicar la generación facturable.
- Máximo 3 reintentos (4 intentos en total), espera creciente 2 s, 4 s, 6 s
  (o el Retry-After que mande Google, con un tope de 10 s).
- Presupuesto total: si la próxima espera haría superar `presupuesto_total_seg`
  (180 s por defecto), no se reintenta más y se devuelve el error.
"""

import asyncio
import time
from typing import Protocol

import httpx

from App.exceptions import LLMError, LLMNotConfiguredError

# Códigos en los que Google rechazó el pedido sin procesarlo (seguro reintentar)
_CODIGOS_REINTENTABLES = {429, 503}
_RETRY_AFTER_MAX_SEG = 10.0


class LLMClient(Protocol):
    """Interfaz mínima que debe cumplir cualquier cliente de IA."""

    async def generate(self, prompt: str) -> str:
        ...


class GeminiClient:
    """Implementación real que llama a la API REST de Gemini, con reintentos acotados."""

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_reintentos: int = 3,
        espera_base_seg: float = 2.0,
        presupuesto_total_seg: float = 180.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_reintentos = max_reintentos
        self.espera_base_seg = espera_base_seg
        self.presupuesto_total_seg = presupuesto_total_seg

    async def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise LLMNotConfiguredError("Falta GEMINI_API_KEY para llamar al proveedor de IA")

        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        # La clave va en un header y no en la URL: las URLs quedan registradas en
        # los logs (httpx, proxies), y así la clave nunca aparece en ellos.
        headers = {"x-goog-api-key": self.api_key}

        inicio = time.monotonic()
        for intento in range(self.max_reintentos + 1):
            espera: float | None = None
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as http_client:
                try:
                    response = await http_client.post(url, json=payload, headers=headers)
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    # El pedido nunca llegó a Gemini: es seguro reintentar.
                    ultimo_error = f"No se pudo conectar con el proveedor de IA: {exc}"
                    espera = self._espera(intento, None)
                except httpx.HTTPError as exc:
                    # Timeout de lectura u otro error: el pedido pudo procesarse. No se repite.
                    raise LLMError(f"Error al contactar al proveedor de IA: {exc}") from exc

            if espera is None:
                if response.status_code < 400:
                    return self._extraer_texto(response)
                ultimo_error = f"El proveedor de IA respondió {response.status_code}: {response.text[:200]}"
                if response.status_code not in _CODIGOS_REINTENTABLES:
                    raise LLMError(ultimo_error)
                espera = self._espera(intento, response.headers.get("retry-after"))

            ultimo_intento = intento >= self.max_reintentos
            excede_presupuesto = time.monotonic() - inicio + espera > self.presupuesto_total_seg
            if ultimo_intento or excede_presupuesto:
                break
            await asyncio.sleep(espera)

        raise LLMError(f"Se agotaron los reintentos. Último error: {ultimo_error}")

    @staticmethod
    def _extraer_texto(response: httpx.Response) -> str:
        """Une todas las partes de texto del primer candidato (Gemini puede partir la respuesta)."""
        try:
            partes = response.json()["candidates"][0]["content"]["parts"]
            texto = "".join(p.get("text", "") for p in partes).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Respuesta inesperada del proveedor de IA: {exc}") from exc
        if not texto:
            raise LLMError("El proveedor de IA devolvió una respuesta sin texto")
        return texto

    def _espera(self, intento: int, retry_after: str | None) -> float:
        """Espera creciente (2 s, 4 s, 6 s...) o el Retry-After del proveedor, con tope."""
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), _RETRY_AFTER_MAX_SEG)
            except ValueError:
                pass
        return self.espera_base_seg * (intento + 1)
