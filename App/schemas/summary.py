"""Schemas (DTOs) de la API de Resumen."""


from pydantic import BaseModel, Field

# Límites del parámetro max_words. El límite es orientativo para el modelo
# (se le pide "un máximo de N palabras"), pero el rango se valida antes de
# llamar a Gemini: 0, negativos o valores enormes se rechazan con 422.
MAX_WORDS_DEFAULT = 150
MAX_WORDS_MIN = 10
MAX_WORDS_MAX = 500


class SummarizeRequest(BaseModel):
    text: str
    max_words: int = Field(
        default=MAX_WORDS_DEFAULT,
        ge=MAX_WORDS_MIN,
        le=MAX_WORDS_MAX,
        description=(
            f"Máximo orientativo de palabras del resumen ({MAX_WORDS_MIN}-{MAX_WORDS_MAX}, "
            f"por defecto {MAX_WORDS_DEFAULT})."
        ),
    )


class SummaryResponse(BaseModel):
    summary: str
    input_char_count: int
    summary_char_count: int
