"""Pruebas unitarias para ResumenService, con un cliente de IA falso."""

from unittest.mock import AsyncMock

import pytest
from App.exceptions import EmptyTextError
from App.services.resumen_service import ResumenService


async def test_summarize_success():
    fake_llm = AsyncMock()
    fake_llm.generate.return_value = "Este es el resumen generado."
    service = ResumenService(llm_client=fake_llm)

    result = await service.summarize("Un texto largo para resumir.", max_words=50)

    assert result.summary == "Este es el resumen generado."
    assert result.input_char_count == len("Un texto largo para resumir.")
    assert result.summary_char_count > 0
    fake_llm.generate.assert_awaited_once()


async def test_summarize_rejects_empty_text():
    fake_llm = AsyncMock()
    service = ResumenService(llm_client=fake_llm)
    with pytest.raises(EmptyTextError):
        await service.summarize("   ", max_words=50)
    fake_llm.generate.assert_not_awaited()


async def test_prompt_includes_max_words():
    fake_llm = AsyncMock()
    fake_llm.generate.return_value = "resumen"
    service = ResumenService(llm_client=fake_llm)
    await service.summarize("texto", max_words=42)
    prompt_usado = fake_llm.generate.await_args.args[0]
    assert "42" in prompt_usado


async def test_trunca_el_texto_segun_el_limite_inyectado():
    llm = AsyncMock()
    llm.generate.return_value = "resumen"
    service = ResumenService(llm_client=llm, max_input_chars=10)

    resultado = await service.summarize("a" * 50)

    prompt = llm.generate.await_args.args[0]
    assert prompt.endswith("a" * 10)
    assert "a" * 11 not in prompt
    assert resultado.input_char_count == 50
