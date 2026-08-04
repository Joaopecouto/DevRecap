"""Gera assets/icon.png e assets/icon.ico. Rode uma vez: python make_icon.py"""
import os

from devrecap.ui.tray import save_icon_files

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    save_icon_files(out)
    print(f"Ícones gerados em {out}")
