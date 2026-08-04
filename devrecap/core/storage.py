"""Persistência dos relatórios diários e renderização em Markdown.

Cada dia vira uma pasta em %APPDATA%/DevRecap/reports/YYYY-MM-DD/ com:
  - report.json  (DailyReport.to_dict, fonte da verdade p/ histórico)
  - report.md    (versão legível; é o que a janela de histórico mostra)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import DailyReport
from .paths import reports_dir

_WEEKDAYS_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def report_dir_for(day: str) -> Path:
    p = reports_dir() / day
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_report(report: DailyReport) -> Path:
    """Salva report.json + report.md e devolve a pasta do dia."""
    folder = report_dir_for(report.day)
    (folder / "report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / "report.md").write_text(render_markdown(report), encoding="utf-8")
    return folder


def load_report(day: str) -> Optional[DailyReport]:
    f = reports_dir() / day / "report.json"
    if not f.exists():
        return None
    try:
        return DailyReport.from_dict(json.loads(f.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def list_report_days() -> list[str]:
    """Datas com relatório salvo, mais recentes primeiro."""
    base = reports_dir()
    days = [p.name for p in base.iterdir() if p.is_dir() and (p / "report.json").exists()]
    return sorted(days, reverse=True)


def latest_report() -> Optional[DailyReport]:
    days = list_report_days()
    return load_report(days[0]) if days else None


# --------------------------------------------------------------------------- #
def _weekday_pt(day: str) -> str:
    try:
        d = datetime.strptime(day, "%Y-%m-%d")
        return _WEEKDAYS_PT[d.weekday()]
    except ValueError:
        return ""


def render_markdown(report: DailyReport) -> str:
    a = report.activity
    ins = report.insights
    wd = _weekday_pt(report.day)
    head = f"# Recap — {report.day}" + (f" ({wd})" if wd else "")

    lines: list[str] = [head, ""]
    if report.generated_at:
        lines += [f"_Gerado em {report.generated_at}_", ""]

    if ins.error:
        lines += [f"> ⚠️ A IA falhou: {ins.error}", ""]

    # ---- O que foi feito ----
    lines.append("## ✅ O que foi feito")
    if ins.bullet_highlights:
        lines += [f"- {b}" for b in ins.bullet_highlights]
    elif a.total_commits:
        for r in a.active_repos:
            for c in r.commits:
                lines.append(f"- **{r.name}**: {c.subject}")
    else:
        lines.append("- (sem atividade registrada hoje)")
    lines.append("")

    # ---- Resumo ----
    if ins.summary:
        lines += ["## 📊 Resumo", ins.summary, ""]

    # ---- Tecnologias ----
    if ins.technologies:
        lines += ["## 🛠 Tecnologias", ", ".join(ins.technologies), ""]

    # ---- Progresso ----
    if ins.progress:
        lines += ["## 📈 Progresso", ins.progress, ""]

    # ---- Valor agregado ----
    if ins.value_added:
        lines += ["## 💡 Como agregou ao projeto", ins.value_added, ""]

    # ---- Post LinkedIn ----
    if ins.linkedin_post:
        lines += ["## 📝 Post sugerido pro LinkedIn", "", ins.linkedin_post, ""]
        if ins.linkedin_hashtags:
            lines += [" ".join(f"#{h.lstrip('#')}" for h in ins.linkedin_hashtags), ""]

    # ---- Fotos ----
    if report.photos:
        lines.append("## 🖼 Fotos sugeridas")
        for i, ph in enumerate(report.photos, 1):
            ref = ph.local_path or ph.url or ""
            cap = ph.caption or ph.source
            credit = f" — _{ph.attribution}_" if ph.attribution else ""
            lines.append(f"{i}. **[{ph.source}]** {cap}{credit}")
            if ref:
                lines.append(f"   - {ref}")
        lines.append("")

    # ---- Detalhe por repo ----
    if a.active_repos:
        lines.append("## 🔎 Detalhe por repositório")
        for r in a.active_repos:
            stats = f"{r.commit_count} commit(s), +{r.insertions}/−{r.deletions}"
            dirty = " · _mudanças não commitadas_" if r.is_dirty else ""
            lines += [f"### {r.name} ({stats}){dirty}"]
            for c in r.commits:
                sha = f"`{c.short_sha}` " if c.short_sha else ""
                lines.append(f"- {sha}{c.subject}")
            for pr in r.prs:
                lines.append(f"- PR #{pr.number} ({pr.state}): {pr.title}")
            for iss in r.issues:
                lines.append(f"- Issue #{iss.number} ({iss.state}): {iss.title}")
            lines.append("")

    # ---- Dados brutos ----
    langs = a.languages
    lines += ["## 📦 Dados brutos"]
    lines.append(
        f"- {a.total_commits} commit(s) em {len(a.active_repos)} repo(s) ativo(s); "
        f"+{a.total_insertions}/−{a.total_deletions} linhas; {a.total_files_changed} arquivo(s)."
    )
    if langs:
        lines.append("- Linguagens: " + ", ".join(f"{ext} ({n})" for ext, n in langs.items()))
    for n in a.notes:
        lines.append(f"- ⚠️ {n}")
    lines.append("")

    return "\n".join(lines)
