import json
import re
import unicodedata
import logging

from google.genai import types

VERIFIER_INSTRUCTION = """Você compara um trecho original com sua versão simplificada, em português.
Liste apenas alterações de sentido de dois tipos:
- "perdida": ressalva, qualificador ou limitação do original que sumiu ou ficou mais forte
  (ex.: "pode" virou afirmação, "depende diretamente" virou "só funciona se").
- "alterada": termo, entidade, número ou fato do original trocado por outro de sentido diferente (ex.: "instituição de ensino" virou "escola"). Copie em "citacao" o trecho EXATO do original.
Não liste omissão se a ideia foi mantida com outras palavras (ex.: "Baldo afã" virou "esforço em vão").
- "acrescentada": certeza, exclusividade ou atribuição que não estava no original
  (ex.: "os autores afirmam", "só assim é certo", "apenas").
Não liste mudanças de vocabulário que mantêm o sentido.
Para cada alteração, copie em "citacao" um trecho EXATO do original (para "perdida")
ou da versão simplificada (para "acrescentada").
Responda só com JSON: {"trechos":[{"indice":1,"alertas":[{"tipo":"perdida","citacao":"..."}]}]}
Use "alertas": [] quando não houver alteração."""


def _norm(texto: str) -> str:
    d = unicodedata.normalize("NFD", texto.lower())
    d = "".join(c for c in d if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", d).strip()


def verify_caveats(client, model_name, segments):
    """Retorna {indice: [avisos]} ou None se a verificação falhar."""
    entrada = [
        {"indice": s["indice"], "original": s["original"], "simplificado": s["simplificado"]}
        for s in segments
    ]
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=json.dumps({"trechos": entrada}, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=VERIFIER_INSTRUCTION,
                temperature=0,
                response_mime_type="application/json",
                max_output_tokens=4096,
            ),
        )
        dados = json.loads(response.text)
        por_indice = {s["indice"]: s for s in segments}
        avisos = {}
        for item in dados["trechos"]:
            seg = por_indice.get(item.get("indice"))
            if seg is None:
                continue
            lista = []
            for alerta in item.get("alertas", []):
                tipo, citacao = alerta.get("tipo"), alerta.get("citacao", "")
                fonte = seg["simplificado"] if tipo == "acrescentada" else seg["original"]
                if tipo in ("perdida", "acrescentada", "alterada") and citacao and _norm(citacao) in _norm(fonte):
                    lista.append(f"{tipo}: “{citacao}”")
            avisos[seg["indice"]] = lista
        return avisos
    except Exception as error:
        logging.getLogger("clareia").warning(
            "verify_caveats_failed type=%s", type(error).__name__
        )
        return None