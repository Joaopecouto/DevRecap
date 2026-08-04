"""Autoteste do DevRecap — valida que todas as dependências carregam e o
pipeline roda, SEM abrir a GUI. Serve para conferir o executável empacotado
(PyInstaller), onde uma falha de import seria silenciosa (app --windowed).

Escreve o resultado em %TEMP%\\devrecap_selftest.txt e retorna 0 (OK) ou 1 (falha).
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback


def run_selftest() -> int:
    lines: list[str] = []
    ok = True

    # Isola APPDATA para não tocar na config real durante o teste.
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="devrecap_selftest_")

    try:
        import requests  # noqa: F401
        lines.append("requests OK")

        from PIL import Image  # noqa: F401
        lines.append("Pillow OK")

        import pystray  # noqa: F401
        lines.append("pystray OK")

        import webview  # noqa: F401
        lines.append("pywebview OK")

        # Força o backend EdgeChromium (clr/pythonnet) — pega falha de empacotamento
        # sem precisar abrir janela.
        import webview.platforms.edgechromium  # noqa: F401
        lines.append("edgechromium/clr OK")

        from devrecap.ui import webview_app
        html = webview_app.build_html()
        lines.append(f"build_html OK ({len(html)} chars)")

        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: F401
        from apscheduler.triggers.cron import CronTrigger  # noqa: F401
        lines.append("apscheduler OK")

        # O mais arriscado de empacotar — importar explicitamente p/ falhar alto.
        from google import genai  # noqa: F401
        lines.append("google-genai OK")

        from devrecap.ui import tray
        img = tray.make_image()
        lines.append(f"icone {img.size}")

        from devrecap.scheduler.daily import DailyScheduler
        sch = DailyScheduler(lambda: None, time_str="18:00")
        sch.start()
        lines.append(f"scheduler next: {sch.next_run_time()}")
        sch.shutdown()

        from devrecap.core.config import Settings
        from devrecap import pipeline
        rep = pipeline.generate_recap(Settings())
        lines.append(f"pipeline rodou (day={rep.day}, activity={rep.activity.has_activity})")

    except Exception:
        ok = False
        lines.append("EXCEPTION:\n" + traceback.format_exc())

    result = ("OK" if ok else "FAIL") + "\n" + "\n".join(lines) + "\n"

    try:
        out = os.path.join(tempfile.gettempdir(), "devrecap_selftest.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(result)
    except OSError:
        pass

    try:
        print(result)
    except Exception:
        pass

    return 0 if ok else 1
