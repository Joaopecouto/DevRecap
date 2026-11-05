<p align="center"><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/projects/v4/devrecap.png" width="96" alt="Ícone do projeto"></p>

<h1 align="center">DevRecap</h1>

<p align="center">App de bandeja do Windows que resume o seu dia de código e prepara um post a partir disso.<br><sub><i>Windows tray app that summarizes your coding day and drafts a post from it.</i></sub></p>

<p align="center">
  <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/python.svg" height="18" align="absmiddle" alt=""> Python</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/pyinstaller.svg" height="18" align="absmiddle" alt=""> PyInstaller</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/apscheduler.svg" height="18" align="absmiddle" alt=""> APScheduler</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/webview2.svg" height="18" align="absmiddle" alt=""> WebView2</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/claude.svg" height="18" align="absmiddle" alt=""> Claude Code</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/v2/github.svg" height="18" align="absmiddle" alt=""> GitHub API</kbd>
</p>

<p align="center"><a href="#portugu%C3%AAs"><b>Português</b></a> &nbsp;|&nbsp; <a href="#english"><b>English</b></a></p>

## Português

<table>
<tr>
<td align="center" width="33%"><b>18:00</b><br><sub>roda todo dia</sub></td><td align="center" width="33%"><b>3 saídas</b><br><sub>lista, resumo e post</sub></td><td align="center" width="33%"><b>Windows</b><br><sub>10 e 11, sem admin</sub></td>
</tr>
</table>

### Visão geral

O DevRecap é um app de bandeja do Windows, escrito em Python, que fecha o seu dia de desenvolvimento sozinho. Todo dia às 18:00 ele lê os commits das suas pastas locais pelo git e a atividade do GitHub pela API REST, junta as duas fontes e produz um relatório: a lista do que foi feito, um resumo com tecnologias e progresso, uma ideia de post para o LinkedIn e sugestões de foto. A interface é HTML e CSS dentro de uma janela WebView2, com tema claro e escuro. Os dados ficam em `%APPDATA%\DevRecap`, o autostart não pede administrador e o app vira um `.exe` com PyInstaller.

### Como funciona

1. O agendador acorda no horário configurado (padrão 18:00, só em dias úteis) ou você pede "Gerar recap agora" no menu da bandeja.
2. O coletor local varre as pastas marcadas atrás de repositórios e lê, com o git CLI, os commits do dia, as linhas alteradas, os arquivos e as mudanças não commitadas.
3. O cliente do GitHub lista os repositórios com push recente, busca seus commits do dia e as PRs e issues abertas ou mescladas.
4. O agregador casa os repositórios locais com os do GitHub e produz uma única atividade do dia.
5. O pipeline grava um relatório preliminar em disco e chama a análise de IA, que lê esse relatório e devolve resumo, tecnologias, progresso, destaques, post, hashtags e palavras-chave de foto.
6. O módulo de mídia procura imagens nos próprios projetos e, se houver chave, no Pexels ou no Unsplash.
7. O relatório final é salvo em JSON e Markdown, a janela mostra o resultado e uma notificação avisa que terminou.

```mermaid
flowchart TD
    S[Agendador 18h] --> P[Pipeline]
    M[Menu da bandeja] --> P
    P --> L[Git local]
    P --> G[GitHub REST]
    L --> A[Agregador]
    G --> A
    A --> R[Relatorio preliminar]
    R --> I[Analise de IA]
    I --> F[Fotos]
    F --> O[Relatorio final]
    O --> U[Janela WebView2]
```

### Funcionalidades em detalhe

#### Coleta local com git

Cada pasta marcada é varrida até uma profundidade configurável (padrão 3), sem descer dentro de um repositório já encontrado e pulando `node_modules`, `dist`, `build`, ambientes virtuais e similares.

<p align="center"><img src="./assets/screens/config-pastas.png" alt="Configurações: pastas varridas, profundidade da busca e filtro por e-mail de autor." width="92%"><br><sub>Configurações: pastas varridas, profundidade da busca e filtro por e-mail de autor.</sub></p>

