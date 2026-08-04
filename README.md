# DevRecap

App de **bandeja do Windows** que, todo dia às **18:00**, analisa seus projetos
(pastas locais + GitHub), lista o que foi feito e gera, com o **Google Gemini**:

- ✅ a **lista** do que você fez no dia (por repositório);
- 📊 um **resumo** com tecnologias usadas, progresso e como o trabalho agregou ao projeto;
- 📝 uma **ideia de post para o LinkedIn** (texto pronto, em primeira pessoa);
- 🖼 **sugestões de foto** para o post — print/asset do próprio projeto **e** banco de fotos (Pexels/Unsplash), com opção de imagem gerada por IA.

Tudo fica num ícone discreto na bandeja. Clicou → vê o relatório, copia o post, abre a foto.

---

## Como funciona

```
pastas locais (git CLI) ─┐
                         ├─► agrega ─► Gemini ─► resumo + post + keywords
GitHub (REST API)       ─┘                   └─► fotos (projeto + banco + IA)
                                   ▼
                         relatório do dia (janela + arquivos salvos)
```

O coletor lê os **commits do dia** (data de commit, em horário local), `+/−` linhas,
arquivos tocados, linguagens por extensão e mudanças não commitadas. O GitHub
adiciona PRs/issues abertas/merge no dia. O Gemini transforma isso em texto.

---

A interface é em **HTML/CSS** (janela WebView2) com o **visual espelhado do Mappex**:
sidebar, acento azul, cantos arredondados e **light/dark**. O post do LinkedIn e a
foto sugerida aparecem **lado a lado**.

## Requisitos

- **Windows 10/11**
- **Python 3.11+** (instalação padrão do Windows)
- **WebView2 Runtime** (já vem no Windows 10/11 atual; se faltar, baixe em
  developer.microsoft.com/microsoft-edge/webview2)
- **git** no PATH (para ler os repositórios locais)
- Uma **API key do Gemini** (gratuita p/ começar) — sem ela, o app ainda lista a
  atividade, mas não gera resumo/post.

---

## Instalação

```powershell
cd "C:\Users\jojob\OneDrive\Documentos\Projetos\Other\DevRecap"
.\setup.ps1
```

O `setup.ps1` cria um ambiente virtual em `.venv` e instala as dependências.
Para rodar:

```powershell
# com janela de console (vê logs):
.\.venv\Scripts\python.exe run.py

# sem console (recomendado no dia a dia):
.\.venv\Scripts\pythonw.exe run.py
```

> 💡 **OneDrive:** exclua a pasta `.venv` da sincronização do OneDrive
> (Configurações do OneDrive → *Escolher pastas*) — são milhares de arquivos
> que não precisam sincronizar.

Na primeira execução, como nada está configurado ainda, a janela de
**Configurações** abre sozinha.

---

## Configuração (o que preencher)

Abra **Configurações** pelo menu da bandeja. Campos principais:

| Seção | O que colocar |
|---|---|
| 📁 **Projetos locais** | As pastas onde ficam seus projetos. O app procura repositórios git dentro delas. Opcional: filtrar commits por e-mail de autor. |
| 🐙 **GitHub** | Seu usuário + um **token (PAT)**. Para repositórios privados, use um token clássico com escopo **`repo`** (ou fine-grained com **Contents: Read**). |
| ✨ **Gemini** | Sua **API key**. Modelo de texto padrão: `gemini-2.5-flash`. Imagem: `gemini-2.5-flash-image`. |
| 📝 **Estilo do post** | Idioma, tom e (opcional) um arquivo de referência de estilo — ex.: seu `Perfil-LinkedIn-Vencedor.md`. |
| 🖼 **Fotos** | Quais fontes usar (projeto / banco de fotos / IA) + provedor e key do banco de fotos. |
| ⏰ **Agendamento** | Horário (padrão **18:00**), fins de semana, iniciar com o Windows, notificações. |

### Onde pegar cada chave

- **Gemini:** <https://aistudio.google.com/apikey> (gratuito p/ começar; custo é de centavos por dia no `gemini-2.5-flash`).
- **GitHub PAT:** GitHub → *Settings* → *Developer settings* → *Personal access tokens*. Para privados, escopo `repo`.
- **Pexels** (banco de fotos recomendado): <https://www.pexels.com/api/> — key instantânea, sem aprovação. (Unsplash também é suportado, mas exige aplicar para “produção”.)

---

## Uso

