"""Modelo de dominio para el resultado de un resumen."""

from pydantic import BaseModel


class SummaryResult(BaseModel):
    summary: str
    input_char_count: int
    summary_char_count: int