- Roda `git log --no-merges` entre 00:00 e 23:59 do dia local, usando a data de commit para casar com o filtro de janela.
- Pede o corpo completo da mensagem (`%B`), porque é nele que vive o raciocínio do commit. Como o corpo tem várias linhas, os registros são separados por caracteres de controle em vez de quebras de linha.
- Para cada commit, `git show --numstat` devolve linhas somadas e removidas, arquivos tocados e a contagem por extensão, que vira o mapa de linguagens.
- `git status --porcelain` marca trabalho não commitado. Um repositório entra no relatório se tiver commits ou mudanças pendentes.
- Dá para filtrar commits por e-mail de autor. As chamadas ao git saem sem abrir janela de console, detalhe que importa num app de bandeja.

#### Atividade do GitHub

- Lista `/user/repos` ordenado por `pushed_at` e para de paginar quando passa da fronteira do dia, calculada em horário local e convertida para UTC.
- Por repositório ativo, busca commits do seu usuário no intervalo do dia, com o link de cada um.
- Três buscas em `/search/issues` trazem PRs criadas, PRs mescladas e issues criadas no dia, anexadas ao repositório certo.
- Em rate limit, respeita `Retry-After` ou `X-RateLimit-Reset` e dorme no máximo 120 segundos antes de tentar de novo. Falhas por repositório viram avisos no relatório, sem derrubar a coleta.

<p align="center"><img src="./assets/screens/config-github.png" alt="Configurações do GitHub: usuário, token e opção de incluir repositórios privados." width="92%"><br><sub>Configurações do GitHub: usuário, token e opção de incluir repositórios privados.</sub></p>

#### Agregação

O agregador casa cada repositório local com o seu par do GitHub pelo `remote_url` normalizado (sem esquema, sem `.git`) e, na falta dele, pelo nome. No par, une commits sem duplicar por SHA, une PRs e issues, soma estatísticas e marca a origem como "both". O estado de árvore suja vem do local.

<p align="center"><img src="./assets/screens/por-repositorio.png" alt="Detalhe por repositório: commits, PR e issue unidos, com linhas somadas e removidas." width="92%"><br><sub>Detalhe por repositório: commits, PR e issue unidos, com linhas somadas e removidas.</sub></p>

#### Análise de IA e post

Esta etapa lê o relatório preliminar e devolve um objeto com resumo, tecnologias, progresso, valor agregado, destaques, post, hashtags e palavras-chave de foto.

<p align="center"><img src="./assets/screens/post-e-foto.png" alt="Post de LinkedIn gerado, com hashtags, ao lado das fotos sugeridas." width="92%"><br><sub>Post de LinkedIn gerado, com hashtags, ao lado das fotos sugeridas.</sub></p>

- Em vez de uma chamada de API, a etapa executa o Claude Code em modo headless (`claude -p`), com o prompt enviado por stdin. O agente consegue ler arquivos e abrir commits, coisa que um prompt único não comporta.
- Roda com `acceptEdits` e diretórios extras liberados por `--add-dir`, o escopo mínimo para gravar o resultado sem alguém para aprovar.
- Tem teto de 15 minutos, e uma falha nunca derruba o recap: o relatório segue válido com a atividade do git e o erro aparece na tela.
- Você escolhe o idioma, o tom e o tamanho do post (curto, médio ou longo), e pode apontar um arquivo de referência de estilo.

#### Mídia e fotos

- Fotos do projeto: varre os repositórios locais atrás de imagens, ignora pastas de build e dependências e arquivos abaixo de 5 KB (exceto SVG). Pontua por nome (`screenshot`, `banner`, `hero`, `demo`), por pasta (`docs`, `assets`, `public`), por casamento com as palavras-chave e por recência.
- Banco de fotos: Pexels ou Unsplash, com busca pelas palavras-chave, download local e a atribuição ao fotógrafo guardada junto. No Unsplash, o endpoint de download é acionado como a diretriz pede.
- A ordem de preferência é a imagem real do projeto, depois o banco de imagens.

