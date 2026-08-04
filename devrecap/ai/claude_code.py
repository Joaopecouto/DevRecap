"""Etapa de lapidação: entrega o relatório do dia ao Claude Code em modo headless.

## Por que não é uma chamada de API

O DevRecap já gera texto via Gemini. Esta etapa é diferente: em vez de uma chamada
de LLM, invoca o **Claude Code** (`claude -p`), que roda como agente — lê arquivos,
abre commits, consulta as skills de marketing instaladas e os subagentes do projeto
LinkedIn. Nada disso cabe num prompt único.

Consequências práticas:
- Não precisa de chave de API nova: usa a assinatura do Claude Code já instalada.
- Roda local, então enxerga todos os repositórios e o `%APPDATA%`.
- É mais lento que uma chamada de API (minutos, não segundos). Por isso roda em
  background depois do relatório ficar pronto — o app não espera.

## Por que o gatilho é aqui e não no agendador do Claude

O `CronCreate` do Claude Code é de sessão: morre quando o Claude fecha, só dispara
com o REPL ocioso e expira em 7 dias. Não serve para job diário desassistido. O
DevRecap já acorda às 18h — ele é o agendador natural.

## Saída

Grava na pasta do dia (`%APPDATA%\\DevRecap\\reports\\<dia>\\`):
- `post-linkedin.md`   — o candidato a post
- `post-linkedin.json` — metadados para a UI

Nenhuma exceção vaza: em falha, devolve ClaudeResult(ok=False, error=...).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from devrecap.core.logging_setup import get_logger

logger = get_logger(__name__)

# Mesmo motivo do git_local: sem isto, cada chamada abre uma janela de console
# quando o processo pai não tem console (app de bandeja).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# A lapidação é agêntica (lê arquivos, abre commits, roda subagentes). Minutos,
# não segundos. O teto existe para não deixar processo órfão se algo travar.
_TIMEOUT_S = 900

PROJETO_LINKEDIN = Path(
    r"C:\Users\jojob\OneDrive\Documentos\Projetos\Linkedin"
)
PROMPT_FILE = PROJETO_LINKEDIN / "scripts" / "prompt-diario.md"

# Diretórios que a execução headless precisa enxergar além do cwd. Sem isto o
# Claude Code pediria permissão — e em modo headless não há ninguém para responder.
def _dirs_extras(pasta_relatorio: Path) -> list[str]:
    return [
        str(pasta_relatorio),
        r"C:\Users\jojob\OneDrive\Documentos\Projetos",
        r"C:\Users\jojob\OneDrive\Documentos\Projetos de Estudos",
    ]


def _cli() -> str | None:
    """Caminho do executável do Claude Code.

    No Windows o npm instala um shim `claude.CMD`. `subprocess` sem shell=True
    não resolve `.CMD` a partir do nome — precisa do caminho completo, que o
    `shutil.which` encontra consultando o PATHEXT.
    """
    return shutil.which("claude")


@dataclass
class ClaudeResult:
    ok: bool
    status: str = ""          # "candidato" | "dia-sem-material" | ""
    md_path: str = ""
    json_path: str = ""
    insights: dict | None = None   # payload de AIInsights (substitui o do Gemini)
    error: str = ""


def disponivel() -> bool:
    """True se o CLI do Claude Code responde e o prompt do processo existe."""
    exe = _cli()
    if not exe or not PROMPT_FILE.exists():
        return False
    try:
        p = subprocess.run(
            [exe, "--version"],
            capture_output=True, timeout=20, creationflags=_NO_WINDOW,
        )
        return p.returncode == 0
    except Exception:
        return False


def gerar_post(pasta_relatorio: str | Path) -> ClaudeResult:
    """Roda a lapidação sobre o relatório de um dia.

    `pasta_relatorio` é a pasta que contém o `report.json` daquele dia.
    """
    pasta = Path(pasta_relatorio)
    if not (pasta / "report.json").exists():
        return ClaudeResult(False, error=f"report.json não encontrado em {pasta}")
    if not PROMPT_FILE.exists():
        return ClaudeResult(False, error=f"prompt não encontrado: {PROMPT_FILE}")

    exe = _cli()
    if not exe:
        return ClaudeResult(False, error="CLI 'claude' não encontrado no PATH")

    instrucao = PROMPT_FILE.read_text(encoding="utf-8")
    prompt = (
        f"{instrucao}\n\n"
        f"---\n\n"
        f"**Pasta do relatório de hoje:** `{pasta}`\n"
        f"**Projeto LinkedIn (contexto e formato):** `{PROJETO_LINKEDIN}`\n"
    )

    # O prompt vai por STDIN, não como argumento.
    #
    # No Windows o `claude` é um shim .CMD, ou seja, passa por cmd.exe — e
    # argumento multilinha quebra na primeira quebra de linha. Medido: a execução
    # recebia só a primeira linha do arquivo de instrução (o título em markdown)
    # e abortava, sem erro aparente. Por stdin o texto chega inteiro.
    cmd = [exe, "-p"]
    for d in _dirs_extras(pasta):
        cmd += ["--add-dir", d]

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            cwd=str(PROJETO_LINKEDIN),   # cwd = projeto LinkedIn: carrega os subagentes de lá
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_S,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        logger.warning("claude -p estourou %ss", _TIMEOUT_S)
        return ClaudeResult(False, error=f"timeout após {_TIMEOUT_S}s")
    except FileNotFoundError:
        return ClaudeResult(False, error="CLI 'claude' não encontrado no PATH")
    except Exception as e:
        logger.exception("claude -p falhou")
        return ClaudeResult(False, error=str(e))

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300] or "erro desconhecido"
        return ClaudeResult(False, error=err)

    # A execução headless grava dentro do projeto LinkedIn (seu cwd), porque
    # escrever em %APPDATA% exigiria uma permissão que ninguém pode conceder sem
    # interação. Python não tem essa restrição — copia para a pasta do dia aqui.
    origem = PROJETO_LINKEDIN / "posts" / "diario" / pasta.name
    md = pasta / "post-linkedin.md"
    js = pasta / "post-linkedin.json"
    for nome in ("post-linkedin.md", "post-linkedin.json", "insights.json"):
        src = origem / nome
        if src.exists():
            try:
                shutil.copy2(src, pasta / nome)
            except Exception:
                logger.exception("falha ao copiar %s para %s", src, pasta)

    if not md.exists():
        # A saída costuma explicar o motivo (permissão negada, dia sem material
        # com gravação falha, etc). Preservar generosamente ajuda o diagnóstico.
        saida = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return ClaudeResult(
            False,
            error="execução terminou sem gravar post-linkedin.md. "
                  f"Saída: {saida[:1500]}",
        )

    status = ""
    if js.exists():
        try:
            status = json.loads(js.read_text(encoding="utf-8")).get("status", "")
        except Exception:
            logger.warning("post-linkedin.json inválido em %s", pasta)

    insights = None
    ins_file = pasta / "insights.json"
    if ins_file.exists():
        try:
            insights = json.loads(ins_file.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("insights.json inválido em %s", pasta)

    logger.info("lapidação concluída: %s (status=%s)", md, status or "?")
    return ClaudeResult(
        True, status=status, md_path=str(md), json_path=str(js), insights=insights
    )
