"""Sugestão de imagem gerada por IA (Gemini) para o post.

Recebe um cliente Gemini já configurado e um prompt de imagem, chama
`generate_image` para produzir um PNG no disco e empacota o resultado em
uma `PhotoSuggestion`. Nunca levanta exceção: em qualquer falha, devolve None.
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from devrecap.core.models import PhotoSuggestion
from devrecap.core.logging_setup import get_logger

logger = get_logger(__name__)


def suggest_generated_image(
    gemini_client,
    prompt: str,
    out_dir: str,
) -> Optional[PhotoSuggestion]:
    """Gera uma imagem via Gemini e devolve a sugestão de foto correspondente.

    `gemini_client` é uma instância de `ai.gemini.GeminiClient` (ou None).
    Se o cliente for None ou o prompt vazio, retorna None. O arquivo é nomeado
    a partir de um hash md5 do prompt (`gemini_<hash8>.png`) dentro de `out_dir`.
    Em qualquer falha, loga e retorna None.
    """
    if gemini_client is None or not (prompt or "").strip():
        return None

    try:
        # Nome estável a partir do hash do prompt.
        digest = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8]
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"gemini_{digest}.png")

        result = gemini_client.generate_image(prompt, path)
        if not result:
            logger.info("Gemini não retornou imagem para o prompt fornecido.")
            return None

        return PhotoSuggestion(
            source="gemini",
            local_path=result,
            caption="Imagem gerada por IA (Gemini)",
        )
    except Exception as e:  # noqa: BLE001 — nunca deixar exceção vazar
        logger.error("Falha ao gerar imagem com Gemini: %s", e)
        return None