<p align="center"><img src="./assets/screens/fotos-sugeridas.png" alt="Fotos sugeridas, com a origem de cada uma (projeto ou banco de imagens)." width="92%"><br><sub>Fotos sugeridas, com a origem de cada uma (projeto ou banco de imagens).</sub></p>

#### Janela, bandeja e agendador

- A janela tem três áreas: Hoje (post e foto lado a lado, resumo, números e detalhe por repositório), Histórico e Configurações.
- Em Hoje, os repositórios do dia viram chips: marque os que entram, escolha o tamanho do texto e regenere sem recoletar commits.
- Fechar a janela só a esconde. O menu da bandeja abre o app, gera o recap, abre as configurações, liga o autostart e encerra.
- O tema claro ou escuro lembra a sua escolha e, sem ela, segue o sistema.

<p align="center"><img src="./assets/screens/config-agendamento.png" alt="Configurações de agendamento: horário diário, fins de semana, início com o Windows e notificações." width="92%"><br><sub>Configurações de agendamento: horário diário, fins de semana, início com o Windows e notificações.</sub></p>

<p align="center"><img src="./assets/screens/hoje-escuro.png" alt="Aba Hoje no tema escuro: foco por repositório, post e foto lado a lado, resumo." width="92%"><br><sub>Aba Hoje no tema escuro: foco por repositório, post e foto lado a lado, resumo.</sub></p>

### Arquitetura

- `app.py`: o controlador. Junta janela, bandeja e agendador, e expõe a API ao JavaScript.
- `pipeline.py`: o fluxo coleta, agregação, IA, fotos e gravação.
- `analyzers/`: git local, cliente do GitHub e agregador.
- `ai/`: a ponte com o Claude Code.
- `media/`: fotos do projeto e do banco de imagens.
- `scheduler/`: o agendamento diário com APScheduler.
- `ui/`: ícone da bandeja, ponte do webview e frontend em `web/`.
- `core/`: modelos, configuração, caminhos, armazenamento, autostart e área de transferência.

```mermaid
flowchart LR
    T[pystray] --> C[AppController]
    W[pywebview] <--> C
    D[APScheduler] --> C
    C --> PL[pipeline]
    PL --> AN[analyzers]
    PL --> AI[ai]
    PL --> MD[media]
    PL --> ST[core storage]
    ST --> DISK[(APPDATA DevRecap)]
```

Onde ficam os dados, tudo em `%APPDATA%\DevRecap`: `config.json` com ajustes e chaves, `reports/AAAA-MM-DD/` com `report.json` (fonte da verdade) e `report.md`, `media/` com imagens baixadas e `logs/devrecap.log`.

### Decisões de engenharia

1. **Gravar o relatório antes da IA.** A análise lê o `report.json` do disco, então o pipeline salva um preliminar com a atividade do git e só depois chama a IA. Se a IA falhar, o recap continua válido.
2. **Nada vaza para o orquestrador.** Cada módulo captura a exceção, loga e devolve um objeto parcial com campo de erro. Um repositório quebrado vira aviso, não pane.
3. **Agente em vez de prompt único.** Commits com corpo completo e diffs não cabem bem num prompt só. Rodar o Claude Code headless troca velocidade (minutos) por contexto, e por isso o trabalho roda em segundo plano.
4. **Threads separadas.** O loop da janela ocupa a thread principal, a bandeja roda numa thread daemon e o pipeline numa thread própria, com resultado empurrado ao JavaScript.
5. **Autostart por registro, sem admin.** A chave `HKCU\...\Run` funciona tanto pelo código-fonte quanto pelo `.exe` congelado.
6. **Autoteste do executável.** `--selftest` valida imports, ícone, agendador e pipeline com um `APPDATA` isolado. Num app `--windowed` uma falha de import seria silenciosa.

### Privacidade

- Config, relatórios, imagens e logs ficam na sua máquina, em `%APPDATA%\DevRecap`. O token do GitHub e a chave do banco de fotos ficam em texto no `config.json`, fora do repositório e listado no `.gitignore`.
- Para o GitHub saem seu usuário e o token, nas chamadas da API. Para o Pexels ou o Unsplash saem a chave e as palavras-chave de busca.
- A leitura dos commits locais usa o git instalado. O conteúdo do relatório é entregue ao CLI do Claude Code, instalado na máquina, que o processa conforme o funcionamento dele.
- Projetos sensíveis ficam de fora se não estiverem nas pastas monitoradas.

