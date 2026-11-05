<h1 align="center">DevRecap</h1>

<p align="center">App de bandeja do Windows que resume o seu dia de código e prepara um post a partir disso.<br><sub><i>Windows tray app that summarizes your coding day and drafts a post from it.</i></sub></p>

<p align="center">
  <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/python.svg" height="18" alt=""> Python</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/pyinstaller.svg" height="18" alt=""> PyInstaller</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/apscheduler.svg" height="18" alt=""> APScheduler</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/webview2.svg" height="18" alt=""> WebView2</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/gemini.svg" height="18" alt=""> Gemini API</kbd> <kbd><img src="https://raw.githubusercontent.com/Joaopecouto/Joaopecouto/main/assets/icons/github.svg" height="18" alt=""> GitHub API</kbd>
</p>

## Português

Todo dia às **18:00** o DevRecap analisa seus projetos (pastas locais e GitHub), lista o que foi feito e gera, com o **Google Gemini**:

- a **lista** do que você fez no dia, por repositório;
- um **resumo** com tecnologias usadas, progresso e o valor que o trabalho agregou ao projeto;
- uma **ideia de post para o LinkedIn**, com texto pronto;
- **sugestões de foto** para o post: print do próprio projeto, banco de fotos (Pexels e Unsplash) ou imagem gerada por IA.

Tudo fica num ícone discreto na bandeja. Um clique abre o relatório, copia o post e abre a foto.

### Como funciona

```
pastas locais (git CLI) ─┐
                         ├─► agrega ─► Gemini ─► resumo + post + palavras-chave
GitHub (REST API)       ─┘                   └─► fotos (projeto + banco + IA)
                                   ▼
                         relatório do dia (janela + arquivos salvos)
```

O coletor lê os commits do dia (em horário local), as linhas adicionadas e removidas, os arquivos tocados, as linguagens por extensão e as mudanças não commitadas. O GitHub acrescenta PRs, issues abertas e merges do dia. O Gemini transforma isso em texto. A interface é HTML e CSS numa janela WebView2, com tema claro e escuro.

### Requisitos

- Windows 10 ou 11 com WebView2 Runtime.
- Python 3.11 ou superior e `git` no PATH.
- Uma API key do Gemini (gratuita para começar). Sem ela, o app ainda lista a atividade, mas não gera resumo nem post.

### Instalação

```powershell
.\setup.ps1                                  # cria o .venv e instala as dependências
.\.venv\Scripts\pythonw.exe run.py            # roda sem console
```

Na primeira execução, a janela de **Configurações** abre sozinha. Para um executável único: `.\build.ps1` gera `dist\DevRecap.exe` com PyInstaller.

### Configuração

| Seção | O que preencher |
| --- | --- |
| Projetos locais | As pastas onde ficam seus projetos; o app procura repositórios git dentro delas. |
| GitHub | Usuário e token (PAT) com escopo `repo` para repositórios privados. |
| Gemini | API key. Modelo de texto padrão `gemini-2.5-flash` e de imagem `gemini-2.5-flash-image`. |
| Estilo do post | Idioma, tom e, se quiser, um arquivo de referência de estilo. |
| Fotos | Fontes (projeto, banco de fotos, IA), provedor e key do banco de fotos. |
| Agendamento | Horário (padrão 18:00), fins de semana, iniciar com o Windows e notificações. |

### Uso

Pelo menu da bandeja: **Gerar recap agora**, **Ver último recap**, **Configurações** e **Iniciar com o Windows**. Na janela, **Hoje** mostra o post e a foto lado a lado, o resumo, as tecnologias e o detalhe por repositório; **Histórico** guarda os recaps anteriores. Dá para focar em um projeto só, escolher o tamanho do post (curto, médio ou longo) e regenerar o texto sem recoletar os commits.

### Dados e privacidade

Tudo fica em `%APPDATA%\DevRecap\` (configuração, relatórios por data, mídia e logs). Os commits e diffs são enviados ao Gemini para gerar o texto: deixe de fora das pastas monitoradas qualquer projeto sensível. Fotos de banco exigem crédito ao fotógrafo, e o relatório já mostra o crédito.

## English

Every day at **6:00 PM** DevRecap scans your projects (local folders and GitHub), lists what you did and uses **Google Gemini** to produce:

- the **list** of what you did that day, per repository;
- a **summary** with the technologies used, progress and the value the work added to the project;
- a **LinkedIn post idea** with ready-to-use text;
- **photo suggestions** for the post: a screenshot from the project itself, stock photos (Pexels and Unsplash) or an AI-generated image.

Everything lives in a discreet tray icon. One click opens the report, copies the post and opens the photo.

### How it works

```
local folders (git CLI) ─┐
                         ├─► aggregate ─► Gemini ─► summary + post + keywords
GitHub (REST API)       ─┘                   └─► photos (project + stock + AI)
                                   ▼
                         daily report (window + saved files)
```

The collector reads the day's commits (in local time), added and removed lines, touched files, languages by extension and uncommitted changes. GitHub adds the day's PRs, open issues and merges. Gemini turns that into text. The interface is HTML and CSS in a WebView2 window, with light and dark themes.

### Requirements

- Windows 10 or 11 with the WebView2 Runtime.
- Python 3.11 or newer and `git` on the PATH.
- A Gemini API key (free to start). Without it the app still lists activity, but it does not generate a summary or a post.

### Installation

```powershell
.\setup.ps1                                  # creates the .venv and installs dependencies
.\.venv\Scripts\pythonw.exe run.py            # runs without a console
```

On first run the **Settings** window opens by itself. For a single executable: `.\build.ps1` produces `dist\DevRecap.exe` with PyInstaller.

### Configuration

| Section | What to fill in |
| --- | --- |
| Local projects | The folders where your projects live; the app looks for git repositories inside them. |
| GitHub | Username and a token (PAT) with the `repo` scope for private repositories. |
| Gemini | API key. Default text model `gemini-2.5-flash` and image model `gemini-2.5-flash-image`. |
| Post style | Language, tone and, optionally, a style reference file. |
| Photos | Sources (project, stock photos, AI), provider and stock-photo key. |
| Schedule | Time (default 6:00 PM), weekends, start with Windows and notifications. |

### Usage

From the tray menu: **Generate recap now**, **View last recap**, **Settings** and **Start with Windows**. In the window, **Today** shows the post and photo side by side, the summary, the technologies and a per-repository breakdown; **History** keeps previous recaps. You can focus on a single project, pick the post length (short, medium or long) and regenerate the text without re-collecting commits.

### Data and privacy

Everything is stored in `%APPDATA%\DevRecap\` (configuration, reports by date, media and logs). Commits and diffs are sent to Gemini to generate the text: keep any sensitive project out of the monitored folders. Stock photos require crediting the photographer, and the report already shows the credit.

<sub>Contato · Contact: <a href="https://joaocouto.alcetus.com">joaocouto.alcetus.com</a> · <a href="mailto:joaopecouto77@gmail.com">joaopecouto77@gmail.com</a></sub>
