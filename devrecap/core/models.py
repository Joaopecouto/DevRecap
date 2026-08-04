"""Modelos de dados do DevRecap.

Fluxo dos dados:

    analyzers.git_local  ─┐
                          ├─►  aggregate  ─►  DayActivity  ─►  ai.gemini  ─►  AIInsights
    analyzers.github_api ─┘                                 └─►  media.*    ─►  [PhotoSuggestion]

    DailyReport = DayActivity + AIInsights + [PhotoSuggestion]

Todos os dataclasses têm `to_dict()` (via asdict) para persistência JSON.
A reconstrução a partir do disco é feita só quando necessário (storage.load_report),
usando os classmethods `from_dict`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Atividade bruta (coletada dos analisadores)
# --------------------------------------------------------------------------- #
@dataclass
class CommitInfo:
    sha: str
    message: str
    timestamp: str                       # ISO 8601, hora local
    repo: str                            # nome do repo / pasta
    source: str = "local"                # "local" | "github"
    author: str = ""
    branch: Optional[str] = None
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    files: list[str] = field(default_factory=list)
    url: Optional[str] = None            # link do commit no GitHub, se houver

    @property
    def short_sha(self) -> str:
        return self.sha[:8] if self.sha else ""

    @property
    def subject(self) -> str:
        """Primeira linha não-vazia da mensagem do commit."""
        parts = (self.message or "").strip().splitlines()
        return parts[0] if parts else ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommitInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PullRequestInfo:
    number: int
    title: str
    repo: str
    state: str                           # "open" | "closed" | "merged"
    url: str = ""
    created_at: str = ""
    merged_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PullRequestInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class IssueInfo:
    number: int
    title: str
    repo: str
    state: str                           # "open" | "closed"
    url: str = ""
    created_at: str = ""
    closed_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IssueInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RepoActivity:
    """Atividade de um único repositório no dia."""
    name: str
    path: Optional[str] = None           # caminho local (None se for só do GitHub)
    remote_url: Optional[str] = None
    source: str = "local"                # "local" | "github" | "both"
    commits: list[CommitInfo] = field(default_factory=list)
    branches_touched: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)   # ".py" -> nº de arquivos tocados
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    is_dirty: bool = False               # há mudanças não commitadas?
    uncommitted_files: list[str] = field(default_factory=list)
    prs: list[PullRequestInfo] = field(default_factory=list)
    issues: list[IssueInfo] = field(default_factory=list)
    error: Optional[str] = None          # mensagem se a análise falhou

    @property
    def commit_count(self) -> int:
        return len(self.commits)

    @property
    def has_activity(self) -> bool:
        return bool(self.commits or self.is_dirty or self.prs or self.issues)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RepoActivity":
        d = dict(d)
        d["commits"] = [CommitInfo.from_dict(c) for c in d.get("commits", [])]
        d["prs"] = [PullRequestInfo.from_dict(p) for p in d.get("prs", [])]
        d["issues"] = [IssueInfo.from_dict(i) for i in d.get("issues", [])]
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class DayActivity:
    """Tudo que aconteceu no dia, agregado de todas as fontes."""
    day: str                             # "YYYY-MM-DD"
    repos: list[RepoActivity] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # avisos da coleta (ex.: repo inacessível)

    # ---- agregados de conveniência ----
    @property
    def active_repos(self) -> list[RepoActivity]:
        return [r for r in self.repos if r.has_activity]

    @property
    def total_commits(self) -> int:
        return sum(r.commit_count for r in self.repos)

    @property
    def total_insertions(self) -> int:
        return sum(r.insertions for r in self.repos)

    @property
    def total_deletions(self) -> int:
        return sum(r.deletions for r in self.repos)

    @property
    def total_files_changed(self) -> int:
        return sum(r.files_changed for r in self.repos)

    @property
    def languages(self) -> dict[str, int]:
        agg: dict[str, int] = {}
        for r in self.repos:
            for ext, n in r.languages.items():
                agg[ext] = agg.get(ext, 0) + n
        return dict(sorted(agg.items(), key=lambda kv: kv[1], reverse=True))

    @property
    def has_activity(self) -> bool:
        return bool(self.active_repos)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "repos": [r.to_dict() for r in self.repos],
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DayActivity":
        return cls(
            day=d.get("day", ""),
            repos=[RepoActivity.from_dict(r) for r in d.get("repos", [])],
            notes=list(d.get("notes", [])),
        )


# --------------------------------------------------------------------------- #
# Saídas da IA
# --------------------------------------------------------------------------- #
@dataclass
class AIInsights:
    """Resultado do Gemini sobre o dia."""
    summary: str = ""                    # resumo do que foi feito
    technologies: list[str] = field(default_factory=list)
    progress: str = ""                   # avaliação de progresso
    value_added: str = ""                # como agregou ao projeto
    bullet_highlights: list[str] = field(default_factory=list)  # lista "o que foi feito"
    linkedin_post: str = ""              # texto pronto pro LinkedIn
    linkedin_hashtags: list[str] = field(default_factory=list)
    photo_keywords: list[str] = field(default_factory=list)     # p/ busca de foto + geração
    photo_prompt: str = ""               # prompt p/ gerar imagem (Gemini/Imagen)
    model: str = ""                      # modelo usado
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AIInsights":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PhotoSuggestion:
    """Uma sugestão de imagem para o post."""
    source: str                          # "project" | "stock" | "gemini"
    local_path: Optional[str] = None     # arquivo salvo no disco (se baixado/gerado)
    url: Optional[str] = None            # URL remota (banco de fotos)
    thumb_url: Optional[str] = None
    caption: str = ""                    # por que essa imagem
    attribution: str = ""                # crédito obrigatório (banco de fotos)
    attribution_url: str = ""            # link do crédito (página da foto)
    download_trigger: str = ""           # Unsplash: endpoint a chamar ao baixar (uso interno)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PhotoSuggestion":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# --------------------------------------------------------------------------- #
# Relatório final do dia
# --------------------------------------------------------------------------- #
@dataclass
class DailyReport:
    day: str                             # "YYYY-MM-DD"
    generated_at: str = ""               # ISO 8601
    activity: DayActivity = field(default_factory=lambda: DayActivity(day=""))
    insights: AIInsights = field(default_factory=AIInsights)
    photos: list[PhotoSuggestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "generated_at": self.generated_at,
            "activity": self.activity.to_dict(),
            "insights": self.insights.to_dict(),
            "photos": [p.to_dict() for p in self.photos],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DailyReport":
        return cls(
            day=d.get("day", ""),
            generated_at=d.get("generated_at", ""),
            activity=DayActivity.from_dict(d.get("activity", {})),
            insights=AIInsights.from_dict(d.get("insights", {})),
            photos=[PhotoSuggestion.from_dict(p) for p in d.get("photos", [])],
        )


def today_str() -> str:
    """Data de hoje no formato YYYY-MM-DD (sem usar Date.now em scripts de workflow)."""
    return date.today().isoformat()
