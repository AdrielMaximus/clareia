import asyncio
import json
import logging
import os
import re
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai.errors import APIError
from google.genai import types
from pydantic import BaseModel
try:
    from backend.ressalvas_llm import verify_caveats
except ImportError:
    from ressalvas_llm import verify_caveats
try:
    from backend.ressalvas import find_lost_caveats
except ImportError:
    from ressalvas import find_lost_caveats
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_MODEL_NAME = "gemini-3.5-flash-lite"
REQUEST_TIMEOUT_SECONDS = 30
RETRY_DELAYS_SECONDS = (2, 4, 8, 16)
MAX_GENERATION_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1
TOTAL_REQUEST_TIMEOUT_SECONDS = (
    REQUEST_TIMEOUT_SECONDS * MAX_GENERATION_ATTEMPTS
    + sum(RETRY_DELAYS_SECONDS)
    + 5
)
MAX_TEXT_CHARACTERS = 5000
GEMINI_FAILURE_MESSAGE = "Não foi possível simplificar o texto agora. Tente novamente."
FRONTEND_DIRECTORY = Path(__file__).resolve().parents[1] / "dist" / "public"
SYSTEM_INSTRUCTION = """Você é um assistente que simplifica textos acadêmicos em português
brasileiro para facilitar a leitura de pessoas com dificuldade de atenção
e concentração. Reescreva o texto recebido seguindo estas regras:
(1) use frases mais curtas e diretas;
(2) preserve as informações principais do texto;
(3) preserve os conceitos técnicos e seus significados originais;
(4) preserve as relações de causa e consequência;
(5) preserve as ressalvas e limitações feitas pelo autor;
(6) não invente informações, exemplos, dados ou fontes que não estejam no
texto original;
(7) organize o resultado em parágrafos curtos;
(8) responda apenas com o texto simplificado, sem comentários, títulos,
listas ou explicações sobre o que foi feito."""
SimplificationLevel = Literal["leve", "media", "forte"]
TermStrategy = Literal["manter", "explicar"]


class GeminiRetryExhaustedError(RuntimeError):
    pass


LEVEL_INSTRUCTIONS: dict[SimplificationLevel, str] = {
    "leve": "faça poucas alterações, divida apenas as frases mais longas.",
    "media": "use frases curtas e diretas e reorganize frases complexas.",
    "forte": "use frases muito curtas, uma ideia por frase, e vocabulário cotidiano.",
}

TERM_INSTRUCTIONS: dict[TermStrategy, str] = {
    "manter": "mantenha os termos técnicos exatamente como estão.",
    "explicar": "mantenha os termos técnicos e explique cada um brevemente, "
    "sem alterar o sentido.",
}

ABBREVIATION_PATTERN = re.compile(
    r"(?<!\w)(?:pp|p|dr|dra|sr|et\s+al|etc|ex|cap|fig)\.",
    re.IGNORECASE,
)
SENTENCE_CLOSERS = "\"'”’»)]}"


