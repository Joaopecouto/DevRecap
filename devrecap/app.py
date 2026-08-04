"""AppController — janela webview (pywebview) + bandeja (pystray) + agendador.

Modelo de threads (verificado p/ pywebview no Windows):
  - webview.start() roda o loop GUI na MAIN thread e BLOQUEIA (mantém o app vivo).
  - pystray.Icon.run roda numa thread daemon.
  - O pipeline roda numa thread worker; o resultado volta pro JS via evaluate_js.
  - Fechar a janela apenas a ESCONDE (closing -> False); "Sair" no menu encerra.
"""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from typing import Any, Optional

import webview
import pystray
from pystray import Menu, MenuItem

from .core import autostart, clipboard
from .core.config import Settings, DEFAULT_TEXT_MODEL, DEFAULT_IMAGE_MODEL
from .core.logging_setup import get_logger
from .core.models import DailyReport
from .core.paths import asset_path
from .core import storage
from .pipeline import generate_recap, regenerate_report
from .scheduler.daily import DailyScheduler
from .ui import tray as tray_ui
from .ui import webview_app as wv

log = get_logger(__name__)


class Api:
    """Métodos expostos ao JS como window.pywebview.api.*."""

    def __init__(self, controller: "AppController") -> None:
        self._c = controller

    def get_initial(self) -> dict[str, Any]:
        return self._c.initial_payload()

    def get_report(self, day: str) -> Optional[dict[str, Any]]:
        return self._c.get_report_vm(day)

    def list_history(self) -> list[dict[str, Any]]:
        try:
            return wv.history_vm()
        except Exception:
            log.exception("history_vm falhou")
            return []

    def get_settings(self) -> dict[str, Any]:
        return wv.settings_vm(self._c.settings)

    def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._c.save_settings(data or {})

    def run_recap(self) -> bool:
        self._c.trigger_recap(show_when_done=False)
        return True

    def regenerate(self, options: dict[str, Any] = None) -> bool:
        self._c.trigger_regenerate(options or {})
        return True

    def test_stock(self, provider: str = None, api_key: str = None) -> dict[str, Any]:
        return self._c.test_stock(provider, api_key)

    def test_gemini(self, api_key: str = None, model: str = None) -> dict[str, Any]:
        return self._c.test_gemini(api_key, model)

    def pick_folder(self) -> str:
        return self._c.pick_folder()

    def open_path(self, path: str) -> bool:
        return self._c.open_path(path)

    def open_url(self, url: str) -> bool:
        return self._c.open_url(url)

    def copy(self, text: str) -> bool:
        return clipboard.set_text(text or "")


