"""Pipeline do recap diário: coleta -> agrega -> IA -> fotos -> salva.

`generate_recap` é o coração do app. É chamado pelo agendador (18:00) e pelo
menu "Gerar agora". Nunca levanta exceção para o chamador — devolve sempre um
DailyReport (possivelmente com avisos em activity.notes / insights.error).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .core.config import Settings
from .core.logging_setup import get_logger
from .core.models import AIInsights, DailyReport, DayActivity, PhotoSuggestion, today_str
from .core.paths import media_dir
from .core import storage

log = get_logger(__name__)

ProgressCb = Optional[Callable[[str], None]]


def _emit(cb: ProgressCb, msg: str) -> None:
    log.info(msg)
    if cb:
        try:
            cb(msg)
        except Exception:  # callback de UI nunca pode derrubar o pipeline
            log.exception("progress callback falhou")


def _read_style_reference(settings: Settings) -> Optional[str]:
    path = (settings.style_reference_file or "").strip()
    if not path:
        return None
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        log.warning("não consegui ler style_reference_file: %s", path)
    return None


def collect_activity(settings: Settings, day: str, cb: ProgressCb = None) -> DayActivity:
    """Coleta atividade local + GitHub e agrega num DayActivity."""
    from .analyzers.git_local import scan_folders
    from .analyzers.aggregate import build_day_activity

    notes: list[str] = []

    # ---- Projetos locais ----
    local_repos = []
    if settings.folders:
        _emit(cb, f"Analisando {len(settings.folders)} pasta(s) local(is)…")
        try:
            local_repos = scan_folders(
                settings.folders,
                day,
                scan_subfolders=settings.scan_subfolders,
                max_depth=settings.max_scan_depth,
                author_emails=settings.git_author_emails,
            )
        except Exception as e:  # defensivo: o módulo já trata, isto é cinto+suspensório
            log.exception("scan_folders falhou")
            notes.append(f"Falha ao analisar pastas locais: {e}")

    # ---- GitHub ----
    github_repos = []
    if settings.github_enabled and settings.github_username and settings.github_token:
        _emit(cb, "Consultando atividade no GitHub…")
        try:
            from .analyzers.github_api import GitHubClient

            client = GitHubClient(
                settings.github_token,
                settings.github_username,
                include_private=settings.github_include_private,
            )
            github_repos, gh_notes = client.day_activity(day)
            notes.extend(gh_notes or [])
        except Exception as e:
            log.exception("GitHub falhou")
            notes.append(f"Falha no GitHub: {e}")

    _emit(cb, "Consolidando atividade do dia…")
    return build_day_activity(day, local_repos, github_repos, notes)


# A análise do dia saiu do Gemini e passou para o Claude Code em modo headless
# (`ai/claude_code.py`), chamado de dentro de generate_recap/regenerate_report.
# Não existe mais um passo "gerar insights" isolado: quem produz o AIInsights é
# a mesma execução que escreve o post, porque as duas coisas dependem da mesma
# leitura dos commits.


def collect_photos(settings: Settings, activity: DayActivity, insights: AIInsights,
                   _reservado=None, cb: ProgressCb = None) -> list[PhotoSuggestion]:
    """Reúne sugestões de foto conforme settings.photo_sources.

    As palavras-chave vêm de `insights.photo_keywords`, hoje produzidas pela
    análise do Claude Code. O 4º parâmetro era o cliente Gemini e está reservado
    para o provedor de geração de imagem que assumir a etapa 3.
    """
    photos: list[PhotoSuggestion] = []
    sources = settings.photo_sources or []
    keywords = insights.photo_keywords or _fallback_keywords(activity)
    out_dir = str(media_dir())

    # 1) Do próprio projeto
    if "project" in sources:
        _emit(cb, "Procurando imagens nos projetos…")
        try:
            from .media.project_photos import find_project_images

            photos.extend(find_project_images(activity.repos, keywords, limit=3))
        except Exception:
            log.exception("find_project_images falhou")

    # 2) Banco de fotos (Pexels/Unsplash)
    if "stock" in sources:
        provider = settings.stock_provider or "pexels"
        if not settings.stock_api_key:
            activity.notes.append(f"Banco de fotos ({provider}) ativado, mas sem API key configurada.")
        else:
            _emit(cb, f"Buscando fotos no {provider}…")
            from .media.stock import search_stock, download_photo, StockError

            try:
                found = search_stock(
                    provider, settings.stock_api_key, keywords,
                    count=2, orientation="landscape", app_name="DevRecap",
                )
                if found:
                    for ph in found:
                        try:
                            download_photo(ph, out_dir)  # baixa p/ local_path (best-effort)
                        except Exception:
                            log.exception("download_photo falhou")
                    photos.extend(found)
                else:
                    activity.notes.append(
                        f"Banco de fotos ({provider}): nenhum resultado para as palavras-chave.")
            except StockError as e:
                log.warning("busca de fotos falhou: %s", e)
                activity.notes.append(f"Banco de fotos — {e}")
            except Exception:
                log.exception("search_stock falhou")
                activity.notes.append(f"Banco de fotos ({provider}): erro inesperado (veja o log).")

    # 3) Não existe mais etapa de geração de imagem por IA.
    #
    #    A escolha da imagem migrou para dentro da análise do dia: o Claude Code
    #    busca no banco do Freepik (servidor MCP `magnific`) e devolve o que
    #    escolheu em `insights.photo_keywords` / `photo_prompt`, com a
    #    justificativa em post-linkedin.json.
    #
    #    A ordem de preferência é deliberada: imagem real do próprio projeto >
    #    banco de imagens > geração por IA. Ilustração de IA no feed do LinkedIn
    #    é reconhecível e desvaloriza o post — por isso é último caso, não o
    #    caminho padrão. A regra está escrita no Passo 5 de
    #    <projeto LinkedIn>/scripts/prompt-diario.md.
    return photos


def _fallback_keywords(activity: DayActivity) -> list[str]:
    """Palavras-chave de foto caso a IA não tenha rodado."""
    langs = [ext.lstrip(".") for ext in list(activity.languages.keys())[:2]]
    base = ["software development", "code", "developer"]
    return (langs + base)[:4]


def filter_activity(activity: DayActivity, selected_names: set[str]) -> DayActivity:
    """Nova DayActivity só com os repos cujo nome está em `selected_names`."""
    kept = [r for r in activity.repos if r.name in selected_names]
    return DayActivity(day=activity.day, repos=kept, notes=list(activity.notes))


def regenerate_report(settings: Settings, full_activity: DayActivity,
                      selected_names, cb: ProgressCb = None) -> DailyReport:
    """Refaz o recap focando só nos repos selecionados (sem recoletar git/GitHub).

    Usa a atividade já coletada (`full_activity`), filtra pelos nomes escolhidos e
    roda a IA + fotos de novo. Se nada for selecionado, usa todos os repos ativos.
    """
    day = full_activity.day
    selected = set(selected_names or [])
    if not selected:
        selected = {r.name for r in full_activity.active_repos}

    activity = filter_activity(full_activity, selected)
    _emit(cb, f"Regenerando com foco em {len(selected)} projeto(s)…")

    report = DailyReport(
        day=day,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        activity=activity,
        insights=AIInsights(),
        photos=[],
    )

    # Mesmo desenho do generate_recap: grava o preliminar (a etapa de análise lê
    # o report.json do disco), roda o Claude Code, depois coleta as fotos com as
    # palavras-chave que ele devolveu.
    folder = None
    try:
        folder = storage.save_report(report)
    except Exception:
        log.exception("falha ao salvar relatório preliminar (regenerar)")

    if folder:
        try:
            from .ai import claude_code

            if claude_code.disponivel():
                res = claude_code.gerar_post(folder)
                if res.ok and res.insights:
                    report.insights = AIInsights.from_dict(res.insights)
                elif not res.ok:
                    report.insights.error = res.error[:300]
            else:
                report.insights.error = "Claude Code indisponível — sem análise do dia."
        except Exception as e:
            log.exception("etapa de análise falhou (regenerar)")
            report.insights.error = f"erro interno: {e}"

    report.photos = collect_photos(settings, activity, report.insights, None, cb)

    try:
        storage.save_report(report)
    except Exception:
        log.exception("falha ao salvar relatório regenerado")
    return report


def generate_recap(settings: Settings, day: Optional[str] = None, cb: ProgressCb = None) -> DailyReport:
    """Roda o pipeline completo e salva o relatório. Sempre retorna um DailyReport."""
    day = day or today_str()
    _emit(cb, f"Iniciando recap de {day}…")

    activity = collect_activity(settings, day, cb)

    # Salva um relatório preliminar (só a atividade do git) porque a etapa
    # seguinte LÊ o report.json do disco. É a inversão em relação ao desenho
    # antigo, em que a IA rodava antes de qualquer gravação.
    report = DailyReport(
        day=day,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        activity=activity,
        insights=AIInsights(),
        photos=[],
    )

    folder = None
    try:
        folder = storage.save_report(report)
    except Exception:
        log.exception("falha ao salvar relatório preliminar")
        _emit(cb, "Falha ao salvar em disco.")

    # Análise do dia + post: Claude Code em modo headless, no lugar do Gemini.
    #
    # Não é uma chamada de LLM — é um agente que lê os commits, abre diffs quando
    # precisa e consulta as skills de marketing e os subagentes do projeto
    # LinkedIn. Por isso leva minutos, e por isso a qualidade não depende de
    # caber tudo num prompt.
    #
    # Se falhar, o relatório continua válido com a atividade do git; o que se
    # perde é a narrativa e o post. Nunca derruba o recap.
    if folder:
        try:
            from .ai import claude_code

            if claude_code.disponivel():
                _emit(cb, "Analisando o dia e escrevendo o post…")
                res = claude_code.gerar_post(folder)
                if res.ok:
                    if res.insights:
                        report.insights = AIInsights.from_dict(res.insights)
                    _emit(cb, f"Post do dia: {res.status or 'gerado'}")
                else:
                    # Só em insights.error. A UI (app.js) já injeta esse campo
                    # na lista de avisos; escrever também em activity.notes fazia
                    # a mesma falha aparecer duas vezes na tela, com cortes
                    # diferentes, parecendo dois problemas.
                    report.insights.error = res.error[:300]
                    _emit(cb, "Análise falhou (atividade do git preservada).")
            else:
                msg = "Claude Code indisponível: sem análise do dia."
                report.insights.error = msg
                _emit(cb, msg)
        except Exception as e:
            log.exception("etapa de análise falhou")
            report.insights.error = f"erro interno: {e}"

    # As fotos dependem das palavras-chave que a etapa acima produziu.
    report.photos = collect_photos(settings, activity, report.insights, None, cb)

    try:
        folder = storage.save_report(report)
        _emit(cb, f"Recap salvo em {folder}")
    except Exception:
        log.exception("falha ao salvar relatório final")
        _emit(cb, "Recap gerado (falha ao salvar em disco).")

    return report
