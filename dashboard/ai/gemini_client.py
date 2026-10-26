"""Cliente fino do Google Gemini, compartilhado por chat.py e insights.py."""

import os

import google.generativeai as genai

_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")

# Modelos tentados em ordem: o configurado e depois reservas (o free tier às vezes responde 503 "high demand").
_MODELOS = list(dict.fromkeys([_GEMINI_MODEL, "gemini-flash-lite-latest", "gemini-flash-latest"]))
_TIMEOUT_SEGUNDOS = 20

_configurado = False


def _configurar():
    global _configurado
    if not _configurado:
        if not _GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY não configurada (defina em .env ou nas env vars do Render).")
        genai.configure(api_key=_GEMINI_API_KEY)
        _configurado = True


def perguntar(prompt: str) -> str:
    ultimo_erro = None
    for modelo in _MODELOS:
        try:
            _configurar()
            # Sem retry automático do SDK: ele pode segurar a requisição por minutos e travar o dashboard.
            resposta = genai.GenerativeModel(modelo).generate_content(
                prompt, request_options={"timeout": _TIMEOUT_SEGUNDOS, "retry": None}
            )
            return (resposta.text or "").strip()
        except Exception as exc:  # degrada sem quebrar o dashboard
            ultimo_erro = exc
    print(f"[ERRO] Gemini indisponível: {ultimo_erro!r}", flush=True)
    return "IA indisponível no momento. Tente novamente em instantes."
