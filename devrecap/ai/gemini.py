"""Cliente do Google Gemini (texto + imagem) para o DevRecap.

Usa o SDK oficial `google-genai` (`from google import genai`). Gera os insights
do dia (resumo, post de LinkedIn, etc.) a partir de uma `DayActivity` e, opcional-
mente, uma imagem para o post via o modelo "Nano Banana".

Regra de ouro: nenhuma exceção vaza. Falhas viram `AIInsights(error=...)` ou
`None` (imagem), sempre logadas via `get_logger(__name__)`.
"""
from __future__ import annotations

import json
import re
import time
from io import BytesIO
from typing import Any, Optional

# O SDK externo pode não estar instalado no ambiente de build/compile.
# Envolvemos em try/except para que o py_compile e imports do pacote funcionem
# mesmo sem as dependências; em runtime, `available()` indica se dá pra usar.
try:
    from google import genai
    from google.genai import types, errors

    _SDK_OK = True
except ImportError:  # pragma: no cover - depende do ambiente
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
    errors = None  # type: ignore[assignment]
    _SDK_OK = False

from devrecap.core.models import AIInsights, DayActivity
from devrecap.core.logging_setup import get_logger
from devrecap.ai.prompts import SYSTEM_INSTRUCTION, build_user_prompt

log = get_logger(__name__)


def available() -> bool:
    """Diz se o SDK `google-genai` está importável neste ambiente."""
    return _SDK_OK


# Nº de tentativas e backoff (s) para erros transitórios (503/429/sobrecarga).
_RETRIES = 3
_BACKOFF = 2.0


