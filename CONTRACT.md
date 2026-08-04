# DevRecap — Contrato de módulos (interface pública obrigatória)

Os módulos abaixo DEVEM expor exatamente estas assinaturas. Os tipos vêm de
`devrecap.core.models` e `devrecap.core.config`. Não mudar nomes/assinaturas.

Imports disponíveis:
```python
from devrecap.core.models import (
    CommitInfo, PullRequestInfo, IssueInfo, RepoActivity, DayActivity,
    AIInsights, PhotoSuggestion, DailyReport,
)
from devrecap.core.config import Settings
from devrecap.core.logging_setup import get_logger
from devrecap.core.paths import media_dir
```

Regras gerais:
- Nunca deixar exceção vazar para o orquestrador: capturar, logar via `get_logger(__name__)`,
  e devolver objeto parcial com campo `error`/`notes` preenchido quando fizer sentido.
- Sem prints. Usar o logger.
- Datas no formato `"YYYY-MM-DD"` (string `day`). Fronteiras de dia em horário LOCAL,
  convertidas p/ UTC quando a API exigir.

---

## analyzers/git_local.py
```python
def find_git_repos(folder: str, max_depth: int = 3) -> list[str]:
    """Caminhos-raiz de repositórios git dentro de `folder` (até max_depth níveis).
    Um repo é uma pasta que contém `.git`. Não descer dentro de um repo já encontrado."""

def analyze_repo(repo_path: str, day: str, author_emails: list[str]) -> RepoActivity:
    """Commits do dia `day` no repo. Se author_emails != [], filtrar por autor (email).
    Usar o git CLI (subprocess). Preencher commits (sha, message, timestamp ISO local,
    files, insertions, deletions, branch), languages (extensão->nº arquivos tocados),
    files_changed/insertions/deletions agregados, is_dirty + uncommitted_files
    (via `git status --porcelain`). source="local". Em erro, RepoActivity(name=..., error=...)."""

def scan_folders(folders: list[str], day: str, *, scan_subfolders: bool = True,
                 max_depth: int = 3, author_emails: list[str] | None = None) -> list[RepoActivity]:
    """Para cada pasta: se scan_subfolders, find_git_repos; senão tratar a própria pasta como repo.
    Retornar a lista de RepoActivity (incluir só os que têm atividade OU is_dirty)."""
```
Notas git CLI:
- Janela do dia: `since = day 00:00:00 local`, `until = day 23:59:59 local`.
- Commits: `git -C <repo> log --since=<iso> --until=<iso> --pretty=format:%H%x1f%an%x1f%ae%x1f%aI%x1f%s --no-merges`
  (separador 0x1f). Filtrar por email se author_emails.
- Numstat por commit: `git -C <repo> show --numstat --format= <sha>` -> linhas `add\tdel\tpath`.
- Branch atual: `git -C <repo> rev-parse --abbrev-ref HEAD`.
- Encoding: decodificar como utf-8 com errors="replace".

---

## analyzers/github_api.py
```python
class GitHubClient:
    def __init__(self, token: str, username: str, *, include_private: bool = True): ...
    def day_activity(self, day: str) -> tuple[list[RepoActivity], list[str]]:
        """Retorna (repos, notes). repos: RepoActivity com source="github",
        commits (com url), prs, issues. notes: avisos (rate limit, repo inacessível)."""
```
Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
Estratégia (verificada):
1. `GET /user/repos?affiliation=owner,collaborator,organization_member&sort=pushed&direction=desc&per_page=100`,
   parar de paginar quando `pushed_at` < início-do-dia (UTC). Respeitar include_private (visibility).
2. Por repo ativo: `GET /repos/{owner}/{repo}/commits?author=<username>&since=<iso>&until=<iso>&per_page=100`.
   Montar CommitInfo (sha, message=`commit.message`, timestamp=`commit.author.date`, url=`html_url`).
3. PRs/issues: `GET /search/issues?q=...`:
   - PRs abertas: `is:pr author:{u} created:{day}`
   - PRs merged: `is:pr author:{u} is:merged merged:{day}`
   - Issues abertas: `is:issue author:{u} created:{day}`
   Anexar ao RepoActivity correspondente (derivar repo de `repository_url`); criar repo se preciso.
Rate limit: em 403 com `X-RateLimit-Remaining: 0`, dormir até `X-RateLimit-Reset`. Search = 30/min.
`requests.Session` com timeout=30. Paginação via `r.links['next']['url']`.

---

## analyzers/aggregate.py
```python
def build_day_activity(day: str, local_repos: list[RepoActivity],
                       github_repos: list[RepoActivity], notes: list[str] | None = None) -> DayActivity:
    """Mesclar repos locais e do GitHub. Casar por remote_url (normalizado, sem .git/sufixo)
    ou por nome. Ao casar, unir commits (dedup por sha de 7+ chars), unir prs/issues,
    somar stats, source="both". Retornar DayActivity(day, repos, notes)."""
```

---