def build_system_instruction(
    level: SimplificationLevel,
    terms: TermStrategy,
) -> str:
    return (
        f"{SYSTEM_INSTRUCTION}\n"
        f"Nível de simplificação: {LEVEL_INSTRUCTIONS[level]}\n"
        f"Termos técnicos: {TERM_INSTRUCTIONS[terms]}\n"
        "Formato de saída estruturada (substitui a instrução anterior sobre "
        "formato): processe cada trecho numerado separadamente, mantendo a ordem "
        "e o índice recebido. Responda somente com um objeto JSON válido no formato "
        '{"trechos":[{"indice":1,"simplificado":"...","explicacao":"...","contexto":"..."}]}. '
        "Cada item deve ter indice numérico e os campos simplificado, explicacao "
        "e contexto em texto simples. A explicacao deve ser curta e dizer o que "
        "mudou e por quê. O campo contexto é opcional: preencha com no máximo "
        "duas frases apenas quando o trecho citar uma obra, evento histórico, "
        "época, movimento ou conceito amplamente conhecido cujo contexto ajude a "
        "entender o trecho. Nunca coloque contexto dentro de simplificado."
        "O campo simplificado deve conter somente a reescrita do trecho, sem "
        "comentários sobre a simplificação nem frases como 'isso foi simplificado'. "
        "Se for preciso explicar um termo técnico, use no máximo uma frase curta "
        "dentro do próprio trecho; todo o resto vai em explicacao. "
        "explique autores citados em referências bibliográficas e não invente "
        'fatos; se não tiver certeza ou não houver o que contextualizar, use "". '
        "Não inclua o texto original, comentários, HTML, Markdown ou texto fora do JSON."
        "Preserve citações bibliográficas (autor, ano, página, números entre "
        "colchetes) exatamente como aparecem. Não troque termos específicos por "
        "outros de sentido diferente. Não acrescente nomes de pessoas, deuses, "
        "lugares ou obras que não estejam no trecho e não complete trechos "
        "cortados. Se o original expressar opinião dos autores, mantenha-a como "
        "opinião. Só explique um termo técnico se a definição for consensual e "
        "correta; na dúvida, não explique. "
    )

logger = logging.getLogger("clareia")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


class SimplifyRequest(BaseModel):
    text: str
    level: SimplificationLevel = "media"
    terms: TermStrategy = "explicar"


def _log_request(status: int, text_length: int) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(
        "timestamp=%s status=%d text_length=%d",
        timestamp,
        status,
        text_length,
    )


def _error_response(status: int, message: str, text_length: int) -> JSONResponse:
    _log_request(status, text_length)
    return JSONResponse(status_code=status, content={"error": message})


def extract_text_parts(response: Any) -> str:
    text_parts: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                text_parts.append(part_text)
    return "".join(text_parts).strip()

def _join_lines(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    return [
        " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        for paragraph in paragraphs
        if paragraph.strip()
    ]
def split_text_into_segments(text: str) -> list[str]:
    segments: list[str] = []

    for paragraph in _join_lines(text):
        line = " ".join(paragraph.split())
        if not line:
            continue

        protected_abbreviation_periods = {
            match.end() - 1 for match in ABBREVIATION_PATTERN.finditer(line)
        }
        segment_start = 0

        for position, character in enumerate(line):
            if character not in ".?!…":
                continue
            if character == ".":
                if position in protected_abbreviation_periods:
                    continue
                if (
                    position > 0
                    and position + 1 < len(line)
                    and line[position - 1].isdigit()
                    and line[position + 1].isdigit()
                ):
                    continue

            boundary_end = position + 1
            while (
                boundary_end < len(line)
                and line[boundary_end] in SENTENCE_CLOSERS
            ):
                boundary_end += 1
            if boundary_end < len(line) and not line[boundary_end].isspace():
                continue

            segment = line[segment_start:boundary_end].strip()
            if segment:
                segments.append(segment)
            segment_start = boundary_end
            while segment_start < len(line) and line[segment_start].isspace():
                segment_start += 1

        remainder = line[segment_start:].strip()
        if remainder:
            segments.append(remainder)

    return segments


def _strip_outer_json_fence(response_text: str) -> str:
    content = response_text.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, count=1, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content, count=1)
    return content.strip()