class AppController:
    def __init__(self) -> None:
        self.settings = Settings.load()
        self._lock = threading.Lock()
        self._running = False
        self._quitting = False
        self.window = None
        self.api = Api(self)

        # Foco por projeto: atividade completa do dia (candidatos) + seleção atual.
        self._full_activity = None      # DayActivity coletada (todos os repos do dia)
        self._selected_repos: set[str] = set()

        self.scheduler = DailyScheduler(
            self._on_schedule_fire,
            time_str=self.settings.schedule_time,
            run_on_weekends=self.settings.run_on_weekends,
        )
        self.icon = pystray.Icon("DevRecap", tray_ui.make_image(), "DevRecap", menu=self._build_menu())

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self.scheduler.start()
        try:
            autostart.set_enabled(self.settings.autostart)
        except Exception:
            log.exception("falha ao aplicar autostart")

        threading.Thread(target=self.icon.run, name="pystray", daemon=True).start()

        self.window = webview.create_window(
            "DevRecap",
            html=wv.build_html(),
            js_api=self.api,
            width=940, height=680, min_size=(720, 520),
            hidden=True, background_color="#f5f7fa",
        )
        self.window.events.closing += self._on_closing

        self._notify("DevRecap ativo", f"Resumo diário às {self.settings.schedule_time}.")

        # No Windows o ícone da janela precisa ser .ico (System.Drawing.Icon).
        icon_file = asset_path("assets/icon.ico")
        webview.start(
            self._post_start,
            gui="edgechromium",
            icon=str(icon_file) if icon_file.exists() else None,
        )
        # quando webview.start() retorna, o app encerrou
        log.info("DevRecap encerrado")

    def _post_start(self) -> None:
        # roda numa thread após o loop GUI iniciar
        try:
            if self.settings.missing_requirements():
                self._show_window()
        except Exception:
            log.exception("post_start falhou")

    def _on_closing(self):
        # Fechar a janela só esconde; "Sair" no menu é que encerra.
        if self._quitting:
            return True
        try:
            self.window.hide()
        except Exception:
            log.exception("falha ao esconder janela")
        return False

    # ------------------------------------------------------------------ #
    # Menu da bandeja
    # ------------------------------------------------------------------ #
    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem("Abrir DevRecap", self._on_open, default=True),
            MenuItem("Gerar recap agora", self._on_run_now),
            MenuItem("Configurações", self._on_open_settings),
            Menu.SEPARATOR,
            MenuItem(self._next_run_label, None, enabled=False),
            MenuItem("Iniciar com o Windows", self._on_toggle_autostart,
                     checked=lambda item: autostart.is_enabled()),
            Menu.SEPARATOR,
            MenuItem("Sair", self._on_quit),
        )

    def _next_run_label(self, item=None) -> str:
        nxt = self.scheduler.next_run_time()
        if nxt:
            return "Próximo resumo: " + nxt.strftime("%d/%m %H:%M")
        return f"Resumo diário às {self.settings.schedule_time}"

    def _on_open(self, icon=None, item=None) -> None:
        self._show_window(view="today")

    def _on_open_settings(self, icon=None, item=None) -> None:
        self._show_window(view="settings")

    def _on_run_now(self, icon=None, item=None) -> None:
        self._show_window(view="today")
        self.trigger_recap(show_when_done=True)

    def _on_toggle_autostart(self, icon=None, item=None) -> None:
        new = not autostart.is_enabled()
        try:
            autostart.set_enabled(new)
            self.settings.autostart = new
            self.settings.save()
        except Exception:
            log.exception("falha ao alternar autostart")
        self.icon.update_menu()

    def _on_schedule_fire(self) -> None:
        self.trigger_recap(show_when_done=self.settings.auto_open_report)

    def _on_quit(self, icon=None, item=None) -> None:
        log.info("encerrando DevRecap")
        self._quitting = True
        try:
            self.scheduler.shutdown()
        except Exception:
            log.exception("erro ao desligar scheduler")
        try:
            self.icon.stop()
        except Exception:
            log.exception("erro ao parar icon")
        try:
            for w in list(webview.windows):
                w.destroy()
        except Exception:
            log.exception("erro ao destruir janela")

    # ------------------------------------------------------------------ #
    # Janela / push p/ o JS
    # ------------------------------------------------------------------ #
    def _show_window(self, view: Optional[str] = None) -> None:
        w = self.window
        if w is None:
            return
        try:
            w.show()
            w.on_top = True
            w.on_top = False
        except Exception:
            log.exception("falha ao mostrar janela")
        if view:
            self._push({"view": view})

    def _push(self, payload: dict[str, Any]) -> None:
        w = self.window
        if w is None:
            return
        try:
            js = "window.devrecapPush(" + json.dumps(payload, ensure_ascii=False) + ")"
            w.evaluate_js(js)
        except Exception:
            log.debug("push p/ o JS falhou (página ainda carregando?)")

    # ------------------------------------------------------------------ #
    # Dados p/ o JS
    # ------------------------------------------------------------------ #
    def _set_current(self, report: DailyReport, selected=None) -> None:
        """Marca `report` como o recap atual; candidatos = seus repos ativos."""
        self._full_activity = report.activity
        names = {r.name for r in report.activity.active_repos}
        self._selected_repos = (set(selected) & names) if selected else names

    def _focus_vm(self) -> Optional[dict[str, Any]]:
        if not self._full_activity:
            return None
        return {
            "repos": [
                {"name": r.name, "commits": r.commit_count, "selected": r.name in self._selected_repos}
                for r in self._full_activity.active_repos
            ],
            "post_length": self.settings.post_length,
        }

    def _live_vm(self, report: DailyReport) -> dict[str, Any]:
        """View-model do recap atual, com os controles de foco/tamanho."""
        vm = wv.report_vm(report)
        vm["live"] = True
        vm["focus"] = self._focus_vm()
        return vm

    def initial_payload(self) -> dict[str, Any]:
        rep = storage.latest_report()
        report_vm = None
        if rep:
            self._set_current(rep)
            report_vm = self._live_vm(rep)
        return {
            "report": report_vm,
            "settings": wv.settings_vm(self.settings),
            "generating": self._running,
            "open_settings": bool(self.settings.missing_requirements()),
        }

    def get_report_vm(self, day: str) -> Optional[dict[str, Any]]:
        try:
            rep = storage.load_report(day)
            if not rep:
                return None
            self._set_current(rep)
            return self._live_vm(rep)
        except Exception:
            log.exception("get_report_vm falhou")
            return None

    def save_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            merged = {**self.settings.to_dict(), **data}
            s = Settings.from_dict(merged)
            s.gemini_text_model = s.gemini_text_model or DEFAULT_TEXT_MODEL
            s.gemini_image_model = s.gemini_image_model or DEFAULT_IMAGE_MODEL
            s.save()
            self.settings = s
            self.scheduler.reschedule(s.schedule_time, s.run_on_weekends)
            autostart.set_enabled(s.autostart)
            self.icon.update_menu()
            return {"missing": s.missing_requirements()}
        except Exception as e:
            log.exception("save_settings falhou")
            return {"missing": [f"Erro ao salvar: {e}"]}

    def pick_folder(self) -> str:
        try:
            res = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            if res:
                return res[0] if isinstance(res, (list, tuple)) else str(res)
        except Exception:
            log.exception("pick_folder falhou")
        return ""

    def open_path(self, path: str) -> bool:
        try:
            if path and os.path.exists(path):
                os.startfile(path)  # type: ignore[attr-defined]
                return True
        except Exception:
            log.exception("open_path falhou")
        return False

    def open_url(self, url: str) -> bool:
        try:
            if url:
                webbrowser.open(url)
                return True
        except Exception:
            log.exception("open_url falhou")
        return False

    def test_stock(self, provider, api_key) -> dict[str, Any]:
        """Testa a chave do banco de fotos AGORA e devolve o resultado exato."""
        prov = (provider or self.settings.stock_provider or "pexels")
        key = api_key if api_key is not None else self.settings.stock_api_key
        if not (key or "").strip():
            return {"ok": False, "message": f"Sem API key do {prov}."}
        try:
            from .media.stock import search_stock, StockError

            res = search_stock(prov, key, ["developer", "code"], count=1)
            if res:
                return {"ok": True, "message": f"{prov}: chave OK — a busca funcionou."}
            return {"ok": False, "message": f"{prov}: conectou, mas não veio resultado."}
        except StockError as e:
            return {"ok": False, "message": str(e)}
        except Exception as e:
            log.exception("test_stock falhou")
            return {"ok": False, "message": f"Erro inesperado: {e}"}

    def test_gemini(self, api_key, model) -> dict[str, Any]:
        """Testa a chave do Gemini AGORA (uma geração mínima)."""
        key = api_key if api_key is not None else self.settings.gemini_api_key
        if not (key or "").strip():
            return {"ok": False, "message": "Sem API key do Gemini."}
        try:
            from .ai.gemini import available

            if not available():
                return {"ok": False, "message": "SDK google-genai indisponível."}
            from google import genai

            m = model or self.settings.gemini_text_model or "gemini-2.5-flash"
            client = genai.Client(api_key=key)
            client.models.generate_content(model=m, contents="responda só: ok")
            return {"ok": True, "message": f"Gemini OK ({m})."}
        except Exception as e:
            from .ai.gemini import _friendly_ai_error

            return {"ok": False, "message": _friendly_ai_error(e)}

    # ------------------------------------------------------------------ #
    # Worker do recap
    # ------------------------------------------------------------------ #
    def trigger_recap(self, *, show_when_done: bool, day: Optional[str] = None) -> None:
        with self._lock:
            if self._running:
                self._push({"toast": "Já estou gerando…"})
                return
            self._running = True
        self._push({"generating": True})
        threading.Thread(
            target=self._worker, args=(day, show_when_done), name="recap", daemon=True
        ).start()

    def _worker(self, day: Optional[str], show_when_done: bool) -> None:
        try:
            self._set_title("DevRecap — gerando recap…")
            report = generate_recap(self.settings, day=day, cb=self._progress)
            self._set_current(report)
            vm = self._live_vm(report)
            if show_when_done:
                self._show_window()
            self._push({"report": vm, "generating": False, "toast": "Recap gerado!"})
            self._notify_done(report)
        except Exception:
            log.exception("pipeline falhou")
            self._push({"generating": False, "toast": "Falha ao gerar o recap"})
        finally:
            with self._lock:
                self._running = False
            self._set_title("DevRecap")

    def trigger_regenerate(self, options: dict[str, Any]) -> None:
        """Regenera o texto focando nos repos selecionados (options: repos, post_length)."""
        options = options or {}
        with self._lock:
            if self._running:
                self._push({"toast": "Já estou gerando…"})
                return
            if self._full_activity is None:
                self._push({"toast": "Gere um recap primeiro."})
                return
            self._running = True

        pl = str(options.get("post_length") or "").strip().lower()
        if pl in ("curto", "medio", "longo"):
            self.settings.post_length = pl
            try:
                self.settings.save()
            except Exception:
                log.exception("falha ao salvar post_length")

        selected = options.get("repos")
        self._push({"generating": True})
        threading.Thread(
            target=self._regen_worker, args=(selected,), name="regen", daemon=True
        ).start()

    def _regen_worker(self, selected) -> None:
        try:
            self._set_title("DevRecap — regenerando texto…")
            names = {r.name for r in self._full_activity.active_repos}
            sel = (set(selected) & names) if selected else names
            self._selected_repos = sel or names
            report = regenerate_report(
                self.settings, self._full_activity, self._selected_repos, cb=self._progress
            )
            # _full_activity NÃO muda -> os candidatos (marcáveis) são preservados
            vm = self._live_vm(report)
            self._push({"report": vm, "generating": False, "toast": "Texto regenerado!"})
        except Exception:
            log.exception("regenerate falhou")
            self._push({"generating": False, "toast": "Falha ao regenerar"})
        finally:
            with self._lock:
                self._running = False
            self._set_title("DevRecap")

    def _notify_done(self, report: DailyReport) -> None:
        if report.activity.has_activity:
            self._notify("Recap do dia pronto", f"{report.activity.total_commits} commit(s).")
        else:
            self._notify("DevRecap", "Nenhuma atividade detectada hoje.")
        self.icon.update_menu()

    # ------------------------------------------------------------------ #
    def _progress(self, msg: str) -> None:
        self._set_title(f"DevRecap — {msg}")

    def _set_title(self, title: str) -> None:
        try:
            self.icon.title = title[:127]
        except Exception:
            pass

    def _notify(self, title: str, message: str) -> None:
        if not self.settings.show_notifications:
            return
        try:
            if getattr(self.icon, "HAS_NOTIFICATION", False):
                self.icon.notify(message, title)
        except Exception:
            log.debug("notify indisponível")


def main() -> None:
    log.info("DevRecap iniciando")
    AppController().start()


if __name__ == "__main__":
    main()