### Limites conhecidos

- Só Windows 10 ou 11, com Python 3.11 ou mais novo, WebView2 e git no PATH.
- A análise depende do CLI do Claude Code e de um arquivo de instrução do projeto; sem eles o app lista a atividade, mas não gera resumo nem post.
- A análise leva minutos e tem teto de 15 minutos.
- No Unsplash, o modo demo permite 50 requisições por hora. O Pexels dá a chave na hora.
- Repositórios privados no GitHub exigem token com escopo `repo` (ou Contents: Read, no fine-grained).
- Pexels e Unsplash exigem crédito ao fotógrafo; o post deve incluí-lo ao usar foto de banco.
- O README sugere excluir a pasta `.venv` da sincronização do OneDrive.

### Requisitos e instalação

- Windows 10 ou 11 com WebView2 Runtime, Python 3.11 ou superior e `git` no PATH.
- Claude Code instalado: a análise do dia roda pelo CLI, em modo headless.

```powershell
.\setup.ps1                          # cria o .venv e instala as dependências
.\.venv\Scripts\pythonw.exe run.py   # roda sem console
.\build.ps1                          # opcional: gera dist\DevRecap.exe com PyInstaller
```

Na primeira execução, a janela de Configurações abre sozinha.

## English

<table>
<tr>
<td align="center" width="33%"><b>6:00 PM</b><br><sub>runs every day</sub></td><td align="center" width="33%"><b>3 outputs</b><br><sub>list, summary and post</sub></td><td align="center" width="33%"><b>Windows</b><br><sub>10 and 11, no admin</sub></td>
</tr>
</table>

### Overview

DevRecap is a Windows tray app written in Python that wraps up your development day on its own. Every day at 18:00 it reads the commits from your local folders through git and your GitHub activity through the REST API, merges both sources and produces a report: the list of what was done, a summary with technologies and progress, a LinkedIn post idea and photo suggestions. The interface is HTML and CSS inside a WebView2 window, with light and dark themes. Data lives in `%APPDATA%\DevRecap`, autostart needs no administrator rights and the app ships as an `.exe` built with PyInstaller.

### How it works

1. The scheduler wakes at the configured time (default 18:00, weekdays only) or you pick "Generate recap now" from the tray menu.
2. The local collector scans the marked folders for repositories and reads, with the git CLI, the day's commits, changed lines, files and uncommitted changes.
3. The GitHub client lists repositories with a recent push, fetches your commits of the day and the PRs and issues opened or merged.
4. The aggregator matches local repositories with GitHub ones and produces a single activity for the day.
5. The pipeline writes a preliminary report to disk and calls the AI analysis, which reads that report and returns summary, technologies, progress, highlights, post, hashtags and photo keywords.
6. The media module looks for images in your own projects and, if you have a key, in Pexels or Unsplash.
7. The final report is saved as JSON and Markdown, the window shows the result and a notification says it finished.

```mermaid
flowchart TD
    S[Scheduler 6pm] --> P[Pipeline]
    M[Tray menu] --> P
    P --> L[Local git]
    P --> G[GitHub REST]
    L --> A[Aggregator]
    G --> A
    A --> R[Preliminary report]
    R --> I[AI analysis]
    I --> F[Photos]
    F --> O[Final report]
    O --> U[WebView2 window]
```

### Features in detail

#### Local collection with git

Each marked folder is scanned down to a configurable depth (default 3), never descending into a repository already found and skipping `node_modules`, `dist`, `build`, virtual environments and similar.

<p align="center"><img src="./assets/screens/config-pastas.png" alt="Settings: scanned folders, search depth and author email filter." width="92%"><br><sub>Settings: scanned folders, search depth and author email filter.</sub></p>

