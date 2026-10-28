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

const media = (id) => (id ? `/media/${id}` : null);

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
      form.elements[e.field]?.setAttribute("aria-invalid", "true");
      if (!placed) form.elements[e.field]?.focus();
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

function openModal(title, build) {
  const close = () => {
    dialog.close();
    dialog.remove();
  };
  const dialog = h("dialog", { class: "modal", "aria-label": title });
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
    h("a", { class: "brand", href: "#/" }, h("img", { src: "/static/icon.svg", alt: "" }), site?.business_name || "Buffet"),
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
          h("a", { class: "brand", href: "#/", style: "color:var(--ink)" }, h("img", { src: "/static/icon.svg", alt: "" }), s.business_name),
          h("p", { style: "max-width:42ch" }, s.tagline)),
        h("div", null, h("h4", null, "Contato"),
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
  [/^\/portfolio$/, () => renderPortfolio()],
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

async function renderHome(anchor) {
  const s = state.site;
  document.title = `${s.business_name} | ${s.tagline || "Buffet"}`;
  const eventsArea = h("div", { class: "gallery" }, loading());

  publicPage([
    h("section", { class: "hero", "aria-label": "Apresentação" },
      s.hero_image_id ? h("img", { class: "hero__img", src: media(s.hero_image_id), alt: "" }) : null,
      h("div", { class: "wrap hero__content" },
        s.tagline && h("p", { class: "eyebrow" }, s.tagline),
        h("h1", { class: "hero__title" }, s.hero_title || s.business_name),
        s.hero_text && h("p", { class: "hero__text" }, s.hero_text),
        h("div", { class: "hero__actions" },
          h("a", { class: "btn btn--primary", href: "#/orcamento" }, "Agendar evento"),
          h("a", { class: "btn btn--outline-light", href: "#/portfolio" }, "Ver portfólio")))),

    h("section", { class: "section", id: "sobre", "aria-labelledby": "t-sobre" },
      h("div", { class: "wrap" },
        h("div", { class: "about" },
          s.owner_image_id && h("div", { class: "about__photo" }, img(s.owner_image_id, s.owner_name)),
          h("div", { class: "about__text" },
            h("p", { class: "eyebrow" }, "Quem cozinha para você"),
            h("h2", { class: "about__name", id: "t-sobre" }, s.owner_name || "Sobre mim"),
            s.owner_role && h("p", { class: "about__role" }, s.owner_role),
            h("div", { class: "prose" }, paragraphs(s.bio)),
            s.owner_name && h("p", { class: "signature" }, s.owner_name.split(" ")[0]))),
        s.bio_photos.length > 0 && h("div", { class: "photo-strip" },
          s.bio_photos.map((p) => h("figure", null, img(p.image_id, p.caption), p.caption && h("figcaption", null, p.caption)))))),

    h("section", { class: "section section--sand", id: "historia", "aria-labelledby": "t-historia" },
      h("div", { class: "wrap history" },
        h("div", { style: "display:grid;gap:22px" },
          s.founded_year && h("p", { class: "history__year" }, h("small", null, "Desde"), s.founded_year),
          h("h2", { class: "section__title", id: "t-historia" }, s.history_title || "Nossa história"),
          h("div", { class: "prose" }, paragraphs(s.history))),
        s.history_image_id && h("div", { class: "history__img" }, img(s.history_image_id, "")))),

    h("section", { class: "section", "aria-labelledby": "t-portfolio" },
      h("div", { class: "wrap" },
        h("div", { class: "section__head" },
          h("p", { class: "eyebrow" }, "Portfólio"),
          h("h2", { class: "section__title", id: "t-portfolio" }, "Eventos que já servimos"),
          h("p", { class: "section__lede" }, "Um pouco do que fizemos para outras famílias e empresas.")),
        eventsArea,
        h("p", { style: "margin-top:32px" }, h("a", { class: "btn btn--ghost", href: "#/portfolio" }, "Ver todos os eventos")))),

    h("section", { class: "section section--dark", "aria-labelledby": "t-como" },
      h("div", { class: "wrap" },
        h("div", { class: "section__head" },
          h("p", { class: "eyebrow", style: "color:#e9a27f" }, "Orçamento"),
          h("h2", { class: "section__title", id: "t-como" }, "Como pedir o seu orçamento"),
          h("p", { class: "section__lede" }, "Sem formulário perdido no e-mail: a conversa acontece aqui no site e fica guardada.")),
        h("div", { class: "steps" },
          h("div", { class: "step" }, h("h3", null, "Crie sua conta"), h("p", null, "Só nome, e-mail, telefone e cidade. Leva um minuto.")),
          h("div", { class: "step" }, h("h3", null, "Conte sobre o evento"), h("p", null, "Tipo de festa, data, número de convidados, local e o que você imagina.")),
          h("div", { class: "step" }, h("h3", null, `Converse com ${s.owner_name ? s.owner_name.split(" ")[0] : "a gente"}`),
            h("p", null, "Você recebe a resposta aqui mesmo e acompanha tudo pela sua conta."))),
        h("div", { class: "cta", style: "margin-top:clamp(40px,6vw,64px)" },
          h("h2", null, "Vamos conversar sobre a sua festa?"),
          h("a", { class: "btn btn--light", href: "#/orcamento" }, "Agendar evento")))),
  ], { over: Boolean(s.hero_image_id) });

  if (anchor) requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView());

  try {
    const events = await api.get("/events", { limit: 3 });
    fill(eventsArea, events.length ? events.map(eventCard) : h("div", { class: "empty" }, "Os primeiros eventos aparecem aqui em breve."));
  } catch {
    fill(eventsArea, h("div", { class: "empty" }, "Não foi possível carregar o portfólio agora."));
  }
}