def _is_transient(e: Exception) -> bool:
    """True se o erro do Gemini for temporário (vale a pena repetir)."""
    code = getattr(e, "code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    s = str(e).upper()
    return any(k in s for k in (
        "UNAVAILABLE", "503", "OVERLOAD", "HIGH DEMAND", "RESOURCE_EXHAUSTED",
        "DEADLINE", "500", "TRY AGAIN",
    ))


def _friendly_ai_error(e: Exception) -> str:
    """Mensagem curta e clara para o usuário a partir do erro do SDK."""
    code = getattr(e, "code", None)
    s = str(e)
    up = s.upper()
    if code == 503 or "UNAVAILABLE" in up or "HIGH DEMAND" in up or "OVERLOAD" in up:
        return "Gemini sobrecarregado agora (503). Clique em 'Regenerar texto' em alguns segundos."
    if code == 429 or "RESOURCE_EXHAUSTED" in up or "QUOTA" in up:
        return "Limite/cota do Gemini atingido (429). Aguarde um pouco e tente de novo."
    if code in (400, 401, 403) or "API KEY" in up or "API_KEY" in up or "PERMISSION" in up:
        return "Gemini recusou a requisição — verifique a API key (Configurações → Gemini)."
    return "Falha na IA: " + s[:180]


def _extract_json(raw: str) -> str:
    """Extrai o objeto JSON de um texto de resposta de forma defensiva.

    Remove cercas de código (```json ... ```) e devolve o trecho entre a primeira
    chave de abertura `{` e a última chave de fechamento `}`. Se não achar chaves,
    devolve o texto original (json.loads cuidará do erro).
    """
    text = (raw or "").strip()

    # Remover cercas de código, se houver.
    if "```" in text:
        # tira ```json / ``` deixando só o miolo
        text = re.sub(r"```[a-zA-Z0-9_-]*", "", text)
        text = text.replace("```", "")
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _as_str(value: Any, default: str = "") -> str:
    """Converte um valor para string segura (None vira default)."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    """Garante uma `list[str]` a partir de qualquer valor recebido do modelo."""
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = item if isinstance(item, str) else str(item)
            s = s.strip()
            if s:
                out.append(s)
        return out
    # qualquer outro tipo escalar
    return [str(value)]


class GeminiClient:
    """Encapsula chamadas de texto e imagem ao Gemini."""

    def __init__(self, api_key: str, text_model: str, image_model: str) -> None:
        """Cria o client do SDK e guarda os nomes dos modelos de texto/imagem."""
        self._text_model = text_model
        self._image_model = image_model
        self._client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------ #
    def _gen_content(self, *, model, contents, config):
        """generate_content com retry em erros transitórios (503/429/sobrecarga)."""
        last: Optional[Exception] = None
        for attempt in range(_RETRIES):
            try:
                return self._client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except Exception as e:  # noqa: BLE001
                last = e
                if attempt < _RETRIES - 1 and _is_transient(e):
                    wait = _BACKOFF * (attempt + 1)
                    log.warning("Gemini transitório (tentativa %d/%d): %s — repetindo em %.0fs",
                                attempt + 1, _RETRIES, e, wait)
                    time.sleep(wait)
                    continue
                raise
        if last:
            raise last
        raise RuntimeError("generate_content não retornou resposta")

    # ------------------------------------------------------------------ #
    def generate_insights(
        self,
        activity: DayActivity,
        *,
        language: str = "pt-BR",
        tone: str = "",
        style_reference: Optional[str] = None,
        post_length: str = "curto",
    ) -> AIInsights:
        """Gera os insights do dia (resumo, post, hashtags, etc.) via Gemini.

        Monta o prompt do usuário, pede JSON e mapeia para `AIInsights`. Qualquer
        falha (incl. `errors.APIError`) vira `AIInsights(error=str(e))` — nunca
        levanta exceção.
        """
        try:
            user_prompt = build_user_prompt(
                activity,
                language=language,
                tone=tone,
                style_reference=style_reference,
                post_length=post_length,
            )
            resp = self._gen_content(
                model=self._text_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                ),
            )
            payload = _extract_json(getattr(resp, "text", "") or "")
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("Resposta da IA não é um objeto JSON.")

            return AIInsights(
                summary=_as_str(data.get("summary")),
                technologies=_as_str_list(data.get("technologies")),
                progress=_as_str(data.get("progress")),
                value_added=_as_str(data.get("value_added")),
                bullet_highlights=_as_str_list(data.get("bullet_highlights")),
                linkedin_post=_as_str(data.get("linkedin_post")),
                linkedin_hashtags=_as_str_list(data.get("linkedin_hashtags")),
                photo_keywords=_as_str_list(data.get("photo_keywords")),
                photo_prompt=_as_str(data.get("photo_prompt")),
                model=self._text_model,
            )
        except Exception as e:  # noqa: BLE001 - nunca deixar vazar
            log.error("Falha ao gerar insights com Gemini: %s", e)
            return AIInsights(model=self._text_model, error=_friendly_ai_error(e))

    # ------------------------------------------------------------------ #
    def generate_image(self, prompt: str, out_path: str) -> Optional[str]:
        """Gera uma imagem (PNG) a partir de `prompt` e salva em `out_path`.

        Retorna o caminho salvo ou `None` em falha / quando não vier imagem.
        """
        try:
            resp = self._gen_content(
                model=self._image_model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            parts = getattr(resp, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is None:
                    continue
                # Caminho preferencial: helper as_image() do SDK (devolve PIL.Image).
                try:
                    image = part.as_image()
                    if image is not None:
                        image.save(out_path)
                        return out_path
                except Exception as inner:  # noqa: BLE001 - tenta o fallback
                    log.warning("as_image() falhou, tentando fallback PIL: %s", inner)

                # Fallback: abrir os bytes brutos com PIL.
                try:
                    from PIL import Image  # import tardio (dependência externa)

                    raw = getattr(inline, "data", None)
                    if raw:
                        with Image.open(BytesIO(raw)) as img:
                            img.save(out_path)
                        return out_path
                except Exception as inner:  # noqa: BLE001
                    log.warning("Fallback PIL falhou: %s", inner)

            log.warning("Gemini não retornou imagem para o prompt.")
            return None
        except Exception as e:  # noqa: BLE001 - nunca deixar vazar
            log.error("Falha ao gerar imagem com Gemini: %s", e)
            return None
