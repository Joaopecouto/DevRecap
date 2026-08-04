/* DevRecap — frontend (vanilla JS).
   Conversa com a bridge Python via window.pywebview.api.* quando disponível;
   caso contrário usa MOCK (permite abrir o index.html direto no navegador p/ ver o visual).
   O Python entrega/atualiza dados chamando window.devrecapPush(payload). */

(function () {
  "use strict";

  // ---------------------------------------------------------------- //
  // Ícones (Lucide-style)
  // ---------------------------------------------------------------- //
  const I = {
    summary: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    tech: '<path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/>',
    trend: '<path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M12 8a3 3 0 1 0-3-3c0 1.5 1 3 3 3zM12 8a3 3 0 1 1 3-3c0 1.5-1 3-3 3z"/>',
    linkedin: '<path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    open: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14L21 3"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z"/>',
    git: '<circle cx="12" cy="12" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 9v6a3 3 0 0 0 3 3h6"/>',
    spark: '<path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3z"/>',
    warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    run: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
    trash: '<path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  };
  const svg = (p, w) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w || 2}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;

  // ---------------------------------------------------------------- //
  // Estado + helpers
  // ---------------------------------------------------------------- //
  const content = document.getElementById("content");
  const toastEl = document.getElementById("toast");
  let state = { view: "today", report: null, history: [], settings: null, generating: false };

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toastEl.classList.remove("show"), 1900);
  }

  const hasBridge = () => typeof window.pywebview !== "undefined" && window.pywebview.api;

  async function call(method, ...args) {
    if (hasBridge() && typeof window.pywebview.api[method] === "function") {
      return await window.pywebview.api[method](...args);
    }
    return MOCK[method] ? MOCK[method](...args) : null;
  }

  async function copy(text) {
    if (!text) return;
    // Tenta o clipboard do navegador (webview em localhost = secure context);
    // se falhar, usa o fallback Python (Win32) via bridge.
    try { await navigator.clipboard.writeText(text); toast("Copiado!"); return; } catch (e) {}
    try {
      if (hasBridge() && window.pywebview.api.copy) { await window.pywebview.api.copy(text); toast("Copiado!"); return; }
    } catch (e) {}
    toast("Não consegui copiar");
  }

  // ---------------------------------------------------------------- //
  // Navegação / tema
  // ---------------------------------------------------------------- //
  document.getElementById("nav").addEventListener("click", (e) => {
    const item = e.target.closest(".nav-item");
    if (!item) return;
    setView(item.dataset.view);
  });

  function setView(view) {
    state.view = view;
    document.querySelectorAll(".nav-item").forEach((n) =>
      n.classList.toggle("active", n.dataset.view === view));
    render();
  }

  const themeBtn = document.getElementById("themeBtn");
  themeBtn.addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.getAttribute("data-theme") === "dark";
    root.setAttribute("data-theme", dark ? "light" : "dark");
    try { localStorage.setItem("devrecap-theme", dark ? "light" : "dark"); } catch (e) {}
  });
  (function initTheme() {
    let t = "light";
    try { t = localStorage.getItem("devrecap-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); } catch (e) {}
    document.documentElement.setAttribute("data-theme", t);
  })();

  document.getElementById("runBtn").addEventListener("click", runRecap);

  async function runRecap() {
    if (state.generating) { toast("Já estou gerando…"); return; }
    state.generating = true;
    if (state.view === "today") render();
    toast("Gerando recap…");
    try { await call("run_recap"); } catch (e) { state.generating = false; }
  }

  async function regenerate(options) {
    if (state.generating) { toast("Já estou gerando…"); return; }
    state.generating = true;
    if (state.view === "today") render();
    toast("Regenerando texto…");
    try { await call("regenerate", options); } catch (e) { state.generating = false; }
  }

  // Python empurra dados: { type, report, history, settings, generating }
  window.devrecapPush = function (payload) {
    if (!payload) return;
    if ("generating" in payload) state.generating = payload.generating;
    if (payload.report) state.report = payload.report;
    if (payload.history) state.history = payload.history;
    if (payload.settings) state.settings = payload.settings;
    if (payload.toast) toast(payload.toast);
    if (payload.view) { setView(payload.view); return; }
    render();
  };

  // ---------------------------------------------------------------- //
  // Render principal
  // ---------------------------------------------------------------- //
  function render() {
    if (state.view === "today") renderToday();
    else if (state.view === "history") renderHistory();
    else if (state.view === "settings") renderSettings();
  }

  // ---- HOJE -------------------------------------------------------- //
  function renderToday() {
    const r = state.report;
    let html = "";

    html += `<div class="page-head">
      <div>
        <div class="page-title">Recap${r ? " — " + esc(r.day) : ""}</div>
        <div class="page-sub">${r ? esc(r.subtitle || "") : "Seu resumo do dia"}</div>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary" id="genBtn" ${state.generating ? "disabled" : ""}>
          ${state.generating ? '<span class="spinner"></span> Gerando…' : svg(I.run) + " Gerar agora"}
        </button>
      </div>
    </div>`;

    if (!r) {
      html += emptyState("Nenhum recap ainda", "Clique em “Gerar agora” para criar o resumo do dia.", I.inbox);
      content.innerHTML = html;
      bindToday();
      return;
    }

    const ins = r.insights || {};

    // Notas/avisos da coleta (inclui erros de foto)
    const notes = (r.notes || []).slice();
    if (ins.error) notes.push("IA: " + ins.error);
    if (notes.length)
      html += `<div class="notes">${notes.map((n) => `<div class="note">${svg(I.warn)}<span>${esc(n)}</span></div>`).join("")}</div>`;

    // Controles: foco por projeto (do dia) + tamanho do texto + regenerar
    html += controlsHtml(r);

    // HERO: post + imagem juntos
    html += `<div class="card hero fade-in">
      <div class="hero-post">
        <div class="card-title">${svg(I.linkedin)} Post pro LinkedIn</div>
        <div class="post-text">${esc(ins.linkedin_post) || "<span style='color:var(--text-3)'>(post não gerado)</span>"}</div>
        ${(ins.linkedin_hashtags && ins.linkedin_hashtags.length)
          ? `<div class="post-hashtags">${ins.linkedin_hashtags.map((h) => `<span class="hashtag">#${esc(String(h).replace(/^#/, ""))}</span>`).join("")}</div>` : ""}
        <div class="post-actions">
          <button class="btn btn-primary" data-copy="post">${svg(I.copy)} Copiar post</button>
          <button class="btn btn-ghost" data-open-url="https://www.linkedin.com/feed/">${svg(I.open)} Abrir LinkedIn</button>
        </div>
      </div>
      <div class="hero-media">
        <div class="card-title">${svg(I.image)} Foto sugerida</div>
        ${(r.photos && r.photos.length) ? r.photos.map(photoCard).join("") :
          `<div style="font-size:12px;color:var(--text-3)">Nenhuma foto sugerida. Ative as fontes em Configurações.</div>`}
      </div>
    </div>`;

    // Card consolidado: Resumo do dia (o que foi feito + resumo + progresso/valor + tecnologias)
    const hasResumo = (ins.bullet_highlights && ins.bullet_highlights.length) || ins.summary ||
      ins.progress || ins.value_added || (ins.technologies && ins.technologies.length);
    if (hasResumo) {
      html += `<div class="card fade-in"><div class="card-title">${svg(I.summary)} Resumo do dia</div>`;
      if (ins.bullet_highlights && ins.bullet_highlights.length)
        html += `<ul class="bullet-list">${ins.bullet_highlights.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`;
      if (ins.summary)
        html += `<div class="prose"${(ins.bullet_highlights && ins.bullet_highlights.length) ? ' style="margin-top:11px"' : ""}>${esc(ins.summary)}</div>`;
      if (ins.progress || ins.value_added) {
        html += `<div class="divider"></div><div class="subsecs">`;
        if (ins.progress) html += `<div class="subsec"><div class="subsec-label">Progresso</div><p>${esc(ins.progress)}</p></div>`;
        if (ins.value_added) html += `<div class="subsec"><div class="subsec-label">Como agregou</div><p>${esc(ins.value_added)}</p></div>`;
        html += `</div>`;
      }
      if (ins.technologies && ins.technologies.length)
        html += `<div class="divider"></div><div class="chips">${ins.technologies.map((t) => `<span class="chip chip-primary">${esc(t)}</span>`).join("")}</div>`;
      html += `</div>`;
    }

    // Números (strip fino)
    const t = r.totals || {};
    html += `<div class="card fade-in"><div class="stats">
        ${stat(t.commits || 0, "commits")}
        ${stat(t.repos || 0, "repos")}
        ${stat("+" + (t.insertions || 0), "linhas", "pos")}
        ${stat("−" + (t.deletions || 0), "removidas", "neg")}
        ${stat(t.files || 0, "arquivos")}
      </div>
      ${(t.languages && t.languages.length) ? `<div class="chips" style="margin-top:11px">${t.languages.map((l) => `<span class="chip">${esc(l[0])} · ${l[1]}</span>`).join("")}</div>` : ""}
    </div>`;

    // Detalhe por repo
    if (r.repos && r.repos.length) {
      html += `<div class="card fade-in"><div class="card-title">${svg(I.git)} Por repositório</div>`;
      html += r.repos.map(repoCard).join("");
      html += `</div>`;
    }

    content.innerHTML = html;
    bindToday();
  }

  function controlsHtml(r) {
    const f = r.focus;
    if (!r.live || !f) return "";
    const repos = f.repos || [];
    const multi = repos.length >= 2;
    const lens = [["curto", "Curto"], ["medio", "Médio"], ["longo", "Longo"]];
    const pl = f.post_length || "curto";
    return `<div class="controls fade-in">
      ${multi ? `<div class="controls-row">
        <span class="controls-label">Focar em</span>
        <div class="focus-chips">
          ${repos.map((rp) => `<button class="fchip${rp.selected ? " selected" : ""}" data-repo="${esc(rp.name)}">${esc(rp.name)} <span class="fchip-n">${rp.commits}</span></button>`).join("")}
        </div>
      </div>` : ""}
      <div class="controls-row">
        <span class="controls-label">Tamanho</span>
        <select id="postLen" class="mini-select">${lens.map((o) => `<option value="${o[0]}"${pl === o[0] ? " selected" : ""}>${o[1]}</option>`).join("")}</select>
        <button class="btn btn-primary btn-sm" id="regenBtn">${svg(I.run)} Regenerar texto</button>
      </div>
    </div>`;
  }

  function photoCard(p) {
    const ref = p.local_path || p.url || "";
    const srcClass = p.source === "project" ? "src-project" : p.source === "gemini" ? "src-gemini" : "src-stock";
    const srcLabel = p.source === "project" ? "projeto" : p.source === "gemini" ? "IA" : "banco";
    const primary = p.display_url || p.url || "";
    const fb = (p.url && p.url !== primary) ? p.url : "";
    const media = primary
      ? `<img class="photo-img" src="${esc(primary)}" data-fallback="${esc(fb)}" alt="">`
      : `<div class="photo-fallback">${svg(I.image)}<span>sem prévia</span></div>`;
    return `<div class="photo">
      ${media}
      <div class="photo-meta">
        <span class="photo-src ${srcClass}">${srcLabel}</span>
        <div class="photo-actions">
          ${ref ? `<button class="icon-btn" data-open="${esc(ref)}" title="Abrir">${svg(I.open)}</button>` : ""}
          ${ref ? `<button class="icon-btn" data-copy-text="${esc(ref)}" title="Copiar caminho/URL">${svg(I.copy)}</button>` : ""}
        </div>
      </div>
      ${(p.attribution || p.caption) ? `<div class="photo-caption">${esc(p.attribution || p.caption)}</div>` : ""}
    </div>`;
  }

  function repoCard(repo) {
    const commits = (repo.commits || []).map((c) =>
      `<div class="commit">${c.sha ? `<code>${esc(String(c.sha).slice(0, 8))}</code>` : ""}<span>${esc(c.subject || firstLine(c.message))}</span></div>`).join("");
    const prs = (repo.prs || []).map((p) => `<div class="commit"><span>PR #${esc(p.number)} (${esc(p.state)}): ${esc(p.title)}</span></div>`).join("");
    const issues = (repo.issues || []).map((i) => `<div class="commit"><span>Issue #${esc(i.number)} (${esc(i.state)}): ${esc(i.title)}</span></div>`).join("");
    return `<div class="repo" style="margin-top:12px">
      <div class="repo-head">
        <span class="repo-name">${esc(repo.name)}</span>
        ${repo.is_dirty ? `<span class="chip" style="font-size:10px">não commitado</span>` : ""}
        <span class="repo-stat ml">${repo.commits ? repo.commits.length : 0} commit(s) · <span style="color:var(--emerald-600)">+${repo.insertions || 0}</span>/<span style="color:var(--rose-600)">−${repo.deletions || 0}</span></span>
      </div>
      <div class="repo-body">${commits}${prs}${issues || (!commits && !prs ? '<div class="commit"><span style="color:var(--text-3)">só mudanças não commitadas</span></div>' : "")}</div>
    </div>`;
  }

  const firstLine = (m) => String(m || "").split("\n")[0];
  const stat = (v, l, cls) => `<div class="stat"><div class="stat-value ${cls || ""}">${esc(v)}</div><div class="stat-label">${esc(l)}</div></div>`;

  function bindToday() {
    const gen = document.getElementById("genBtn");
    if (gen) gen.addEventListener("click", runRecap);
    content.querySelectorAll("[data-copy='post']").forEach((b) => b.addEventListener("click", () => {
      const ins = (state.report && state.report.insights) || {};
      const tags = (ins.linkedin_hashtags || []).map((h) => "#" + String(h).replace(/^#/, "")).join(" ");
      copy((ins.linkedin_post || "") + (tags ? "\n\n" + tags : ""));
    }));
    content.querySelectorAll("[data-copy-text]").forEach((b) => b.addEventListener("click", () => copy(b.dataset.copyText)));
    content.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => call("open_path", b.dataset.open)));
    content.querySelectorAll("[data-open-url]").forEach((b) => b.addEventListener("click", () => call("open_url", b.dataset.openUrl)));
    // Foco por projeto (marca/desmarca) + regenerar texto
    content.querySelectorAll(".fchip").forEach((ch) => ch.addEventListener("click", () => ch.classList.toggle("selected")));
    const regen = document.getElementById("regenBtn");
    if (regen) regen.addEventListener("click", () => {
      const chips = content.querySelectorAll(".fchip");
      const repos = Array.from(content.querySelectorAll(".fchip.selected")).map((c) => c.dataset.repo);
      if (chips.length && repos.length === 0) { toast("Selecione ao menos um projeto"); return; }
      const sel = document.getElementById("postLen");
      regenerate({ repos: repos, post_length: sel ? sel.value : undefined });
    });
    // imagem que não carrega: tenta a URL remota; se falhar, mostra prévia indisponível
    content.querySelectorAll(".photo-img").forEach((im) => im.addEventListener("error", function () {
      const fb = this.dataset.fallback;
      if (fb && this.src !== fb) { this.src = fb; this.dataset.fallback = ""; return; }
      const box = document.createElement("div");
      box.className = "photo-fallback";
      box.innerHTML = svg(I.image) + "<span>imagem indisponível</span>";
      this.replaceWith(box);
    }));
  }

  // ---- HISTÓRICO --------------------------------------------------- //
  async function renderHistory() {
    content.innerHTML = `<div class="page-head"><div><div class="page-title">Histórico</div><div class="page-sub">Recaps anteriores</div></div></div><div id="histList"></div>`;
    const list = (await call("list_history")) || state.history || [];
    state.history = list;
    const el = document.getElementById("histList");
    if (!list.length) { el.innerHTML = emptyState("Sem histórico", "Os recaps gerados aparecem aqui.", I.inbox); return; }
    el.innerHTML = list.map((h) => `<div class="history-item" data-day="${esc(h.day)}">
      <div><div class="history-date">${esc(h.day)}</div><div class="history-meta">${esc(h.subtitle || "")}</div></div>
      <span class="history-meta">${h.commits || 0} commit(s)</span>
      <span class="history-spark">${svg(I.open)}</span>
    </div>`).join("");
    el.querySelectorAll(".history-item").forEach((it) => it.addEventListener("click", async () => {
      const rep = await call("get_report", it.dataset.day);
      if (rep) { state.report = rep; setView("today"); }
    }));
  }

  // ---- CONFIGURAÇÕES ---------------------------------------------- //
  async function renderSettings() {
    const s = (await call("get_settings")) || state.settings || {};
    state.settings = s;
    const missing = s.missing || [];
    const photo = s.photo_sources || [];

    content.innerHTML = `
    <div class="page-head"><div><div class="page-title">Configurações</div><div class="page-sub">Pastas, contas e agendamento</div></div>
      <div class="page-actions"><button class="btn btn-primary" id="saveBtn">${svg(I.check)} Salvar</button></div></div>
    ${missing.length ? banner("warn", missing.join(" · ")) : ""}

    <div class="grid grid-2">
      <div class="card section">
        <div class="card-title">${svg(I.folder)} Projetos locais</div>
        <div class="field">
          <div class="folder-list" id="folders">${(s.folders || []).map(folderRow).join("")}</div>
          <button class="btn btn-ghost" id="addFolder">${svg(I.folder)} Adicionar pasta</button>
        </div>
        <label class="check"><input type="checkbox" id="scan_subfolders" ${s.scan_subfolders ? "checked" : ""}><span>Procurar repositórios em subpastas</span></label>
        <div class="field"><label>Profundidade da busca</label><input class="input" id="max_scan_depth" type="number" min="1" value="${esc(s.max_scan_depth ?? 3)}" style="width:90px"></div>
        <div class="field"><label>Filtrar por e-mails (vírgula)</label><input class="input" id="git_author_emails" value="${esc((s.git_author_emails || []).join(", "))}"><div class="hint">Vazio = conta todos os commits.</div></div>
      </div>

      <div class="card section">
        <div class="card-title">${svg(I.git)} GitHub</div>
        <label class="check"><input type="checkbox" id="github_enabled" ${s.github_enabled ? "checked" : ""}><span>Analisar minha atividade no GitHub</span></label>
        <div class="field"><label>Usuário</label><input class="input" id="github_username" value="${esc(s.github_username || "")}"></div>
        <div class="field"><label>Token (PAT)</label><input class="input" id="github_token" type="password" value="${esc(s.github_token || "")}"></div>
        <label class="check"><input type="checkbox" id="github_include_private" ${s.github_include_private ? "checked" : ""}><span>Incluir repositórios privados</span></label>
        <div class="hint">Token clássico com escopo <b>repo</b> (privados) ou fine-grained com Contents: Read.</div>
      </div>

      <div class="card section">
        <div class="card-title">${svg(I.spark)} Gemini</div>
        <div class="field"><label>API key</label><input class="input" id="gemini_api_key" type="password" value="${esc(s.gemini_api_key || "")}"><div class="hint">aistudio.google.com/apikey</div></div>
        <div class="row">
          <div class="field"><label>Modelo de texto</label><input class="input" id="gemini_text_model" value="${esc(s.gemini_text_model || "")}"></div>
          <div class="field"><label>Modelo de imagem</label><input class="input" id="gemini_image_model" value="${esc(s.gemini_image_model || "")}"></div>
        </div>
        <label class="check"><input type="checkbox" id="gemini_image_enabled" ${s.gemini_image_enabled ? "checked" : ""}><span>Permitir geração de imagem</span></label>
        <div class="test-row"><button class="btn btn-ghost btn-sm" id="testGemini">Testar chave</button><span class="test-result" id="testGeminiOut"></span></div>
      </div>

      <div class="card section">
        <div class="card-title">${svg(I.linkedin)} Estilo do post</div>
        <div class="row">
          <div class="field"><label>Idioma</label><input class="input" id="language" value="${esc(s.language || "pt-BR")}"></div>
          <div class="field"><label>Tamanho do post</label><select id="post_length">
            <option value="curto"${(s.post_length || "curto") === "curto" ? " selected" : ""}>Curto</option>
            <option value="medio"${s.post_length === "medio" ? " selected" : ""}>Médio</option>
            <option value="longo"${s.post_length === "longo" ? " selected" : ""}>Longo</option>
          </select></div>
        </div>
        <div class="field"><label>Tom / diretrizes</label><textarea class="textarea" id="linkedin_tone">${esc(s.linkedin_tone || "")}</textarea></div>
        <div class="field"><label>Arquivo de referência de estilo</label><input class="input" id="style_reference_file" value="${esc(s.style_reference_file || "")}"><div class="hint">Ex.: seu Perfil-LinkedIn-Vencedor.md</div></div>
      </div>

      <div class="card section">
        <div class="card-title">${svg(I.image)} Fotos do post</div>
        <label class="check"><input type="checkbox" class="psrc" value="project" ${photo.includes("project") ? "checked" : ""}><span>Print/asset do projeto</span></label>
        <label class="check"><input type="checkbox" class="psrc" value="stock" ${photo.includes("stock") ? "checked" : ""}><span>Banco de fotos (Pexels/Unsplash)</span></label>
        <label class="check"><input type="checkbox" class="psrc" value="gemini" ${photo.includes("gemini") ? "checked" : ""}><span>Imagem gerada por IA (Gemini)</span></label>
        <div class="row" style="margin-top:8px">
          <div class="field"><label>Banco de fotos</label><select id="stock_provider"><option value="pexels" ${s.stock_provider === "pexels" ? "selected" : ""}>Pexels</option><option value="unsplash" ${s.stock_provider === "unsplash" ? "selected" : ""}>Unsplash</option></select></div>
          <div class="field"><label>API key do banco</label><input class="input" id="stock_api_key" type="password" value="${esc(s.stock_api_key || "")}"></div>
        </div>
        <div class="test-row"><button class="btn btn-ghost btn-sm" id="testStock">Testar chave do banco</button><span class="test-result" id="testStockOut"></span></div>
      </div>

      <div class="card section">
        <div class="card-title">${svg(I.run)} Agendamento</div>
        <div class="row">
          <div class="field"><label>Horário (HH:MM)</label><input class="input" id="schedule_time" value="${esc(s.schedule_time || "18:00")}" style="width:110px"></div>
        </div>
        <label class="check"><input type="checkbox" id="run_on_weekends" ${s.run_on_weekends ? "checked" : ""}><span>Rodar também aos fins de semana</span></label>
        <label class="check"><input type="checkbox" id="autostart" ${s.autostart ? "checked" : ""}><span>Iniciar com o Windows</span></label>
        <label class="check"><input type="checkbox" id="show_notifications" ${s.show_notifications ? "checked" : ""}><span>Mostrar notificações</span></label>
        <label class="check"><input type="checkbox" id="auto_open_report" ${s.auto_open_report ? "checked" : ""}><span>Abrir o relatório ao gerar</span></label>
      </div>
    </div>`;

    bindSettings();
  }

  function folderRow(path) {
    return `<div class="folder-row"><span class="path" title="${esc(path)}">${esc(path)}</span><button class="icon-btn" data-rmfolder="${esc(path)}" title="Remover">${svg(I.trash)}</button></div>`;
  }

  function bindSettings() {
    document.getElementById("addFolder").addEventListener("click", async () => {
      const p = await call("pick_folder");
      if (p) {
        if (!state.settings.folders) state.settings.folders = [];
        if (!state.settings.folders.includes(p)) {
          state.settings.folders.push(p);
          document.getElementById("folders").insertAdjacentHTML("beforeend", folderRow(p));
          bindFolderRemovers();
        }
      }
    });
    bindFolderRemovers();
    document.getElementById("saveBtn").addEventListener("click", saveSettings);

    const tg = document.getElementById("testGemini");
    if (tg) tg.addEventListener("click", async () => {
      const out = document.getElementById("testGeminiOut");
      out.textContent = "testando…"; out.className = "test-result";
      const key = (document.getElementById("gemini_api_key").value || "").trim();
      const model = (document.getElementById("gemini_text_model").value || "").trim();
      showTest(out, await call("test_gemini", key, model));
    });
    const ts = document.getElementById("testStock");
    if (ts) ts.addEventListener("click", async () => {
      const out = document.getElementById("testStockOut");
      out.textContent = "testando…"; out.className = "test-result";
      const prov = document.getElementById("stock_provider").value;
      const key = (document.getElementById("stock_api_key").value || "").trim();
      showTest(out, await call("test_stock", prov, key));
    });
  }

  function showTest(out, res) {
    if (!out) return;
    if (!res) { out.textContent = "sem resposta"; out.className = "test-result test-bad"; return; }
    out.textContent = res.message || (res.ok ? "OK" : "falhou");
    out.className = "test-result " + (res.ok ? "test-ok" : "test-bad");
  }

  function bindFolderRemovers() {
    document.querySelectorAll("[data-rmfolder]").forEach((b) => b.onclick = () => {
      state.settings.folders = (state.settings.folders || []).filter((f) => f !== b.dataset.rmfolder);
      b.closest(".folder-row").remove();
    });
  }

  async function saveSettings() {
    const v = (id) => { const el = document.getElementById(id); return el ? el.value : ""; };
    const c = (id) => { const el = document.getElementById(id); return el ? el.checked : false; };
    const data = {
      folders: state.settings.folders || [],
      scan_subfolders: c("scan_subfolders"),
      max_scan_depth: parseInt(v("max_scan_depth"), 10) || 3,
      git_author_emails: v("git_author_emails").split(",").map((s) => s.trim()).filter(Boolean),
      github_enabled: c("github_enabled"),
      github_username: v("github_username").trim(),
      github_token: v("github_token").trim(),
      github_include_private: c("github_include_private"),
      gemini_api_key: v("gemini_api_key").trim(),
      gemini_text_model: v("gemini_text_model").trim(),
      gemini_image_model: v("gemini_image_model").trim(),
      gemini_image_enabled: c("gemini_image_enabled"),
      language: v("language").trim() || "pt-BR",
      post_length: v("post_length") || "curto",
      linkedin_tone: v("linkedin_tone").trim(),
      style_reference_file: v("style_reference_file").trim(),
      photo_sources: Array.from(document.querySelectorAll(".psrc:checked")).map((x) => x.value),
      stock_provider: v("stock_provider"),
      stock_api_key: v("stock_api_key").trim(),
      schedule_time: v("schedule_time").trim() || "18:00",
      run_on_weekends: c("run_on_weekends"),
      autostart: c("autostart"),
      show_notifications: c("show_notifications"),
      auto_open_report: c("auto_open_report"),
    };
    const res = await call("save_settings", data);
    state.settings = Object.assign({}, state.settings, data, { missing: (res && res.missing) || [] });
    toast("Configurações salvas");
    renderSettings();
  }

  // ---- comuns ------------------------------------------------------ //
  function banner(kind, text) {
    return `<div class="banner banner-${kind === "warn" ? "warn" : "info"}">${svg(kind === "warn" ? I.warn : I.info)}<span>${text}</span></div>`;
  }
  function emptyState(title, sub, icon) {
    return `<div class="empty">${svg(icon, 1.6)}<h3>${esc(title)}</h3><div>${esc(sub)}</div></div>`;
  }

  // ---------------------------------------------------------------- //
  // Boot
  // ---------------------------------------------------------------- //
  async function boot() {
    let init = null;
    try {
      init = await call("get_initial");
      if (init) {
        state.report = init.report || null;
        state.settings = init.settings || null;
        state.generating = !!init.generating;
      }
    } catch (e) {}
    if (init && init.open_settings) { setView("settings"); return; }
    render();
  }

  if (hasBridge()) boot();
  else window.addEventListener("pywebviewready", boot);
  // fallback p/ navegador (sem bridge): renderiza mock
  setTimeout(() => { if (!content.innerHTML) boot(); }, 50);

  // ---------------------------------------------------------------- //
  // MOCK (apenas quando aberto sem a bridge Python)
  // ---------------------------------------------------------------- //
  const MOCK = {
    get_initial: () => ({ report: MOCK._report(), generating: false }),
    get_report: () => MOCK._report(),
    list_history: () => ([
      { day: "2026-06-19", subtitle: "sexta-feira", commits: 7 },
      { day: "2026-06-18", subtitle: "quinta-feira", commits: 3 },
      { day: "2026-06-17", subtitle: "quarta-feira", commits: 11 },
    ]),
    get_settings: () => ({
      folders: ["C:\\Users\\jojob\\OneDrive\\Documentos\\Projetos\\Mappex", "C:\\Users\\jojob\\OneDrive\\Documentos\\Projetos\\Other"],
      scan_subfolders: true, max_scan_depth: 3, git_author_emails: [],
      github_enabled: true, github_username: "joaopecouto", github_token: "ghp_xxx", github_include_private: true,
      gemini_api_key: "AIza_xxx", gemini_text_model: "gemini-2.5-flash", gemini_image_model: "gemini-2.5-flash-image", gemini_image_enabled: true,
      language: "pt-BR", linkedin_tone: "primeira pessoa, autêntico, sem jargão corporativo", style_reference_file: "",
      photo_sources: ["project", "stock"], stock_provider: "pexels", stock_api_key: "",
      schedule_time: "18:00", run_on_weekends: false, autostart: true, show_notifications: true, auto_open_report: true,
      missing: [],
    }),
    run_recap: () => { setTimeout(() => window.devrecapPush({ generating: false, report: MOCK._report(), toast: "Recap gerado!" }), 1200); return true; },
    regenerate: (opts) => {
      setTimeout(() => {
        const rep = MOCK._report();
        const sel = (opts && opts.repos && opts.repos.length) ? opts.repos : rep.focus.repos.map((r) => r.name);
        rep.focus.repos.forEach((r) => { r.selected = sel.includes(r.name); });
        rep.focus.post_length = (opts && opts.post_length) || rep.focus.post_length;
        rep.repos = rep.repos.filter((r) => sel.includes(r.name));
        rep.insights.linkedin_post = "Foco de hoje: " + sel.join(", ") + ". Fechei a base e resolvi o threading da janela. Curtinho: progresso pequeno também é progresso.";
        window.devrecapPush({ generating: false, report: rep, toast: "Texto regenerado!" });
      }, 900);
      return true;
    },
    save_settings: () => ({ ok: true, missing: [] }),
    test_stock: (prov, key) => key ? { ok: true, message: (prov || "pexels") + ": chave OK — a busca funcionou." } : { ok: false, message: "Sem API key." },
    test_gemini: (key) => key ? { ok: true, message: "Gemini OK (gemini-2.5-flash)." } : { ok: false, message: "Sem API key do Gemini." },
    pick_folder: () => "C:\\Users\\jojob\\OneDrive\\Documentos\\Projetos\\NovoProjeto",
    open_path: () => true, open_url: (u) => { window.open(u, "_blank"); return true; }, copy: () => true,
    _report: () => ({
      day: "2026-06-19", subtitle: "sexta-feira · gerado às 18:00",
      live: true,
      focus: { post_length: "curto", repos: [
        { name: "DevRecap", commits: 6, selected: true },
        { name: "Mappex", commits: 1, selected: true },
      ] },
      notes: ["Banco de fotos (unsplash): chave inválida ou limite atingido (HTTP 401)."],
      insights: {
        linkedin_post: "Terminei o app que resume meu dia de dev sozinho: lê os commits, monta o resumo e já sugere o rascunho do post — tipo esse aqui.\n\nO chato foi o threading entre a bandeja e a janela. Progresso pequeno e constante > sprint heroico.",
        linkedin_hashtags: ["python", "devtools", "buildinpublic"],
        technologies: ["Python", "pywebview", "Tkinter", "APScheduler", "Gemini API", "pystray"],
        summary: "Construí e validei a base do DevRecap: coleta de atividade (git local + GitHub), pipeline de IA com o Gemini e a primeira versão da UI na bandeja do Windows.",
        progress: "Base sólida no ar — todos os módulos integram e os testes de fumaça passam. Falta polir a UI e conectar as chaves reais.",
        value_added: "Automatiza um ritual diário (anotar o que fiz + escrever no LinkedIn) que normalmente eu pulava. Vira consistência sem esforço.",
        bullet_highlights: [
          "Pipeline completo coleta→IA→fotos→relatório funcionando ponta a ponta",
          "Integração com a REST API do GitHub (commits, PRs e issues do dia)",
          "Agendamento diário às 18:00 com APScheduler",
          "Ícone na bandeja + autostart no Windows sem admin",
        ],
        model: "gemini-2.5-flash",
      },
      photos: [
        { source: "project", caption: "screenshot.png (DevRecap)", display_url: "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&q=80", local_path: "C:\\...\\assets\\screenshot.png" },
        { source: "stock", attribution: "Foto de Christina Morillo no Pexels", display_url: "https://images.unsplash.com/photo-1461749280684-dccba630e2f6?w=600&q=80", url: "https://pexels.com/photo/123" },
      ],
      totals: { commits: 7, repos: 2, insertions: 842, deletions: 96, files: 23, languages: [[".py", 14], [".css", 3], [".js", 2], [".md", 4]] },
      repos: [
        { name: "DevRecap", is_dirty: true, insertions: 720, deletions: 40, commits: [
          { sha: "a1b2c3d4e5", subject: "feat: pipeline de recap (coleta→IA→fotos)" },
          { sha: "b2c3d4e5f6", subject: "feat: UI na bandeja + agendamento 18:00" },
          { sha: "c3d4e5f6a7", subject: "fix: data de commit coerente com o filtro do dia" },
        ] },
        { name: "Mappex", insertions: 122, deletions: 56, commits: [
          { sha: "d4e5f6a7b8", subject: "chore: ajustes na sidebar" },
        ] },
      ],
    }),
  };
})();
