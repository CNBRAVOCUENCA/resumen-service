"""Schemas (DTOs) de la API de Resumen."""

from typing import Optional

from pydantic import BaseModel


class SummarizeRequest(BaseModel):
    text: str
    max_words: Optional[int] = 150


class SummaryResponse(BaseModel):
    summary: str
    input_char_count: int
    summary_char_count: int