## ai/prompts.py
```python
SYSTEM_INSTRUCTION: str   # persona: assistente que resume o dia de dev do João e escreve posts de LinkedIn em pt-BR, tom autêntico

def build_user_prompt(activity: DayActivity, *, language: str = "pt-BR",
                      tone: str = "", style_reference: str | None = None) -> str:
    """Monta o prompt com os dados do dia (repos, commits, stats, linguagens) e pede
    um JSON com as chaves de AIInsights. Incluir style_reference (texto) se fornecido."""

RESPONSE_KEYS: list[str]   # ["summary","technologies","progress","value_added","bullet_highlights",
                           #  "linkedin_post","linkedin_hashtags","photo_keywords","photo_prompt"]
```
O prompt deve INSTRUIR a responder SOMENTE JSON válido com exatamente essas chaves.
`technologies`, `bullet_highlights`, `linkedin_hashtags`, `photo_keywords` = listas de strings;
o resto = strings.

---

## ai/gemini.py  (SDK: `from google import genai`, pacote `google-genai`)
```python
class GeminiClient:
    def __init__(self, api_key: str, text_model: str, image_model: str): ...
    def generate_insights(self, activity: DayActivity, *, language: str = "pt-BR",
                          tone: str = "", style_reference: str | None = None) -> AIInsights: ...
    def generate_image(self, prompt: str, out_path: str) -> str | None:
        """Gera imagem e salva em out_path (PNG). Retorna o caminho ou None em falha."""
```
Texto (verificado):
```python
from google import genai
from google.genai import types, errors
client = genai.Client(api_key=key)
resp = client.models.generate_content(
    model=text_model, contents=user_prompt,
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
    ),
)
data = json.loads(resp.text)   # parse defensivo: se vier cercado por ```json, extrair
```
Preencher AIInsights(model=text_model). Em `errors.APIError` (ou qualquer Exception),
retornar AIInsights(error=str(e)) — nunca levantar.
Imagem (verificado — Nano Banana):
```python
resp = client.models.generate_content(
    model=image_model, contents=[prompt],
    config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
)
for part in resp.parts:
    if getattr(part, "inline_data", None) is not None:
        part.as_image().save(out_path)   # PIL; fallback: Image.open(BytesIO(part.inline_data.data))
        return out_path
return None
```

---

## media/project_photos.py
```python
def find_project_images(repos: list[RepoActivity], keywords: list[str] | None = None,
                        limit: int = 4) -> list[PhotoSuggestion]:
    """Varrer os paths locais dos repos por imagens (.png/.jpg/.jpeg/.webp/.gif/.svg).
    Priorizar nomes/pastas relevantes (screenshot, og, banner, cover, hero, demo, preview,
    logo, docs/, assets/, public/, screenshots/, images/). Pontuar por match com keywords,
    heurística de nome e mtime recente. Ignorar node_modules/.git/dist/build/venv e ícones <5KB.
    Retornar PhotoSuggestion(source="project", local_path=..., caption=...)."""
```

---

## media/stock.py
```python
def search_stock(provider: str, api_key: str, keywords: list[str], *, count: int = 3,
                 orientation: str = "landscape", app_name: str = "DevRecap") -> list[PhotoSuggestion]:
    """provider in {"pexels","unsplash"}. Buscar pela junção das keywords.
    Retornar PhotoSuggestion(source="stock", url=<preview>, thumb_url=..., caption=keyword,
    attribution="Photo by X on <Provider>", attribution_url=<source page>)."""

def download_photo(suggestion: PhotoSuggestion, out_dir: str) -> str | None:
    """Baixar a imagem (url) p/ out_dir, preencher local_path e retornar o caminho.
    Para Unsplash, disparar o download_location se presente (em attribution_url? guardar em thumb_url)."""
```
Pexels (verificado): `GET https://api.pexels.com/v1/search`, header `Authorization: <KEY>` (sem Bearer),
params `query,per_page(<=80),orientation`. Resp `photos[].src.large/.original`, `.photographer`,
`.photographer_url`, `.url`.
Unsplash (verificado): `GET https://api.unsplash.com/search/photos`, header `Authorization: Client-ID <KEY>`,
params `query,per_page,orientation(squarish)`. Resp `results[].urls.regular/.full`, `.user.name`,
`.user.links.html`, `.links.html`, `.links.download_location`. UTM `?utm_source=DevRecap&utm_medium=referral`.
Em erro: logar e retornar [].

---

## media/gemini_image.py
```python
def suggest_generated_image(gemini_client, prompt: str, out_dir: str) -> PhotoSuggestion | None:
    """Usar gemini_client.generate_image(prompt, <out_dir>/gemini_<...>.png).
    Retornar PhotoSuggestion(source="gemini", local_path=..., caption="Imagem gerada por IA")
    ou None se falhar/desligado."""
```

---

## scheduler/daily.py
```python
class DailyScheduler:
    def __init__(self, callback, *, time_str: str = "18:00",
                 run_on_weekends: bool = False): ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def reschedule(self, time_str: str, run_on_weekends: bool) -> None: ...
    def next_run_time(self): ...   # datetime | None
```
APScheduler `BackgroundScheduler` (timezone local) + `CronTrigger(hour, minute, day_of_week=...)`.
Se run_on_weekends False -> `day_of_week="mon-fri"`. `callback` é chamado sem args.
`time_str` "HH:MM"; validar e cair em 18:00 se inválido. `replace_existing=True`, id="daily_recap".
