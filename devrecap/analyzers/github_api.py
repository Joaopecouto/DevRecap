"""Coleta de atividade do GitHub via REST API (commits, PRs, issues do dia).

Fluxo de `day_activity(day)`:
  1. lista repos do usuário ordenados por `pushed_at` (para na fronteira do dia);
  2. para cada repo ativo, busca os commits do usuário no intervalo do dia;
  3. busca PRs/issues do dia via /search/issues e anexa ao repo correspondente.

Toda falha de rede/HTTP é capturada: erro por repo vira uma "note", erro geral
devolve ([], [mensagem]). Nunca levanta exceção para o orquestrador.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from devrecap.core.logging_setup import get_logger
from devrecap.core.models import (
    CommitInfo,
    IssueInfo,
    PullRequestInfo,
    RepoActivity,
)

logger = get_logger(__name__)

_API_ROOT = "https://api.github.com"
_TIMEOUT = 30
_MAX_SLEEP = 120  # teto p/ não travar eternamente em rate limit


class GitHubClient:
    """Cliente fino da REST API do GitHub para a atividade de um dia."""

    def __init__(self, token: str, username: str, *, include_private: bool = True):
        """Cria a sessão HTTP com os headers obrigatórios da API v2022-11-28."""
        self.token = token
        self.username = username
        self.include_private = include_private
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #
    def get(self, url: str, params: Optional[dict[str, Any]] = None) -> requests.Response:
        """GET com tratamento de rate limit; repete uma vez após dormir.

        - 403 + X-RateLimit-Remaining=="0" -> dorme até X-RateLimit-Reset (teto 120s).
        - 403/429 com Retry-After -> dorme Retry-After (teto 120s).
        - demais erros -> raise_for_status.
        """
        for attempt in range(2):
            r = self.session.get(url, params=params, timeout=_TIMEOUT)
            if r.status_code in (403, 429) and attempt == 0:
                slept = self._handle_rate_limit(r)
                if slept:
                    continue
            r.raise_for_status()
            return r
        # se chegou aqui, a segunda tentativa não foi retornada acima
        r.raise_for_status()
        return r

    def _handle_rate_limit(self, r: requests.Response) -> bool:
        """Dorme conforme os headers de rate limit. Retorna True se dormiu (deve repetir)."""
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                wait = min(int(retry_after), _MAX_SLEEP)
            except ValueError:
                wait = _MAX_SLEEP
            logger.warning("Rate limit (Retry-After=%s): dormindo %ss", retry_after, wait)
            time.sleep(max(wait, 0))
            return True

        remaining = r.headers.get("X-RateLimit-Remaining")
        if r.status_code == 403 and remaining == "0":
            reset = r.headers.get("X-RateLimit-Reset")
            wait = _MAX_SLEEP
            if reset:
                try:
                    wait = int(reset) - int(time.time())
                except ValueError:
                    wait = _MAX_SLEEP
            wait = min(max(wait, 0), _MAX_SLEEP)
            logger.warning("Rate limit atingido: dormindo %ss até reset", wait)
            time.sleep(wait)
            return True

        return False

    def paginate(self, url: str, params: Optional[dict[str, Any]] = None):
        """Itera sobre todas as páginas seguindo o header Link 'next'."""
        next_url: Optional[str] = url
        next_params = params
        while next_url:
            r = self.get(next_url, params=next_params)
            yield r
            next_url = r.links.get("next", {}).get("url")
            next_params = None  # a URL de 'next' já carrega os params

    # ------------------------------------------------------------------ #
    # Fronteiras do dia (local -> UTC)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _day_bounds_utc(day: str) -> tuple[datetime, datetime, str, str]:
        """Calcula início/fim do dia local em UTC.

        Retorna (since_utc, until_utc, since_str, until_str) onde os strings
        estão no formato "%Y-%m-%dT%H:%M:%SZ" exigido pela API.
        """
        local_tz = datetime.now().astimezone().tzinfo
        d = datetime.strptime(day, "%Y-%m-%d").date()
        start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=local_tz)
        end_local = start_local + timedelta(days=1) - timedelta(seconds=1)
        # converte as fronteiras locais para UTC explícito
        since_utc = start_local.astimezone(_utc())
        until_utc = end_local.astimezone(_utc())
        since_str = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        until_str = until_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        return since_utc, until_utc, since_str, until_str

    # ------------------------------------------------------------------ #
    # Coleta principal
    # ------------------------------------------------------------------ #
    def day_activity(self, day: str) -> tuple[list[RepoActivity], list[str]]:
        """Retorna (repos, notes) com a atividade do GitHub no dia `day`.

        repos: RepoActivity com source="github", commits (com url), prs, issues.
        notes: avisos (rate limit, repo inacessível, falha geral).
        """
        notes: list[str] = []
        try:
            since_utc, until_utc, since_str, until_str = self._day_bounds_utc(day)
        except Exception as exc:  # noqa: BLE001 — data inválida não derruba o app
            logger.error("Dia inválido para GitHub (%r): %s", day, exc)
            return [], [f"GitHub: dia inválido '{day}': {exc}"]

        try:
            active_repos = self._list_active_repos(since_utc)
        except Exception as exc:  # noqa: BLE001 — falha geral de rede/HTTP
            logger.error("Falha ao listar repos do GitHub: %s", exc)
            return [], [f"GitHub: falha ao listar repositórios: {exc}"]

        # full_name -> RepoActivity (índice para casar PRs/issues depois)
        by_full_name: dict[str, RepoActivity] = {}
        order: list[str] = []

        for repo in active_repos:
            full_name = repo.get("full_name") or ""
            owner = (repo.get("owner") or {}).get("login") or ""
            name = repo.get("name") or full_name
            if not full_name or not owner:
                continue
            try:
                commits = self._fetch_commits(owner, name, full_name, since_str, until_str)
            except Exception as exc:  # noqa: BLE001 — erro por repo vira note
                logger.warning("Repo %s inacessível: %s", full_name, exc)
                notes.append(f"GitHub: repo '{full_name}' inacessível: {exc}")
                continue

            ra = RepoActivity(
                name=name,
                path=None,
                remote_url=repo.get("html_url"),
                source="github",
                commits=commits,
            )
            by_full_name[full_name] = ra
            order.append(full_name)

        # PRs e issues do dia
        try:
            self._collect_search(day, by_full_name, order)
        except Exception as exc:  # noqa: BLE001 — search falhou, não derruba commits
            logger.warning("Busca de PRs/issues falhou: %s", exc)
            notes.append(f"GitHub: busca de PRs/issues falhou: {exc}")

        repos = [by_full_name[fn] for fn in order]
        return repos, notes

    # ------------------------------------------------------------------ #
    def _list_active_repos(self, since_utc: datetime) -> list[dict[str, Any]]:
        """Lista repos ordenados por pushed_at desc, parando na fronteira do dia."""
        url = f"{_API_ROOT}/user/repos"
        params = {
            "affiliation": "owner,collaborator,organization_member",
            "sort": "pushed",
            "direction": "desc",
            "per_page": 100,
        }
        active: list[dict[str, Any]] = []
        stop = False
        for r in self.paginate(url, params):
            for repo in r.json():
                if not self.include_private and repo.get("private") is True:
                    continue
                pushed_at = repo.get("pushed_at")
                if pushed_at:
                    pushed_dt = _parse_iso(pushed_at)
                    if pushed_dt is not None and pushed_dt < since_utc:
                        # ordenado desc por pushed: a partir daqui todos são antigos
                        stop = True
                        break
                active.append(repo)
            if stop:
                break
        return active

    # ------------------------------------------------------------------ #
    def _fetch_commits(
        self,
        owner: str,
        name: str,
        full_name: str,
        since_str: str,
        until_str: str,
    ) -> list[CommitInfo]:
        """Busca os commits do usuário no repo dentro do intervalo do dia."""
        url = f"{_API_ROOT}/repos/{owner}/{name}/commits"
        params = {
            "author": self.username,
            "since": since_str,
            "until": until_str,
            "per_page": 100,
        }
        commits: list[CommitInfo] = []
        for r in self.paginate(url, params):
            payload = r.json()
            if not isinstance(payload, list):
                break
            for commit in payload:
                commit_data = commit.get("commit") or {}
                author_data = commit_data.get("author") or {}
                commits.append(
                    CommitInfo(
                        sha=commit.get("sha") or "",
                        message=commit_data.get("message") or "",
                        timestamp=author_data.get("date") or "",
                        repo=full_name,
                        source="github",
                        author=self.username,
                        url=commit.get("html_url"),
                    )
                )
        return commits

    # ------------------------------------------------------------------ #
    def _collect_search(
        self,
        day: str,
        by_full_name: dict[str, RepoActivity],
        order: list[str],
    ) -> None:
        """Roda as 3 buscas (PR criada, PR merged, issue criada) e anexa aos repos."""
        u = self.username
        # PRs abertas/criadas no dia
        for item in self._search(f"is:pr author:{u} created:{day}"):
            self._attach_pr(item, by_full_name, order, merged=False)
        # PRs merged no dia
        for item in self._search(f"is:pr author:{u} is:merged merged:{day}"):
            self._attach_pr(item, by_full_name, order, merged=True)
        # Issues criadas no dia
        for item in self._search(f"is:issue author:{u} created:{day}"):
            self._attach_issue(item, by_full_name, order)

    def _search(self, query: str) -> list[dict[str, Any]]:
        """Executa /search/issues paginado e devolve a lista de items."""
        url = f"{_API_ROOT}/search/issues"
        params = {"q": query, "per_page": 100}
        items: list[dict[str, Any]] = []
        for r in self.paginate(url, params):
            payload = r.json()
            items.extend(payload.get("items", []) if isinstance(payload, dict) else [])
        return items

    # ------------------------------------------------------------------ #
    def _ensure_repo(
        self,
        full_name: str,
        item: dict[str, Any],
        by_full_name: dict[str, RepoActivity],
        order: list[str],
    ) -> RepoActivity:
        """Pega o RepoActivity do full_name, criando um se ainda não existir."""
        ra = by_full_name.get(full_name)
        if ra is None:
            name = full_name.split("/")[-1] if "/" in full_name else full_name
            html_url = item.get("html_url") or ""
            repo_url = ""
            if "/issues/" in html_url:
                repo_url = html_url.split("/issues/")[0]
            elif "/pull/" in html_url:
                repo_url = html_url.split("/pull/")[0]
            ra = RepoActivity(
                name=name,
                path=None,
                remote_url=repo_url or None,
                source="github",
            )
            by_full_name[full_name] = ra
            order.append(full_name)
        return ra

    def _attach_pr(
        self,
        item: dict[str, Any],
        by_full_name: dict[str, RepoActivity],
        order: list[str],
        *,
        merged: bool,
    ) -> None:
        """Monta um PullRequestInfo a partir de um item de busca e anexa ao repo."""
        full_name = _repo_full_name(item)
        if not full_name:
            return
        ra = self._ensure_repo(full_name, item, by_full_name, order)
        number = item.get("number") or 0
        pr_data = item.get("pull_request") or {}
        merged_at = pr_data.get("merged_at") if merged else None
        if merged:
            state = "merged"
        else:
            state = item.get("state") or "open"
        # evita duplicar a mesma PR (a busca created pode trazer uma já listada como merged)
        for existing in ra.prs:
            if existing.number == number:
                if merged:
                    existing.state = "merged"
                    existing.merged_at = merged_at
                return
        ra.prs.append(
            PullRequestInfo(
                number=number,
                title=item.get("title") or "",
                repo=full_name,
                state=state,
                url=item.get("html_url") or "",
                created_at=item.get("created_at") or "",
                merged_at=merged_at,
            )
        )

    def _attach_issue(
        self,
        item: dict[str, Any],
        by_full_name: dict[str, RepoActivity],
        order: list[str],
    ) -> None:
        """Monta um IssueInfo a partir de um item de busca e anexa ao repo."""
        full_name = _repo_full_name(item)
        if not full_name:
            return
        ra = self._ensure_repo(full_name, item, by_full_name, order)
        number = item.get("number") or 0
        for existing in ra.issues:
            if existing.number == number:
                return
        ra.issues.append(
            IssueInfo(
                number=number,
                title=item.get("title") or "",
                repo=full_name,
                state=item.get("state") or "open",
                url=item.get("html_url") or "",
                created_at=item.get("created_at") or "",
                closed_at=item.get("closed_at"),
            )
        )


# --------------------------------------------------------------------------- #
# Helpers de módulo
# --------------------------------------------------------------------------- #
def _utc():
    """Timezone UTC (timezone-aware)."""
    from datetime import timezone

    return timezone.utc


def _parse_iso(value: str) -> Optional[datetime]:
    """Parseia um timestamp ISO 8601 do GitHub (ex.: '2024-01-02T03:04:05Z') como UTC-aware."""
    if not value:
        return None
    try:
        # GitHub usa 'Z'; fromisoformat aceita offset, então trocamos Z por +00:00
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _repo_full_name(item: dict[str, Any]) -> str:
    """Deriva o full_name (owner/repo) de um item de /search/issues via repository_url."""
    repo_url = item.get("repository_url") or ""
    marker = "/repos/"
    idx = repo_url.find(marker)
    if idx == -1:
        return ""
    return repo_url[idx + len(marker):]
