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


def _build_gemini(settings: Settings):
    """Cria um GeminiClient se houver chave e SDK; senão None (+ motivo)."""
    if not settings.gemini_api_key:
        return None, "Sem API key do Gemini — resumo e post não foram gerados."
    try:
        from .ai.gemini import GeminiClient, available

        if not available():
            return None, "SDK google-genai não está instalado."
        return GeminiClient(
            settings.gemini_api_key,
            settings.gemini_text_model,
            settings.gemini_image_model,
        ), None
    except Exception as e:
        log.exception("falha ao criar GeminiClient")
        return None, f"Falha ao iniciar Gemini: {e}"


def generate_insights(settings: Settings, activity: DayActivity, gemini, cb: ProgressCb = None) -> AIInsights:
    if gemini is None:
        return AIInsights(error="Gemini indisponível (sem chave ou SDK).")
    _emit(cb, "Gerando resumo e post com o Gemini…")
    return gemini.generate_insights(
        activity,
        language=settings.language,
        tone=settings.linkedin_tone,
        style_reference=_read_style_reference(settings),
        post_length=settings.post_length,
    )


def collect_photos(settings: Settings, activity: DayActivity, insights: AIInsights,
                   gemini, cb: ProgressCb = None) -> list[PhotoSuggestion]:
    """Reúne sugestões de foto conforme settings.photo_sources."""
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

    # 3) Imagem gerada por IA (opcional)
    if "gemini" in sources and gemini is not None and settings.gemini_image_enabled and insights.photo_prompt:
        _emit(cb, "Gerando imagem com o Gemini…")
        try:
            from .media.gemini_image import suggest_generated_image

            g = suggest_generated_image(gemini, insights.photo_prompt, out_dir)
            if g:
                photos.append(g)
        except Exception:
            log.exception("suggest_generated_image falhou")

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

    gemini, gem_note = _build_gemini(settings)
    if gem_note:
        activity.notes.append(gem_note)

    insights = generate_insights(settings, activity, gemini, cb)
    photos = collect_photos(settings, activity, insights, gemini, cb)

    report = DailyReport(
        day=day,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        activity=activity,
        insights=insights,
        photos=photos,
    )
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

    gemini, gem_note = _build_gemini(settings)
    if gem_note:
        activity.notes.append(gem_note)

    insights = generate_insights(settings, activity, gemini, cb)
    photos = collect_photos(settings, activity, insights, gemini, cb)

    report = DailyReport(
        day=day,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        activity=activity,
        insights=insights,
        photos=photos,
    )

    folder = None
    try:
        folder = storage.save_report(report)
        _emit(cb, f"Recap salvo em {folder}")
    except Exception:
        log.exception("falha ao salvar relatório")
        _emit(cb, "Recap gerado (falha ao salvar em disco).")

    # Etapa de lapidação: entrega o relatório ao Claude Code, que lê os commits
    # completos, consulta as skills de marketing e grava um candidato a post na
    # mesma pasta. Roda DEPOIS do save porque depende do report.json em disco.
    #
    # É a etapa mais lenta do pipeline (agêntica, minutos). Nunca derruba o
    # recap: qualquer falha aqui vira nota, e o relatório do dia continua válido.
    if folder:
        try:
            from .ai import claude_code

            if claude_code.disponivel():
                _emit(cb, "Gerando post do LinkedIn (Claude Code)…")
                res = claude_code.gerar_post(folder)
                if res.ok:
                    _emit(cb, f"Post do dia: {res.status or 'gerado'}")
                else:
                    activity.notes.append(f"Post do LinkedIn não gerado: {res.error}")
                    _emit(cb, "Post do LinkedIn falhou (recap segue válido).")
            else:
                log.info("Claude Code indisponível; etapa de lapidação pulada")
        except Exception:
            log.exception("etapa de lapidação falhou")
            activity.notes.append("Post do LinkedIn não gerado (erro interno).")

    return report
