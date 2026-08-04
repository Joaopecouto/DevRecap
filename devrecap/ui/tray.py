"""Ícone da bandeja (imagem). O menu e os callbacks ficam no AppController."""
from __future__ import annotations

import os

from ..core.logging_setup import get_logger
from ..core.paths import asset_path

log = get_logger(__name__)

# Paleta (matiz único, estilo do guia do João) — azul.
_BG = (37, 99, 235)      # azul
_FG = (255, 255, 255)


def make_image(size: int = 64):
    """Imagem do ícone (PIL). Usa assets/icon.png se existir; senão desenha."""
    from PIL import Image, ImageDraw

    icon_file = asset_path("assets/icon.png")
    if os.path.exists(icon_file):
        try:
            return Image.open(icon_file)
        except Exception:
            log.debug("falha ao abrir icon.png; desenhando fallback")

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(2, size // 12)
    radius = size // 5
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=_BG)

    # três barras ascendentes (mini "recap" / progresso)
    base = size - pad * 2
    bottom = size - pad * 2
    bar_w = base // 7
    gap = bar_w // 2
    heights = [base * 0.35, base * 0.55, base * 0.78]
    x = pad * 2 + gap
    for h in heights:
        top = bottom - h + pad
        d.rounded_rectangle([x, top, x + bar_w, bottom], radius=max(1, bar_w // 3), fill=_FG)
        x += bar_w + gap
    return img


def save_icon_files(out_dir: str, size: int = 256) -> None:
    """Gera assets/icon.png e icon.ico (para empacotar com PyInstaller)."""
    from PIL import Image

    img = make_image(size).convert("RGBA")
    os.makedirs(out_dir, exist_ok=True)
    img.save(os.path.join(out_dir, "icon.png"))
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(os.path.join(out_dir, "icon.ico"), sizes=sizes)
