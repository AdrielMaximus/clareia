import re
import unicodedata

RESSALVAS = (
    ("integralmente", "totalmente", "completamente", "por completo"),
    ("pode", "podem"),
    ("depende", "dependem"),
    ("geralmente", "normalmente", "em geral"),
    ("apenas", "somente", "so"),
)


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _contem_palavra(texto_normalizado: str, palavra: str) -> bool:
    return re.search(rf"\b{re.escape(palavra)}\b", texto_normalizado) is not None


def find_lost_caveats(original: str, simplificado: str) -> list[str]:
    original_n = _normalizar(original)
    simplificado_n = _normalizar(simplificado)
    return [
        grupo[0]
        for grupo in RESSALVAS
        if any(_contem_palavra(original_n, p) for p in grupo)
        and not any(_contem_palavra(simplificado_n, p) for p in grupo)
    ]