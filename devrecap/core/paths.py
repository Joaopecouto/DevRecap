"""Caminhos padrão do app (config, relatórios, logs, assets).

Tudo do usuário vai para %APPDATA%/DevRecap. Assets embarcados (ícone) são
resolvidos levando em conta o PyInstaller (sys._MEIPASS) quando empacotado.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DevRecap"


def app_data_dir() -> Path:
    """Pasta de dados do usuário: %APPDATA%/DevRecap (criada se não existir)."""
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return app_data_dir() / "config.json"


def reports_dir() -> Path:
    p = app_data_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = app_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def media_dir() -> Path:
    """Onde ficam imagens geradas/baixadas para os posts."""
    p = app_data_dir() / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bundle_root() -> Path:
    """Raiz dos arquivos embarcados (lida com PyInstaller --onefile)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # devrecap/core/paths.py -> sobe 2 níveis até a raiz do projeto
    return Path(__file__).resolve().parents[2]


def asset_path(name: str) -> Path:
    """Resolve um asset embarcado (ex.: 'assets/icon.png')."""
    return _bundle_root() / name


def web_dir() -> Path:
    """Pasta do frontend (index.html, styles.css, app.js), source ou empacotado."""
    return _bundle_root() / "devrecap" / "ui" / "web"
