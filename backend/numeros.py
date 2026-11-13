import re
from decimal import Decimal, InvalidOperation

_UNIDADES = sorted(
    ["%", "°C", "ºC", "km", "cm", "mm", "kg", "mg", "ml", "m", "g", "l", "h",
     "min", "s", "anos", "ano", "meses", "mês", "dias", "dia", "semanas",
     "semana", "horas", "hora", "minutos", "minuto", "segundos", "segundo"],
    key=len, reverse=True,
)
_UN = "|".join(re.escape(u) for u in _UNIDADES)

PADRAO = re.compile(
    r"(?<![\w.,/])(?P<data>\d{1,2}/\d{1,2}/\d{2,4})"
    r"|(?<![\w.,/])(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    rf"(?:\s?(?P<un>(?:{_UN})(?![\wÀ-ÿ])))?",
    re.IGNORECASE,
)

def _valor(token: str) -> str:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", token):
        token = token.replace(".", "")
    token = token.replace(",", ".")
    try:
        return format(Decimal(token).normalize(), "f")
    except InvalidOperation:
        return token

def _extrair(texto: str) -> list[tuple[str, str, str]]:
    achados = []
    for m in PADRAO.finditer(texto):
        if m.group("data"):
            chave = "/".join(str(int(p)) for p in m.group("data").split("/"))
            unidade = ""
        else:
            chave = _valor(m.group("num"))
            unidade = (m.group("un") or "").lower().replace("º", "°")
        achados.append((chave, unidade, m.group(0).strip()))
    return achados

def find_number_changes(original: str, simplificado: str) -> list[str]:
    restantes = _extrair(simplificado)
    alertas: list[tuple[str, str]] = []
    for chave, unidade, trecho in _extrair(original):
        i = next((k for k, (c, u, _) in enumerate(restantes)
                  if c == chave and u == unidade), None)
        if i is not None:
            restantes.pop(i)
            continue
        i = next((k for k, (c, _, _) in enumerate(restantes) if c == chave), None)
        if i is not None:
            restantes.pop(i)
            alertas.append(("alterada", trecho))
        else:
            alertas.append(("perdida", trecho))
    alertas += [("acrescentada", t) for _, _, t in restantes]
    return [f"{tipo}: “{citacao}”" for tipo, citacao in alertas]