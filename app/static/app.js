/* Site do buffet: JavaScript puro, sem framework nem etapa de build.
 *
 * 1. Utilitários (criação de elementos, datas, avisos)
 * 2. Comunicação com a API e sessão
 * 3. Estrutura das páginas (cabeçalho, rodapé, rotas)
 * 4. Site público: início, portfólio, evento
 * 5. Entrar, cadastro e pedido de orçamento
 * 6. Área do cliente e conversa
 * 7. Painel da administração
 */
"use strict";

/* ===================== 1. Utilitários ===================== */

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "html") el.innerHTML = value; // usado só com SVG fixo deste arquivo
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function fill(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

const ICONS = {
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  left: '<path d="M15 5l-7 7 7 7"/>',
  right: '<path d="M9 5l7 7-7 7"/>',
  send: '<path d="M5 12l14-7-5 14-3-6-6-1z"/>',
  chat: '<path d="M5 5h14v10H9l-4 4z"/>',
  photo: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-8 8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  whatsapp: '<path d="M4 20l1.3-4A8 8 0 1 1 8 18.7z"/><path d="M9 9.5c.5 2 2.5 4 4.5 4.5l1.2-1.2 2 1-1 1.8c-3.5 0-7.8-4.3-7.8-7.8l1.8-1 1 2z"/>',
  up: '<path d="M5 15l7-7 7 7"/>',
  down: '<path d="M5 9l7 7 7-7"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
};

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name];
  return svg;
}

const media = (id) => (typeof id === "string" ? id : id ? `/media/${id}` : null); // id ou endereço pronto

function img(id, alt = "", attrs = {}) {
  if (!id) return null;
  return h("img", { src: media(id), alt, loading: "lazy", decoding: "async", ...attrs });
}

/** Texto com parágrafos separados por linha em branco. */
function paragraphs(text) {
  return String(text || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean).map((p) => h("p", null, p));
}

const DATE_LONG = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const DATE_SHORT = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const MONTH_YEAR = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" });
const TIME = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });
const DAY = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long" });

const isoDate = (s) => (s ? new Date(`${s}T12:00:00Z`) : null);
const fmtDate = (s) => (s ? DATE_LONG.format(isoDate(s)) : "");
const fmtShort = (s) => (s ? DATE_SHORT.format(isoDate(s)) : "");
const fmtMonth = (s) => (s ? MONTH_YEAR.format(isoDate(s)) : "");

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  const same = (a, b) => a.toDateString() === b.toDateString();
  if (same(date, today)) return "Hoje";
  if (same(date, yesterday)) return "Ontem";
  return DAY.format(date);
}

