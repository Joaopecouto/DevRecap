"""Suporte ao frontend webview: monta o HTML inline e os view-models.

- build_html(): junta index.html + styles.css + app.js num HTML único (robusto
  tanto rodando do fonte quanto empacotado).
- *_vm(): convertem os dataclasses do DevRecap nos dicts que o app.js consome.
- image_to_data_uri(): miniatura base64 p/ exibir imagens locais no webview.
"""
from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from ..core.config import Settings
from ..core.logging_setup import get_logger
from ..core.models import DailyReport, PhotoSuggestion, RepoActivity
from ..core.paths import web_dir
from ..core import storage

log = get_logger(__name__)

_WEEKDAYS_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
def build_html() -> str:
    """HTML único com CSS e JS embutidos (sem depender de arquivos irmãos)."""
    d = web_dir()
    html = (d / "index.html").read_text(encoding="utf-8")
    css = (d / "styles.css").read_text(encoding="utf-8")
    js = (d / "app.js").read_text(encoding="utf-8")

    html = html.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>\n{css}\n</style>",
    )
    html = html.replace(
        '<script src="app.js"></script>',
        f"<script>\n{js}\n</script>",
    )
    return html


# --------------------------------------------------------------------------- #
# Imagens -> data URI
# --------------------------------------------------------------------------- #
def image_to_data_uri(path: str, max_w: int = 680) -> Optional[str]:
    """Miniatura JPEG base64 de uma imagem local (ou SVG inline). None se falhar."""
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None
        if p.suffix.lower() == ".svg":
            raw = p.read_bytes()
            return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")

        from PIL import Image  # lazy

        with Image.open(p) as img:
            img = img.convert("RGB")
            if img.width > max_w:
                ratio = max_w / float(img.width)
                img = img.resize((max_w, max(1, int(img.height * ratio))))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=82)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001 — sem imagem é só não exibir
        log.debug("não consegui gerar data URI de %s", path)
        return None


# --------------------------------------------------------------------------- #
# View-models
# --------------------------------------------------------------------------- #
def _weekday(day: str) -> str:
    try:
        return _WEEKDAYS_PT[datetime.strptime(day, "%Y-%m-%d").weekday()]
    except ValueError:
        return ""


def _photo_vm(p: PhotoSuggestion) -> dict[str, Any]:
    disp = None
    if p.local_path:
        disp = image_to_data_uri(p.local_path)
    if not disp:
        disp = p.url or p.thumb_url
    return {
        "source": p.source,
        "caption": p.caption,
        "attribution": p.attribution,
        "attribution_url": p.attribution_url,
        "local_path": p.local_path,
        "url": p.url,
        "display_url": disp,
    }


def _repo_vm(r: RepoActivity) -> dict[str, Any]:
    return {
        "name": r.name,
        "is_dirty": r.is_dirty,
        "insertions": r.insertions,
        "deletions": r.deletions,
        "commits": [{"sha": c.sha, "subject": c.subject} for c in r.commits],
        "prs": [{"number": p.number, "title": p.title, "state": p.state} for p in r.prs],
        "issues": [{"number": i.number, "title": i.title, "state": i.state} for i in r.issues],
    }


def report_vm(report: DailyReport) -> dict[str, Any]:
    """Converte um DailyReport no dict que o app.js renderiza."""
    a = report.activity
    wd = _weekday(report.day)
    gen = ""
    if report.generated_at:
        try:
            gen = "gerado às " + datetime.fromisoformat(report.generated_at).strftime("%H:%M")
        except ValueError:
            gen = ""
    subtitle = " · ".join(x for x in (wd, gen) if x)

    langs = list(a.languages.items())
    return {
        "day": report.day,
        "subtitle": subtitle,
        "insights": report.insights.to_dict(),
        "photos": [_photo_vm(p) for p in report.photos],
        "repos": [_repo_vm(r) for r in a.active_repos],
        "totals": {
            "commits": a.total_commits,
            "repos": len(a.active_repos),
            "insertions": a.total_insertions,
            "deletions": a.total_deletions,
            "files": a.total_files_changed,
            "languages": [[ext, n] for ext, n in langs],
        },
        "notes": list(a.notes),
    }


def history_vm(limit: int = 60) -> list[dict[str, Any]]:
    """Lista resumida dos relatórios salvos (mais recentes primeiro)."""
    out: list[dict[str, Any]] = []
    for day in storage.list_report_days()[:limit]:
        rep = storage.load_report(day)
        if not rep:
            continue
        out.append({
            "day": day,
            "subtitle": _weekday(day),
            "commits": rep.activity.total_commits,
        })
    return out


def settings_vm(settings: Settings) -> dict[str, Any]:
    """Settings + lista de pendências para a tela de configuração."""
    d = settings.to_dict()
    d["missing"] = settings.missing_requirements()
    return d