- It runs `git log --no-merges` between 00:00 and 23:59 of the local day, using the commit date so it matches the window filter.
- It asks for the full message body (`%B`), because that is where the reasoning of a commit lives. Since the body spans several lines, records are separated by control characters instead of line breaks.
- For each commit, `git show --numstat` returns added and removed lines, touched files and the count per extension, which becomes the language map.
- `git status --porcelain` flags uncommitted work. A repository enters the report if it has commits or pending changes.
- Commits can be filtered by author e-mail. Git calls run without opening a console window, a detail that matters in a tray app.

#### GitHub activity

- It lists `/user/repos` sorted by `pushed_at` and stops paginating once it passes the day boundary, computed in local time and converted to UTC.
- For each active repository, it fetches your commits in the day's interval, with the link of each one.
- Three `/search/issues` queries bring PRs created, PRs merged and issues created that day, attached to the right repository.
- On a rate limit, it honors `Retry-After` or `X-RateLimit-Reset` and sleeps at most 120 seconds before trying again. Per-repository failures become warnings in the report without stopping the collection.

<p align="center"><img src="./assets/screens/config-github.png" alt="GitHub settings: username, token and the option to include private repositories." width="92%"><br><sub>GitHub settings: username, token and the option to include private repositories.</sub></p>

#### Aggregation

The aggregator matches each local repository with its GitHub counterpart by normalized `remote_url` (no scheme, no `.git`) and, failing that, by name. For a pair it merges commits without duplicating by SHA, merges PRs and issues, sums the stats and marks the source as "both". The dirty-tree state comes from the local side.

<p align="center"><img src="./assets/screens/por-repositorio.png" alt="Per-repository detail: commits, PR and issue merged, with lines added and removed." width="92%"><br><sub>Per-repository detail: commits, PR and issue merged, with lines added and removed.</sub></p>

#### AI analysis and post

This step reads the preliminary report and returns an object with summary, technologies, progress, added value, highlights, post, hashtags and photo keywords.

<p align="center"><img src="./assets/screens/post-e-foto.png" alt="Generated LinkedIn post with hashtags, next to the suggested photos." width="92%"><br><sub>Generated LinkedIn post with hashtags, next to the suggested photos.</sub></p>

- Instead of an API call, the step runs Claude Code in headless mode (`claude -p`), with the prompt sent over stdin. The agent can read files and open commits, which a single prompt cannot hold.
- It runs with `acceptEdits` and extra directories granted through `--add-dir`, the minimum scope to write the result with nobody around to approve.
- It has a 15-minute ceiling, and a failure never takes the recap down: the report stays valid with the git activity and the error shows on screen.
- You choose the language, the tone and the post length (short, medium or long), and can point to a style reference file.

#### Media and photos

- Project photos: it scans local repositories for images, ignores build and dependency folders and files under 5 KB (except SVG). It scores by name (`screenshot`, `banner`, `hero`, `demo`), by folder (`docs`, `assets`, `public`), by match with the keywords and by recency.
- Photo bank: Pexels or Unsplash, searching by the keywords, downloading locally and keeping the photographer attribution alongside. On Unsplash, the download endpoint is triggered as the guidelines ask.
- The order of preference is a real image from the project, then the photo bank.

<p align="center"><img src="./assets/screens/fotos-sugeridas.png" alt="Suggested photos, with the source of each one (project or stock library)." width="92%"><br><sub>Suggested photos, with the source of each one (project or stock library).</sub></p>

#### Window, tray and scheduler

- The window has three areas: Today (post and photo side by side, summary, numbers and per-repository detail), History and Settings.
- In Today, the day's repositories become chips: tick the ones that count, pick the text size and regenerate without recollecting commits.
- Closing the window only hides it. The tray menu opens the app, generates the recap, opens settings, toggles autostart and quits.
- The light or dark theme remembers your choice and, without one, follows the system.

<p align="center"><img src="./assets/screens/config-agendamento.png" alt="Scheduling settings: daily time, weekends, start with Windows and notifications." width="92%"><br><sub>Scheduling settings: daily time, weekends, start with Windows and notifications.</sub></p>

