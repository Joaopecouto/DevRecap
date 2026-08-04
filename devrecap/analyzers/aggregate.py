"""Mescla a atividade coletada localmente (git CLI) com a do GitHub API.

Junta `RepoActivity` da fonte local e do GitHub num único `DayActivity`,
casando repositórios pelo `remote_url` normalizado (ou pelo nome) e unindo
commits, PRs, issues e estatísticas. Nunca levanta exceção: em caso de erro
loga e devolve o melhor objeto parcial possível.
"""
from __future__ import annotations

from dataclasses import replace

from devrecap.core.models import (
    CommitInfo,
    DayActivity,
    IssueInfo,
    PullRequestInfo,
    RepoActivity,
)
from devrecap.core.logging_setup import get_logger

logger = get_logger(__name__)


def _norm_remote(url: str | None) -> str:
    """Normaliza um remote_url p/ comparação (lower, sem .git, sem esquema/host extra)."""
    if not url:
        return ""
    s = str(url).strip().lower()
    # remove esquemas conhecidos
    for prefix in ("https://", "http://", "ssh://", "git://"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # remove forma scp "git@github.com:owner/repo"
    if s.startswith("git@"):
        s = s[len("git@"):]
    # normaliza "host:owner/repo" -> "host/owner/repo"
    s = s.replace(":", "/", 1) if ":" in s and "/" not in s.split(":", 1)[0] else s.replace(":", "/")
    # remove possível "user@" residual (ex.: "git@" já tratado, mas por segurança)
    if "@" in s:
        s = s.split("@", 1)[1]
    # remove sufixo .git
    if s.endswith(".git"):
        s = s[: -len(".git")]
    # remove barras finais
    s = s.rstrip("/")
    return s


def _sha_match(a: str | None, b: str | None) -> bool:
    """True se dois SHAs se referem ao mesmo commit (um é prefixo do outro, >=7 chars)."""
    if not a or not b:
        return False
    a = a.strip().lower()
    b = b.strip().lower()
    if not a or not b:
        return False
    n = min(len(a), len(b))
    if n < 7:
        return a == b
    return a[:n] == b[:n]


def _merge_commits(
    base: list[CommitInfo], extra: list[CommitInfo]
) -> list[CommitInfo]:
    """Une duas listas de commits deduplicando por SHA (prefixo de 7+ chars).

    Copia os commits-base (dataclasses.replace) p/ não mutar os objetos do
    chamador ao preencher url a partir do par do GitHub."""
    merged: list[CommitInfo] = [replace(c) for c in (base or [])]
    for c in extra or []:
        dup = False
        for existing in merged:
            if _sha_match(existing.sha, c.sha):
                dup = True
                # preferir manter url do GitHub se o existente não tiver
                if not existing.url and c.url:
                    existing.url = c.url
                break
        if not dup:
            merged.append(c)
    return merged


def _merge_prs(
    base: list[PullRequestInfo], extra: list[PullRequestInfo]
) -> list[PullRequestInfo]:
    """Une PRs deduplicando por número."""
    merged: list[PullRequestInfo] = list(base or [])
    seen = {p.number for p in merged}
    for p in extra or []:
        if p.number not in seen:
            merged.append(p)
            seen.add(p.number)
    return merged


def _merge_issues(
    base: list[IssueInfo], extra: list[IssueInfo]
) -> list[IssueInfo]:
    """Une issues deduplicando por número."""
    merged: list[IssueInfo] = list(base or [])
    seen = {i.number for i in merged}
    for i in extra or []:
        if i.number not in seen:
            merged.append(i)
            seen.add(i.number)
    return merged


def _union_branches(a: list[str], b: list[str]) -> list[str]:
    """União de branches preservando ordem e sem duplicar."""
    out: list[str] = []
    for br in list(a or []) + list(b or []):
        if br and br not in out:
            out.append(br)
    return out


def _merge_pair(local: RepoActivity, github: RepoActivity) -> RepoActivity:
    """Mescla um repo local com seu par do GitHub num RepoActivity source='both'."""
    merged = RepoActivity(
        name=local.name or github.name,
        path=local.path,
        remote_url=local.remote_url or github.remote_url,
        source="both",
    )
    merged.commits = _merge_commits(local.commits, github.commits)
    merged.prs = _merge_prs(local.prs, github.prs)
    merged.issues = _merge_issues(local.issues, github.issues)
    merged.branches_touched = _union_branches(
        local.branches_touched, github.branches_touched
    )
    # linguagens: somar contagens por extensão
    langs: dict[str, int] = dict(local.languages or {})
    for ext, n in (github.languages or {}).items():
        langs[ext] = langs.get(ext, 0) + n
    merged.languages = langs
    # estatísticas somadas
    merged.files_changed = (local.files_changed or 0) + (github.files_changed or 0)
    merged.insertions = (local.insertions or 0) + (github.insertions or 0)
    merged.deletions = (local.deletions or 0) + (github.deletions or 0)
    # estado de working tree vem do local
    merged.is_dirty = bool(local.is_dirty)
    merged.uncommitted_files = list(local.uncommitted_files or [])
    # propaga erros, se houver
    errs = [e for e in (local.error, github.error) if e]
    merged.error = "; ".join(errs) if errs else None
    return merged


def build_day_activity(
    day: str,
    local_repos: list[RepoActivity],
    github_repos: list[RepoActivity],
    notes: list[str] | None = None,
) -> DayActivity:
    """Mescla repos locais e do GitHub num único DayActivity.

    Casa por remote_url normalizado (sem .git/esquema) ou, na falta, por nome
    (case-insensitive). Ao casar: une commits (dedup por SHA de 7+ chars), une
    prs/issues, soma stats, faz união de branches e marca source='both'. Repos
    sem par entram como estão. Nunca levanta — em erro, devolve o que conseguiu.
    """
    try:
        locals_list = list(local_repos or [])
        github_list = list(github_repos or [])

        # índices dos repos GitHub por remote normalizado e por nome (lower)
        gh_by_remote: dict[str, int] = {}
        gh_by_name: dict[str, int] = {}
        for idx, gr in enumerate(github_list):
            rk = _norm_remote(gr.remote_url)
            if rk and rk not in gh_by_remote:
                gh_by_remote[rk] = idx
            nk = (gr.name or "").strip().lower()
            if nk and nk not in gh_by_name:
                gh_by_name[nk] = idx

        used_github: set[int] = set()
        merged_repos: list[RepoActivity] = []

        for lr in locals_list:
            match_idx: int | None = None
            lr_remote = _norm_remote(lr.remote_url)
            if lr_remote and lr_remote in gh_by_remote:
                cand = gh_by_remote[lr_remote]
                if cand not in used_github:
                    match_idx = cand
            if match_idx is None:
                lr_name = (lr.name or "").strip().lower()
                if lr_name and lr_name in gh_by_name:
                    cand = gh_by_name[lr_name]
                    if cand not in used_github:
                        match_idx = cand

            if match_idx is not None:
                used_github.add(match_idx)
                merged_repos.append(_merge_pair(lr, github_list[match_idx]))
            else:
                merged_repos.append(lr)

        # repos do GitHub que não casaram com nenhum local entram como estão
        for idx, gr in enumerate(github_list):
            if idx not in used_github:
                merged_repos.append(gr)

        return DayActivity(day=day, repos=merged_repos, notes=list(notes or []))
    except Exception as exc:  # nunca deixar vazar
        logger.exception("Falha ao mesclar atividade do dia %s: %s", day, exc)
        fallback: list[RepoActivity] = list(local_repos or []) + list(github_repos or [])
        out_notes = list(notes or [])
        out_notes.append(f"Erro ao agregar atividade: {exc}")
        return DayActivity(day=day, repos=fallback, notes=out_notes)