function relative(isoString) {
  const date = new Date(isoString);
  const minutes = Math.round((Date.now() - date) / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  if (dayLabel(date) === "Hoje") return TIME.format(date);
  if (dayLabel(date) === "Ontem") return "ontem";
  return DATE_SHORT.format(date).slice(0, 5);
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function maskPhone(value) {
  const d = value.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d ? `(${d}` : "";
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

function whatsappLink(phone) {
  const digits = String(phone || "").replace(/\D/g, "");
  return digits.length >= 10 ? `https://wa.me/55${digits}` : null;
}

function toast(message, kind = "info") {
  const el = h("div", { class: `toast${kind === "error" ? " toast--error" : ""}`, role: kind === "error" ? "alert" : "status" }, message);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}

const loading = () => h("div", { class: "loading", role: "status" }, h("div", { class: "spinner", "aria-label": "Carregando" }));

function debounce(fn, wait = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

/* ---------- Formulários ---------- */

let fieldSeq = 0;

function field({ label, name, as = "input", hint, options, ...attrs }) {
  const id = `f-${name}-${++fieldSeq}`;
  let control;
  if (as === "select") {
    control = h("select", { id, name, class: "input", ...attrs },
      options.map(([value, text]) => h("option", { value, selected: String(value) === String(attrs.value ?? "") }, text)));
  } else if (as === "textarea") {
    const { value, ...rest } = attrs;
    control = h("textarea", { id, name, class: "input", ...rest });
    control.value = value ?? "";
  } else {
    control = h("input", { id, name, class: "input", ...attrs });
  }
  return h("div", { class: "field" },
    h("label", { class: "field__label", for: id }, label),
    control,
    hint && h("p", { class: "field__hint" }, hint),
    h("p", { class: "field__error", "data-error-for": name, "aria-live": "polite" }));
}

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function clearErrors(form) {
  form.querySelectorAll("[data-error-for]").forEach((el) => (el.textContent = ""));
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  const general = form.querySelector(".form__error");
  if (general) general.textContent = "";
}

/** Mostra os erros da API ao lado de cada campo (ou no topo, quando não há campo). */
function showErrors(form, err) {
  clearErrors(form);
  let placed = false;
  for (const e of err.errors || []) {
    const slot = form.querySelector(`[data-error-for="${CSS.escape(e.field)}"]`);
    if (slot) {
      slot.textContent = e.message;
      const control = form.elements[e.field];
      const el = control instanceof Element ? control : control?.[0]; // grupo de opções: o 1º item
      if (control instanceof Element) control.setAttribute("aria-invalid", "true");
      if (!placed) el?.focus();
      placed = true;
    }
  }
  if (!placed) {
    const general = form.querySelector(".form__error");
    if (general) {
      general.textContent = err.message;
      general.focus?.();
    } else toast(err.message, "error");
  }
}

async function submitting(form, task) {
  const button = form.querySelector('[type="submit"]');
  const original = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "Enviando…";
  }
  clearErrors(form);
  try {
    return await task();
  } catch (err) {
    if (err.status !== 401 || form.dataset.auth) showErrors(form, err);
    return undefined;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

/* ---------- Diálogo ---------- */

function openModal(title, build, { onClose, className = "" } = {}) {
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    onClose?.(); // devolve ao formulário o que estava na aba, antes de ela sumir
    dialog.close();
    dialog.remove();
  };
  const dialog = h("dialog", { class: `modal ${className}`.trim(), "aria-label": title });
  dialog.append(
    h("div", { class: "modal__head" }, h("h2", null, title),
      h("button", { class: "icon-btn", type: "button", "aria-label": "Fechar", onclick: close }, icon("close"))),
    h("div", { class: "modal__body" }, build(close)));
  dialog.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  document.body.append(dialog);
  dialog.showModal();
  dialog.querySelector("input, textarea, select")?.focus();
  return close;
}

/* ===================== 2. API e sessão ===================== */

const TOKEN_KEY = "buffet.token";

class ApiError extends Error {
  constructor(status, message, errors = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

const api = {
  get token() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set token(value) {
    try {
      if (value) localStorage.setItem(TOKEN_KEY, value);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* navegador sem armazenamento: a sessão dura até fechar a aba */
    }
    memoryToken = value;
  },

  async request(method, path, { json, form, body } = {}) {
    const headers = {};
    const token = this.token || memoryToken;
    if (token) headers.Authorization = `Bearer ${token}`;
    let payload = body;
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(json);
    } else if (form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      payload = new URLSearchParams(form);
    }
    let response;
    try {
      response = await fetch(path, { method, headers, body: payload });
    } catch {
      throw new ApiError(0, "Sem conexão com o servidor. Confira a internet e tente de novo.");
    }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && token && path !== "/auth/token") {
        session.clear();
        toast("Sua sessão expirou. Entre novamente.", "error");
        go(`/entrar?volta=${encodeURIComponent(currentPath())}`);
      }
      const message = typeof data.detail === "string" ? data.detail
        : response.status === 413 ? "Arquivo grande demais." : "Não foi possível concluir. Tente de novo.";
      throw new ApiError(response.status, message, data.errors || []);
    }
    return data;
  },

  get(path, params) {
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== "") query.set(k, v);
    const qs = query.toString();
    return this.request("GET", qs ? `${path}?${qs}` : path);
  },
  post: (path, json) => api.request("POST", path, { json }),
  put: (path, json) => api.request("PUT", path, { json }),
  patch: (path, json) => api.request("PATCH", path, { json }),
  del: (path) => api.request("DELETE", path),

  upload(file) {
    const data = new FormData();
    data.append("file", file);
    return this.request("POST", "/admin/images", { body: data });
  },
  sendPhoto(quoteId, file, caption = "") {
    const data = new FormData();
    data.append("file", file);
    if (caption) data.append("caption", caption);
    return this.request("POST", `/quotes/${quoteId}/photos`, { body: data });
  },
};

let memoryToken = null;

const state = { user: null, site: null, demo: false, unread: { unread: 0, new_quotes: 0 } };

const session = {
  async login(email, password) {
    const data = await api.request("POST", "/auth/token", { form: { username: email, password } });
    api.token = data.access_token;
    state.user = await api.get("/auth/me");
    refreshUnread();
    return state.user;
  },
  async restore() {
    if (!(api.token || memoryToken)) return;
    try {
      state.user = await api.get("/auth/me");
    } catch {
      api.token = null;
    }
  },
  clear() {
    api.token = null;
    state.user = null;
    state.unread = { unread: 0, new_quotes: 0 };
  },
  logout() {
    this.clear();
    toast("Você saiu da sua conta.");
    go("/");
  },
};

const isOwner = () => state.user?.role === "owner";

async function refreshUnread() {
  if (!state.user) return;
  try {
    state.unread = await api.get("/quotes/unread");
    document.querySelectorAll("[data-unread]").forEach(paintBadge);
  } catch {
    /* tenta de novo no próximo ciclo */
  }
}

function paintBadge(el) {
  const n = isOwner() ? state.unread.unread + state.unread.new_quotes : state.unread.unread;
  el.textContent = n > 99 ? "99+" : String(n);
  el.hidden = n === 0;
  el.setAttribute("aria-label", plural(n, "novidade", "novidades"));
}

setInterval(() => {
  if (document.visibilityState === "visible") refreshUnread();
}, 20000);

/* ===================== 3. Estrutura e rotas ===================== */

const root = () => document.getElementById("root");
const currentPath = () => location.hash.replace(/^#/, "") || "/";
const go = (path) => {
  if (currentPath() === path) render();
  else location.hash = `#${path}`;
};

/* Tarefas da tela atual (consulta de mensagens, ouvintes) que param ao trocar de página. */
let cleanups = [];
const onLeave = (fn) => cleanups.push(fn);

/** Logo da marca: versão vinho no fundo claro e branca sobre a foto da capa. */
function brandLogo(name = "") {
  return h("a", { class: "brand brand--logo", href: "#/", "aria-label": `${name}, início` },
    h("img", { class: "brand__light", src: "/static/marca-clara.png", alt: name, width: 221, height: 75 }),
    h("img", { class: "brand__dark", src: "/static/marca-escura.png", alt: "", width: 221, height: 75 }));
}

function header({ over = false } = {}) {
  const site = state.site;
  const bar = h("header", { class: `topbar${over ? " topbar--over" : ""}` });
  const nav = h("nav", { class: "nav", "aria-label": "Principal" },
    h("a", { href: "#/" }, "Início"),
    h("a", { href: "#/sobre" }, "Sobre"),
    h("a", { href: "#/historia" }, "Nossa história"),
    h("a", { href: "#/portfolio" }, "Portfólio"),
    h("a", { href: "#/contato" }, "Contato"));
  nav.addEventListener("click", () => bar.classList.remove("is-open"));

  let account;
  if (state.user) {
    const badge = h("span", { class: "badge", "data-unread": true });
    paintBadge(badge);
    account = h("a", { class: "account-link", href: isOwner() ? "#/painel" : "#/conta" },
      icon("user"), h("span", null, isOwner() ? "Painel" : "Minha conta"), badge);
  } else {
    account = h("a", { class: "account-link", href: "#/entrar" }, icon("user"), h("span", null, "Entrar"));
  }

  fill(bar, h("div", { class: "wrap topbar__inner" },
    brandLogo(site?.business_name),
    nav,
    h("button", {
      class: "menu-btn", type: "button", "aria-label": "Abrir menu", "aria-expanded": "false",
      onclick: (e) => {
        const open = bar.classList.toggle("is-open");
        e.currentTarget.setAttribute("aria-expanded", String(open));
      },
    }, icon("menu")),
    h("div", { class: "topbar__actions" },
      account,
      !isOwner() && h("a", { class: "btn btn--primary btn--small", href: "#/orcamento" }, "Agendar evento"))));

  const onScroll = () => bar.classList.toggle("is-scrolled", window.scrollY > 24);
  window.addEventListener("scroll", onScroll, { passive: true });
  onLeave(() => window.removeEventListener("scroll", onScroll));
  onScroll();
  return bar;
}

function footer() {
  const s = state.site;
  const wa = whatsappLink(s.phone);
  return h("footer", { class: "footer", id: "contato" },
    h("div", { class: "wrap" },
      h("div", { class: "footer__grid" },
        h("div", { style: "display:grid;gap:10px" },
          h("a", { class: "brand brand--logo", href: "#/", "aria-label": `${s.business_name}, início` },
            h("img", { src: "/static/marca-escura.png", alt: s.business_name, width: 221, height: 75 })),
          h("p", { style: "max-width:42ch" }, s.tagline)),
        (s.phone || s.email || s.instagram || s.city) && h("div", null, h("h4", null, "Contato"),
          h("ul", null,
            s.phone && h("li", null, wa ? h("a", { href: wa, target: "_blank", rel: "noopener" }, s.phone) : s.phone),
            s.email && h("li", null, h("a", { href: `mailto:${s.email}` }, s.email)),
            s.instagram && h("li", null, h("a", { href: `https://instagram.com/${encodeURIComponent(s.instagram)}`, target: "_blank", rel: "noopener" }, `@${s.instagram}`)),
            s.city && h("li", null, s.city))),
        h("div", null, h("h4", null, "Navegue"),
          h("ul", null,
            h("li", null, h("a", { href: "#/portfolio" }, "Portfólio")),
            h("li", null, h("a", { href: "#/orcamento" }, "Pedir orçamento")),
            h("li", null, h("a", { href: state.user ? (isOwner() ? "#/painel" : "#/conta") : "#/entrar" }, state.user ? "Minha área" : "Entrar"))))),
      h("div", { class: "footer__bottom" },
        h("span", null, `© ${new Date().getFullYear()} ${s.business_name}`),
        h("a", { href: "/docs" }, "API do site"))));
}

function publicPage(content, opts = {}) {
  fill(root(),
    h("a", { class: "skip", href: "#conteudo", onclick: (e) => { e.preventDefault(); document.getElementById("conteudo")?.focus(); } }, "Pular para o conteúdo"),
    header(opts), h("main", { id: "conteudo", tabindex: "-1" }, content), footer());
}

const ROUTES = [
  [/^\/$/, () => renderHome()],
  [/^\/(sobre|historia|contato)$/, (m) => renderHome(m[1])],
  [/^\/portfolio$/, (m, q) => renderPortfolio(q)],
  [/^\/portfolio\/(\d+)$/, (m) => renderEvent(Number(m[1]))],
  [/^\/entrar$/, (m, q) => renderAuth("login", q)],
  [/^\/cadastro$/, (m, q) => renderAuth("register", q)],
  [/^\/orcamento$/, () => renderQuoteForm()],
  [/^\/conta$/, () => renderAccount()],
  [/^\/conta\/pedidos\/(\d+)$/, (m) => renderAccount(Number(m[1]))],
  [/^\/painel$/, () => renderAdmin("pedidos")],
  [/^\/painel\/pedidos\/(\d+)$/, (m) => renderAdmin("pedidos", Number(m[1]))],
  [/^\/painel\/(portfolio|site|clientes)$/, (m) => renderAdmin(m[1])],
];

let renderSeq = 0;

async function render() {
  cleanups.forEach((fn) => fn());
  cleanups = [];
  document.querySelectorAll("dialog.modal, .lightbox").forEach((el) => el.remove());
  const seq = ++renderSeq;
  const [path, queryString] = currentPath().split("?");
  const query = new URLSearchParams(queryString || "");
  const match = ROUTES.map(([re, fn]) => [path.match(re), fn]).find(([m]) => m);
  if (!match) return go("/");
  await match[1](match[0], query, seq);
}

const isCurrent = (seq) => seq === renderSeq;

async function boot() {
  fill(root(), loading());
  try {
    const [site, health] = await Promise.all([api.get("/site"), api.get("/health"), session.restore()]);
    state.site = site;
    state.demo = Boolean(health?.demo);
    document.title = site.business_name;
  } catch (err) {
    fill(root(), h("div", { class: "loading" }, err.message));
    return;
  }
  refreshUnread();
  window.addEventListener("hashchange", () => {
    window.scrollTo(0, 0);
    render();
  });
  render();
}

/* ===================== 4. Site público ===================== */

const EVENT_ICONS = {
  Casamento: '<circle cx="9" cy="14" r="5"/><circle cx="15" cy="14" r="5"/><path d="M10 5l2-2 2 2"/>',
  "Aniversário": '<path d="M4 20h16v-7H4z"/><path d="M4 16c2 1.5 4 1.5 6 0s4-1.5 6 0 3 1 4 0"/><path d="M12 13V9M12 6.5a1 1 0 0 1 0-2c.5.6.5 1.4 0 2z"/>',
  "15 anos": '<path d="M5 18h14l1-9-5 4-3-6-3 6-5-4z"/><path d="M5 21h14"/>',
  Corporativo: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2M3 12h18"/>',
  Batizado: '<path d="M4.2 10.6c0-1.7 1.2-2.9 2.8-2.9 1.2 0 2.1.6 2.6 1.6l1.2 2c1.6-.3 3.2.2 4.4 1.3l4.6 1.1-2.7 1.7c-.9 2.3-3.1 3.8-5.8 3.8-3.3 0-5.6-2.4-6-5.4"/><path d="M4.2 10.6L2.3 11.4l2.1.5"/><path d="M10.8 11.5c.3-3.5 2.5-6.2 6.2-7.3 0 3.2-1.4 5.8-4.1 7.6"/><circle cx="6.9" cy="9.9" r=".45" fill="currentColor" stroke="none"/>',
  "Chá de bebê": '<path d="M10.6 6V4.4a1.4 1.4 0 0 1 2.8 0V6"/><rect x="8.5" y="6" width="7" height="2.4" rx="1"/><path d="M9.2 8.4h5.6l.7 2.6v8.3a1.7 1.7 0 0 1-1.7 1.7h-3.6a1.7 1.7 0 0 1-1.7-1.7V11z"/><path d="M11 12.8h2.2M11 15.6h2.2M11 18.2h1.4"/>',
  Formatura: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5M22 9v6"/>',
  Outro: '<path d="M12 3l2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z"/>',
};

function eventIcon(type) {
  const svg = icon("photo");
  svg.innerHTML = EVENT_ICONS[type] || EVENT_ICONS.Outro;
  return svg;
}

const firstName = (name, fallback = "") => (name ? name.split(" ")[0] : fallback);
const NUMBER = new Intl.NumberFormat("pt-BR");

/** Título com a parte depois da última vírgula em itálico: "Sua festa…, *e serviço…*". */
function accentTitle(text) {
  const cut = text.lastIndexOf(",");
  if (cut < 8 || cut > text.length - 6) return text;
  return [text.slice(0, cut + 1), " ", h("em", null, text.slice(cut + 1).trim())];
}

/** Anima a entrada dos blocos marcados com .reveal e os contadores com [data-count]. */
function animateOnScroll(scope = document) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const items = scope.querySelectorAll(".reveal, [data-count]");
  if (reduce || !("IntersectionObserver" in window)) {
    items.forEach((el) => {
      el.classList.add("is-in");
      if (el.dataset.count) el.textContent = NUMBER.format(Number(el.dataset.count));
    });
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const el = entry.target;
      observer.unobserve(el);
      el.classList.add("is-in");
      if (el.dataset.count) countUp(el, Number(el.dataset.count));
    }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
  items.forEach((el) => observer.observe(el));
  onLeave(() => observer.disconnect());
}

function countUp(el, target) {
  const start = performance.now();
  const duration = 1400;
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = NUMBER.format(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function sectionHead(eyebrow, title, lede, id, center = false) {
  return h("div", { class: `section__head reveal${center ? " section__head--center" : ""}` },
    h("p", { class: "eyebrow" }, eyebrow),
    h("h2", { class: "section__title", id }, title),
    lede && h("p", { class: "section__lede" }, lede));
}

async function renderHome(anchor) {
  const s = state.site;
  document.title = `${s.business_name} | ${s.tagline || "Buffet"}`;
  const occasions = h("div", { class: "occasions" });
  const featured = h("div", { class: "featured" }, loading());
  const years = s.founded_year ? new Date().getFullYear() - s.founded_year : 0;
  const ownerFirst = firstName(s.owner_name, "a gente");

  const stats = [
    years > 0 && [years, years === 1 ? "ano de história" : "anos de história"],
    s.stats.events > 0 && [s.stats.events, s.stats.events === 1 ? "evento no portfólio" : "eventos no portfólio"],
    s.stats.guests > 0 && [s.stats.guests, "convidados nesses eventos"],
    s.stats.photos > 0 && [s.stats.photos, "fotos para você conhecer"],
  ].filter(Boolean);

  const marqueeWords = [...new Set(s.event_types.filter((t) => t !== "Outro"))];
  const marqueeRow = () => h("div", { class: "marquee__row", "aria-hidden": "true" },
    marqueeWords.map((w) => [h("span", null, w), h("span", { class: "marquee__dot" }, "✦")]));

  const paragraphsWithCap = (text) => {
    const ps = paragraphs(text);
    if (ps[0]) ps[0].classList.add("dropcap");
    return ps;
  };

  publicPage([
    h("section", { class: `hero${s.hero_image_id ? "" : " hero--plain"}`, "aria-label": "Apresentação" },
      s.hero_image_id ? h("img", { class: "hero__img", src: media(s.hero_image_id), alt: "", fetchpriority: "high" }) : null,
      h("div", { class: "wrap hero__content" },
        s.tagline && h("p", { class: "hero__eyebrow" }, h("span", null, s.tagline)),
        h("h1", { class: "hero__title" }, accentTitle(s.hero_title || s.business_name)),
        s.hero_text && h("p", { class: "hero__text" }, s.hero_text),
        h("div", { class: "hero__actions" },
          h("a", { class: "btn btn--primary btn--lg", href: "#/orcamento" }, "Agendar evento"),
          h("a", { class: "btn btn--outline-light btn--lg", href: "#/portfolio" }, "Ver portfólio"))),
      h("a", { class: "hero__scroll", href: "#/sobre", "aria-label": "Conhecer mais" }, h("span", null, "Conheça"), icon("down"))),

    stats.length > 0 && h("section", { class: "stats", "aria-label": "Em números" },
      h("div", { class: "wrap stats__grid" },
        stats.map(([n, label]) => h("div", { class: "stat reveal" },
          h("strong", { class: "stat__n", "data-count": n }, "0"),
          h("span", { class: "stat__label" }, label))))),

    marqueeWords.length > 2 && h("div", { class: "marquee", role: "presentation" },
      h("div", { class: "marquee__track" }, marqueeRow(), marqueeRow())),

    h("section", { class: "section", id: "sobre", "aria-labelledby": "t-sobre" },
      h("div", { class: "wrap" },
        h("div", { class: "about" },
          s.owner_image_id && h("figure", { class: "about__photo reveal" },
            img(s.owner_image_id, s.owner_name),
            s.founded_year && h("figcaption", { class: "about__badge" }, h("small", null, "Desde"), s.founded_year)),
          h("div", { class: "about__text reveal" },
            h("p", { class: "eyebrow" }, "Quem cozinha para você"),
            h("h2", { class: "about__name", id: "t-sobre" }, s.owner_name || "Sobre mim"),
            s.owner_role && h("p", { class: "about__role" }, s.owner_role),
            h("div", { class: "prose" }, paragraphsWithCap(s.bio)),
            s.owner_name && h("p", { class: "signature" }, firstName(s.owner_name)))),
        s.bio_photos.length > 0 && h("div", { class: `collage collage--${Math.min(s.bio_photos.length, 3)}` },
          s.bio_photos.map((p) => h("figure", { class: "reveal" }, img(p.image_id, p.caption), p.caption && h("figcaption", null, p.caption)))))),

    h("section", { class: "section section--sand", id: "historia", "aria-labelledby": "t-historia" },
      h("div", { class: "wrap history" },
        h("div", { class: "history__text reveal" },
          s.founded_year && h("p", { class: "history__year" }, h("small", null, "Desde"), s.founded_year),
          h("h2", { class: "section__title", id: "t-historia" }, s.history_title || "Nossa história"),
          h("div", { class: "prose" }, paragraphs(s.history))),
        s.history_image_id && h("figure", { class: "history__img reveal" }, img(s.history_image_id, "")))),

    h("section", { class: "section", "aria-labelledby": "t-ocasioes" },
      h("div", { class: "wrap" },
        sectionHead("Para cada ocasião", "Do brinde ao último doce", "Cardápio, montagem e serviço pensados para o tipo de festa que você vai receber.", "t-ocasioes"),
        occasions)),

    h("section", { class: "section section--tight", "aria-labelledby": "t-portfolio" },
      h("div", { class: "wrap" },
        h("div", { class: "section__row" },
          sectionHead("Portfólio", "Eventos que já servimos", null, "t-portfolio"),
          h("a", { class: "link-arrow reveal", href: "#/portfolio" }, "Ver todos os eventos", icon("right"))),
        featured)),

    h("section", { class: "section section--dark", "aria-labelledby": "t-como" },
      h("div", { class: "wrap" },
        sectionHead("Orçamento", "Como pedir o seu orçamento", "A conversa acontece aqui no site e fica guardada na sua conta. Nada de mensagem perdida.", "t-como"),
        h("ol", { class: "steps" },
          h("li", { class: "step reveal" }, h("h3", null, "Crie sua conta"), h("p", null, "Nome, e-mail, telefone e cidade. Leva um minuto.")),
          h("li", { class: "step reveal" }, h("h3", null, "Conte sobre o evento"), h("p", null, "Tipo de festa, data, convidados, local e o que você imagina.")),
          h("li", { class: "step reveal" }, h("h3", null, `Converse com ${ownerFirst}`), h("p", null, "A resposta chega aqui mesmo. Você acompanha tudo pela sua conta."))))),

    h("section", { class: "cta-band", "aria-labelledby": "t-cta" },
      (s.hero_image_id || s.history_image_id) && h("img", { src: media(s.hero_image_id || s.history_image_id), alt: "", loading: "lazy" }),
      h("div", { class: "wrap cta-band__inner reveal" },
        h("p", { class: "eyebrow" }, "Vamos conversar?"),
        h("h2", { id: "t-cta" }, "Conte como você imagina a sua festa"),
        h("a", { class: "btn btn--light btn--lg", href: "#/orcamento" }, "Agendar evento"))),
  ], { over: Boolean(s.hero_image_id) });

  animateOnScroll();
  if (anchor) requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView());

  let events = [];
  try {
    events = await api.get("/events", { limit: 200 });
  } catch {
    /* mostra o vazio abaixo */
  }
  const byType = new Map();
  for (const e of events) {
    if (!byType.has(e.event_type)) byType.set(e.event_type, { cover: null, count: 0 });
    const t = byType.get(e.event_type);
    t.count += 1;
    t.cover ||= e.photos[0]?.image_id;
  }
  fill(occasions, byType.size
    ? [...byType.entries()].slice(0, 6).map(([type, info]) => h("a", { class: "occasion reveal", href: `#/portfolio?tipo=${encodeURIComponent(type)}` },
      info.cover && img(info.cover, ""),
      h("div", { class: "occasion__body" },
        h("span", { class: "occasion__icon" }, eventIcon(type)),
        h("h3", null, type),
        h("p", null, plural(info.count, "evento", "eventos"), " no portfólio"))))
    : s.event_types.slice(0, 6).map((type) => h("div", { class: "occasion occasion--plain reveal" },
      h("div", { class: "occasion__body" }, h("span", { class: "occasion__icon" }, eventIcon(type)), h("h3", null, type)))));

  fill(featured, events.length
    ? events.slice(0, 3).map((e, i) => eventCard(e, i === 0 ? "card--wide" : ""))
    : h("div", { class: "empty" }, "Os primeiros eventos aparecem aqui em breve."));
  animateOnScroll(occasions.parentElement);
  animateOnScroll(featured);
}

function eventCard(e, extra = "") {
  const cover = e.photos[0]?.image_id;
  const meta = [e.event_date && fmtMonth(e.event_date), e.guests && plural(e.guests, "convidado", "convidados")].filter(Boolean).join(" · ");
  return h("a", { class: `card reveal ${extra}`, href: `#/portfolio/${e.id}` },
    h("div", { class: "card__img" },
      cover ? img(cover, e.title) : h("div", { class: "loading" }, icon("photo")),
      h("div", { class: "card__overlay" },
        h("span", { class: "card__type" }, e.event_type),
        h("h3", { class: "card__title" }, e.title),
        meta && h("p", { class: "card__meta" }, meta)),
      e.photos.length > 1 && h("span", { class: "card__count" }, icon("photo"), e.photos.length)));
}

async function renderPortfolio(query) {
  document.title = `Portfólio | ${state.site.business_name}`;
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Filtrar por tipo de evento" });
  const grid = h("div", { class: "masonry" }, loading());
  publicPage(h("div", { class: "wrap", style: "padding-bottom:96px" },
    h("div", { class: "page-head page-head--center" },
      h("p", { class: "eyebrow" }, "Portfólio"),
      h("h1", null, "Eventos que ", h("em", null, "já servimos")),
      h("p", { class: "section__lede" }, "Clique em um evento para ver todas as fotos.")),
    chips, grid));

  let all;
  try {
    all = await api.get("/events", { limit: 200 });
  } catch (err) {
    fill(grid, h("div", { class: "empty" }, err.message));
    return;
  }
  const types = [...new Set(all.map((e) => e.event_type))];
  let current = types.includes(query?.get("tipo")) ? query.get("tipo") : "";
  const draw = () => {
    fill(chips, ["", ...types].map((t) => h("button", {
      class: "chip", type: "button", "aria-pressed": String(current === t),
      onclick: () => {
        current = t;
        history.replaceState(null, "", t ? `#/portfolio?tipo=${encodeURIComponent(t)}` : "#/portfolio");
        draw();
      },
    }, t || "Todos", h("small", null, t ? all.filter((e) => e.event_type === t).length : all.length))));
    const list = all.filter((e) => !current || e.event_type === current);
    fill(grid, list.length ? list.map((e) => eventCard(e)) : h("div", { class: "empty" }, "Nenhum evento publicado ainda."));
    animateOnScroll(grid);
  };
  draw();
}

async function renderEvent(id) {
  const area = h("div", null, loading());
  publicPage(area);
  let e, all;
  try {
    [e, all] = await Promise.all([api.get(`/events/${id}`), api.get("/events", { limit: 200 }).catch(() => [])]);
  } catch (err) {
    fill(area, h("div", { class: "wrap", style: "padding:80px 0" },
      h("div", { class: "empty" }, err.message, h("a", { class: "btn btn--ghost", href: "#/portfolio" }, "Voltar ao portfólio"))));
    return;
  }
  document.title = `${e.title} | ${state.site.business_name}`;
  const photos = e.photos.map((p) => p.image_id);
  const index = all.findIndex((x) => x.id === e.id);
  const prev = index > 0 ? all[index - 1] : null;
  const next = index >= 0 && index < all.length - 1 ? all[index + 1] : null;

  fill(area,
    h("header", { class: `event-hero${photos[0] ? "" : " event-hero--plain"}` },
      photos[0] && h("img", { src: media(photos[0]), alt: "" }),
      h("div", { class: "wrap event-hero__content" },
        h("a", { class: "back back--light", href: "#/portfolio" }, icon("left"), "Portfólio"),
        h("p", { class: "eyebrow" }, e.event_type),
        h("h1", null, e.title),
        h("ul", { class: "facts" },
          e.event_date && h("li", null, h("small", null, "Data"), fmtDate(e.event_date)),
          e.guests && h("li", null, h("small", null, "Convidados"), NUMBER.format(e.guests)),
          e.location && h("li", null, h("small", null, "Local"), e.location),
          photos.length > 0 && h("li", null, h("small", null, "Fotos"), photos.length)))),
    h("div", { class: "wrap event" },
      e.description && h("div", { class: "event__desc reveal" }, h("div", { class: "prose prose--lg" }, paragraphs(e.description))),
      photos.length ? h("div", { class: "masonry masonry--photos" },
        photos.map((imageId, i) => h("button", {
          class: "photo reveal", type: "button", "aria-label": `Ampliar foto ${i + 1} de ${photos.length}`,
          onclick: () => lightbox(photos, i, e.title),
        }, img(imageId, `${e.title}, foto ${i + 1}`)))) : null,
      (prev || next) && h("nav", { class: "pager-events", "aria-label": "Outros eventos" },
        prev ? h("a", { href: `#/portfolio/${prev.id}` }, h("small", null, "Anterior"), prev.title) : h("span"),
        next ? h("a", { href: `#/portfolio/${next.id}`, class: "is-next" }, h("small", null, "Próximo"), next.title) : h("span")),
      h("div", { class: "cta reveal" },
        h("h2", null, "Quer uma festa assim?"),
        h("a", { class: "btn btn--light", href: "#/orcamento" }, "Agendar evento"))));
  animateOnScroll(area);
}

function lightbox(ids, start, title) {
  let index = start;
  const picture = h("img", { alt: "" });
  const counter = h("span");
  const thumbs = h("div", { class: "lightbox__thumbs" },
    ids.map((id, i) => h("button", { type: "button", "aria-label": `Foto ${i + 1}`, onclick: () => { index = i; show(); } }, h("img", { src: media(id), alt: "" }))));
  const show = () => {
    picture.src = media(ids[index]);
    picture.alt = `${title}, foto ${index + 1}`;
    counter.textContent = `${index + 1} / ${ids.length}`;
    [...thumbs.children].forEach((b, i) => b.setAttribute("aria-current", String(i === index)));
    thumbs.children[index]?.scrollIntoView({ block: "nearest", inline: "center" });
  };
  const step = (d) => {
    index = (index + d + ids.length) % ids.length;
    show();
  };
  const close = () => {
    box.remove();
    document.removeEventListener("keydown", keys);
    document.body.style.overflow = "";
    opener?.focus();
  };
  const keys = (e) => {
    if (e.key === "Escape") close();
    if (e.key === "ArrowRight") step(1);
    if (e.key === "ArrowLeft") step(-1);
  };
  const opener = document.activeElement;
  const closeBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Fechar", onclick: close }, icon("close"));
  const stage = h("div", { class: "lightbox__stage", onclick: (e) => e.target === e.currentTarget && close() }, picture);
  let touchX = null;
  stage.addEventListener("touchstart", (e) => (touchX = e.touches[0].clientX), { passive: true });
  stage.addEventListener("touchend", (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1);
    touchX = null;
  });
  const box = h("div", { class: "lightbox", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "lightbox__top" }, h("span", { class: "lightbox__title" }, title), counter, closeBtn),
    stage,
    ids.length > 1 && thumbs,
    ids.length > 1 && h("button", { class: "lightbox__nav lightbox__nav--prev", type: "button", "aria-label": "Foto anterior", onclick: () => step(-1) }, icon("left")),
    ids.length > 1 && h("button", { class: "lightbox__nav lightbox__nav--next", type: "button", "aria-label": "Próxima foto", onclick: () => step(1) }, icon("right")));
  document.body.append(box);
  document.body.style.overflow = "hidden";
  show();
  document.addEventListener("keydown", keys);
  onLeave(close);
  closeBtn.focus();
}

/* ===================== 5. Entrar, cadastro e orçamento ===================== */

function splitPage(asideTitle, asideText, content) {
  const s = state.site;
  fill(root(), header(), h("main", { id: "conteudo", class: "split" },
    h("aside", { class: "split__aside" },
      s.hero_image_id && h("img", { src: media(s.hero_image_id), alt: "" }),
      h("div", null, h("h2", null, asideTitle), h("p", null, asideText))),
    h("div", { class: "split__main" }, content)));
}

function afterLogin(user, back) {
  if (user.role === "owner") return go(back && back.startsWith("/painel") ? back : "/painel");
  go(back && !back.startsWith("/painel") && !back.startsWith("/entrar") ? back : "/conta");
}

function renderAuth(mode, query) {
  const back = query.get("volta") || "";
  const isLogin = mode === "login";
  if (state.user) return afterLogin(state.user, back);
  document.title = `${isLogin ? "Entrar" : "Criar conta"} | ${state.site.business_name}`;
  const suffix = back ? `?volta=${encodeURIComponent(back)}` : "";

  const form = h("form", { class: "form", novalidate: true, "data-auth": "1" },
    h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
    !isLogin && field({ label: "Nome completo", name: "name", autocomplete: "name", required: true }),
    field({ label: "E-mail", name: "email", type: "email", autocomplete: "email", required: true }),
    !isLogin && h("div", { class: "form__row" },
      field({ label: "Telefone / WhatsApp", name: "phone", type: "tel", inputmode: "tel", autocomplete: "tel", placeholder: "(00) 00000-0000", required: true }),
      field({ label: "Cidade", name: "city", autocomplete: "address-level2", required: true })),
    field({ label: "Senha", name: "password", type: "password", autocomplete: isLogin ? "current-password" : "new-password", required: true, hint: isLogin ? null : "Pelo menos 8 caracteres." }),
    h("button", { class: "btn btn--primary btn--block", type: "submit" }, isLogin ? "Entrar" : "Criar minha conta"));

  form.elements.phone?.addEventListener("input", (e) => (e.target.value = maskPhone(e.target.value)));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const v = formValues(form);
    submitting(form, async () => {
      if (!isLogin) await api.post("/auth/register", { name: v.name, email: v.email, phone: v.phone, city: v.city, password: v.password });
      const user = await session.login(v.email, v.password);
      toast(isLogin ? `Olá, ${user.name.split(" ")[0]}!` : "Conta criada. Bem-vindo(a)!");
      afterLogin(user, back);
    });
  });

  const demo = state.demo && h("div", { class: "demo-box" },
    h("p", null, "Demonstração: entre com uma das contas de exemplo."),
    h("div", null,
      h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: () => demoLogin("marcos@cliente.dev") }, "Entrar como cliente"),
      h("button", { class: "btn btn--dark btn--small", type: "button", onclick: () => demoLogin("helena@buffet.dev") }, "Entrar como administração")));

  async function demoLogin(email) {
    try {
      afterLogin(await session.login(email, "demo12345"), back);
    } catch (err) {
      toast(err.message, "error");
    }
  }

  splitPage(
    back === "/orcamento" ? "Falta pouco para o seu orçamento" : `Bem-vindo(a) ao ${state.site.business_name}`,
    back === "/orcamento" ? "Entre ou crie sua conta para contar sobre o evento. A conversa fica guardada e você recebe a resposta aqui no site."
      : "Na sua conta você acompanha os pedidos de orçamento e conversa direto com a gente.",
    h("div", { class: "panel-card" },
      h("h1", null, isLogin ? "Entrar" : "Criar conta"),
      h("div", { class: "tabs", role: "tablist" },
        h("button", { type: "button", role: "tab", "aria-selected": String(isLogin), onclick: () => go(`/entrar${suffix}`) }, "Entrar"),
        h("button", { type: "button", role: "tab", "aria-selected": String(!isLogin), onclick: () => go(`/cadastro${suffix}`) }, "Criar conta")),
      demo, form));
  form.querySelector("input")?.focus();
}

