"""Rutas REST del microservicio de Resumen con IA."""

from fastapi import APIRouter, Depends

from App.config.settings import settings
from App.schemas.summary import SummarizeRequest, SummaryResponse
from App.services.llm_client import GeminiClient
from App.services.resumen_service import ResumenService

router = APIRouter(tags=["resumen"])


def _get_service() -> ResumenService:
    client = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        base_url=settings.gemini_base_url,
    )
    return ResumenService(llm_client=client)


@router.post("/summarize", response_model=SummaryResponse)
async def summarize(payload: SummarizeRequest, service: ResumenService = Depends(_get_service)) -> SummaryResponse:
    """Genera un resumen del texto recibido usando IA (Gemini)."""
    result = await service.summarize(payload.text, payload.max_words or 150)
    return SummaryResponse(
        summary=result.summary,
        input_char_count=result.input_char_count,
        summary_char_count=result.summary_char_count,
    )
