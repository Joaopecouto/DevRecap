"""Configuração persistente do DevRecap (%APPDATA%/DevRecap/config.json).

Guarda: pastas monitoradas, credenciais (GitHub, banco de fotos),
horário do resumo, fontes de foto, idioma/tom do post e flags de comportamento.

Segredos ficam em texto neste JSON (app local de uso pessoal). O arquivo está
no .gitignore e mora fora do repositório, em %APPDATA%.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

from .paths import config_path

# A análise do dia é feita pelo Claude Code (ai/claude_code.py), que usa a
# instalação local do CLI — não há chave nem modelo para configurar aqui.
# Os defaults abaixo ficaram só para não quebrar config.json já existentes.
# (mantidos configuráveis: o João pode trocar na tela de Configurações)
DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"


@dataclass
class Settings:
    # ---- Projetos locais ----
    folders: list[str] = field(default_factory=list)        # pastas marcadas p/ análise
    scan_subfolders: bool = True                            # procurar repos git aninhados
    max_scan_depth: int = 3                                 # profundidade ao procurar repos
    git_author_emails: list[str] = field(default_factory=list)  # filtra commits por autor (vazio = todos)

    # ---- GitHub ----
    github_enabled: bool = False
    github_username: str = ""
    github_token: str = ""
    github_include_private: bool = True

    # ---- Legado do Gemini ----
    # Mantidos só para que config.json antigos continuem carregando sem erro.
    # Nada no pipeline lê estes campos desde a migração para o Claude Code.
    gemini_api_key: str = ""
    gemini_text_model: str = DEFAULT_TEXT_MODEL
    gemini_image_enabled: bool = False
    gemini_image_model: str = DEFAULT_IMAGE_MODEL

    # ---- Texto / post ----
    language: str = "pt-BR"
    linkedin_tone: str = (
        "primeira pessoa, tom de conversa (como contar pra um amigo dev), "
        "curto e direto, nada de jargão corporativo nem tom de release; "
        "1 a 3 hashtags"
    )
    post_length: str = "curto"                              # "curto" | "medio" | "longo"
    style_reference_file: str = ""                          # ex.: caminho do Perfil-LinkedIn-Vencedor.md

    # ---- Fotos ----
    photo_sources: list[str] = field(default_factory=lambda: ["project", "stock"])  # "project"|"stock"|"gemini"
    stock_provider: str = "pexels"                          # "pexels" | "unsplash"
    stock_api_key: str = ""

    # ---- Agendamento / comportamento ----
    schedule_time: str = "18:00"                            # HH:MM 24h, hora local
    run_on_weekends: bool = False
    autostart: bool = False                                 # iniciar com o Windows
    show_notifications: bool = True
    auto_open_report: bool = True                           # abrir janela do relatório ao gerar

    # ---- Versão do schema (p/ migrações futuras) ----
    schema_version: int = 1

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Settings":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.exists():
            s = cls()
            s.save()
            return s
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except (json.JSONDecodeError, OSError):
            # config corrompida: não derruba o app — volta ao default e preserva backup
            try:
                path.replace(path.with_suffix(".json.bak"))
            except OSError:
                pass
            s = cls()
            s.save()
            return s

    def save(self) -> None:
        path = config_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)  # escrita atômica

    # ------------------------------------------------------------------ #
    # Validação leve usada pela UI para avisar o que falta configurar.
    def missing_requirements(self) -> list[str]:
        problems: list[str] = []
        if not self.folders and not self.github_enabled:
            problems.append("Nenhuma pasta marcada e GitHub desativado — não há o que analisar.")
        # A análise depende do CLI do Claude Code estar instalado, não de chave.
        try:
            from ..ai.claude_code import disponivel as _claude_ok

            if not _claude_ok():
                problems.append(
                    "Claude Code indisponível (CLI 'claude' fora do PATH ou "
                    "prompt-diario.md ausente) — sem resumo do dia nem post."
                )
        except Exception:
            problems.append("Não foi possível checar o Claude Code.")
        if self.github_enabled and (not self.github_username or not self.github_token):
            problems.append("GitHub ativado mas faltam usuário e/ou token.")
        if "stock" in self.photo_sources and not self.stock_api_key:
            problems.append(f"Fonte de foto 'banco de fotos' ({self.stock_provider}) sem API key.")
        return problems