function renderQuoteForm() {
  if (!state.user) return go(`/cadastro?volta=${encodeURIComponent("/orcamento")}`);
  if (isOwner()) {
    toast("Pedidos de orçamento são feitos pelos clientes. Veja os recebidos no painel.");
    return go("/painel");
  }
  const s = state.site;
  document.title = `Pedir orçamento | ${s.business_name}`;
  const STEPS = ["O evento", "Detalhes", "Revisar"];
  let current = 0;

  const typeTiles = h("div", { class: "tiles", role: "radiogroup", "aria-label": "Tipo de evento" },
    s.event_types.map((t) => h("label", { class: "tile" },
      h("input", { type: "radio", name: "event_type", value: t, class: "sr-only" }),
      h("span", { class: "tile__icon" }, eventIcon(t)), h("span", null, t))));

  const guests = h("input", { class: "input stepper__input", id: "f-guests", name: "guests", type: "number", min: 1, inputmode: "numeric", placeholder: "0" });
  const bump = (d) => {
    guests.value = Math.max(1, (Number(guests.value) || 0) + d);
    guests.dispatchEvent(new Event("input"));
  };
  const stepper = h("div", { class: "field" },
    h("label", { class: "field__label", for: "f-guests" }, "Número de convidados"),
    h("div", { class: "stepper" },
      h("button", { type: "button", "aria-label": "Menos 10 convidados", onclick: () => bump(-10) }, "−"),
      guests,
      h("button", { type: "button", "aria-label": "Mais 10 convidados", onclick: () => bump(10) }, "+")),
    h("p", { class: "field__error", "data-error-for": "guests" }));

  const budgetChips = h("div", { class: "field" },
    h("span", { class: "field__label" }, "Quanto pretende investir"),
    h("div", { class: "chips chips--choice", role: "radiogroup", "aria-label": "Faixa de investimento" },
      s.budgets.map((b) => h("label", { class: "chip" },
        h("input", { type: "radio", name: "budget", value: b, class: "sr-only", checked: b === "" }),
        b || "Prefiro conversar"))),
    h("p", { class: "field__error", "data-error-for": "budget" }));

  const typeField = h("div", { class: "field" }, h("span", { class: "field__label" }, "Que tipo de evento?"), typeTiles,
    h("p", { class: "field__error", "data-error-for": "event_type" }));
  const dateField = field({ label: "Data do evento", name: "event_date", type: "date", required: true, min: todayISO() });
  const locationField = field({ label: "Local do evento", name: "location", required: true, placeholder: "Salão, chácara, casa… e a cidade" });
  const detailsField = field({ label: "Conte como você imagina a festa", name: "details", as: "textarea", placeholder: "Cardápio que gosta, restrições alimentares, horário, estilo da festa…", hint: "Opcional, mas ajuda a preparar uma proposta certeira." });
  // Cada item da revisão abre só o campo dele numa aba, sem voltar ao começo.
  const editors = {
    event_type: { node: typeField, title: "Tipo de evento" },
    event_date: { node: dateField, title: "Data do evento" },
    guests: { node: stepper, title: "Número de convidados" },
    location: { node: locationField, title: "Local do evento" },
    budget: { node: budgetChips, title: "Quanto pretende investir" },
    details: { node: detailsField, title: "Detalhes da festa" },
  };

  const review = h("dl", { class: "review" });
  const panes = [
    h("fieldset", { class: "wizard__pane" },
      h("legend", { class: "sr-only" }, STEPS[0]),
      typeField,
      h("div", { class: "form__row" }, dateField, stepper)),
    h("fieldset", { class: "wizard__pane" },
      h("legend", { class: "sr-only" }, STEPS[1]),
      locationField,
      budgetChips,
      detailsField),
    h("fieldset", { class: "wizard__pane" },
      h("legend", { class: "sr-only" }, STEPS[2]),
      h("p", { class: "muted" }, "Confira antes de enviar. Depois, a conversa continua na sua conta."),
      review),
  ];

  const progress = h("ol", { class: "wizard__progress" }, STEPS.map((label, i) => h("li", null, h("span", null, i + 1), label)));
  const back = h("button", { class: "btn btn--ghost", type: "button", onclick: () => show(current - 1) }, "Voltar");
  const nextBtn = h("button", { class: "btn btn--primary", type: "submit" });
  const form = h("form", { class: "form wizard", novalidate: true },
    progress,
    h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
    panes,
    h("div", { class: "wizard__actions" }, back, nextBtn));

  const v = () => formValues(form);
  const fieldStep = { event_type: 0, event_date: 0, guests: 0, location: 1, budget: 1, details: 1 };

  function show(i) {
    current = i;
    panes.forEach((p, n) => (p.hidden = n !== i));
    [...progress.children].forEach((li, n) => {
      li.classList.toggle("is-done", n < i);
      li.classList.toggle("is-current", n === i);
    });
    back.hidden = i === 0;
    nextBtn.textContent = i === STEPS.length - 1 ? "Enviar pedido e abrir conversa" : "Continuar";
    if (i === 2) {
      const d = v();
      const row = (label, value, key) => [h("dt", null, label), h("dd", null, value || h("span", { class: "muted" }, "—"),
        h("button", { class: "link-btn", type: "button", "aria-label": `Alterar ${label.toLowerCase()}`, onclick: () => editField(key) }, "alterar"))];
      fill(review,
        row("Evento", d.event_type, "event_type"),
        row("Data", fmtDate(d.event_date), "event_date"),
        row("Convidados", d.guests && plural(Number(d.guests), "convidado", "convidados"), "guests"),
        row("Local", d.location, "location"),
        row("Investimento", d.budget || "Prefiro conversar", "budget"),
        row("Detalhes", d.details, "details"));
    }
    panes[i].querySelector("input:not([type=radio]), textarea, input")?.focus({ preventScroll: true });
  }

  /** Erros de um campo só (as mesmas regras das etapas). */
  function fieldErrors(key, d) {
    if (key === "event_type" && !d.event_type) return "Escolha o tipo de evento.";
    if (key === "event_date" && !d.event_date) return "Informe a data.";
    if (key === "event_date" && d.event_date < todayISO()) return "A data já passou.";
    if (key === "guests" && !(Number(d.guests) > 0)) return "Informe quantos convidados.";
    if (key === "location" && (d.location || "").trim().length < 2) return "Informe o local do evento.";
    return null;
  }

  /** Abre uma aba com o campo escolhido, já preenchido; ao salvar, volta para a revisão. */
  function editField(key) {
    const { node, title } = editors[key];
    const spot = document.createComment("campo");
    const controls = () => [...node.querySelectorAll("input, textarea")];
    const before = controls().map((el) => (el.type === "radio" ? el.checked : el.value));
    let saved = false;
    node.replaceWith(spot);
    openModal(`Alterar: ${title.toLowerCase()}`, (close) => {
      const save = h("button", { class: "btn btn--primary", type: "button" }, "Salvar alteração");
      save.addEventListener("click", () => {
        const values = Object.fromEntries(controls().filter((el) => el.type !== "radio" || el.checked).map((el) => [el.name, el.value]));
        const message = fieldErrors(key, values);
        const slot = node.querySelector(`[data-error-for="${key}"]`);
        if (slot) slot.textContent = message || "";
        if (message) return;
        saved = true;
        close();
        toast("Alteração salva.");
      });
      return h("div", { class: "form" }, node,
        h("div", { class: "form__actions" },
          h("button", { class: "btn btn--ghost", type: "button", onclick: close }, "Cancelar"), save));
    }, {
      className: "modal--sheet",
      onClose: () => {
        if (!saved) controls().forEach((el, i) => (el.type === "radio" ? (el.checked = before[i]) : (el.value = before[i])));
        node.querySelectorAll("[data-error-for]").forEach((el) => (el.textContent = ""));
        spot.replaceWith(node);
        show(2); // continua na revisão, com o valor novo
      },
    });
  }

  function checkStep(i) {
    clearErrors(form);
    const d = v();
    const errors = [];
    if (i === 0) {
      if (!d.event_type) errors.push({ field: "event_type", message: "Escolha o tipo de evento." });
      if (!d.event_date) errors.push({ field: "event_date", message: "Informe a data." });
      else if (d.event_date < todayISO()) errors.push({ field: "event_date", message: "A data já passou." });
      if (!(Number(d.guests) > 0)) errors.push({ field: "guests", message: "Informe quantos convidados." });
    }
    if (i === 1 && (d.location || "").trim().length < 2) errors.push({ field: "location", message: "Informe o local do evento." });
    if (errors.length) showErrors(form, { errors, message: errors[0].message });
    return errors.length === 0;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (current < STEPS.length - 1) {
      if (checkStep(current)) show(current + 1);
      return;
    }
    const d = v();
    submitting(form, async () => {
      try {
        const quote = await api.post("/quotes", { ...d, guests: Number(d.guests) || null });
        toast("Pedido enviado! Agora é só conversar por aqui.");
        go(`/conta/pedidos/${quote.id}`);
      } catch (err) {
        const step = Math.min(...(err.errors || []).map((e) => fieldStep[e.field] ?? 2), 2);
        show(Number.isFinite(step) ? step : 2);
        throw err;
      }
    }).then(() => {
      // o envio restaura o texto do botão; recoloca o do passo em que a pessoa está
      nextBtn.textContent = current === STEPS.length - 1 ? "Enviar pedido e abrir conversa" : "Continuar";
    });
  });

  show(0);
  const ownerFirst = firstName(s.owner_name, "a gente");
  splitPage("Conte sobre o seu evento",
    `Com essas informações, ${ownerFirst} prepara a proposta e responde aqui no site. Você recebe as mensagens na sua conta.`,
    h("div", { class: "panel-card panel-card--wide" },
      h("p", { class: "eyebrow" }, `Olá, ${firstName(state.user.name)}`),
      h("h1", null, "Pedir orçamento"),
      form));
}