function eventCard(e) {
  const cover = e.photos[0]?.image_id;
  const meta = [e.event_date && fmtMonth(e.event_date), e.guests && plural(e.guests, "convidado", "convidados"), e.location]
    .filter(Boolean).join(" · ");
  return h("a", { class: "card", href: `#/portfolio/${e.id}` },
    h("div", { class: "card__img" },
      cover ? img(cover, e.title) : h("div", { class: "loading" }, icon("photo")),
      e.photos.length > 1 && h("span", { class: "card__count" }, plural(e.photos.length, "foto", "fotos"))),
    h("p", { class: "card__type" }, e.event_type),
    h("h3", { class: "card__title" }, e.title),
    meta && h("p", { class: "card__meta" }, meta));
}

async function renderPortfolio() {
  document.title = `Portfólio | ${state.site.business_name}`;
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Filtrar por tipo de evento" });
  const grid = h("div", { class: "gallery" }, loading());
  publicPage(h("div", { class: "wrap", style: "padding-bottom:88px" },
    h("div", { class: "page-head" },
      h("p", { class: "eyebrow" }, "Portfólio"),
      h("h1", null, "Eventos que já servimos"),
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
  let current = "";
  const draw = () => {
    fill(chips, ["", ...types].map((t) => h("button", {
      class: "chip", type: "button", "aria-pressed": String(current === t),
      onclick: () => {
        current = t;
        draw();
      },
    }, t || "Todos")));
    const list = all.filter((e) => !current || e.event_type === current);
    fill(grid, list.length ? list.map(eventCard) : h("div", { class: "empty" }, "Nenhum evento publicado ainda."));
  };
  draw();
}

async function renderEvent(id) {
  const area = h("div", { class: "wrap event" }, loading());
  publicPage(area);
  let e;
  try {
    e = await api.get(`/events/${id}`);
  } catch (err) {
    fill(area, h("div", { class: "empty" }, err.message, h("a", { class: "btn btn--ghost", href: "#/portfolio" }, "Voltar ao portfólio")));
    return;
  }
  document.title = `${e.title} | ${state.site.business_name}`;
  const photos = e.photos.map((p) => p.image_id);
  fill(area,
    h("div", { class: "page-head", style: "padding-bottom:0" },
      h("a", { class: "back", href: "#/portfolio" }, icon("left"), "Portfólio"),
      h("div", { class: "event__head" },
        h("p", { class: "eyebrow" }, e.event_type),
        h("h1", null, e.title),
        h("div", { class: "facts" },
          e.event_date && h("span", null, h("strong", null, "Data: "), fmtDate(e.event_date)),
          e.guests && h("span", null, h("strong", null, "Convidados: "), e.guests),
          e.location && h("span", null, h("strong", null, "Local: "), e.location)),
        e.description && h("div", { class: "prose" }, paragraphs(e.description)))),
    photos.length ? h("div", { class: "event__photos" },
      photos.map((imageId, i) => h("button", {
        type: "button", "aria-label": `Ampliar foto ${i + 1} de ${photos.length}`, onclick: () => lightbox(photos, i, e.title),
        style: i === 0 ? null : `grid-column: span ${gallerySpan(photos.length - 1)}`,
      },
        img(imageId, `${e.title}, foto ${i + 1}`)))) : null,
    h("div", { class: "cta" },
      h("h2", null, "Quer uma festa assim?"),
      h("a", { class: "btn btn--light", href: "#/orcamento" }, "Agendar evento")));
}

/** Depois da capa, as fotos ocupam a linha toda: 1 por linha, 2 lado a lado ou 3 por linha. */
function gallerySpan(rest) {
  if (rest === 1) return 6;
  if (rest % 3 === 0) return 2;
  if (rest % 2 === 0) return 3;
  return 2;
}

function lightbox(ids, start, title) {
  let index = start;
  const picture = h("img", { alt: "" });
  const counter = h("span");
  const show = () => {
    picture.src = media(ids[index]);
    picture.alt = `${title}, foto ${index + 1}`;
    counter.textContent = `${index + 1} de ${ids.length}`;
  };
  const step = (d) => {
    index = (index + d + ids.length) % ids.length;
    show();
  };
  const close = () => {
    box.remove();
    document.removeEventListener("keydown", keys);
    opener?.focus();
  };
  const keys = (e) => {
    if (e.key === "Escape") close();
    if (e.key === "ArrowRight") step(1);
    if (e.key === "ArrowLeft") step(-1);
  };
  const opener = document.activeElement;
  const closeBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Fechar", onclick: close }, icon("close"));
  const box = h("div", { class: "lightbox", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "lightbox__top" }, counter, closeBtn),
    h("div", { class: "lightbox__stage", onclick: (e) => e.target === e.currentTarget && close() }, picture),
    ids.length > 1 && h("button", { class: "lightbox__nav lightbox__nav--prev", type: "button", "aria-label": "Foto anterior", onclick: () => step(-1) }, icon("left")),
    ids.length > 1 && h("button", { class: "lightbox__nav lightbox__nav--next", type: "button", "aria-label": "Próxima foto", onclick: () => step(1) }, icon("right")));
  show();
  document.body.append(box);
  document.addEventListener("keydown", keys);
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
  const form = h("form", { class: "form", novalidate: true },
    h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
    h("div", { class: "form__row" },
      field({ label: "Tipo de evento", name: "event_type", as: "select", required: true, options: [["", "Escolha…"], ...s.event_types.map((t) => [t, t])] }),
      field({ label: "Data do evento", name: "event_date", type: "date", required: true, min: todayISO() })),
    h("div", { class: "form__row" },
      field({ label: "Número de convidados", name: "guests", type: "number", min: 1, inputmode: "numeric", required: true, placeholder: "Ex.: 120" }),
      field({ label: "Quanto pretende investir", name: "budget", as: "select", options: s.budgets.map((b) => [b, b || "Prefiro conversar"]) })),
    field({ label: "Local do evento", name: "location", required: true, placeholder: "Salão, chácara, casa… e a cidade" }),
    field({ label: "Conte como você imagina a festa", name: "details", as: "textarea", placeholder: "Cardápio que gosta, restrições alimentares, horário, estilo da festa…", hint: "Opcional, mas ajuda a preparar uma proposta certeira." }),
    h("button", { class: "btn btn--primary btn--block", type: "submit" }, "Enviar pedido e abrir conversa"));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const v = formValues(form);
    submitting(form, async () => {
      const quote = await api.post("/quotes", { ...v, guests: v.guests ? Number(v.guests) : null });
      toast("Pedido enviado! Agora é só conversar por aqui.");
      go(`/conta/pedidos/${quote.id}`);
    });
  });

  const firstName = s.owner_name ? s.owner_name.split(" ")[0] : "a gente";
  splitPage("Conte sobre o seu evento",
    `Com essas informações, ${firstName} prepara a proposta e responde aqui no site. Você recebe as mensagens na sua conta.`,
    h("div", { class: "panel-card" },
      h("p", { class: "eyebrow" }, `Olá, ${state.user.name.split(" ")[0]}`),
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
    body.append(h("div", { class: `bubble ${mine ? "bubble--me" : "bubble--them"}` },
      !mine && h("span", { class: "bubble__who" }, m.from_owner ? state.site.owner_name || state.site.business_name : quote.client.name),
      h("span", null, m.body),
      h("time", { datetime: m.created_at }, TIME.format(date))));
  };

  body.append(h("p", { class: "chat__notice" }, owner
    ? `Pedido enviado em ${DATE_SHORT.format(new Date(quote.created_at))}. As mensagens que você escrever aqui aparecem na conta de ${quote.client.name.split(" ")[0]}.`
    : `Pedido enviado! ${ownerFirst} responde por aqui. Você também pode mandar mais detalhes, fotos de referência por link ou dúvidas.`));
  quote.messages.forEach(addMessage);

  const text = h("textarea", { class: "input", name: "body", rows: "1", placeholder: "Escreva sua mensagem…", "aria-label": "Mensagem", maxlength: "4000" });
  const sendBtn = h("button", { class: "btn btn--primary", type: "submit", "aria-label": "Enviar" }, icon("send"), h("span", null, "Enviar"));
  const compose = h("form", { class: "chat__compose" }, text, sendBtn,
    h("p", { class: "chat__hint" }, "Enter envia · Shift + Enter quebra a linha"));
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
      addMessage(m);
      body.scrollTop = body.scrollHeight;
      if (owner && quote.status === "novo") {
        quote.status = "em_conversa";
        statusSlot.replaceChildren(statusControl());
        onStatus?.();
      }
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