def parse_structured_segments(
    response_text: str,
    original_segments: list[str],
) -> list[dict[str, Any]]:
    content = _strip_outer_json_fence(response_text)
    result = json.loads(content)
    if not isinstance(result, dict) or not isinstance(result.get("trechos"), list):
        raise ValueError("invalid structured response")

    model_segments = result["trechos"]
    if len(model_segments) != len(original_segments):
        raise ValueError("invalid structured response")

    parsed_segments: list[dict[str, Any]] = []
    for expected_index, (item, original) in enumerate(
        zip(model_segments, original_segments),
        start=1,
    ):
        if not isinstance(item, dict):
            raise ValueError("invalid structured response")
        if type(item.get("indice")) is not int or item["indice"] != expected_index:
            raise ValueError("invalid structured response")

        simplified = item.get("simplificado")
        explanation = item.get("explicacao")
        if (
            not isinstance(simplified, str)
            or not simplified.strip()
            or not isinstance(explanation, str)
            or not explanation.strip()
        ):
            raise ValueError("invalid structured response")

        contexto = item.get("contexto", "")
        if not isinstance(contexto, str):
            contexto = ""

        parsed_segments.append(
            {
                "indice": expected_index,
                "original": original,
                "simplificado": simplified.strip(),
                "explicacao": explanation.strip(),
                "contexto": contexto.strip(),
                "ressalvas": find_lost_caveats(original, simplified.strip()),
            }
        )

    return parsed_segments


def _plain_text_fallback(response_text: str) -> str:
    return _strip_outer_json_fence(response_text)


def generate_simplified_result(
    text: str,
    api_key: str,
    level: SimplificationLevel = "media",
    terms: TermStrategy = "explicar",
) -> tuple[str, list[dict[str, Any]]]:
    model_name = os.environ.get("MODEL_NAME", DEFAULT_MODEL_NAME).strip()
    if not model_name:
        model_name = DEFAULT_MODEL_NAME

    original_segments = split_text_into_segments(text)
    numbered_segments = [
        {"indice": index, "original": original}
        for index, original in enumerate(original_segments, start=1)
    ]
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000),
    )
    try:
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=json.dumps(
                        {"trechos": numbered_segments},
                        ensure_ascii=False,
                    ),
                    config=types.GenerateContentConfig(
                        system_instruction=build_system_instruction(level, terms),
                        temperature=0.2,
                        top_p=0.9,
                        max_output_tokens=8192,
                    ),
                )
            except Exception as error:
                error_code = _error_code_for_log(error)
                _log_gemini_error(error, error_code, attempt, "unavailable")

                if not _is_retryable_gemini_error(error):
                    raise
                if attempt == MAX_GENERATION_ATTEMPTS:
                    raise GeminiRetryExhaustedError(
                        "Gemini retry limit reached"
                    ) from error

                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue

            finish_reason = _log_finish_reasons(response)
            response_text = extract_text_parts(response)
            if not response_text:
                logger.warning(
                    "gemini_error type=EmptyResponse code=empty_response "
                    "attempt=%d finish_reason=%s",
                    attempt,
                    finish_reason,
                )
                if attempt == MAX_GENERATION_ATTEMPTS:
                    raise GeminiRetryExhaustedError(
                        "Gemini returned empty responses"
                    )
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue

            try:
                segments = parse_structured_segments(
                    response_text,
                    original_segments,
                )
            except (ValueError, json.JSONDecodeError):
                logger.warning(
                    "gemini_error type=InvalidStructuredResponse "
                    "code=invalid_json attempt=%d finish_reason=%s",
                    attempt,
                    finish_reason,
                )
                if attempt == MAX_GENERATION_ATTEMPTS:
                    return _plain_text_fallback(response_text), []
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                continue

            avisos = verify_caveats(client, model_name, segments)
            if avisos is not None:
                for segment in segments:
                    segment["ressalvas"] = avisos.get(segment["indice"], [])

            simplified = "\n\n".join(
                segment["simplificado"] for segment in segments
            )
            return simplified, segments

        raise GeminiRetryExhaustedError("Gemini retry limit reached")
    finally:
        client.close()


def _is_timeout(error: BaseException) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, (TimeoutError, asyncio.TimeoutError)):
            return True
        if "timeout" in type(current).__name__.lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def _error_code_for_log(error: BaseException) -> str:
    if _is_timeout(error):
        return "timeout"

    code = getattr(error, "code", None)
    if isinstance(code, int):
        return str(code)
    if isinstance(code, str) and code.isdigit():
        return code
    return "unknown"