/* ===================== 6. Área do cliente e conversa ===================== */

const STATUS = {
  novo: "Novo",
  em_conversa: "Em conversa",
  proposta_enviada: "Proposta enviada",
  fechado: "Fechado",
  nao_fechado: "Não fechado",
};

const statusPill = (s) => h("span", { class: `status status--${s}` }, STATUS[s] || s);

function quoteItem(q, href, active, showClient) {
  return h("a", { class: `quote-item${q.unread ? " has-unread" : ""}`, href, "aria-current": active ? "true" : null },
    h("div", null,
      h("p", { class: "quote-item__title" }, showClient ? q.client.name : q.event_type, statusPill(q.status)),
      h("p", { class: "quote-item__meta" },
        [showClient && q.event_type, fmtShort(q.event_date), plural(q.guests, "convidado", "convidados")].filter(Boolean).join(" · "))),
    h("div", { class: "quote-item__side" },
      h("span", null, relative(q.last_message_at)),
      q.unread ? h("span", { class: "badge", "aria-label": plural(q.unread, "mensagem nova", "mensagens novas") }, q.unread) : null),
    h("p", { class: "quote-item__last" }, q.last_message || "Ainda sem mensagens."));
}

async function renderAccount(openId) {
  if (!state.user) return go(`/entrar?volta=${encodeURIComponent(currentPath())}`);
  if (isOwner()) return go(openId ? `/painel/pedidos/${openId}` : "/painel");
  document.title = `Minha conta | ${state.site.business_name}`;
  const area = h("div", { class: "wrap account" }, loading());
  fill(root(), header(), h("main", { id: "conteudo" }, area));

  if (openId) {
    const chat = await chatView(openId, { back: "#/conta" });
    if (chat) fill(area, chat);
    return;
  }

  let quotes;
  try {
    quotes = await api.get("/quotes");
  } catch (err) {
    fill(area, h("div", { class: "empty" }, err.message));
    return;
  }
  const u = state.user;
  fill(area,
    h("div", { class: "account__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Minha conta"), h("h1", null, `Olá, ${u.name.split(" ")[0]}`)),
      h("div", { style: "display:flex;gap:10px;flex-wrap:wrap" },
        h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: editProfile }, "Meus dados"),
        h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: () => session.logout() }, "Sair"),
        h("a", { class: "btn btn--primary btn--small", href: "#/orcamento" }, "Novo pedido"))),
    h("section", { "aria-labelledby": "t-pedidos", style: "display:grid;gap:14px" },
      h("h2", { id: "t-pedidos", style: "font-size:26px" }, "Meus pedidos de orçamento"),
      quotes.length
        ? h("div", { class: "quote-list" }, quotes.map((q) => quoteItem(q, `#/conta/pedidos/${q.id}`)))
        : h("div", { class: "empty" }, "Você ainda não pediu nenhum orçamento.",
          h("a", { class: "btn btn--primary", href: "#/orcamento" }, "Agendar evento"))));
}

