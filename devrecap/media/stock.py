"""Busca e download de fotos de banco de imagens (Pexels / Unsplash).

Fluxo:
    keywords ─► search_stock(provider, ...) ─► [PhotoSuggestion]
    PhotoSuggestion ─► download_photo(...) ─► arquivo local (.jpg)

`search_stock` levanta `StockError` (mensagem amigável em pt-BR) quando a API
falha, para o pipeline poder mostrar o motivo no relatório. `download_photo`
nunca levanta (retorna None em falha).

Atribuição:
- Pexels: header `Authorization: <KEY>` (sem "Bearer").
- Unsplash: header `Authorization: Client-ID <KEY>`; a diretriz exige disparar um
  GET no `download_location` ao baixar — guardamos isso em
  `PhotoSuggestion.download_trigger` e o `download_photo` o dispara.
"""
from __future__ import annotations

import hashlib
import os

import requests

from devrecap.core.models import PhotoSuggestion
from devrecap.core.logging_setup import get_logger

logger = get_logger(__name__)

_TIMEOUT = 30


class StockError(Exception):
    """Falha ao buscar no banco de fotos, com mensagem amigável p/ o usuário."""


def _clean_key(api_key: str) -> str:
    """Limpa a chave: tira espaços e prefixos colados por engano (Client-ID/Bearer)."""
    k = (api_key or "").strip()
    for pref in ("client-id ", "bearer "):
        if k.lower().startswith(pref):
            k = k[len(pref):].strip()
    return k


def _friendly_status(provider: str, status: int) -> str:
    prov = "Unsplash" if provider == "unsplash" else "Pexels"
    if status == 401:
        # 401 NÃO é limite de taxa (no Unsplash o limite é 403). 401 = chave rejeitada.
        extra = (" — use a Access Key (a pública), NÃO a Secret; confira se copiou inteira"
                 if provider == "unsplash" else " — verifique a API key")
        return f"{prov}: chave REJEITADA (HTTP 401){extra}."
    if status == 403:
        if provider == "unsplash":
            return f"{prov}: limite de requisições atingido (HTTP 403 — demo permite 50/h). Aguarde ~1h."
        return f"{prov}: acesso negado (HTTP 403)."
    if status == 429:
        return f"{prov}: limite de requisições atingido (HTTP 429). Aguarde e tente de novo."
    return f"{prov}: erro HTTP {status}."


def search_stock(
    provider: str,
    api_key: str,
    keywords: list[str],
    *,
    count: int = 3,
    orientation: str = "landscape",
    app_name: str = "DevRecap",
) -> list[PhotoSuggestion]:
    """Busca fotos no banco de imagens. Levanta StockError em falha de API."""
    provider = (provider or "pexels").lower()
    api_key = _clean_key(api_key)
    if not api_key:
        raise StockError(f"{'Unsplash' if provider == 'unsplash' else 'Pexels'}: falta a API key.")
    query = " ".join(keywords[:4]) if keywords else "software development"
    count = max(int(count or 1), 1)
    try:
        if provider == "unsplash":
            return _search_unsplash(api_key, query, count, orientation, app_name)
        return _search_pexels(api_key, query, count, orientation)
    except StockError:
        raise
    except requests.Timeout:
        raise StockError(f"{provider}: tempo esgotado ao conectar.")
    except requests.RequestException as e:
        raise StockError(f"{provider}: falha de rede ({e.__class__.__name__}).")


def _api_reason(resp: requests.Response) -> str:
    """Extrai a mensagem de erro REAL do corpo da resposta (Unsplash/Pexels)."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            if data.get("errors"):            # Unsplash: {"errors": ["OAuth error: ..."]}
                return "; ".join(str(x) for x in data["errors"])[:200]
            for k in ("error", "message", "status"):
                if data.get(k):
                    return str(data[k])[:200]
    except Exception:  # noqa: BLE001
        pass
    txt = (resp.text or "").strip()
    return txt[:160]


def _check(provider: str, resp: requests.Response) -> None:
    if resp.status_code >= 400:
        base = _friendly_status(provider, resp.status_code)
        reason = _api_reason(resp)
        raise StockError(base + (f" — a API respondeu: “{reason}”" if reason else ""))


def _search_pexels(api_key: str, query: str, count: int, orientation: str) -> list[PhotoSuggestion]:
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": query, "per_page": min(max(count, 1), 80), "orientation": orientation},
        timeout=_TIMEOUT,
    )
    _check("pexels", resp)
    out: list[PhotoSuggestion] = []
    for p in resp.json().get("photos", []):
        src = p.get("src", {}) or {}
        out.append(PhotoSuggestion(
            source="stock",
            url=src.get("large"),
            thumb_url=src.get("medium"),
            caption=query,
            attribution="Foto de " + str(p.get("photographer", "")) + " no Pexels",
            attribution_url=p.get("url", "") or "",
        ))
    return out


def _search_unsplash(api_key: str, query: str, count: int, orientation: str,
                     app_name: str = "DevRecap") -> list[PhotoSuggestion]:
    utm = f"?utm_source={app_name or 'DevRecap'}&utm_medium=referral"
    orient = "squarish" if orientation == "square" else orientation
    resp = requests.get(
        "https://api.unsplash.com/search/photos",
        headers={"Authorization": "Client-ID " + api_key, "Accept-Version": "v1"},
        params={"query": query, "per_page": min(max(count, 1), 30), "orientation": orient},
        timeout=_TIMEOUT,
    )
    _check("unsplash", resp)
    out: list[PhotoSuggestion] = []
    for p in resp.json().get("results", []):
        urls = p.get("urls", {}) or {}
        user = p.get("user", {}) or {}
        links = p.get("links", {}) or {}
        out.append(PhotoSuggestion(
            source="stock",
            url=urls.get("regular"),
            thumb_url=urls.get("small"),
            caption=query,
            attribution="Foto de " + str(user.get("name", "")) + " no Unsplash",
            attribution_url=(links.get("html", "") or "") + utm,
            download_trigger=links.get("download_location", "") or "",
        ))
    return out


def download_photo(suggestion: PhotoSuggestion, out_dir: str) -> str | None:
    """Baixa `suggestion.url` para `out_dir`. Retorna o caminho ou None. Nunca levanta."""
    url = suggestion.url
    if not url:
        return None
    try:
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, hashlib.md5(url.encode("utf-8")).hexdigest() + ".jpg")
        with requests.get(url, stream=True, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        suggestion.local_path = dest
        _trigger_unsplash_download(suggestion.download_trigger)
        return dest
    except Exception as e:  # noqa: BLE001 — download nunca derruba o app
        logger.warning("Falha ao baixar foto (%s): %s", url, e)
        return None


def _trigger_unsplash_download(dl_url: str) -> None:
    """Dispara o GET no `download_location` da Unsplash (best-effort, ignora falha)."""
    if not dl_url:
        return
    try:
        requests.get(dl_url, timeout=_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        logger.info("Trigger de download Unsplash falhou (ignorado): %s", e)
