"""Analisador de repositórios git locais via git CLI (subprocess).

Coleta os commits do dia em horário LOCAL, agrega estatísticas (insertions,
deletions, arquivos tocados, linguagens por extensão) e o estado da árvore
de trabalho (is_dirty + arquivos não commitados). Não usa bibliotecas
externas (nada de GitPython) — apenas o binário `git` disponível no PATH.

Nenhuma exceção vaza: em falha, devolve `RepoActivity(name=..., error=...)`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from devrecap.core.logging_setup import get_logger
from devrecap.core.models import CommitInfo, RepoActivity

logger = get_logger(__name__)

# Separador de unidade (0x1f) usado no --pretty=format do git log.
_US = "\x1f"

# Separador de REGISTRO (0x1e). Necessário desde que o log passou a trazer %B
# (corpo completo do commit), que é multilinha — não dá mais para quebrar por
# splitlines(). Nenhum dos dois caracteres aparece em mensagem de commit real.
_RS = "\x1e"

# Windows: sem isto, cada subprocess.run abre uma janela de console. Como o app
# roda na bandeja (processo sem console), o efeito era dezenas de janelas de cmd
# piscando às 18:00 — são 4 chamadas por repositório MAIS uma por commit
# (_commit_numstat), o que em ~16 repos passa de 80 janelas e trava a máquina.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# Pastas que nunca devem ser exploradas ao procurar repositórios.
_SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "venv",
    ".venv",
    "__pycache__",
}


def _run_git(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Executa `git <args>` e devolve o CompletedProcess (stdout/stderr texto).

    Usa utf-8 com errors="replace" e não levanta em código de saída != 0
    (o chamador inspeciona returncode/stdout)."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        creationflags=_NO_WINDOW,
    )


def find_git_repos(folder: str, max_depth: int = 3) -> list[str]:
    """Caminhos-raiz de repositórios git dentro de `folder` (até max_depth níveis).

    Um repo é uma pasta que contém `.git`. Não desce dentro de um repo já
    encontrado e pula pastas ruidosas (node_modules, dist, venv, etc.)."""
    repos: list[str] = []
    root = Path(folder)
    try:
        if not root.is_dir():
            return repos
    except OSError as exc:
        logger.warning("find_git_repos: pasta inacessível %s: %s", folder, exc)
        return repos

    def _walk(current: Path, depth: int) -> None:
        # A própria pasta é um repo?
        try:
            if (current / ".git").exists():
                repos.append(str(current))
                return  # não descer dentro de um repo já encontrado
        except OSError:
            return

        if depth >= max_depth:
            return

        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            logger.debug("find_git_repos: não listou %s: %s", current, exc)
            return

        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name in _SKIP_DIRS:
                continue
            _walk(Path(entry.path), depth + 1)

    _walk(root, 0)
    return repos


def _current_branch(repo_path: str) -> str | None:
    """Branch atual via `git rev-parse --abbrev-ref HEAD` (None se falhar)."""
    proc = _run_git(["-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if proc.returncode != 0:
        return None
    branch = (proc.stdout or "").strip()
    return branch or None


def _remote_url(repo_path: str) -> str | None:
    """URL do remote origin (None se não houver ou falhar)."""
    proc = _run_git(
        ["-C", repo_path, "config", "--get", "remote.origin.url"], cwd=repo_path
    )
    if proc.returncode != 0:
        return None
    url = (proc.stdout or "").strip()
    return url or None


def _commit_numstat(repo_path: str, sha: str) -> tuple[int, int, int, list[str], dict[str, int]]:
    """Numstat de um commit: (insertions, deletions, files_changed, files, languages).

    Lê `git show --numstat --format= <sha>` -> linhas "adds\\tdels\\tpath".
    Em arquivos binários adds/dels vêm como "-" e contam como 0."""
    insertions = 0
    deletions = 0
    files: list[str] = []
    languages: dict[str, int] = {}

    proc = _run_git(
        ["-C", repo_path, "show", "--numstat", "--format=", sha], cwd=repo_path
    )
    if proc.returncode != 0:
        return (0, 0, 0, [], {})

    for line in (proc.stdout or "").splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        adds_raw, dels_raw, path = parts[0], parts[1], parts[2]
        try:
            adds = int(adds_raw) if adds_raw != "-" else 0
        except ValueError:
            adds = 0
        try:
            dels = int(dels_raw) if dels_raw != "-" else 0
        except ValueError:
            dels = 0
        insertions += adds
        deletions += dels
        files.append(path)
        ext = Path(path).suffix.lower()
        languages[ext] = languages.get(ext, 0) + 1

    return (insertions, deletions, len(files), files, languages)


def analyze_repo(repo_path: str, day: str, author_emails: list[str]) -> RepoActivity:
    """Commits do dia `day` no repo `repo_path`, com estatísticas agregadas.

    Janela em hora LOCAL: since="<day> 00:00:00", until="<day> 23:59:59".
    Se author_emails != [], mantém só commits cujo %ae esteja na lista
    (case-insensitive). source="local". Em erro devolve RepoActivity com error."""
    name = Path(repo_path).name or repo_path
    try:
        since = f"{day} 00:00:00"
        until = f"{day} 23:59:59"

        log_proc = _run_git(
            [
                "-C",
                repo_path,
                "log",
                "--no-merges",
                f"--since={since}",
                f"--until={until}",
                # %cI (data de COMMIT) p/ casar com o filtro --since/--until,
                # que também é por data de commit — evita commit cair no dia errado.
                # %B (corpo completo) e não %s (só o assunto): é no corpo que vive
                # o raciocínio — causa-raiz, alternativas descartadas, o que foi
                # medido. Com %s a IA recebia ~72 caracteres por commit e tinha que
                # adivinhar o resto. Por ser multilinha, %B vai POR ÚLTIMO e cada
                # registro é fechado com _RS.
                f"--pretty=format:%H{_US}%an{_US}%ae{_US}%cI{_US}%B{_RS}",
            ],
            cwd=repo_path,
        )
        if log_proc.returncode != 0:
            err = (log_proc.stderr or "").strip() or "git log falhou"
            logger.warning("analyze_repo: %s: %s", repo_path, err)
            return RepoActivity(name=name, path=repo_path, source="local", error=err)

        branch = _current_branch(repo_path)
        remote = _remote_url(repo_path)

        emails_lower = {e.strip().lower() for e in author_emails if e and e.strip()}

        commits: list[CommitInfo] = []
        languages: dict[str, int] = {}
        total_files = 0
        total_ins = 0
        total_dels = 0

        # Quebra por REGISTRO (_RS), não por linha: %B é multilinha.
        for registro in (log_proc.stdout or "").split(_RS):
            if not registro.strip():
                continue
            fields = registro.split(_US)
            if len(fields) < 5:
                continue
            sha, author_name, author_email, timestamp, corpo = fields[:5]
            sha = sha.strip()
            corpo = corpo.strip()

            if emails_lower and author_email.strip().lower() not in emails_lower:
                continue

            ins, dels, fchanged, files, langs = _commit_numstat(repo_path, sha)

            commits.append(
                CommitInfo(
                    sha=sha,
                    message=corpo,
                    timestamp=timestamp,
                    repo=name,
                    source="local",
                    author=author_name,
                    branch=branch,
                    files_changed=fchanged,
                    insertions=ins,
                    deletions=dels,
                    files=files,
                )
            )

            total_files += fchanged
            total_ins += ins
            total_dels += dels
            for ext, n in langs.items():
                languages[ext] = languages.get(ext, 0) + n

        is_dirty, uncommitted = _working_tree_status(repo_path)

        branches_touched = [branch] if branch else []

        return RepoActivity(
            name=name,
            path=repo_path,
            remote_url=remote,
            source="local",
            commits=commits,
            branches_touched=branches_touched,
            languages=languages,
            files_changed=total_files,
            insertions=total_ins,
            deletions=total_dels,
            is_dirty=is_dirty,
            uncommitted_files=uncommitted,
        )
    except Exception as exc:  # nunca deixar vazar
        logger.exception("analyze_repo: erro inesperado em %s", repo_path)
        return RepoActivity(name=name, path=repo_path, source="local", error=str(exc))


def _working_tree_status(repo_path: str) -> tuple[bool, list[str]]:
    """Estado da árvore via `git status --porcelain`: (is_dirty, uncommitted_files).

    Cada linha não vazia indica mudança; o caminho é a parte após o status."""
    proc = _run_git(["-C", repo_path, "status", "--porcelain"], cwd=repo_path)
    if proc.returncode != 0:
        return (False, [])

    uncommitted: list[str] = []
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        # Formato porcelain: "XY <path>" (XY = 2 chars de status + espaço).
        path = line[3:].strip() if len(line) > 3 else line.strip()
        # Rename/copy aparece como "old -> new": guardar o destino (new).
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            uncommitted.append(path)

    return (bool(uncommitted), uncommitted)


def scan_folders(
    folders: list[str],
    day: str,
    *,
    scan_subfolders: bool = True,
    max_depth: int = 3,
    author_emails: list[str] | None = None,
) -> list[RepoActivity]:
    """Analisa cada pasta de `folders` e devolve as RepoActivity relevantes.

    Se scan_subfolders, usa find_git_repos em cada pasta; senão trata a própria
    pasta como repo (se tiver `.git`). Inclui só repos com atividade OU is_dirty.
    Loga e segue adiante em qualquer erro."""
    author_emails = author_emails or []
    results: list[RepoActivity] = []
    seen: set[str] = set()

    for folder in folders:
        try:
            if scan_subfolders:
                repo_paths = find_git_repos(folder, max_depth=max_depth)
            else:
                repo_paths = []
                try:
                    if (Path(folder) / ".git").exists():
                        repo_paths = [folder]
                except OSError as exc:
                    logger.warning("scan_folders: pasta inacessível %s: %s", folder, exc)
                    continue

            for repo_path in repo_paths:
                key = str(Path(repo_path).resolve()) if repo_path else repo_path
                if key in seen:
                    continue
                seen.add(key)

                activity = analyze_repo(repo_path, day, author_emails)
                if activity.has_activity or activity.is_dirty:
                    results.append(activity)
        except Exception:  # nunca deixar vazar — segue para a próxima pasta
            logger.exception("scan_folders: erro inesperado processando %s", folder)
            continue

    return results