function editProfile() {
  const u = state.user;
  openModal("Meus dados", (close) => {
    const form = h("form", { class: "form", novalidate: true },
      h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
      field({ label: "Nome completo", name: "name", value: u.name, required: true }),
      h("div", { class: "form__row" },
        field({ label: "Telefone / WhatsApp", name: "phone", type: "tel", value: u.phone || "", required: true }),
        field({ label: "Cidade", name: "city", value: u.city || "", required: true })),
      h("p", { class: "muted", style: "font-size:14px" }, `E-mail: ${u.email}`),
      h("div", { class: "form__actions" },
        h("button", { class: "btn btn--ghost", type: "button", onclick: close }, "Cancelar"),
        h("button", { class: "btn btn--primary", type: "submit" }, "Salvar")));
    form.elements.phone.addEventListener("input", (e) => (e.target.value = maskPhone(e.target.value)));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitting(form, async () => {
        state.user = await api.patch("/auth/me", formValues(form));
        close();
        toast("Dados atualizados.");
      });
    });
    return form;
  });
}

/** A conversa de um pedido. Serve ao cliente e à administração. */
async function chatView(quoteId, { back, onStatus } = {}) {
  let quote;
  try {
    quote = await api.get(`/quotes/${quoteId}`);
  } catch (err) {
    return h("div", { class: "empty" }, err.message, back && h("a", { class: "btn btn--ghost", href: back }, "Voltar"));
  }
  refreshUnread();
  const owner = isOwner();
  const ownerFirst = state.site.owner_name ? state.site.owner_name.split(" ")[0] : "A equipe";
  const body = h("div", { class: "chat__body", role: "log", "aria-live": "polite", "aria-label": "Mensagens" });
  let lastId = 0;
  let lastDay = "";

  const addMessage = (m) => {
    if (m.id <= lastId) return;
    lastId = m.id;
    const date = new Date(m.created_at);
    const day = date.toDateString();
    if (day !== lastDay) {
      lastDay = day;
      body.append(h("p", { class: "chat__day" }, dayLabel(date)));
    }
    const mine = m.from_owner === owner;
    let photo = null;
    if (m.image_url) {
      const index = photos.push(m.image_url) - 1;
      photo = h("button", { class: "bubble__photo", type: "button", "aria-label": "Ampliar foto", onclick: () => lightbox(photos, index, "Foto da conversa") },
        h("img", { src: m.image_url, alt: m.body || "Foto enviada na conversa", width: m.image_width, height: m.image_height, loading: "lazy" }));
      photo.querySelector("img").addEventListener("load", () => {
        if (stick) body.scrollTop = body.scrollHeight; // a foto carregou depois: continua no fim
      });
    }
    body.append(h("div", { class: `bubble ${mine ? "bubble--me" : "bubble--them"}${photo ? " bubble--photo" : ""}` },
      !mine && h("span", { class: "bubble__who" }, m.from_owner ? state.site.owner_name || state.site.business_name : quote.client.name),
      photo,
      m.body && h("span", null, m.body),
      h("time", { datetime: m.created_at }, TIME.format(date))));
  };
  const photos = [];
  let stick = true; // a conversa está no fim (as fotos que chegarem mantêm o fim à vista)
  body.addEventListener("scroll", () => {
    stick = body.scrollHeight - body.scrollTop - body.clientHeight < 120;
  });

  body.append(h("p", { class: "chat__notice" }, owner
    ? `Pedido enviado em ${DATE_SHORT.format(new Date(quote.created_at))}. As mensagens que você escrever aqui aparecem na conta de ${quote.client.name.split(" ")[0]}.`
    : `Pedido enviado! ${ownerFirst} responde por aqui. Você também pode mandar mais detalhes, fotos de referência ou dúvidas.`));
  quote.messages.forEach(addMessage);

  const text = h("textarea", { class: "input", name: "body", rows: "1", placeholder: "Escreva sua mensagem…", "aria-label": "Mensagem", maxlength: "4000" });
  const sendBtn = h("button", { class: "btn btn--primary", type: "submit", "aria-label": "Enviar" }, icon("send"), h("span", null, "Enviar"));
  const picker = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", multiple: true, hidden: true });
  const attachBtn = h("button", { class: "chat__attach", type: "button", "aria-label": "Enviar fotos", title: "Enviar fotos", onclick: () => picker.click() }, icon("photo"));
  const compose = h("form", { class: "chat__compose" }, attachBtn, picker, text, sendBtn,
    h("p", { class: "chat__hint" }, "Enter envia · Shift + Enter quebra a linha · Cole ou arraste fotos aqui"));

  const afterSend = (m) => {
    addMessage(m);
    body.scrollTop = body.scrollHeight;
    if (owner && quote.status === "novo") {
      quote.status = "em_conversa";
      statusSlot.replaceChildren(statusControl());
      onStatus?.();
    }
  };

  // Fotos: escolher, colar ou arrastar abre uma prévia com legenda antes de enviar.
  const MAX_PHOTOS = 10;
  const sendPhotos = (fileList) => {
    let files = [...fileList].filter((f) => /^image\/(jpeg|png|webp)$/.test(f.type));
    if (!files.length) {
      toast("Envie fotos em JPG, PNG ou WebP.", "error");
      return;
    }
    if (files.length > MAX_PHOTOS) {
      toast(`Até ${MAX_PHOTOS} fotos por vez.`, "error");
      files = files.slice(0, MAX_PHOTOS);
    }
    openModal(files.length > 1 ? `Enviar ${files.length} fotos` : "Enviar foto", (close) => {
      const grid = h("div", { class: `photo-preview${files.length === 1 ? " photo-preview--one" : ""}` },
        files.map((file) => {
          const img = h("img", { alt: file.name });
          const reader = new FileReader();
          reader.onload = () => { img.src = reader.result; };
          reader.readAsDataURL(file);
          return h("figure", null, img);
        }));
      const caption = h("textarea", { class: "input", rows: "2", maxlength: "4000", placeholder: "Legenda (opcional)", "aria-label": "Legenda" });
      const send = h("button", { class: "btn btn--primary", type: "submit" }, icon("send"), h("span", null, "Enviar"));
      const form = h("form", { class: "form" }, grid,
        h("div", { class: "field" }, caption),
        h("div", { class: "form__actions" },
          h("button", { class: "btn btn--ghost", type: "button", onclick: close }, "Cancelar"), send));
      caption.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          form.requestSubmit();
        }
      });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        send.disabled = true;
        const label = send.querySelector("span");
        let sent = 0;
        try {
          for (const file of files) {
            label.textContent = files.length > 1 ? `Enviando ${sent + 1} de ${files.length}…` : "Enviando…";
            // A legenda vai junto com a primeira foto.
            afterSend(await api.sendPhoto(quote.id, file, sent === 0 ? caption.value.trim() : ""));
            sent += 1;
          }
          close();
        } catch (err) {
          if (err.status !== 401) toast(sent ? `${sent} de ${files.length} enviadas. ${err.message}` : err.message, "error");
          files = files.slice(sent);
          [...grid.children].slice(0, sent).forEach((f) => f.remove());
          label.textContent = "Tentar de novo";
          send.disabled = false;
        }
      });
      return form;
    }, { className: "modal--sheet" });
  };
  picker.addEventListener("change", () => {
    if (picker.files.length) sendPhotos(picker.files);
    picker.value = "";
  });
  text.addEventListener("paste", (e) => {
    const images = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (images.length) {
      e.preventDefault();
      sendPhotos(images);
    }
  });
  const grow = () => {
    text.style.height = "auto";
    text.style.height = `${Math.min(text.scrollHeight + 2, 160)}px`;
  };
  text.addEventListener("input", grow);
  text.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      compose.requestSubmit();
    }
  });
  compose.addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = text.value.trim();
    if (!value) return;
    sendBtn.disabled = true;
    try {
      const m = await api.post(`/quotes/${quote.id}/messages`, { body: value });
      text.value = "";
      grow();
      afterSend(m);
    } catch (err) {
      if (err.status !== 401) toast(err.message, "error");
    } finally {
      sendBtn.disabled = false;
      text.focus();
    }
  });

  const statusSlot = h("span");
  const statusControl = () => {
    if (!owner) return statusPill(quote.status);
    const select = h("select", { class: "input", "aria-label": "Situação do pedido", style: "min-height:38px;width:auto;padding-top:4px;padding-bottom:4px" },
      Object.entries(STATUS).map(([v, label]) => h("option", { value: v, selected: v === quote.status }, label)));
    select.addEventListener("change", async () => {
      try {
        const updated = await api.patch(`/admin/quotes/${quote.id}`, { status: select.value });
        quote.status = updated.status;
        toast(`Situação: ${STATUS[updated.status]}.`);
        onStatus?.();
        refreshUnread();
      } catch (err) {
        toast(err.message, "error");
        select.value = quote.status;
      }
    });
    return select;
  };
  statusSlot.append(statusControl());

  const facts = h("div", { class: "quote-facts" },
    h("span", null, h("b", null, quote.event_type), ` em ${fmtDate(quote.event_date)}`),
    h("span", null, plural(quote.guests, "convidado", "convidados")),
    h("span", null, quote.location),
    quote.budget && h("span", null, `Investimento: ${quote.budget}`));

  const head = h("div", { class: "chat__head" },
    back && h("a", { class: "back", href: back }, icon("left"), owner ? "Todos os pedidos" : "Meus pedidos"),
    h("div", { class: "chat__title" },
      h("h2", null, owner ? quote.client.name : `Pedido de orçamento · ${quote.event_type}`), statusSlot),
    h("details", { class: "chat__details", open: window.innerWidth > 700 },
      h("summary", null, "Detalhes do pedido"),
      h("div", null, facts,
        quote.details && h("p", { style: "font-size:14px;color:var(--ink-soft);white-space:pre-wrap" }, quote.details))));

  const chat = h("section", { class: "chat", "aria-label": "Conversa do pedido" }, head, body, compose);
  chat.addEventListener("dragover", (e) => {
    if (![...e.dataTransfer.types].includes("Files")) return;
    e.preventDefault();
    chat.classList.add("is-dragging");
  });
  chat.addEventListener("dragleave", (e) => {
    if (!chat.contains(e.relatedTarget)) chat.classList.remove("is-dragging");
  });
  chat.addEventListener("drop", (e) => {
    e.preventDefault();
    chat.classList.remove("is-dragging");
    if (e.dataTransfer.files.length) sendPhotos(e.dataTransfer.files);
  });

  // Mensagens novas a cada 4 segundos, enquanto esta tela estiver aberta e visível.
  const poll = setInterval(async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const fresh = await api.get(`/quotes/${quote.id}/messages`, { after: lastId });
      if (fresh.length) {
        const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 120;
        fresh.forEach(addMessage);
        if (nearBottom) body.scrollTop = body.scrollHeight;
        refreshUnread();
        // A situação pode ter mudado do outro lado (ex.: a primeira resposta tira de "Novo").
        if (!owner) {
          const latest = await api.get(`/quotes/${quote.id}`);
          if (latest.status !== quote.status) {
            quote.status = latest.status;
            statusSlot.replaceChildren(statusControl());
          }
        }
      }
    } catch {
      /* tenta de novo no próximo ciclo */
    }
  }, 4000);
  onLeave(() => clearInterval(poll));
  requestAnimationFrame(() => {
    body.scrollTop = body.scrollHeight;
  });

  const wrapper = h("div", { style: "display:grid;gap:14px;min-width:0" });
  if (owner) wrapper.append(clientCard(quote.client));
  wrapper.append(chat);
  return wrapper;
}

