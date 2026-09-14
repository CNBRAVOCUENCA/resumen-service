"""Test que demuestra el principio Abierto/Cerrado (SOLID - O):

ResumenService funciona con cualquier implementación de LLMClient sin
necesidad de modificarlo. Acá se le inyecta un proveedor de IA totalmente
distinto (uno falso, que no es Gemini) y el servicio funciona igual —
prueba de que está abierto a extensión y cerrado a modificación.
"""

from App.services.resumen_service import ResumenService


class ProveedorIAAlternativo:
    """Un proveedor de IA distinto a Gemini, que cumple la interfaz LLMClient
    sin heredar de nada — solo implementa el método generate()."""

    async def generate(self, prompt: str) -> str:
        return "resumen de otro proveedor de IA"


async def test_servicio_funciona_con_otro_proveedor_de_ia():
    # Se inyecta un proveedor completamente distinto, sin tocar ResumenService
    service = ResumenService(llm_client=ProveedorIAAlternativo())
    resultado = await service.summarize("texto a resumir", max_words=50)
    assert resultado.summary == "resumen de otro proveedor de IA"
