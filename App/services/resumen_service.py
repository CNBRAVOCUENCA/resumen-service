"""Servicio de resumen: arma el prompt y delega en el cliente de IA.

Con el cliente de IA inyectado (DIP), lo que permite testear la lógica de
armado de prompt y validación sin llamar a la API real.
"""

from App.config.settings import settings
from App.exceptions import EmptyTextError
from App.models.summary_result import SummaryResult
from App.services.llm_client import LLMClient


class ResumenService:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def _build_prompt(self, text: str, max_words: int) -> str:
        return (
            f"Resumí el siguiente texto en español, en un máximo de {max_words} palabras, "
            f"de forma clara y objetiva. Devolvé solo el resumen, sin preámbulos.\n\n"
            f"TEXTO:\n{text}"
        )

    async def summarize(self, text: str, max_words: int = 150) -> SummaryResult:
        normalized = text.strip()
        if not normalized:
            raise EmptyTextError("El texto a resumir está vacío")

        # Truncar entradas excesivas para no exceder límites del proveedor
        truncated = normalized[: settings.max_input_chars]
        prompt = self._build_prompt(truncated, max_words)
        summary = await self.llm_client.generate(prompt)

        return SummaryResult(
            summary=summary,
            input_char_count=len(normalized),
            summary_char_count=len(summary),
        )