function clientCard(c) {
  const wa = whatsappLink(c.phone);
  return h("dl", { class: "client-card", "aria-label": "Dados do cliente" },
    h("div", null, h("dt", null, "Cliente"), h("dd", null, c.name)),
    h("div", null, h("dt", null, "E-mail"), h("dd", null, h("a", { href: `mailto:${c.email}` }, c.email))),
    h("div", null, h("dt", null, "Telefone"), h("dd", null, c.phone || "—",
      wa && h("a", { href: wa, target: "_blank", rel: "noopener", style: "margin-left:8px;font-size:13px" }, "WhatsApp"))),
    h("div", null, h("dt", null, "Cidade"), h("dd", null, c.city || "—")),
    h("div", null, h("dt", null, "Cliente desde"), h("dd", null, DATE_SHORT.format(new Date(c.created_at)))));
}

/* ===================== 7. Painel da administração ===================== */

const ADMIN_TABS = [
  ["pedidos", "Orçamentos", "#/painel"],
  ["portfolio", "Portfólio", "#/painel/portfolio"],
  ["site", "Textos e fotos do site", "#/painel/site"],
  ["clientes", "Clientes", "#/painel/clientes"],
];

async function renderAdmin(tab, openId) {
  if (!state.user) return go(`/entrar?volta=${encodeURIComponent(currentPath())}`);
  if (!isOwner()) return go("/conta");
  document.title = `Painel | ${state.site.business_name}`;
  const main = h("div", { class: "admin__main" }, loading());
  const badge = h("span", { class: "badge", "data-unread": true });
  paintBadge(badge);
  fill(root(), header(), h("div", { class: "admin", id: "conteudo" },
    h("nav", { class: "admin__side", "aria-label": "Painel" },
      h("p", { class: "eyebrow" }, "Painel"),
      ADMIN_TABS.map(([key, label, href]) => h("a", { href, "aria-current": key === tab ? "page" : null }, label, key === "pedidos" && badge)),
      h("a", { href: "#/" }, "Ver o site"),
      h("a", { href: "#", onclick: (e) => { e.preventDefault(); session.logout(); } }, "Sair")),
    main));
  const views = { pedidos: adminQuotes, portfolio: adminPortfolio, site: adminSite, clientes: adminClients };
  await views[tab](main, openId);
}

