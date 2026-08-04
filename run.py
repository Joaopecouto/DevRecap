"""Ponto de entrada do DevRecap.

Uso:
    python run.py            # roda o app de bandeja
    pythonw run.py           # roda sem janela de console (recomendado p/ autostart)
"""
from __future__ import annotations

import os
import sys

# Garante que o pacote 'devrecap' seja importável, independente do cwd
# (importante quando iniciado pelo autostart do Windows).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _main() -> None:
    # Modo de autoteste: valida imports/pipeline (útil p/ checar o .exe congelado)
    # e sai, sem abrir a GUI. Escreve o resultado em %TEMP%\devrecap_selftest.txt.
    if "--selftest" in sys.argv:
        from devrecap.selftest import run_selftest

        raise SystemExit(run_selftest())

    from devrecap.app import main

    main()


if __name__ == "__main__":
    _main()