def _is_retryable_gemini_error(error: BaseException) -> bool:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code.isdigit():
        code = int(code)
    return _is_timeout(error) or code in {429, 500, 503}


def _finish_reason_name(candidate: Any) -> str:
    reason = getattr(candidate, "finish_reason", None)
    if reason is None:
        return "unspecified"

    name = getattr(reason, "name", None)
    if isinstance(name, str):
        return name

    value = getattr(reason, "value", None)
    if isinstance(value, str):
        return value

    return str(reason).rsplit(".", 1)[-1]


def _log_finish_reasons(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    reasons = [_finish_reason_name(candidate) for candidate in candidates]
    rendered = ",".join(reasons) if reasons else "none"
    logger.info("gemini_response finish_reason=%s", rendered)
    if "MAX_TOKENS" in reasons:
        logger.warning("gemini_response_warning finish_reason=MAX_TOKENS")
    return rendered


def _log_gemini_error(
    error: BaseException,
    error_code: str,
    attempt: int,
    finish_reason: str,
) -> None:
    logger.warning(
        "gemini_error type=%s code=%s attempt=%d finish_reason=%s",
        type(error).__name__,
        error_code,
        attempt,
        finish_reason,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.environ.get("GEMINI_API_KEY"):
        logger.warning(
            "GEMINI_API_KEY não configurada. A simplificação de textos está indisponível."
        )
    yield


app = FastAPI(title="Clareia API", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _: Request,
    error: RequestValidationError,
) -> JSONResponse:
    body: Any = error.body
    value = body.get("text") if isinstance(body, dict) else None
    text_length = len(value.strip()) if isinstance(value, str) else 0
    return _error_response(400, "Envie um texto válido para simplificar.", text_length)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/simplify")
async def simplify(payload: SimplifyRequest) -> JSONResponse:
    text = payload.text.strip()
    text_length = len(text)

    if not text:
        return _error_response(400, "Digite ou cole um texto para simplificar.", 0)

    if text_length > MAX_TEXT_CHARACTERS:
        return _error_response(
            413,
            "O texto precisa ter até 5.000 caracteres.",
            text_length,
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return _error_response(
            503,
            "A simplificação ainda não está configurada. Tente novamente mais tarde.",
            text_length,
        )

    try:
        simplified, segments = await asyncio.wait_for(
            asyncio.to_thread(
                generate_simplified_result,
                text,
                api_key,
                payload.level,
                payload.terms,
            ),
            timeout=TOTAL_REQUEST_TIMEOUT_SECONDS,
        )
    except GeminiRetryExhaustedError:
        return _error_response(502, GEMINI_FAILURE_MESSAGE, text_length)
    except asyncio.TimeoutError:
        _log_gemini_error(
            asyncio.TimeoutError(),
            "timeout",
            MAX_GENERATION_ATTEMPTS,
            "unavailable",
        )
        return _error_response(502, GEMINI_FAILURE_MESSAGE, text_length)
    except APIError as error:
        return _error_response(502, GEMINI_FAILURE_MESSAGE, text_length)
    except Exception as error:
        logger.exception("unexpected_error type=%s", type(error).__name__)
        if _is_timeout(error):
            _log_gemini_error(
                error,
                "timeout",
                MAX_GENERATION_ATTEMPTS,
                "unavailable",
            )
            return _error_response(502, GEMINI_FAILURE_MESSAGE, text_length)
        return _error_response(
            500,
            "Ocorreu um erro ao simplificar o texto. Tente novamente.",
            text_length,
        )

    if not simplified:
        return _error_response(
            502,
            GEMINI_FAILURE_MESSAGE,
            text_length,
        )

    _log_request(200, text_length)
    return JSONResponse(
        content={
            "simplified": simplified,
            "segments": segments,
        }
    )


app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIRECTORY), html=True),
    name="frontend",
)