/* ---------- Orçamentos ---------- */

const adminFilters = { status: "", q: "" };

async function adminQuotes(main, openId) {
  const list = h("div", { class: "inbox__list", role: "list" }, loading());
  const chatArea = h("div", { class: "inbox__chat" },
    h("div", { class: "placeholder" }, h("div", null, icon("chat"), h("p", null, "Escolha um pedido para ver a conversa e os dados do cliente."))));
  const status = h("select", { class: "input", "aria-label": "Filtrar por situação" },
    h("option", { value: "" }, "Todas as situações"),
    Object.entries(STATUS).map(([v, label]) => h("option", { value: v, selected: v === adminFilters.status }, label)));
  const search = h("input", { class: "input", type: "search", placeholder: "Buscar cliente", "aria-label": "Buscar cliente", value: adminFilters.q });
  const inbox = h("div", { class: `inbox${openId ? " has-open" : ""}` },
    h("div", { style: "display:grid;gap:12px;align-content:start;min-width:0" }, h("div", { class: "inbox__filters" }, status, search), list),
    chatArea);

  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Pedidos de orçamento"))),
    inbox);

  async function load() {
    try {
      const quotes = await api.get("/quotes", { status: adminFilters.status, q: adminFilters.q });
      fill(list, quotes.length
        ? quotes.map((q) => quoteItem(q, `#/painel/pedidos/${q.id}`, q.id === openId, true))
        : h("div", { class: "empty" }, adminFilters.status || adminFilters.q ? "Nenhum pedido com esse filtro." : "Os pedidos de orçamento aparecem aqui."));
    } catch (err) {
      fill(list, h("div", { class: "empty" }, err.message));
    }
  }
  status.addEventListener("change", () => {
    adminFilters.status = status.value;
    load();
  });
  search.addEventListener("input", debounce(() => {
    adminFilters.q = search.value.trim();
    load();
  }));
  await load();

  const refresh = setInterval(() => document.visibilityState === "visible" && load(), 15000);
  onLeave(() => clearInterval(refresh));

  if (openId) {
    fill(chatArea, loading());
    const chat = await chatView(openId, { back: "#/painel", onStatus: load });
    fill(chatArea, chat);
    load();
  }
}

/* ---------- Envio de fotos ---------- */

/** Envia as fotos uma por vez e devolve os ids, avisando o progresso. */
async function uploadFiles(files, onProgress) {
  const ids = [];
  const list = [...files].filter((f) => f.type.startsWith("image/") || /\.(jpe?g|png|webp|heic)$/i.test(f.name));
  for (let i = 0; i < list.length; i++) {
    onProgress?.(i + 1, list.length);
    try {
      const image = await api.upload(list[i]);
      ids.push(image.id);
    } catch (err) {
      toast(`${list[i].name}: ${err.message}`, "error");
    }
  }
  return ids;
}

function uploader({ multiple = true, label = "Arraste fotos para cá ou clique para escolher", onFiles }) {
  const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", multiple, class: "sr-only" });
  const text = h("span", null, label);
  const zone = h("label", { class: "uploader" }, icon("photo"), h("strong", null, multiple ? "Adicionar fotos" : "Escolher foto"), text, input);
  const busy = (msg) => (text.textContent = msg || label);
  const handle = async (files) => {
    if (!files.length) return;
    zone.style.pointerEvents = "none";
    await onFiles(files, busy);
    zone.style.pointerEvents = "";
    busy();
    input.value = "";
  };
  input.addEventListener("change", () => handle(input.files));
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("is-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("is-over");
    handle(e.dataTransfer.files);
  });
  return zone;
}

/* ---------- Portfólio ---------- */

async function adminPortfolio(main) {
  const list = h("div", { class: "admin-events" }, loading());
  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Portfólio")),
      h("button", { class: "btn btn--primary", type: "button", onclick: () => eventEditor(null, load) }, "Publicar evento")),
    h("p", { class: "muted" }, "Os eventos aparecem no site em ordem de data, do mais recente para o mais antigo. A primeira foto de cada evento é a capa."),
    list);

  async function load() {
    try {
      const events = await api.get("/events", { limit: 200 });
      fill(list, events.length ? events.map((e) => h("div", { class: "admin-event" },
        e.photos[0] ? img(e.photos[0].image_id, "") : h("div", { class: "noimg" }),
        h("div", null,
          h("h3", null, e.title),
          h("p", { class: "muted", style: "font-size:14px" },
            [e.event_type, e.event_date && fmtShort(e.event_date), plural(e.photos.length, "foto", "fotos")].filter(Boolean).join(" · "))),
        h("div", { class: "admin-event__actions" },
          h("a", { class: "btn btn--ghost btn--small", href: `#/portfolio/${e.id}`, target: "_blank" }, "Ver"),
          h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: () => eventEditor(e, load) }, "Editar"),
          h("button", {
            class: "btn btn--danger btn--small", type: "button",
            onclick: async (ev) => {
              const button = ev.currentTarget;
              if (button.dataset.confirm !== "1") {
                button.dataset.confirm = "1";
                button.textContent = "Confirmar exclusão";
                setTimeout(() => {
                  button.dataset.confirm = "";
                  button.textContent = "Excluir";
                }, 4000);
                return;
              }
              try {
                await api.del(`/admin/events/${e.id}`);
                toast(`"${e.title}" saiu do portfólio.`);
                load();
              } catch (err) {
                toast(err.message, "error");
              }
            },
          }, "Excluir"))))
        : h("div", { class: "empty" }, "Nenhum evento publicado ainda.",
          h("button", { class: "btn btn--primary", type: "button", onclick: () => eventEditor(null, load) }, "Publicar o primeiro evento")));
    } catch (err) {
      fill(list, h("div", { class: "empty" }, err.message));
    }
  }
  await load();
}

