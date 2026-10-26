"""Cliente fino do Google Gemini, compartilhado por chat.py e insights.py."""

import os

import google.generativeai as genai

_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_model = None


def get_model():
    global _model
    if _model is None:
        if not _GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY não configurada (defina em .env ou nas env vars do Render).")
        genai.configure(api_key=_GEMINI_API_KEY)
        _model = genai.GenerativeModel(_GEMINI_MODEL)
    return _model


def perguntar(prompt: str) -> str:
    try:
        resposta = get_model().generate_content(prompt)
        return (resposta.text or "").strip()
    except Exception as exc:  # free tier do Gemini tem rate limit — degrada sem quebrar o dashboard
        return f"(IA indisponível no momento: {exc})"
