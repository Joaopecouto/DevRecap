"""Busca de imagens dentro dos repositórios locais para sugerir como foto do post.

Varre os caminhos locais (`RepoActivity.path`) procurando imagens, pontua cada
candidata por heurística de nome/pasta, match com keywords e data de modificação,
e devolve as melhores como `PhotoSuggestion(source="project")`.

Só usa stdlib (sem PIL): o "tamanho" e o "mtime" vêm de `os.stat`.
"""
from __future__ import annotations

import os
from pathlib import Path

from devrecap.core.models import PhotoSuggestion, RepoActivity
from devrecap.core.logging_setup import get_logger

logger = get_logger(__name__)

# Extensões de imagem consideradas.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

# Diretórios que nunca devem ser varridos (ruído / build / deps).
_IGNORED_DIRS = {
    "node_modules", ".git", "dist", "build", ".venv", "venv",
    "__pycache__", ".next", "out", "coverage",
}

# Termos no nome/caminho que indicam imagem "de vitrine" (peso por termo).
_RELEVANT_TERMS = (
    "screenshot", "screen", "og", "banner", "cover", "hero", "demo",
    "preview", "mockup", "dashboard", "app", "logo",
)

# Pastas que costumam guardar imagens "de produto"/documentação (peso por pasta).
_RELEVANT_DIRS = (
    "docs", "assets", "public", "screenshots", "images", "img", "media",
)

# Ignorar arquivos menores que isto (ícones), exceto .svg.
_MIN_SIZE_BYTES = 5 * 1024

# Máximo de IMAGENS coletadas por repo (suficiente p/ ranquear).
_MAX_IMAGES_PER_REPO = 300
# Teto duro de arquivos percorridos, p/ não travar em monorepos gigantes.
_WALK_CAP = 100_000

# Pesos das heurísticas.
_W_TERM = 3.0       # por termo relevante encontrado no caminho
_W_DIR = 2.0        # por pasta relevante no caminho
_W_KEYWORD = 4.0    # por keyword (do usuário/IA) que casa no caminho
_W_RECENT_MAX = 5.0  # peso máximo dado ao arquivo mais recente


def _score_path(rel_lower: str, keywords_lower: list[str]) -> float:
    """Pontua um caminho (já em minúsculas) por termos, pastas e keywords."""
    score = 0.0
    for term in _RELEVANT_TERMS:
        if term in rel_lower:
            score += _W_TERM
    parts = rel_lower.replace("\\", "/").split("/")
    dir_parts = set(parts[:-1])  # tudo menos o nome do arquivo
    for d in _RELEVANT_DIRS:
        if d in dir_parts:
            score += _W_DIR
    for kw in keywords_lower:
        if kw and kw in rel_lower:
            score += _W_KEYWORD
    return score


def _iter_images(root: Path, max_images: int) -> list[Path]:
    """Lista até `max_images` imagens dentro de `root`, pulando dirs ignorados.

    Conta IMAGENS para o limite (não arquivos quaisquer), p/ não parar antes de
    achar imagens em repos com muito código; ainda assim aborta após `_WALK_CAP`
    arquivos percorridos como salvaguarda contra monorepos gigantes."""
    found: list[Path] = []
    walked = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # poda in-place dos diretórios ignorados (não desce neles)
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
        for fname in filenames:
            walked += 1
            if walked > _WALK_CAP:
                logger.info("Varredura abortada após %s arquivos: %s", _WALK_CAP, root)
                return found
            ext = os.path.splitext(fname)[1].lower()
            if ext in _IMAGE_EXTS:
                found.append(Path(dirpath) / fname)
                if len(found) >= max_images:
                    return found
    return found


def find_project_images(
    repos: list[RepoActivity],
    keywords: list[str] | None = None,
    limit: int = 4,
) -> list[PhotoSuggestion]:
    """Varre os paths locais dos repos por imagens e devolve as melhores.

    Pontua por heurística de nome/pasta, match com `keywords` e mtime recente;
    ignora ícones (<5KB, exceto .svg) e diretórios de build/deps. Deduplica por
    caminho e retorna até `limit` `PhotoSuggestion(source="project")`.
    """
    keywords_lower = [k.lower() for k in (keywords or []) if k]

    # candidatos: (path_resolvido, score_base, mtime, repo_name)
    candidates: list[tuple[str, float, float, str]] = []
    seen_paths: set[str] = set()

    for repo in repos:
        try:
            path = getattr(repo, "path", None)
            if not path:
                continue
            root = Path(path)
            if not root.exists() or not root.is_dir():
                continue

            repo_name = repo.name or root.name
            root_str = str(root)

            for img in _iter_images(root, _MAX_IMAGES_PER_REPO):
                try:
                    resolved = str(img.resolve())
                    if resolved in seen_paths:
                        continue

                    st = os.stat(img)
                    ext = img.suffix.lower()
                    # ignora ícones pequenos, exceto SVG
                    if ext != ".svg" and st.st_size < _MIN_SIZE_BYTES:
                        continue

                    # caminho relativo (cai no absoluto se der erro de drive)
                    try:
                        rel = os.path.relpath(resolved, root_str)
                    except ValueError:
                        rel = resolved
                    rel_lower = rel.lower()

                    score = _score_path(rel_lower, keywords_lower)
                    seen_paths.add(resolved)
                    candidates.append((resolved, score, st.st_mtime, repo_name))
                except OSError as exc:
                    logger.info("Falha ao inspecionar imagem %s: %s", img, exc)
                    continue
        except Exception as exc:  # nunca deixa vazar p/ o orquestrador
            logger.warning(
                "Erro ao varrer imagens do repo %r: %s",
                getattr(repo, "name", "?"), exc,
            )
            continue

    if not candidates:
        return []

    # peso por recência: normaliza mtime no intervalo [min, max] -> [0, _W_RECENT_MAX]
    mtimes = [c[2] for c in candidates]
    m_min, m_max = min(mtimes), max(mtimes)
    span = (m_max - m_min) or 1.0

    scored: list[tuple[float, str, str]] = []
    for resolved, base, mtime, repo_name in candidates:
        recency = ((mtime - m_min) / span) * _W_RECENT_MAX
        total = base + recency
        scored.append((total, resolved, repo_name))

    # ordena por score desc; desempate por caminho p/ resultado estável
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    suggestions: list[PhotoSuggestion] = []
    for _total, resolved, repo_name in scored[: max(0, limit)]:
        fname = os.path.basename(resolved)
        caption = f"{fname} ({repo_name})" if repo_name else fname
        suggestions.append(
            PhotoSuggestion(
                source="project",
                local_path=resolved,
                caption=caption,
            )
        )
    return suggestions
