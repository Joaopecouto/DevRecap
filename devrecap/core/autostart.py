"""Iniciar com o Windows (sem admin) via HKCU\\...\\Run.

Funciona tanto rodando do código-fonte (lança python + run.py) quanto
empacotado com PyInstaller (sys.frozen -> o próprio .exe).
"""
from __future__ import annotations

import os
import sys

APP_NAME = "DevRecap"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

try:
    import winreg  # type: ignore
except ImportError:  # não-Windows (dev em outra plataforma)
    winreg = None  # type: ignore


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # roda o entry-point a partir do fonte
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{script}"' if script else f'"{exe}"'


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> None:
    if winreg is None:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass


def set_enabled(value: bool) -> None:
    enable() if value else disable()