Menu da bandeja (clique no ícone):

- **Gerar recap agora** — roda o pipeline na hora (também é a ação de duplo-clique).
- **Ver último recap** — reabre o último relatório salvo.
- **Configurações…**
- **Iniciar com o Windows** — liga/desliga o autostart (sem precisar de admin).
- **Sair**.

A janela tem uma **sidebar** com **Hoje** (o recap: post + foto lado a lado, resumo,
tecnologias, progresso, valor, números e detalhe por repo), **Histórico** (recaps
anteriores) e **Configurações**. No rodapé da sidebar, botões de **Tema** (light/dark)
e **Gerar**. Fechar a janela apenas a esconde na bandeja; **Sair** (no menu da bandeja)
encerra de vez.

No topo do **Hoje** há controles rápidos:
- **Focar em** — os projetos modificados no dia viram chips; marque/desmarque para
  gerar o texto sobre **um só** projeto ou **todos** (os candidatos mudam a cada dia).
- **Tamanho** — post **curto** (padrão), **médio** ou **longo**.
- **Regenerar texto** — refaz o resumo/post com o foco e o tamanho escolhidos
  (sem recoletar os commits).

O texto sai **curto e casual** por padrão (nada de "release corporativo"); ajuste o
tom em *Configurações → Estilo do post*.

---

## Onde ficam os dados

Tudo em `%APPDATA%\DevRecap\`:

```
%APPDATA%\DevRecap\
├── config.json              # suas configurações e chaves (NÃO versionar)
├── reports\YYYY-MM-DD\
│   ├── report.json          # dados do dia (fonte da verdade)
│   └── report.md            # versão legível
├── media\                   # imagens baixadas/geradas p/ os posts
└── logs\devrecap.log
```

As chaves ficam em texto no `config.json` (app local, de uso pessoal). O arquivo
fica fora do repositório.

---

## Empacotar em .exe (opcional)

Para um executável único, sem precisar de Python instalado:

```powershell
.\build.ps1
```

Gera `dist\DevRecap.exe` (usa PyInstaller, modo `--windowed`, com o ícone embarcado).
O autostart detecta sozinho se está rodando do `.exe` ou do código-fonte.

---

## Estrutura do projeto

```
DevRecap/
├── run.py                     # ponto de entrada
├── make_icon.py               # (re)gera assets/icon.png e icon.ico
├── setup.ps1 / build.ps1      # instalar / empacotar
├── CONTRACT.md                # contrato das interfaces dos módulos
├── assets/icon.png, icon.ico
└── devrecap/
    ├── app.py                 # AppController (webview + tray + agendador)
    ├── pipeline.py            # pipeline do recap (coleta→IA→fotos→salva)
    ├── selftest.py            # --selftest: valida deps/empacotamento
    ├── core/                  # models, config, storage, paths, autostart, clipboard, logging
    ├── analyzers/             # git_local, github_api, aggregate
    ├── ai/                    # prompts, gemini
    ├── media/                 # project_photos, stock, gemini_image
    ├── scheduler/             # daily (APScheduler)
    └── ui/                    # tray (ícone) · webview_app (bridge/HTML) · web/ (frontend HTML/CSS/JS)
```

---

## Notas

- **Modelos Gemini:** o app usa `gemini-2.5-flash` (texto) e `gemini-2.5-flash-image`
  (“Nano Banana”, imagem) por padrão — ambos configuráveis. Imagen 4 foi
  descontinuado pela Google, então não é usado.
- **Atribuição de fotos:** Pexels e Unsplash exigem crédito ao fotógrafo + link.
  O relatório já mostra o crédito; o post no LinkedIn deve incluí-lo quando usar
  uma foto de banco.
- **Privacidade:** os diffs/commits são enviados ao Gemini para gerar o texto.
  Se algum projeto for sensível, deixe-o fora das pastas monitoradas.

---

## Problemas comuns

- **“Falta a API key do Gemini”** → preencha em Configurações ✨.
- **GitHub não traz nada** → confira usuário + token e o escopo (`repo` p/ privados).
- **Nenhuma foto do projeto** → o app ignora imagens < 5KB (ícones); guarde
  screenshots em `docs/`, `assets/`, `public/` etc.
- **Não inicia com o Windows** → marque “Iniciar com o Windows” em Configurações
  (grava em `HKCU\...\Run`, sem admin).
- **Logs** em `%APPDATA%\DevRecap\logs\devrecap.log`.
