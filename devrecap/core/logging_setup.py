"""Logger central do app (arquivo rotativo em %APPDATA%/DevRecap/logs)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir

_configured = False


def get_logger(name: str = "devrecap") -> logging.Logger:
    global _configured
    logger = logging.getLogger("devrecap")
    if not _configured:
        logger.setLevel(logging.INFO)
        fh = RotatingFileHandler(
            logs_dir() / "devrecap.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(fh)
        # também no console (útil rodando do fonte)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
        _configured = True
    return logger.getChild(name) if name != "devrecap" else logger
