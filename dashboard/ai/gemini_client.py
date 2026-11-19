"""Cliente fino do Google Gemini (SDK oficial `google-genai`), compartilhado por chat.py e insights.py."""

import os

from google import genai
from google.genai import types

_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Modelos tentados em ordem: o configurado e depois reservas (o free tier às vezes responde 503 "high demand").
# O lite responde em ~1 s; os modelos "flash" maiores chegaram a levar minutos no free tier.
_MODELOS = list(dict.fromkeys([_GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-3.8-flash"]))
_TIMEOUT_MS = 20_000

_cliente = None


class IAIndisponivel(RuntimeError):
    """Nenhum modelo respondeu. Quem chama decide o fallback (e nada disso vai para cache)."""


def _obter_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        if not _GEMINI_API_KEY:
            raise IAIndisponivel("GEMINI_API_KEY não configurada (defina em .env ou nas env vars do Render).")
        # Sem retry do SDK (attempts=1): o fallback entre modelos já cobre falhas e não trava o dashboard.
        _cliente = genai.Client(
            api_key=_GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)),
        )
    return _cliente


def perguntar(prompt: str, temperatura: float = 0.2, json: bool = False) -> str:
    cliente = _obter_cliente()
    config = types.GenerateContentConfig(
        temperature=temperatura,
        response_mime_type="application/json" if json else None,
    )
    ultimo_erro = None
    for modelo in _MODELOS:
        try:
            texto = (cliente.models.generate_content(model=modelo, contents=prompt, config=config).text or "").strip()
            if texto:
                return texto
        except Exception as exc:
            ultimo_erro = exc
    print(f"[ERRO] Gemini indisponível: {ultimo_erro!r}", flush=True)
    raise IAIndisponivel(str(ultimo_erro))
