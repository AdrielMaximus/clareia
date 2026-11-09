import os
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch
from backend.ressalvas import find_lost_caveats

from fastapi.testclient import TestClient
from google.genai.errors import APIError

from backend.main import (
    DEFAULT_MODEL_NAME,
    GEMINI_FAILURE_MESSAGE,
    SYSTEM_INSTRUCTION,
    app,
    build_system_instruction,
    extract_text_parts,
    generate_simplified_result,
    parse_structured_segments,
    split_text_into_segments,
)


class SimplifyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        verifier = patch("backend.main.verify_caveats", return_value=None)
        verifier.start()
        self.addCleanup(verifier.stop)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_frontend_is_served_by_fastapi(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<div id="root"></div>', response.text)

    def test_prompt_base_matches_the_untouched_snapshot(self) -> None:
        snapshot = Path(__file__).resolve().parents[1] / "docs" / "prompt_v0.txt"
        self.assertEqual(
            snapshot.read_text().removesuffix("\n"),
            SYSTEM_INSTRUCTION,
        )

    def test_segmentation_preserves_abbreviations_decimals_and_line_breaks(self) -> None:
        source = (
            "Dr. Ana leu 2.5 páginas (p. 3). "
            "Ela citou Silva et al., cap. 4, fig. 2, ex. 2, etc. Depois, escreveu.\n"
            "A Dra. Lu e o Sr. João leram pp. 20-22."
        )

        self.assertEqual(
            split_text_into_segments(source),
            [
                "Dr. Ana leu 2.5 páginas (p. 3).",
                "Ela citou Silva et al., cap. 4, fig. 2, ex. 2, etc. Depois, escreveu.",
                "A Dra. Lu e o Sr. João leram pp. 20-22.",
            ],
        )

    def test_structured_response_uses_source_segments_and_validates_fields(self) -> None:
        original = "Texto original. Outra frase."
        source_segments = split_text_into_segments(original)
        model_response = (
            '{"trechos":['
            '{"indice":1,"original":"texto inventado",'
            '"simplificado":"Texto claro.","explicacao":"Frase mais direta."},'
            '{"indice":2,"simplificado":"Outra ideia.",'
            '"explicacao":"Mantém o sentido."}'
            "]}"
        )

        parsed = parse_structured_segments(model_response, source_segments)

        expected = [
            {
                "indice": 1,
                "original": "Texto original.",
                "simplificado": "Texto claro.",
                "explicacao": "Frase mais direta.",
                "contexto": "",
                "ressalvas": [],
            },
            {
                "indice": 2,
                "original": "Outra frase.",
                "simplificado": "Outra ideia.",
                "explicacao": "Mantém o sentido.",
                "contexto": "",
                "ressalvas": [],
            },
        ]

        self.assertEqual(parsed, expected)
        self.assertEqual(
            parse_structured_segments(
                f"```json\n{model_response}\n```",
                source_segments,
            ),
            expected,
        )

    def test_structured_response_rejects_invalid_shape_count_index_and_fields(self) -> None:
        originals = ["Frase original."]
        invalid_responses = (
            "não é JSON",
            '{"trechos":[]}',
            '{"trechos":[{"indice":2,"simplificado":"x","explicacao":"y"}]}',
            '{"trechos":[{"indice":1,"simplificado":2,"explicacao":"y"}]}',
        )

        for response_text in invalid_responses:
            with self.subTest(response_text=response_text):
                with self.assertRaises(ValueError):
                    parse_structured_segments(response_text, originals)

    def test_prompt_uses_the_exact_selected_rules(self) -> None:
        prompt = build_system_instruction("media", "explicar")
        self.assertTrue(prompt.startswith(f"{SYSTEM_INSTRUCTION}\n"))
        self.assertIn(
            "Nível de simplificação: use frases curtas e diretas e reorganize "
            "frases complexas.",
            prompt,
        )
        self.assertIn(
            "Termos técnicos: mantenha os termos técnicos e explique cada um "
            "brevemente, sem alterar o sentido.",
            prompt,
        )
        self.assertIn("somente com um objeto JSON válido", prompt)
        self.assertIn('"indice":1,"simplificado":"...","explicacao":"..."', prompt)
        self.assertIn(
            "Nível de simplificação: faça poucas alterações, divida apenas as "
            "frases mais longas.",
            build_system_instruction("leve", "manter"),
        )
        self.assertIn(
            "Nível de simplificação: use frases muito curtas, uma ideia por "
            "frase, e vocabulário cotidiano.",
            build_system_instruction("forte", "explicar"),
        )
        self.assertIn(
            "Termos técnicos: mantenha os termos técnicos exatamente como estão.",
            build_system_instruction("leve", "manter"),
        )
        self.assertIn(
            "Termos técnicos: mantenha os termos técnicos e explique cada um "
            "brevemente, sem alterar o sentido.",
            build_system_instruction("forte", "explicar"),
        )

    def test_response_keeps_only_text_parts(self) -> None:
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(text="Primeira parte."),
                            SimpleNamespace(thought_signature="nao-devolver"),
                            SimpleNamespace(text="\n\nSegunda parte."),
                        ]
                    )
                )
            ]
        )

        self.assertEqual(
            extract_text_parts(response),
            "Primeira parte.\n\nSegunda parte.",
        )

    def test_model_name_uses_environment_override(self) -> None:
        generated = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                text=(
                                    '{"trechos":[{"indice":1,'
                                    '"simplificado":"Resultado",'
                                    '"explicacao":"Frase mais direta."}]}'
                                )
                            )
                        ]
                    )
                )
            ]
        )
        with patch.dict(os.environ, {"MODEL_NAME": "modelo-de-teste"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.return_value = generated

                result = generate_simplified_result(
                    "Texto",
                    "test-key",
                    level="forte",
                    terms="explicar",
                )

        self.assertEqual(result[0], "Resultado")
        self.assertEqual(result[1][0]["original"], "Texto")
        call = client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], "modelo-de-teste")
        self.assertEqual(
            json.loads(call.kwargs["contents"]),
            {"trechos": [{"indice": 1, "original": "Texto"}]},
        )
        self.assertEqual(call.kwargs["config"].temperature, 0.2)
        self.assertEqual(call.kwargs["config"].top_p, 0.9)
        self.assertEqual(call.kwargs["config"].max_output_tokens, 8192)
        self.assertEqual(
            call.kwargs["config"].system_instruction,
            build_system_instruction("forte", "explicar"),
        )

    def test_model_name_defaults_to_gemini_3_5_flash_lite(self) -> None:
        generated = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                text=(
                                    '{"trechos":[{"indice":1,'
                                    '"simplificado":"Resultado",'
                                    '"explicacao":"Frase mais direta."}]}'
                                )
                            )
                        ]
                    )
                )
            ]
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MODEL_NAME", None)
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.return_value = generated

                result = generate_simplified_result("Texto", "test-key")

        self.assertEqual(result[0], "Resultado")
        self.assertEqual(result[1][0]["original"], "Texto")
        self.assertEqual(
            client.models.generate_content.call_args.kwargs["model"],
            DEFAULT_MODEL_NAME,
        )

    def test_empty_text_is_rejected(self) -> None:
        with patch("backend.main.genai.Client") as client_factory:
            response = self.client.post("/api/simplify", json={"text": "  \n  "})

        client_factory.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": "Digite ou cole um texto para simplificar."},
        )

    def test_text_over_limit_is_rejected(self) -> None:
        with patch("backend.main.genai.Client") as client_factory:
            response = self.client.post("/api/simplify", json={"text": "x" * 5001})

        client_factory.assert_not_called()
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json(),
            {"error": "O texto precisa ter até 5.000 caracteres."},
        )

    def test_plain_text_fallback_response_keeps_simplified_text(self) -> None:
        original = "Texto de teste. " * 70
        expected = "Primeiro parágrafo simplificado.\n\nSegundo parágrafo."
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch(
                "backend.main.generate_simplified_result",
                return_value=(expected, []),
            ) as model:
                with self.assertLogs("clareia", level="INFO") as captured:
                    response = self.client.post(
                        "/api/simplify",
                        json={"text": original},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"simplified": expected, "segments": []})
        model.assert_called_once_with(
            original.strip(),
            "test-key",
            "media",
            "explicar",
        )
        self.assertNotIn(original, "\n".join(captured.output))
        self.assertIn(f"text_length={len(original.strip())}", captured.output[0])

    def test_api_returns_segment_objects_from_the_backend(self) -> None:
        expected_segments = [
            {
                "indice": 1,
                "original": "Texto original.",
                "simplificado": "Texto claro.",
                "explicacao": "Frase mais direta.",
                "contexto": "",
                "ressalvas": [],
            }
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch(
                "backend.main.generate_simplified_result",
                return_value=("Texto claro.", expected_segments),
            ):
                response = self.client.post(
                    "/api/simplify",
                    json={"text": "Texto original."},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "simplified": "Texto claro.",
                "segments": expected_segments,
            },
        )

    def test_selected_options_are_passed_to_the_model(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch(
                "backend.main.generate_simplified_result",
                return_value=("Texto simplificado.", []),
            ) as model:
                response = self.client.post(
                    "/api/simplify",
                    json={
                        "text": "Texto válido.",
                        "level": "forte",
                        "terms": "manter",
                    },
                )

        self.assertEqual(response.status_code, 200)
        model.assert_called_once_with(
            "Texto válido.",
            "test-key",
            "forte",
            "manter",
        )

    def test_invalid_options_are_rejected_without_logging_text(self) -> None:
        for invalid_options in (
            {"level": "extremo", "terms": "explicar"},
            {"level": "media", "terms": "traduzir"},
            {"level": "media", "terms": "substituir"},
        ):
            text = "Conteúdo privado para teste."
            with self.subTest(invalid_options=invalid_options):
                with self.assertLogs("clareia", level="INFO") as captured:
                    response = self.client.post(
                        "/api/simplify",
                        json={"text": text, **invalid_options},
                    )

                self.assertEqual(response.status_code, 400)
                self.assertNotIn(text, "\n".join(captured.output))

    def test_retryable_api_errors_retry_four_times_then_return_502(self) -> None:
        text = "Conteúdo privado para teste."
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.side_effect = [
                    APIError(429, {"error": {"message": "rate limit"}}),
                    APIError(500, {"error": {"message": "server error"}}),
                    APIError(503, {"error": {"message": "unavailable"}}),
                    APIError(429, {"error": {"message": "rate limit"}}),
                    APIError(500, {"error": {"message": "server error"}}),
                ]
                with patch("backend.main.time.sleep") as sleep:
                    with self.assertLogs("clareia", level="WARNING") as captured:
                        response = self.client.post(
                            "/api/simplify",
                            json={"text": text},
                        )

        self.assertEqual(client.models.generate_content.call_count, 5)
        sleep.assert_has_calls([call(2), call(4), call(8), call(16)])
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": GEMINI_FAILURE_MESSAGE})
        logs = "\n".join(captured.output)
        self.assertIn("type=APIError code=429", logs)
        self.assertIn("type=APIError code=500", logs)
        self.assertIn("type=APIError code=503", logs)
        self.assertNotIn(text, logs)

    def test_timeout_retries_four_times_then_returns_502(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.side_effect = [
                    TimeoutError(),
                    TimeoutError(),
                    TimeoutError(),
                    TimeoutError(),
                    TimeoutError(),
                ]
                with patch("backend.main.time.sleep") as sleep:
                    with self.assertLogs("clareia", level="WARNING") as captured:
                        response = self.client.post(
                            "/api/simplify",
                            json={"text": "Texto privado."},
                        )

        self.assertEqual(client.models.generate_content.call_count, 5)
        sleep.assert_has_calls([call(2), call(4), call(8), call(16)])
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": GEMINI_FAILURE_MESSAGE})
        self.assertIn("type=TimeoutError code=timeout", "\n".join(captured.output))
        self.assertNotIn("Texto privado.", "\n".join(captured.output))

    def test_empty_response_retries_and_logs_finish_reason(self) -> None:
        empty_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(parts=[]),
                )
            ]
        )
        successful_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                text=(
                                    '{"trechos":[{"indice":1,'
                                    '"simplificado":"Resultado",'
                                    '"explicacao":"Texto mais direto."}]}'
                                )
                            )
                        ]
                    ),
                )
            ]
        )
        with patch("backend.main.genai.Client") as client_factory:
            client = client_factory.return_value
            client.models.generate_content.side_effect = [
                empty_response,
                successful_response,
            ]
            with patch("backend.main.time.sleep") as sleep:
                with self.assertLogs("clareia", level="INFO") as captured:
                    result = generate_simplified_result(
                        "Texto privado.",
                        "test-key",
                    )

        self.assertEqual(result[0], "Resultado")
        self.assertEqual(result[1][0]["original"], "Texto privado.")
        self.assertEqual(client.models.generate_content.call_count, 2)
        sleep.assert_called_once_with(2)
        logs = "\n".join(captured.output)
        self.assertIn("type=EmptyResponse code=empty_response", logs)
        self.assertIn("gemini_response finish_reason=STOP", logs)
        self.assertNotIn("Texto privado.", logs)

    def test_invalid_json_retries_and_falls_back_to_plain_text(self) -> None:
        invalid_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(
                        parts=[SimpleNamespace(text="Versão clara sem JSON.")]
                    ),
                )
            ]
        )
        with patch("backend.main.genai.Client") as client_factory:
            client = client_factory.return_value
            client.models.generate_content.return_value = invalid_response
            with patch("backend.main.time.sleep") as sleep:
                with self.assertLogs("clareia", level="WARNING") as captured:
                    result = generate_simplified_result(
                        "Texto original.",
                        "test-key",
                    )

        self.assertEqual(result, ("Versão clara sem JSON.", []))
        self.assertEqual(client.models.generate_content.call_count, 5)
        sleep.assert_has_calls([call(2), call(4), call(8), call(16)])
        logs = "\n".join(captured.output)
        self.assertEqual(logs.count("code=invalid_json"), 5)
        self.assertNotIn("Texto original.", logs)

    def test_invalid_json_retries_then_accepts_valid_segment_response(self) -> None:
        invalid_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(
                        parts=[SimpleNamespace(text="formato inválido")]
                    ),
                )
            ]
        )
        valid_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                text=(
                                    '{"trechos":[{"indice":1,'
                                    '"original":"Texto original.",'
                                    '"simplificado":"Texto claro.",'
                                    '"explicacao":"Frase mais simples.",'
                                    '"contexto":"","ressalvas":[]}]}'
                                )
                            )
                        ]
                    ),
                )
            ]
        )

        with patch("backend.main.genai.Client") as client_factory:
            client = client_factory.return_value
            client.models.generate_content.side_effect = [
                invalid_response,
                valid_response,
            ]

            with patch("backend.main.time.sleep") as sleep:
                result = generate_simplified_result(
                    "Texto original.",
                    "test-key",
                )

        self.assertEqual(
            result,
            (
                "Texto claro.",
                [
                    {
                        "indice": 1,
                        "original": "Texto original.",
                        "simplificado": "Texto claro.",
                        "explicacao": "Frase mais simples.",
                        "contexto": "",
                        "ressalvas": [],
                    }
                ],
            ),
        )
        self.assertEqual(client.models.generate_content.call_count, 2)
        sleep.assert_called_once_with(2)
    def test_empty_response_after_retries_returns_same_502(self) -> None:
        text = "Conteúdo privado para teste."
        empty_response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(parts=[]),
                )
            ]
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.return_value = empty_response
                with patch("backend.main.time.sleep") as sleep:
                    with self.assertLogs("clareia", level="WARNING") as captured:
                        response = self.client.post(
                            "/api/simplify",
                            json={"text": text},
                        )

        self.assertEqual(client.models.generate_content.call_count, 5)
        sleep.assert_has_calls([call(2), call(4), call(8), call(16)])
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": GEMINI_FAILURE_MESSAGE})
        logs = "\n".join(captured.output)
        self.assertEqual(logs.count("code=empty_response"), 5)
        self.assertNotIn(text, logs)

    def test_other_api_statuses_are_not_retried(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                for code in (408, 504):
                    with self.subTest(code=code):
                        client.models.generate_content.reset_mock()
                        client.models.generate_content.side_effect = APIError(
                            code,
                            {"error": {"message": "not retryable"}},
                        )
                        with patch("backend.main.time.sleep") as sleep:
                            response = self.client.post(
                                "/api/simplify",
                                json={"text": "Texto válido."},
                            )

                        self.assertEqual(response.status_code, 502)
                        self.assertEqual(
                            client.models.generate_content.call_count,
                            1,
                        )
                        sleep.assert_not_called()

    def test_invalid_api_key_is_not_retried(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch("backend.main.genai.Client") as client_factory:
                client = client_factory.return_value
                client.models.generate_content.side_effect = APIError(
                    403,
                    {"error": {"message": "invalid key"}},
                )
                with patch("backend.main.time.sleep") as sleep:
                    with self.assertLogs("clareia", level="WARNING") as captured:
                        response = self.client.post(
                            "/api/simplify",
                            json={"text": "Texto válido."},
                        )

        self.assertEqual(client.models.generate_content.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": GEMINI_FAILURE_MESSAGE})
        self.assertIn("type=APIError code=403", "\n".join(captured.output))

    def test_max_tokens_finish_reason_is_logged_without_changing_config(self) -> None:
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason=SimpleNamespace(name="MAX_TOKENS"),
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                text=(
                                    '{"trechos":[{"indice":1,'
                                    '"simplificado":"Parcial",'
                                    '"explicacao":"Frase mais curta."}]}'
                                )
                            )
                        ]
                    ),
                )
            ]
        )
        with patch("backend.main.genai.Client") as client_factory:
            client = client_factory.return_value
            client.models.generate_content.return_value = response
            with self.assertLogs("clareia", level="WARNING") as captured:
                result = generate_simplified_result("Texto válido.", "test-key")

        self.assertEqual(result[0], "Parcial")
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.max_output_tokens, 8192)
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.top_p, 0.9)
        self.assertIn(
            "gemini_response_warning finish_reason=MAX_TOKENS",
            "\n".join(captured.output),
        )

    def test_gemini_api_error_returns_bad_gateway(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch(
                "backend.main.generate_simplified_result",
                side_effect=APIError(404, {"error": {"message": "model unavailable"}}),
            ):
                response = self.client.post(
                    "/api/simplify",
                    json={"text": "Texto válido."},
                )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(set(response.json()), {"error"})

    def test_unexpected_server_error_returns_500(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch(
                "backend.main.generate_simplified_result",
                side_effect=RuntimeError("internal failure"),
            ):
                response = self.client.post(
                    "/api/simplify",
                    json={"text": "Texto válido."},
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(set(response.json()), {"error"})

    def test_missing_api_key_returns_a_friendly_error(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            response = self.client.post(
                "/api/simplify",
                json={"text": "Texto válido."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            set(response.json()),
            {"error"},
        )

def test_pode_virou_podem():
    assert find_lost_caveats("Isso pode ocorrer.", "Isso podem ocorrer.") == []
if __name__ == "__main__":
    unittest.main()