function eventEditor(event, onSaved) {
  const e = event || { title: "", event_type: "", event_date: "", guests: "", location: "", description: "", photos: [] };
  let photos = e.photos.map((p) => p.image_id);
  openModal(event ? "Editar evento" : "Publicar evento", (close) => {
    const thumbs = h("div", { class: "thumbs" });
    const drawThumbs = () => fill(thumbs, photos.map((id, i) => h("div", { class: "thumb" },
      img(id, `Foto ${i + 1}`),
      i === 0 && h("span", { class: "thumb__tag" }, "CAPA"),
      h("div", { class: "thumb__bar" },
        h("button", { type: "button", "aria-label": "Mover para antes", disabled: i === 0, onclick: () => move(i, -1) }, icon("left")),
        h("button", { type: "button", "aria-label": "Mover para depois", disabled: i === photos.length - 1, onclick: () => move(i, 1) }, icon("right")),
        h("button", { type: "button", "aria-label": "Tirar foto", onclick: () => { photos.splice(i, 1); drawThumbs(); } }, icon("trash"))))));
    const move = (i, d) => {
      [photos[i], photos[i + d]] = [photos[i + d], photos[i]];
      drawThumbs();
    };
    drawThumbs();

    const types = [...new Set([...state.site.event_types, e.event_type].filter(Boolean))];
    const form = h("form", { class: "form", novalidate: true },
      h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
      field({ label: "Título", name: "title", value: e.title, required: true, placeholder: "Ex.: Casamento de Júlia e Rafael" }),
      h("div", { class: "form__row" },
        field({ label: "Tipo de evento", name: "event_type", as: "select", value: e.event_type, options: [["", "Escolha…"], ...types.map((t) => [t, t])] }),
        field({ label: "Data", name: "event_date", type: "date", value: e.event_date || "" })),
      h("div", { class: "form__row" },
        field({ label: "Convidados", name: "guests", type: "number", min: 1, value: e.guests ?? "" }),
        field({ label: "Local", name: "location", value: e.location, placeholder: "Ex.: Chácara em Valinhos" })),
      field({ label: "Descrição", name: "description", as: "textarea", value: e.description, placeholder: "Cardápio, decoração, o que deixou esse evento especial…" }),
      h("div", { class: "field" },
        h("span", { class: "field__label" }, "Fotos"),
        thumbs,
        uploader({
          onFiles: async (files, busy) => {
            const ids = await uploadFiles(files, (n, total) => busy(`Enviando ${n} de ${total}…`));
            photos.push(...ids);
            drawThumbs();
          },
        }),
        h("p", { class: "field__error", "data-error-for": "image_ids" })),
      h("div", { class: "form__actions" },
        h("button", { class: "btn btn--ghost", type: "button", onclick: close }, "Cancelar"),
        h("button", { class: "btn btn--primary", type: "submit" }, event ? "Salvar alterações" : "Publicar")));

    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const v = formValues(form);
      const payload = {
        title: v.title, event_type: v.event_type, event_date: v.event_date || null,
        guests: v.guests ? Number(v.guests) : null, location: v.location, description: v.description, image_ids: photos,
      };
      submitting(form, async () => {
        const saved = event ? await api.put(`/admin/events/${event.id}`, payload) : await api.post("/admin/events", payload);
        close();
        toast(event ? "Evento atualizado." : `"${saved.title}" está no portfólio.`);
        onSaved();
      });
    });
    return form;
  });
}

/* ---------- Textos e fotos do site ---------- */

async function adminSite(main) {
  let s;
  try {
    s = state.site = await api.get("/site");
  } catch (err) {
    fill(main, h("div", { class: "empty" }, err.message));
    return;
  }
  const save = async (changes, message = "Site atualizado.") => {
    state.site = await api.patch("/admin/site", changes);
    document.title = `Painel | ${state.site.business_name}`;
    toast(message);
    return state.site;
  };

  const textForm = (title, fields, intro) => {
    const form = h("form", { class: "box", novalidate: true },
      h("div", { class: "box__head" }, h("h2", null, title)),
      intro && h("p", { class: "muted", style: "font-size:14px;margin-top:-8px" }, intro),
      h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
      h("div", { class: "form" }, fields),
      h("div", { class: "form__actions" }, h("button", { class: "btn btn--primary", type: "submit" }, "Salvar")));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const v = formValues(form);
      if ("founded_year" in v) v.founded_year = v.founded_year ? Number(v.founded_year) : null;
      submitting(form, () => save(v));
    });
    return form;
  };

  const imageField = (label, key, hint) => {
    const preview = h("div", { class: "image-field__preview" });
    const paint = () => fill(preview, state.site[key] ? img(state.site[key], label) : h("span", null, "Sem foto"));
    paint();
    const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "sr-only" });
    const pick = h("label", { class: "btn btn--ghost btn--small" }, "Trocar foto", input);
    input.addEventListener("change", async () => {
      if (!input.files.length) return;
      pick.firstChild.textContent = "Enviando…";
      const [id] = await uploadFiles(input.files);
      if (id) {
        try {
          await save({ [key]: id }, "Foto atualizada.");
          paint();
        } catch (err) {
          toast(err.message, "error");
        }
      }
      pick.firstChild.textContent = "Trocar foto";
      input.value = "";
    });
    return h("div", { class: "image-field" }, preview,
      h("div", { style: "display:grid;gap:6px" },
        h("strong", null, label), hint && h("span", { class: "muted", style: "font-size:14px" }, hint),
        h("div", { class: "image-field__actions" }, pick,
          h("button", {
            class: "btn btn--ghost btn--small", type: "button",
            onclick: async () => {
              try {
                await save({ [key]: null }, "Foto removida.");
                paint();
              } catch (err) {
                toast(err.message, "error");
              }
            },
          }, "Remover"))));
  };

  const bioThumbs = h("div", { class: "thumbs" });
  const drawBio = () => fill(bioThumbs, state.site.bio_photos.map((p) => h("div", { class: "thumb" },
    img(p.image_id, p.caption),
    p.caption && h("span", { class: "muted", style: "font-size:13px" }, p.caption),
    h("div", { class: "thumb__bar" },
      h("button", {
        type: "button", "aria-label": "Tirar foto",
        onclick: async () => {
          try {
            state.site = await api.del(`/admin/site/bio-photos/${p.id}`);
            drawBio();
            toast("Foto removida.");
          } catch (err) {
            toast(err.message, "error");
          }
        },
      }, icon("trash"), " Tirar")))));
  drawBio();

  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Textos e fotos do site")),
      h("a", { class: "btn btn--ghost", href: "#/", target: "_blank" }, "Ver o site")),

    textForm("Capa", [
      field({ label: "Nome da empresa", name: "business_name", value: s.business_name, required: true }),
      field({ label: "Frase curta (aparece acima do título e no rodapé)", name: "tagline", value: s.tagline }),
      field({ label: "Título da capa", name: "hero_title", value: s.hero_title }),
      field({ label: "Texto da capa", name: "hero_text", as: "textarea", value: s.hero_text }),
    ]),
    h("div", { class: "box" }, h("h2", null, "Foto da capa"),
      imageField("Foto de fundo da capa", "hero_image_id", "Foto deitada (horizontal), de preferência de um evento bem iluminado.")),

    textForm("Sobre mim", [
      h("div", { class: "form__row" },
        field({ label: "Seu nome", name: "owner_name", value: s.owner_name }),
        field({ label: "Como você se apresenta", name: "owner_role", value: s.owner_role, placeholder: "Ex.: Chef e fundadora" })),
      field({ label: "Biografia", name: "bio", as: "textarea", value: s.bio, hint: "Deixe uma linha em branco entre os parágrafos.", style: "min-height:220px" }),
    ]),
    h("div", { class: "box" },
      h("h2", null, "Fotos do Sobre mim"),
      imageField("Sua foto", "owner_image_id", "Foto em pé (vertical) fica melhor."),
      h("strong", null, "Mais fotos (aparecem abaixo da biografia)"),
      bioThumbs,
      uploader({
        onFiles: async (files, busy) => {
          const ids = await uploadFiles(files, (n, total) => busy(`Enviando ${n} de ${total}…`));
          for (const id of ids) state.site = await api.post("/admin/site/bio-photos", { image_id: id });
          drawBio();
          if (ids.length) toast(ids.length === 1 ? "Foto adicionada." : `${ids.length} fotos adicionadas.`);
        },
      })),

    textForm("Nossa história", [
      h("div", { class: "form__row" },
        field({ label: "Título", name: "history_title", value: s.history_title, placeholder: "Ex.: Como tudo começou" }),
        field({ label: "Ano de fundação", name: "founded_year", type: "number", min: 1900, max: 2100, value: s.founded_year ?? "" })),
      field({ label: "Como a empresa foi fundada", name: "history", as: "textarea", value: s.history, hint: "Deixe uma linha em branco entre os parágrafos.", style: "min-height:240px" }),
    ]),
    h("div", { class: "box" }, h("h2", null, "Foto da história"), imageField("Foto da seção Nossa história", "history_image_id")),

    textForm("Contato", [
      h("div", { class: "form__row" },
        field({ label: "Telefone / WhatsApp", name: "phone", value: s.phone }),
        field({ label: "E-mail", name: "email", type: "email", value: s.email })),
      h("div", { class: "form__row" },
        field({ label: "Instagram (sem @)", name: "instagram", value: s.instagram }),
        field({ label: "Cidade", name: "city", value: s.city })),
    ], "Aparece no rodapé do site."));
}

/* ---------- Clientes ---------- */

async function adminClients(main) {
  const area = h("div", null, loading());
  const search = h("input", { class: "input", type: "search", placeholder: "Buscar por nome, e-mail ou cidade", "aria-label": "Buscar cliente", style: "max-width:420px" });
  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Clientes cadastrados"))),
    search, area);

  async function load() {
    try {
      const clients = await api.get("/admin/clients", { q: search.value.trim() });
      fill(area, clients.length
        ? h("div", { class: "table-wrap" }, h("table", null,
          h("thead", null, h("tr", null, ["Nome", "Contato", "Cidade", "Cadastro", "Pedidos"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", null, clients.map((c) => {
            const wa = whatsappLink(c.phone);
            return h("tr", null,
              h("td", null, h("strong", null, c.name)),
              h("td", null, h("a", { href: `mailto:${c.email}` }, c.email), h("br"),
                c.phone || "—", wa && h("a", { href: wa, target: "_blank", rel: "noopener", style: "margin-left:8px;font-size:13px" }, "WhatsApp")),
              h("td", null, c.city || "—"),
              h("td", null, DATE_SHORT.format(new Date(c.created_at))),
              h("td", null, c.quotes
                ? h("a", { href: "#/painel", onclick: () => { adminFilters.q = c.email; adminFilters.status = ""; } }, plural(c.quotes, "pedido", "pedidos"))
                : h("span", { class: "muted" }, "Nenhum")));
          }))))
        : h("div", { class: "empty" }, search.value ? "Nenhum cliente encontrado." : "Os clientes que criarem conta aparecem aqui."));
    } catch (err) {
      fill(area, h("div", { class: "empty" }, err.message));
    }
  }
  search.addEventListener("input", debounce(load));
  await load();
}

boot();