<p align="center"><img src="./assets/screens/hoje-escuro.png" alt="Today tab in the dark theme: per-repository focus, post and photo side by side, summary." width="92%"><br><sub>Today tab in the dark theme: per-repository focus, post and photo side by side, summary.</sub></p>

### Architecture

- `app.py`: the controller. It joins window, tray and scheduler, and exposes the API to JavaScript.
- `pipeline.py`: the flow of collection, aggregation, AI, photos and saving.
- `analyzers/`: local git, GitHub client and aggregator.
- `ai/`: the bridge to Claude Code.
- `media/`: project photos and the photo bank.
- `scheduler/`: the daily schedule with APScheduler.
- `ui/`: tray icon, webview bridge and the frontend in `web/`.
- `core/`: models, settings, paths, storage, autostart and clipboard.

```mermaid
flowchart LR
    T[pystray] --> C[AppController]
    W[pywebview] <--> C
    D[APScheduler] --> C
    C --> PL[pipeline]
    PL --> AN[analyzers]
    PL --> AI[ai]
    PL --> MD[media]
    PL --> ST[core storage]
    ST --> DISK[(APPDATA DevRecap)]
```

Where the data lives, all under `%APPDATA%\DevRecap`: `config.json` with settings and keys, `reports/YYYY-MM-DD/` with `report.json` (source of truth) and `report.md`, `media/` with downloaded images and `logs/devrecap.log`.

### Engineering decisions

1. **Write the report before the AI.** The analysis reads `report.json` from disk, so the pipeline saves a preliminary one with the git activity and only then calls the AI. If the AI fails, the recap stays valid.
2. **Nothing leaks to the orchestrator.** Each module catches its exception, logs it and returns a partial object with an error field. A broken repository becomes a warning, not a crash.
3. **Agent instead of a single prompt.** Commits with full bodies and diffs do not fit well in one prompt. Running Claude Code headless trades speed (minutes) for context, which is why the work runs in the background.
4. **Separate threads.** The window loop owns the main thread, the tray runs on a daemon thread and the pipeline on its own thread, with the result pushed to JavaScript.
5. **Registry autostart, no admin.** The `HKCU\...\Run` key works both from source and from the frozen `.exe`.
6. **Executable self-test.** `--selftest` validates imports, icon, scheduler and pipeline with an isolated `APPDATA`. In a `--windowed` app an import failure would be silent.

### Privacy

- Settings, reports, images and logs stay on your machine, in `%APPDATA%\DevRecap`. The GitHub token and the photo bank key sit in plain text in `config.json`, outside the repository and listed in `.gitignore`.
- To GitHub go your username and token, in the API calls. To Pexels or Unsplash go the key and the search keywords.
- Reading local commits uses the installed git. The report content is handed to the Claude Code CLI installed on the machine, which processes it as that tool works.
- Sensitive projects stay out if they are not in the monitored folders.

### Known limits

- Windows 10 or 11 only, with Python 3.11 or newer, WebView2 and git on PATH.
- The analysis depends on the Claude Code CLI and on an instruction file from the author's project; without them the app lists the activity but produces no summary or post.
- The analysis takes minutes and has a 15-minute ceiling.
- On Unsplash, demo mode allows 50 requests per hour. Pexels gives the key instantly.
- Private GitHub repositories need a token with the `repo` scope (or Contents: Read, on fine-grained tokens).
- Pexels and Unsplash require crediting the photographer; the post should include it when using a bank photo.
- The README suggests excluding the `.venv` folder from OneDrive sync.

### Requirements and installation

- Windows 10 or 11 with the WebView2 Runtime, Python 3.11 or newer and `git` on the PATH.
- Claude Code installed: the daily analysis runs through the CLI in headless mode.

```powershell
.\setup.ps1                          # creates the .venv and installs dependencies
.\.venv\Scripts\pythonw.exe run.py   # runs without a console
.\build.ps1                          # optional: builds dist\DevRecap.exe with PyInstaller
```

On first run the Settings window opens by itself.

<sub>Contato · Contact: <a href="https://joaocouto.alcetus.com">joaocouto.alcetus.com</a> · <a href="mailto:joaopecouto77@gmail.com">joaopecouto77@gmail.com</a></sub>
