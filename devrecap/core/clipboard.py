"""Copiar texto para a área de transferência no Windows via Win32 (ctypes).

Sem dependências externas e com suporte a Unicode (CF_UNICODETEXT). Usado como
fallback quando o navigator.clipboard do webview não está disponível.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .logging_setup import get_logger

log = get_logger(__name__)

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


def set_text(text: str) -> bool:
    """Coloca `text` na área de transferência. Retorna True se conseguiu."""
    if text is None:
        return False
    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.restype = wintypes.LPVOID

        data = str(text)
        size = (len(data) + 1) * 2  # UTF-16LE, +1 p/ terminador nulo

        h = k32.GlobalAlloc(_GMEM_MOVEABLE, size)
        if not h:
            return False
        ptr = k32.GlobalLock(h)
        if not ptr:
            k32.GlobalFree(h)
            return False
        ctypes.memmove(ptr, ctypes.create_unicode_buffer(data), size)
        k32.GlobalUnlock(h)

        if not u32.OpenClipboard(None):
            k32.GlobalFree(h)
            return False
        try:
            u32.EmptyClipboard()
            if not u32.SetClipboardData(_CF_UNICODETEXT, h):
                k32.GlobalFree(h)
                return False
            # Ownership do handle passa para o clipboard; não liberar aqui.
            return True
        finally:
            u32.CloseClipboard()
    except Exception:  # noqa: BLE001 — clipboard nunca pode derrubar o app
        log.exception("falha ao copiar para a área de transferência")
        return False
