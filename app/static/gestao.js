/* Gestão do buffet no painel: o que antes era a planilha (.ods).
 *
 * Abas: Resumo (gráficos), DRE, Eventos, Estoque, Compras, Saídas, Despesas, Precificação e
 * Configurações (alíquotas, listas, importar a planilha antiga e baixar tudo em .xlsx).
 * O site faz as contas (app/finance.py); aqui só lançamos e mostramos.
 *
 * Usa h(), fill(), field(), api, toast(), loading(), openModal(), submitting() e onLeave() de app.js.
 */
"use strict";

const G = "/admin/gestao";
const GESTAO_TABS = [
  ["resumo", "Resumo"],
  ["dre", "DRE"],
  ["eventos", "Eventos"],
  ["estoque", "Estoque"],
  ["compras", "Compras"],
  ["saidas", "Saídas"],
  ["despesas", "Despesas"],
  ["precificacao", "Precificação"],
  ["cardapio", "Cardápio"],
  ["config", "Configurações"],
];
const GESTAO_LIBS = {
  xlsx: {
    src: "https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js",
    integrity: "sha384-EnyY0/GSHQGSxSgMwaIPzSESbqoOLSexfnSMN2AP+39Ckmn92stwABZynq1JyzdT",
  },
  chart: {
    src: "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js",
    integrity: "sha384-dug+JxfBvklEQdJ4AYuBBAIScUz0bVN73xpy273gcAwHjb3qI0fXmuYNaNfdyYJG",
  },
};
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const BRL0 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const INT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const qty = (v) => Number(v || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
const pct = (v) => (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
const short = (v) => (Math.abs(v) >= 1000 ? `R$ ${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil` : BRL0.format(v));
/** Como no DRE da planilha: negativos entre parênteses, zero vira traço. */
const acct = (v) => (Math.abs(v) < 0.005 ? "–" : v < 0 ? `(${BRL0.format(-v)})` : BRL0.format(v));
/** Aceita "1.234,56", "1234,56" e "1234.56". */
function parseNum(value) {
  let s = String(value ?? "").trim().replace(/\s|R\$/g, "");
  if (!s) return null;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? n : NaN;
}
const numText = (v, digits = 3) => (v === null || v === undefined || v === "" ? "" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: digits, useGrouping: false }));
const STATUS_EVENTO = { orcamento: "Orçamento", confirmado: "Confirmado", realizado: "Realizado", cancelado: "Cancelado" };
const TIPO_SAIDA = { evento: "Evento (CMV)", perda: "Perda/Quebra", consumo: "Consumo interno" };

const loadedLibs = {};
function loadLib({ src, integrity }) {
  if (!loadedLibs[src]) {
    loadedLibs[src] = new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.integrity = integrity;
      el.crossOrigin = "anonymous";
      el.onload = resolve;
      el.onerror = () => { delete loadedLibs[src]; reject(new Error("Não foi possível carregar uma biblioteca. Confira a internet e recarregue.")); };
      document.head.append(el);
    });
  }
  return loadedLibs[src];
}

/* ---------- Dados usados em vários formulários (recarregados ao abrir cada aba) ---------- */

const gdata = { config: null, categories: [], items: [], events: [], year: null, years: [] };

async function loadBasics() {
  const [config, categories, items, events, years] = await Promise.all([
    api.get(`${G}/config`), api.get(`${G}/categorias`), api.get(`${G}/insumos`), api.get(`${G}/eventos`), api.get(`${G}/anos`),
  ]);
  Object.assign(gdata, { config, categories, items, events, years });
  if (!gdata.year || !years.includes(gdata.year)) gdata.year = years.includes(new Date().getFullYear()) ? new Date().getFullYear() : years[0];
}

/* ---------- Peças de interface ---------- */

function numField({ label, name, value, hint, required = true, digits = 3, prefix }) {
  return field({
    label, name, hint, required, value: numText(value, digits), inputmode: "decimal", autocomplete: "off",
    placeholder: prefix ? `${prefix} 0,00` : "0",
  });
}

function itemSelect(name, value, { label = "Insumo", onlyActive = true } = {}) {
  const id = `f-${name}-${++fieldSeq}`;
  const groups = {};
  gdata.items.filter((i) => !onlyActive || i.active || i.id === value).forEach((i) => (groups[i.category] ||= []).push(i));
  const select = h("select", { id, name, class: "input", required: true },
    h("option", { value: "" }, "Escolha o insumo"),
    Object.entries(groups).map(([cat, items]) => h("optgroup", { label: cat },
      items.map((i) => h("option", { value: i.id, selected: i.id === value }, `${i.code} · ${i.name} (${i.unit})`)))));
  return h("div", { class: "field" }, h("label", { class: "field__label", for: id }, label), select,
    h("p", { class: "field__error", "data-error-for": name, "aria-live": "polite" }));
}

function eventSelect(name, value, { label = "Evento", required = false, empty = "Nenhum" } = {}) {
  const options = [["", empty], ...gdata.events.map((e) => [e.id, `${e.code} · ${fmtShort(e.event_date)} · ${e.client}`])];
  return field({ label, name, as: "select", options, value: value ?? "", required });
}

const yearSelect = (onChange) => h("select", { class: "input fin-year", "aria-label": "Ano", onchange: (e) => { gdata.year = Number(e.target.value); onChange(); } },
  gdata.years.map((y) => h("option", { value: y, selected: y === gdata.year }, y)));

const monthSelect = (value, onChange) => h("select", { class: "input", "aria-label": "Mês", onchange: (e) => onChange(e.target.value ? Number(e.target.value) : null) },
  h("option", { value: "" }, "Ano inteiro"), MESES.map((m, i) => h("option", { value: i + 1, selected: value === i + 1 }, m)));

function pill(text, tone) {
  return h("span", { class: `fin-pill fin-pill--${tone}` }, text);
}

const STOCK_TONE = { OK: "ok", REPOR: "warn", "SEM ESTOQUE": "bad", NEGATIVO: "bad" };
const EVENT_TONE = { orcamento: "muted", confirmado: "info", realizado: "ok", cancelado: "bad" };

function emptyRow(cols, text) {
  return h("tr", null, h("td", { colspan: cols, class: "fin-empty" }, text));
}

function rowActions(onEdit, onDelete) {
  return h("td", { class: "fin-actions" },
    h("button", { class: "link-btn", type: "button", onclick: onEdit }, "Editar"),
    onDelete && h("button", { class: "link-btn fin-del", type: "button", onclick: onDelete }, "Apagar"));
}

async function confirmDelete(message, path, after) {
  if (!confirm(message)) return;
  try {
    await api.del(path);
    toast("Apagado.");
    after();
  } catch (err) {
    toast(err.message, "error");
  }
}

/** Formulário num diálogo. `fields` monta os campos; `collect` transforma os valores para a API. */
function formModal(title, { fields, collect, save, submitLabel = "Salvar", onSaved }) {
  openModal(title, (close) => {
    const form = h("form", { class: "form", novalidate: true },
      fields(),
      h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
      h("div", { class: "form__actions" },
        h("button", { class: "btn btn--ghost", type: "button", onclick: close }, "Cancelar"),
        h("button", { class: "btn btn--primary", type: "submit" }, submitLabel)));
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitting(form, async () => {
        const values = formValues(form);
        const payload = collect(values, form);
        const saved = await save(payload);
        close();
        toast("Salvo.");
        onSaved?.(saved);
      });
    });
    return form;
  });
}

/** Converte campos numéricos (com vírgula) e avisa no próprio campo se algo não for número. */
function numbers(form, values, names, optional = []) {
  const errors = [];
  for (const name of [...names, ...optional]) {
    const n = parseNum(values[name]);
    if (n === null && optional.includes(name)) { values[name] = null; continue; }
    if (n === null) { errors.push({ field: name, message: "Campo obrigatório." }); continue; }
    if (Number.isNaN(n)) { errors.push({ field: name, message: "Use só números (ex.: 12,5)." }); continue; }
    values[name] = n;
  }
  if (errors.length) {
    const err = new Error("Confira os campos destacados.");
    err.errors = errors;
    throw err;
  }
  return values;
}
const intOrNull = (v) => (v === "" || v === undefined ? null : Number(v));

/* ---------- Formulários de lançamento (também usados pelos atalhos do topo) ---------- */

function stockInForm(row, onSaved) {
  formModal(row ? "Editar compra" : "Nova compra", {
    fields: () => [
      h("div", { class: "form__row" },
        field({ label: "Data", name: "entry_date", type: "date", required: true, value: row?.entry_date || todayISO() }),
        itemSelect("item_id", row?.item_id)),
      h("div", { class: "form__row" },
        numField({ label: "Quantidade", name: "quantity", value: row?.quantity }),
        numField({ label: "Valor unitário (R$)", name: "unit_cost", value: row?.unit_cost, digits: 4, prefix: "R$" })),
      h("div", { class: "form__row" },
        field({ label: "Fornecedor", name: "supplier", value: row?.supplier || "", maxlength: 120 }),
        field({ label: "Nº da nota", name: "invoice", value: row?.invoice || "", maxlength: 40 })),
      h("p", { class: "field__hint" }, "A compra vira estoque e atualiza o custo médio. Ela não entra como despesa no DRE."),
    ],
    collect: (v, form) => ({ ...numbers(form, v, ["quantity", "unit_cost"]), item_id: intOrNull(v.item_id) }),
    save: (p) => (row ? api.put(`${G}/compras/${row.id}`, p) : api.post(`${G}/compras`, p)),
    onSaved,
  });
}

function stockOutForm(row, onSaved, preset = {}) {
  formModal(row ? "Editar saída" : "Nova saída", {
    fields: () => {
      const kind = field({ label: "Tipo de saída", name: "kind", as: "select", required: true, value: row?.kind || preset.kind || "evento",
        options: Object.entries(TIPO_SAIDA) });
      const ev = eventSelect("event_id", row?.event_id ?? preset.event_id, { label: "Evento", empty: "Escolha o evento" });
      const toggle = () => { ev.hidden = kind.querySelector("select").value !== "evento"; };
      kind.querySelector("select").addEventListener("change", toggle);
      queueMicrotask(toggle);
      return [
        h("div", { class: "form__row" },
          field({ label: "Data", name: "entry_date", type: "date", required: true, value: row?.entry_date || todayISO() }),
          itemSelect("item_id", row?.item_id)),
        h("div", { class: "form__row" }, numField({ label: "Quantidade", name: "quantity", value: row?.quantity }), kind),
        ev,
        field({ label: "Observação", name: "note", value: row?.note || "", maxlength: 200 }),
        h("p", { class: "field__hint" }, "O custo é o custo médio do insumo na data da saída. “Evento” vira CMV do evento; perdas e consumo interno vão para as despesas."),
      ];
    },
    collect: (v, form) => ({ ...numbers(form, v, ["quantity"]), item_id: intOrNull(v.item_id), event_id: v.kind === "evento" ? intOrNull(v.event_id) : null }),
    save: (p) => (row ? api.put(`${G}/saidas/${row.id}`, p) : api.post(`${G}/saidas`, p)),
    onSaved,
  });
}

function expenseForm(row, onSaved) {
  const groups = {};
  gdata.categories.forEach((c) => (groups[c.group] ||= []).push(c));
  formModal(row ? "Editar despesa" : "Nova despesa", {
    fields: () => {
      const id = `f-category-${++fieldSeq}`;
      const cat = h("div", { class: "field" }, h("label", { class: "field__label", for: id }, "Categoria"),
        h("select", { id, name: "category_id", class: "input", required: true },
          h("option", { value: "" }, "Escolha a categoria"),
          Object.entries(groups).map(([g, cats]) => h("optgroup", { label: g },
            cats.map((c) => h("option", { value: c.id, selected: c.id === row?.category_id }, c.name))))),
        h("p", { class: "field__hint" }, "A categoria define a linha do DRE."),
        h("p", { class: "field__error", "data-error-for": "category_id", "aria-live": "polite" }));
      return [
        h("div", { class: "form__row" },
          field({ label: "Data", name: "entry_date", type: "date", required: true, value: row?.entry_date || todayISO() }),
          numField({ label: "Valor (R$)", name: "amount", value: row?.amount, digits: 2, prefix: "R$" })),
        cat,
        field({ label: "Descrição", name: "description", value: row?.description || "", maxlength: 200 }),
        h("div", { class: "form__row" },
          field({ label: "Fornecedor", name: "supplier", value: row?.supplier || "", maxlength: 120 }),
          field({ label: "Forma de pagamento", name: "payment", as: "select", value: row?.payment || "",
            options: [["", "—"], ...gdata.config.payment_methods.map((p) => [p, p])] })),
        eventSelect("event_id", row?.event_id, { label: "Evento (opcional)" }),
      ];
    },
    collect: (v, form) => ({ ...numbers(form, v, ["amount"]), category_id: intOrNull(v.category_id), event_id: intOrNull(v.event_id) }),
    save: (p) => (row ? api.put(`${G}/despesas/${row.id}`, p) : api.post(`${G}/despesas`, p)),
    onSaved,
  });
}

function eventForm(row, onSaved) {
  formModal(row ? `Editar evento ${row.code}` : "Novo evento", {
    fields: () => [
      h("div", { class: "form__row" },
        field({ label: "Data do evento", name: "event_date", type: "date", required: true, value: row?.event_date || "" }),
        field({ label: "Situação", name: "status", as: "select", value: row?.status || "confirmado", options: Object.entries(STATUS_EVENTO),
          hint: "Só “Realizado” entra na receita do DRE." })),
      field({ label: "Cliente / evento", name: "client", required: true, value: row?.client || "", maxlength: 120 }),
      h("div", { class: "form__row" },
        field({ label: "Tipo", name: "event_type", as: "select", value: row?.event_type || gdata.config.event_types[0],
          options: [...new Set([...gdata.config.event_types, row?.event_type].filter(Boolean))].map((t) => [t, t]) }),
        field({ label: "Convidados", name: "guests", type: "number", min: 1, required: true, value: row?.guests || "", inputmode: "numeric" })),
      h("div", { class: "form__row" },
        numField({ label: "Valor por pessoa (R$)", name: "price_per_guest", value: row?.price_per_guest, digits: 2, prefix: "R$" }),
        numField({ label: "Desconto (R$)", name: "discount", value: row?.discount || "", digits: 2, required: false, prefix: "R$" })),
      field({ label: "Código", name: "code", value: row?.code || "", maxlength: 20, hint: "Deixe em branco para o site criar (EV001, EV002…)." }),
      field({ label: "Observações", name: "notes", as: "textarea", rows: 2, value: row?.notes || "", maxlength: 2000 }),
    ],
    collect: (v, form) => {
      const out = numbers(form, v, ["price_per_guest"], ["discount"]);
      return { ...out, discount: out.discount || 0, guests: intOrNull(v.guests), quote_id: row?.quote_id ?? null };
    },
    save: (p) => (row ? api.put(`${G}/eventos/${row.id}`, p) : api.post(`${G}/eventos`, p)),
    onSaved,
  });
}

function itemForm(row, onSaved) {
  formModal(row ? `Editar ${row.code}` : "Novo insumo", {
    fields: () => [
      field({ label: "Nome do insumo", name: "name", required: true, value: row?.name || "", maxlength: 120 }),
      h("div", { class: "form__row" },
        field({ label: "Categoria", name: "category", as: "select", value: row?.category || gdata.config.item_categories[0],
          options: [...new Set([...gdata.config.item_categories, row?.category].filter(Boolean))].map((c) => [c, c]) }),
        field({ label: "Unidade", name: "unit", as: "select", value: row?.unit || "kg",
          options: [...new Set([...gdata.config.units, row?.unit].filter(Boolean))].map((u) => [u, u]) })),
      h("div", { class: "form__row" },
        numField({ label: "Estoque mínimo", name: "min_stock", value: row?.min_stock ?? "", required: false }),
        field({ label: "Código", name: "code", value: row?.code || "", maxlength: 20, hint: "Em branco: o site cria (ex.: CAR012)." })),
      h("div", { class: "form__row" },
        numField({ label: "Estoque inicial", name: "initial_stock", value: row?.initial_stock ?? "", required: false }),
        numField({ label: "Custo unitário inicial (R$)", name: "initial_cost", value: row?.initial_cost ?? "", digits: 4, required: false, prefix: "R$" })),
      row && h("label", { class: "fin-check" }, h("input", { type: "checkbox", name: "active", checked: row.active }), " Em uso (desmarque para esconder dos formulários)"),
    ],
    collect: (v, form) => {
      const out = numbers(form, v, [], ["min_stock", "initial_stock", "initial_cost"]);
      return { ...out, min_stock: out.min_stock || 0, initial_stock: out.initial_stock || 0, initial_cost: out.initial_cost || 0, active: row ? !!form.elements.active.checked : true };
    },
    save: (p) => (row ? api.put(`${G}/insumos/${row.id}`, p) : api.post(`${G}/insumos`, p)),
    onSaved,
  });
}

/* ---------- Painel: a aba Gestão ---------- */

async function adminGestao(main, sub = "resumo") {
  if (!GESTAO_TABS.some(([k]) => k === sub)) sub = "resumo";
  const content = h("div", { class: "fin" }, loading());
  const reload = () => adminGestao(main, sub);
  const quick = (label, fn) => h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: fn }, `+ ${label}`);
  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Gestão")),
      h("div", { class: "fin-quick", role: "group", "aria-label": "Lançamentos rápidos" },
        quick("Compra", () => stockInForm(null, reload)),
        quick("Saída", () => stockOutForm(null, reload)),
        quick("Despesa", () => expenseForm(null, reload)),
        quick("Evento", () => eventForm(null, reload)))),
    h("nav", { class: "fin-tabs", "aria-label": "Partes da gestão" },
      GESTAO_TABS.map(([key, label]) => h("a", { href: `#/painel/gestao/${key}`, "aria-current": key === sub ? "page" : null }, label))),
    content);
  try {
    await loadBasics();
  } catch (err) {
    fill(content, h("p", { class: "form__error" }, err.message));
    return;
  }
  const views = { resumo: finResumo, dre: finDre, eventos: finEventos, estoque: finEstoque, compras: finCompras,
    saidas: finSaidas, despesas: finDespesas, precificacao: finPrecificacao, cardapio: finCardapio, config: finConfig };
  await views[sub](content, reload);
}

/* ---------- Resumo: os gráficos da antiga aba Resultados ---------- */

async function finResumo(content) {
  const COLORS = { line: "rgba(214,150,108,.14)", muted: "#c4a493", copper: "#d9925f", wine: "#b8261b", wineLight: "#e0604a", cream: "#fbf3ea", ok: "#7fd6a4", panel: "#1d0a08" };
  const PAL = ["#d9925f", "#b8261b", "#f2c48d", "#fbf3ea", "#e0604a", "#8c3a2b", "#c9a27e", "#ff9f7a", "#7fd6a4", "#a8746b", "#e8d5c4", "#d4483a", "#6e4b3e"];
  const alpha = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };

  const kpi = (label, accent) => {
    const val = h("div", { class: "dash-kpi__val" }, "—");
    const sub = h("div", { class: "dash-kpi__sub" }, "");
    return { el: h("div", { class: "dash-kpi", style: `--k:${accent}` }, h("div", { class: "dash-kpi__lab" }, label), val, sub), val, sub };
  };
  const K = {
    receita: kpi("Receita do ano", COLORS.copper),
    lucro: kpi("Lucro líquido", COLORS.ok),
    eventos: kpi("Eventos realizados", COLORS.cream),
    ticket: kpi("Ticket por convidado", "#f2c48d"),
    estoque: kpi("Valor em estoque", COLORS.copper),
    preco: kpi("Preço sugerido / pessoa", COLORS.wineLight),
  };
  const card = (title, wide, label, center) => {
    const note = h("small", null, "");
    const canvas = h("canvas", { "aria-label": label, role: "img" });
    const centerVal = center ? h("b", null, "—") : null;
    const box = h("div", { class: "dash-chart" }, canvas, center && h("div", { class: "dash-chart__center" }, h("div", null, centerVal, h("span", null, center))));
    return { el: h("article", { class: `dash-card ${wide}` }, h("h2", null, h("span", null, title), note), box), canvas, note, centerVal };
  };
  const C = {
    mes: card("Receita, custos e lucro por mês", "dash-card--w8", "Receita, custos e lucro por mês"),
    desp: card("Para onde vai o dinheiro", "", "Despesas do ano por grupo", "total"),
    ev: card("Receita x insumos por evento", "dash-card--w6", "Receita e custo de insumos por evento"),
    prec: card("Composição do preço por pessoa", "dash-card--w6", "Composição do preço por pessoa", "por pessoa"),
    est: card("Estoque por tipo de produto", "dash-card--w8", "Valor em estoque por tipo"),
  };
  const list = (title, wide = "") => {
    const body = h("div", { class: "dash-alerts" });
    const note = h("small", null, "");
    return { el: h("article", { class: `dash-card ${wide}` }, h("h2", null, h("span", null, title), note), body), body, note };
  };
  const alerts = list("Itens para repor");
  const upcoming = list("Próximos eventos", "dash-card--w12");
  const errorBox = h("p", { class: "dash-error", role: "alert", hidden: true });
  const board = h("div", { class: "dash-board" },
    h("section", { class: "dash-kpis", "aria-label": "Resumo do ano" }, Object.values(K).map((k) => k.el)),
    h("section", { class: "dash-grid" }, C.mes.el, C.desp.el, C.ev.el, C.prec.el, C.est.el, alerts.el, upcoming.el));
  const yearSel = yearSelect(() => load());

  fill(content, h("div", { class: "dash" },
    h("div", { class: "dash-bar" },
      h("div", { class: "dash-brand" },
        h("img", { src: "/static/icone-192.png", alt: "", width: 44, height: 44 }),
        h("div", null, h("strong", null, "Central de resultados"), h("span", null, "estoque, eventos, despesas e DRE"))),
      h("div", { class: "dash-controls" }, h("span", { class: "dash-chip dash-chip--live" }, h("span", { class: "dash-chip__dot" }), h("span", null, "Atualizado a cada lançamento")), yearSel)),
    errorBox, board));

  try {
    await loadLib(GESTAO_LIBS.chart);
    Chart.defaults.color = COLORS.muted;
    Chart.defaults.borderColor = COLORS.line;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    Chart.defaults.plugins.legend.labels.boxHeight = 10;
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(18,6,5,.96)";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(217,146,95,.45)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  }
  const charts = {};
  const draw = (key, cfg) => {
    if (!window.Chart) return;
    if (charts[key]) { charts[key].data = cfg.data; charts[key].options = cfg.options; charts[key].update(); return; }
    charts[key] = new Chart(C[key].canvas, cfg);
  };
  onLeave(() => Object.values(charts).forEach((c) => c.destroy()));

  async function load() {
    let d, sims;
    try {
      [d, sims] = await Promise.all([api.get(`${G}/resumo`, { ano: gdata.year }), api.get(`${G}/precificacao`)]);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      return;
    }
    const V = Object.fromEntries([...d.dre.lines, ...d.dre.indicators].filter((l) => l.months).map((l) => [l.key, l]));
    K.receita.val.textContent = BRL0.format(V.gross.total);
    K.receita.sub.textContent = `líquida: ${BRL0.format(V.net.total)}`;
    K.lucro.val.textContent = BRL0.format(V.net_profit.total);
    K.lucro.val.className = `dash-kpi__val ${V.net_profit.total >= 0 ? "is-pos" : "is-neg"}`;
    K.lucro.sub.textContent = `margem: ${pct(V.net_margin.total)}`;
    K.eventos.val.textContent = INT.format(V.events.total);
    K.eventos.sub.textContent = `${INT.format(V.guests.total)} convidados`;
    K.ticket.val.textContent = BRL.format(V.ticket.total);
    K.ticket.sub.textContent = `insumos: ${BRL.format(V.cmv_per_guest.total)} por pessoa`;
    K.estoque.val.textContent = BRL0.format(d.stock_value);
    K.estoque.sub.textContent = d.alerts.length ? `${d.alerts.length} itens para repor` : "nada para repor";
    K.estoque.sub.className = `dash-kpi__sub ${d.alerts.length ? "is-warn" : ""}`;

    const used = V.gross.months.map((v, i) => (v || V.net_profit.months[i] ? i : -1)).filter((i) => i >= 0);
    const idx = [];
    if (used.length) for (let i = used[0]; i <= used[used.length - 1]; i++) idx.push(i);
    const pick = (arr) => idx.map((i) => arr[i]);
    C.mes.note.textContent = idx.length ? `${MESES[idx[0]]}–${MESES[idx[idx.length - 1]]} ${d.year}` : "sem lançamentos";
    draw("mes", {
      data: {
        labels: idx.map((i) => MESES[i]),
        datasets: [
          { type: "bar", label: "Receita", data: pick(V.gross.months), backgroundColor: alpha(COLORS.copper, 0.8), borderColor: COLORS.copper, borderWidth: 1, borderRadius: 6, order: 2 },
          { type: "bar", label: "Custos e despesas", data: idx.map((i) => Math.abs(V.cmv.months[i]) + Math.abs(V.direct.months[i]) + Math.abs(V.opex.months[i])), backgroundColor: alpha(COLORS.wine, 0.75), borderColor: COLORS.wineLight, borderWidth: 1, borderRadius: 6, order: 3 },
          { type: "line", label: "Lucro líquido", data: pick(V.net_profit.months), borderColor: COLORS.ok, backgroundColor: alpha(COLORS.ok, 0.14), pointBackgroundColor: COLORS.ok, pointRadius: 5, tension: 0.35, fill: true, order: 1 },
        ],
      },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${BRL0.format(c.parsed.y)}` } } },
        scales: { y: { ticks: { callback: (v) => short(v) } }, x: { grid: { display: false } } } },
    });

    const dg = d.expenses.filter((x) => x.value > 0).sort((a, b) => b.value - a.value);
    const totalDesp = dg.reduce((s, x) => s + x.value, 0);
    C.desp.centerVal.textContent = short(totalDesp);
    C.desp.note.textContent = "despesas do ano";
    draw("desp", {
      type: "doughnut",
      data: { labels: dg.map((x) => x.name), datasets: [{ data: dg.map((x) => x.value), backgroundColor: dg.map((_, i) => PAL[i % PAL.length]), borderColor: COLORS.panel, borderWidth: 2, hoverOffset: 6 }] },
      options: { maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${BRL0.format(c.parsed)} (${pct(c.parsed / (totalDesp || 1))})` } } } },
    });

    const ev = d.events;
    C.ev.note.textContent = ev.length ? "passe o mouse para ver a margem" : "nenhum evento realizado";
    draw("ev", {
      type: "bar",
      data: { labels: ev.map((e) => e.code), datasets: [
        { label: "Receita", data: ev.map((e) => e.net), backgroundColor: alpha(COLORS.copper, 0.8), borderColor: COLORS.copper, borderWidth: 1, borderRadius: 5 },
        { label: "Insumos (CMV)", data: ev.map((e) => e.cmv), backgroundColor: alpha(COLORS.wine, 0.8), borderColor: COLORS.wineLight, borderWidth: 1, borderRadius: 5 },
      ] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: {
          title: (it) => `${ev[it[0].dataIndex].code} · ${ev[it[0].dataIndex].client}`,
          label: (c) => ` ${c.dataset.label}: ${BRL0.format(c.parsed.y)}`,
          footer: (it) => `Margem sobre insumos: ${pct(ev[it[0].dataIndex].margin_on_inputs)}`,
        } } },
        scales: { y: { ticks: { callback: (v) => short(v) } }, x: { grid: { display: false } } } },
    });

    const sim = sims[0];
    if (sim) {
      const r = sim.result;
      const g = sim.guests || 1;
      const comp = [...r.breakdown.map((b) => ({ name: b.label.replace(" (insumos)", "").replace(" e custos diretos", "").replace("Rateio de custos fixos", "Custos fixos").replace(" e limpeza", ""), value: b.per_guest })),
        { name: "Impostos", value: r.taxes / g }, { name: "Lucro", value: r.profit / g }].filter((x) => x.value > 0);
      const compColor = { Comida: "#d9925f", Bebidas: "#b8261b", "Descartáveis": "#f2c48d", "Mão de obra": "#fbf3ea", "Custos fixos": "#e0604a", Impostos: "#8a6f66", Lucro: COLORS.ok };
      K.preco.val.textContent = BRL.format(r.suggested_per_guest);
      K.preco.sub.textContent = `${INT.format(sim.guests)} convidados · lucro ${BRL0.format(r.charged.profit)}`;
      C.prec.centerVal.textContent = BRL.format(r.suggested_per_guest);
      C.prec.note.textContent = sim.name;
      draw("prec", {
        type: "doughnut",
        data: { labels: comp.map((x) => x.name), datasets: [{ data: comp.map((x) => x.value), backgroundColor: comp.map((x) => compColor[x.name] || "#a8746b"), borderColor: COLORS.panel, borderWidth: 2, hoverOffset: 6 }] },
        options: { maintainAspectRatio: false, cutout: "66%", plugins: { legend: { position: "right" }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${BRL.format(c.parsed)} (${pct(c.parsed / (r.suggested_per_guest || 1))})` } } } },
      });
    } else {
      K.preco.sub.textContent = "crie uma simulação em Precificação";
      C.prec.note.textContent = "nenhuma simulação salva";
    }

    const et = d.stock_by_category;
    C.est.note.textContent = `total ${BRL0.format(d.stock_value)}`;
    draw("est", {
      type: "bar",
      data: { labels: et.map((x) => x.name), datasets: [{ label: "Valor em estoque", data: et.map((x) => x.value), backgroundColor: et.map((_, i) => alpha(PAL[i % PAL.length], 0.75)), borderColor: et.map((_, i) => PAL[i % PAL.length]), borderWidth: 1, borderRadius: 5 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${BRL.format(c.parsed.x)}` } } },
        scales: { x: { ticks: { callback: (v) => short(v) } }, y: { grid: { display: false } } } },
    });

    const al = d.alerts;
    alerts.note.textContent = al.length ? `${al.length} itens` : "tudo em dia";
    fill(alerts.body,
      al.length ? null : h("p", { class: "dash-muted" }, "Nenhum item abaixo do estoque mínimo."),
      al.slice(0, 9).map((i) => {
        const zero = i.status !== "REPOR";
        return h("div", { class: "dash-alert" },
          h("span", { class: "dash-alert__name", title: i.name }, i.name),
          h("span", { class: "dash-alert__qty" }, `${qty(i.balance)}/${qty(i.min_stock)} ${i.unit}`),
          h("span", { class: `dash-pill${zero ? " dash-pill--zero" : ""}` }, i.status));
      }),
      al.length > 9 ? h("a", { class: "dash-muted", href: "#/painel/gestao/estoque" }, `+ ${al.length - 9} itens na aba Estoque`) : null);

    upcoming.note.textContent = d.upcoming.length ? `a partir de ${fmtShort(d.today)}` : "";
    fill(upcoming.body,
      d.upcoming.length ? null : h("p", { class: "dash-muted" }, "Nenhum evento confirmado pela frente."),
      d.upcoming.map((e) => h("div", { class: "dash-alert" },
        h("span", { class: "dash-alert__name", title: e.client }, `${fmtShort(e.event_date)} · ${e.client}`),
        h("span", { class: "dash-alert__qty" }, `${INT.format(e.guests)} conv.`),
        h("span", { class: `dash-pill${e.status === "orcamento" ? " dash-pill--zero" : ""}` }, STATUS_EVENTO[e.status]))));
  }
  await load();
}

/* ---------- DRE ---------- */

async function finDre(content) {
  const table = h("div", { class: "table-wrap fin-dre" }, loading());
  const yearSel = yearSelect(() => load());
  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, "Regime de competência: receita na data do evento (só eventos realizados); CMV pelas saídas de estoque, não pelas compras. AV % = sobre a receita líquida do ano."),
      yearSel),
    table);
  async function load() {
    const d = await api.get(`${G}/dre`, { ano: gdata.year });
    const num = (v, kind) => (kind === "pct" ? (Math.abs(v) < 0.0005 ? "–" : pct(v)) : kind === "int" ? INT.format(v) : kind === "money" ? (v ? BRL0.format(v) : "–") : acct(v));
    const row = (l, isInd) => {
      if (l.kind === "head") return h("tr", { class: "fin-dre__head" }, h("th", { scope: "row", colspan: 15 }, l.label));
      const kind = isInd ? l.kind : l.kind === "pct" ? "pct" : "money-acct";
      return h("tr", { class: `fin-dre__${l.kind}` },
        h("th", { scope: "row" }, l.label),
        l.months.map((v) => h("td", { class: v < 0 ? "is-neg" : null }, num(v, kind))),
        h("td", { class: `fin-dre__total${l.total < 0 ? " is-neg" : ""}` }, num(l.total, kind)),
        h("td", { class: "fin-dre__av" }, l.av === null || l.av === undefined ? "" : pct(l.av)));
    };
    fill(table, h("table", null,
      h("thead", null, h("tr", null, h("th", null, `DRE ${d.year}`), MESES.map((m) => h("th", null, m)), h("th", null, "Total"), h("th", null, "AV %"))),
      h("tbody", null, d.lines.map((l) => row(l, false)),
        h("tr", { class: "fin-dre__head" }, h("th", { scope: "row", colspan: 15 }, "Indicadores")),
        d.indicators.map((l) => row({ ...l, av: null }, true)))));
  }
  await load();
}

/* ---------- Eventos ---------- */

async function finEventos(content, reload) {
  const filter = { status: "" };
  const tbody = h("tbody");
  const statusSel = h("select", { class: "input", "aria-label": "Filtrar por situação", onchange: (e) => { filter.status = e.target.value; paint(); } },
    h("option", { value: "" }, "Todas as situações"), Object.entries(STATUS_EVENTO).map(([v, t]) => h("option", { value: v }, t)));
  const yearSel = yearSelect(() => paint());
  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, "Mude a situação para “Realizado” para a receita entrar no DRE. O CMV vem das saídas de estoque ligadas ao evento."),
      h("div", { class: "fin-filters" }, statusSel, yearSel, h("button", { class: "btn btn--primary btn--small", type: "button", onclick: () => eventForm(null, reload) }, "Novo evento"))),
    h("div", { class: "table-wrap" }, h("table", { class: "fin-table" },
      h("thead", null, h("tr", null, ["Código", "Data", "Cliente", "Conv.", "Valor/pessoa", "Receita líquida", "Insumos (CMV)", "Custos diretos", "Margem s/ insumos", "Situação", ""].map((t) => h("th", null, t)))),
      tbody)));
  function paint() {
    const rows = gdata.events.filter((e) => (!filter.status || e.status === filter.status) && Number(e.event_date.slice(0, 4)) === gdata.year);
    fill(tbody, rows.length ? rows.map((e) => h("tr", null,
      h("td", null, h("b", null, e.code)),
      h("td", null, fmtShort(e.event_date)),
      h("td", null, e.client, e.quote_id && h("a", { class: "fin-link", href: `#/painel/pedidos/${e.quote_id}` }, " · conversa")),
      h("td", { class: "num" }, INT.format(e.guests)),
      h("td", { class: "num" }, BRL.format(e.price_per_guest)),
      h("td", { class: "num" }, BRL.format(e.net)),
      h("td", { class: "num" }, e.cmv ? BRL.format(e.cmv) : "–"),
      h("td", { class: "num" }, e.direct_costs ? BRL.format(e.direct_costs) : "–"),
      h("td", { class: "num" }, e.cmv ? pct(e.margin_on_inputs) : "–"),
      h("td", null, pill(STATUS_EVENTO[e.status], EVENT_TONE[e.status])),
      h("td", { class: "fin-actions" },
        h("button", { class: "link-btn", type: "button", onclick: () => stockOutForm(null, reload, { kind: "evento", event_id: e.id }) }, "Saída"),
        h("button", { class: "link-btn", type: "button", onclick: () => eventForm(e, reload) }, "Editar"),
        h("button", { class: "link-btn fin-del", type: "button", onclick: () => confirmDelete(`Apagar o evento ${e.code}?`, `${G}/eventos/${e.id}`, reload) }, "Apagar"))))
      : emptyRow(11, "Nenhum evento neste filtro."));
  }
  paint();
}

/* ---------- Estoque ---------- */

async function finEstoque(content, reload) {
  const filter = { q: "", only: false, inactive: false };
  const tbody = h("tbody");
  const total = h("strong");
  const search = h("input", { class: "input", type: "search", placeholder: "Buscar insumo ou código", "aria-label": "Buscar insumo", oninput: debounce((e) => { filter.q = e.target.value; paint(); }, 150) });
  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, "Saldo = estoque inicial + compras − saídas. Custo médio ponderado móvel. Valor total em estoque: ", total, "."),
      h("div", { class: "fin-filters" }, search,
        h("label", { class: "fin-check" }, h("input", { type: "checkbox", onchange: (e) => { filter.only = e.target.checked; paint(); } }), " Só para repor"),
        h("label", { class: "fin-check" }, h("input", { type: "checkbox", onchange: (e) => { filter.inactive = e.target.checked; paint(); } }), " Mostrar fora de uso"),
        h("button", { class: "btn btn--primary btn--small", type: "button", onclick: () => itemForm(null, reload) }, "Novo insumo"))),
    h("div", { class: "table-wrap" }, h("table", { class: "fin-table" },
      h("thead", null, h("tr", null, ["Código", "Insumo", "Unid.", "Mínimo", "Saldo", "Custo médio", "Valor", "Situação", "Comprar", ""].map((t) => h("th", null, t)))),
      tbody)));
  total.textContent = BRL.format(gdata.items.reduce((s, i) => s + i.value, 0));
  function paint() {
    const q = filter.q.trim().toLowerCase();
    const rows = gdata.items.filter((i) => (filter.inactive || i.active) && (!filter.only || i.status !== "OK") && (!q || `${i.code} ${i.name}`.toLowerCase().includes(q)));
    let cat = null;
    const out = [];
    for (const i of rows) {
      if (i.category !== cat) {
        cat = i.category;
        out.push(h("tr", { class: "fin-group" }, h("th", { colspan: 10, scope: "rowgroup" }, cat)));
      }
      out.push(h("tr", { class: i.active ? null : "is-off" },
        h("td", null, h("b", null, i.code)),
        h("td", null, i.name),
        h("td", null, i.unit),
        h("td", { class: "num" }, qty(i.min_stock)),
        h("td", { class: "num" }, qty(i.balance)),
        h("td", { class: "num" }, BRL.format(i.avg_cost)),
        h("td", { class: "num" }, BRL.format(i.value)),
        h("td", null, pill(i.status, STOCK_TONE[i.status])),
        h("td", { class: "num" }, i.suggestion ? `${qty(i.suggestion)} ${i.unit}` : "–"),
        rowActions(() => itemForm(i, reload), () => confirmDelete(`Apagar o insumo ${i.code} (${i.name})?`, `${G}/insumos/${i.id}`, reload))));
    }
    fill(tbody, out.length ? out : emptyRow(10, "Nenhum insumo neste filtro."));
  }
  paint();
}

/* ---------- Compras, saídas e despesas: listas com filtro por mês ---------- */

function ledger(content, { intro, columns, path, row, empty, addLabel, onAdd, extraFilter, totalOf }) {
  const state = { month: null };
  const tbody = h("tbody");
  const total = h("strong");
  const yearSel = yearSelect(() => load());
  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, intro, " Total no período: ", total, "."),
      h("div", { class: "fin-filters" }, extraFilter?.(() => load()), monthSelect(null, (m) => { state.month = m; load(); }), yearSel,
        h("button", { class: "btn btn--primary btn--small", type: "button", onclick: onAdd }, addLabel))),
    h("div", { class: "table-wrap" }, h("table", { class: "fin-table" },
      h("thead", null, h("tr", null, columns.map((t) => h("th", null, t)))), tbody)));
  async function load() {
    fill(tbody, h("tr", null, h("td", { colspan: columns.length }, loading())));
    const params = { ano: gdata.year, ...(state.month ? { mes: state.month } : {}), ...(extraFilter?.params?.() || {}) };
    const rows = await api.get(path, params);
    total.textContent = BRL.format(rows.reduce((s, r) => s + totalOf(r), 0));
    fill(tbody, rows.length ? rows.map(row) : emptyRow(columns.length, empty));
  }
  return load();
}

function finCompras(content, reload) {
  return ledger(content, {
    intro: "Cada compra entra no estoque e atualiza o custo médio do insumo. Compras não são despesa no DRE.",
    columns: ["Data", "Insumo", "Quantidade", "Valor unit.", "Total", "Fornecedor", "NF", ""],
    path: `${G}/compras`, empty: "Nenhuma compra neste período.", addLabel: "Nova compra",
    onAdd: () => stockInForm(null, reload), totalOf: (r) => r.total,
    row: (r) => h("tr", null,
      h("td", null, fmtShort(r.entry_date)),
      h("td", null, h("b", null, r.item_code), ` ${r.item_name}`),
      h("td", { class: "num" }, `${qty(r.quantity)} ${r.unit}`),
      h("td", { class: "num" }, BRL.format(r.unit_cost)),
      h("td", { class: "num" }, BRL.format(r.total)),
      h("td", null, r.supplier || "–"),
      h("td", null, r.invoice || "–"),
      rowActions(() => stockInForm(r, reload), () => confirmDelete("Apagar esta compra? O custo médio será recalculado.", `${G}/compras/${r.id}`, reload))),
  });
}

function finSaidas(content, reload) {
  let kind = "";
  const extra = (onChange) => h("select", { class: "input", "aria-label": "Tipo de saída", onchange: (e) => { kind = e.target.value; onChange(); } },
    h("option", { value: "" }, "Todos os tipos"), Object.entries(TIPO_SAIDA).map(([v, t]) => h("option", { value: v }, t)));
  return ledger(content, {
    intro: "Saídas para eventos viram CMV do evento; perdas e consumo interno vão para as despesas do DRE.",
    columns: ["Data", "Insumo", "Quantidade", "Tipo", "Evento", "Custo unit.", "Custo total", "Obs.", ""],
    path: `${G}/saidas`, empty: "Nenhuma saída neste período.", addLabel: "Nova saída",
    onAdd: () => stockOutForm(null, reload), totalOf: (r) => (!kind || r.kind === kind ? r.total : 0),
    extraFilter: Object.assign(extra, { params: () => ({}) }),
    row: (r) => (kind && r.kind !== kind ? null : h("tr", null,
      h("td", null, fmtShort(r.entry_date)),
      h("td", null, h("b", null, r.item_code), ` ${r.item_name}`),
      h("td", { class: "num" }, `${qty(r.quantity)} ${r.unit}`),
      h("td", null, pill(TIPO_SAIDA[r.kind], r.kind === "evento" ? "info" : "warn")),
      h("td", null, r.event_code || "–"),
      h("td", { class: "num" }, BRL.format(r.unit_cost)),
      h("td", { class: "num" }, BRL.format(r.total)),
      h("td", null, r.note || "–"),
      rowActions(() => stockOutForm(r, reload), () => confirmDelete("Apagar esta saída?", `${G}/saidas/${r.id}`, reload)))),
  });
}

function finDespesas(content, reload) {
  let group = "";
  const extra = Object.assign((onChange) => h("select", { class: "input", "aria-label": "Grupo do DRE", onchange: (e) => { group = e.target.value; onChange(); } },
    h("option", { value: "" }, "Todos os grupos"), gdata.config.groups.map((g) => h("option", { value: g }, g))), { params: () => (group ? { grupo: group } : {}) });
  return ledger(content, {
    intro: "Contas fixas, folha, freelancers, tarifas… A categoria define em que linha do DRE o valor cai.",
    columns: ["Data", "Categoria", "Grupo no DRE", "Descrição", "Fornecedor", "Valor", "Pagamento", "Evento", ""],
    path: `${G}/despesas`, empty: "Nenhuma despesa neste período.", addLabel: "Nova despesa",
    onAdd: () => expenseForm(null, reload), totalOf: (r) => (r.group === "Receita financeira" ? -r.amount : r.amount), extraFilter: extra,
    row: (r) => h("tr", null,
      h("td", null, fmtShort(r.entry_date)),
      h("td", null, r.category),
      h("td", null, pill(r.group, r.group === "Receita financeira" ? "ok" : "muted")),
      h("td", null, r.description || "–"),
      h("td", null, r.supplier || "–"),
      h("td", { class: "num" }, BRL.format(r.amount)),
      h("td", null, r.payment || "–"),
      h("td", null, r.event_code || "–"),
      rowActions(() => expenseForm(r, reload), () => confirmDelete("Apagar esta despesa?", `${G}/despesas/${r.id}`, reload))),
  });
}

/* ---------- Precificação ---------- */

async function finPrecificacao(content) {
  let sims = await api.get(`${G}/precificacao`);
  let current = sims[0] ? structuredClone(sims[0]) : null;
  const listEl = h("div", { class: "fin-sims" });
  const editor = h("div", { class: "fin-pricing" });
  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, "Monte o cardápio com o consumo por convidado. Insumos pelo custo médio do estoque; mão de obra e custos fixos pelo histórico do DRE."),
      h("div", { class: "fin-filters" }, h("button", { class: "btn btn--primary btn--small", type: "button", onclick: () => { current = blank(); paintAll(); } }, "Nova simulação"))),
    listEl, editor);

  function blank() {
    return { id: null, name: "Nova simulação", event_type: gdata.config.event_types[0] || "", guests: 100, safety_margin: 0.1, profit_margin: 0.2, charged_per_guest: null, items: [] };
  }
  function paintList() {
    fill(listEl, sims.map((s) => h("button", { class: "chip", type: "button", "aria-pressed": String(current?.id === s.id), onclick: () => { current = structuredClone(s); paintAll(); } }, s.name)));
  }
  function paintAll() {
    paintList();
    if (!current) {
      fill(editor, h("div", { class: "box" }, h("p", { class: "muted" }, "Nenhuma simulação ainda. Clique em “Nova simulação”.")));
      return;
    }
    paintEditor();
  }

  function paintEditor() {
    const sim = current;
    const result = h("div", { class: "fin-pricing__result" }, loading());
    const err = h("p", { class: "form__error", role: "alert" });
    const input = (label, value, onChange, attrs = {}) => {
      const id = `f-p-${++fieldSeq}`;
      const el = h("input", { id, class: "input", value, ...attrs });
      el.addEventListener("input", () => { onChange(el.value); recalc(); });
      return h("div", { class: "field" }, h("label", { class: "field__label", for: id }, label), el);
    };
    const pctIn = (label, key) => input(label, numText(sim[key] * 100, 1), (v) => { const n = parseNum(v); sim[key] = n === null || Number.isNaN(n) ? 0 : n / 100; }, { inputmode: "decimal" });
    const typeSel = h("select", { class: "input", onchange: (e) => { sim.event_type = e.target.value; } },
      gdata.config.event_types.map((t) => h("option", { value: t, selected: t === sim.event_type }, t)));
    const itemsBody = h("tbody");
    const paintItems = () => fill(itemsBody, sim.items.length ? sim.items.map((it, i) => {
      const sel = itemSelect(`p-item-${i}`, it.item_id, { label: "" }).querySelector("select");
      sel.required = false;
      sel.addEventListener("change", () => { it.item_id = Number(sel.value) || null; recalc(); });
      const kind = h("select", { class: "input", onchange: (e) => { it.kind = e.target.value; recalc(); } },
        ["Comida", "Bebidas", "Descartáveis"].map((k) => h("option", { value: k, selected: k === it.kind }, k)));
      const per = h("input", { class: "input", inputmode: "decimal", value: numText(it.per_guest), "aria-label": "Consumo por convidado" });
      per.addEventListener("input", () => { const n = parseNum(per.value); it.per_guest = n && !Number.isNaN(n) ? n : 0; recalc(); });
      const line = lastResult?.items?.find((x) => x.item_id === it.item_id);
      return h("tr", null, h("td", null, kind), h("td", null, sel), h("td", null, per),
        h("td", { class: "num" }, line ? `${qty(line.quantity)} ${line.unit}` : "–"),
        h("td", { class: "num" }, line ? BRL.format(line.total) : "–"),
        h("td", { class: "num" }, line?.missing ? `${qty(line.missing)} ${line.unit}` : "–"),
        h("td", null, h("button", { class: "link-btn fin-del", type: "button", onclick: () => { sim.items.splice(i, 1); paintItems(); recalc(); } }, "Tirar")));
    }) : emptyRow(7, "Adicione os itens do cardápio."));
    let lastResult = null;

    fill(editor,
      h("div", { class: "box" },
        h("div", { class: "form__row" },
          input("Nome da simulação", sim.name, (v) => { sim.name = v; }, { maxlength: 120 }),
          h("div", { class: "field" }, h("label", { class: "field__label" }, "Tipo de evento"), typeSel)),
        h("div", { class: "fin-row4" },
          input("Convidados", sim.guests, (v) => { sim.guests = Math.max(1, parseInt(v, 10) || 1); }, { inputmode: "numeric" }),
          pctIn("Margem de segurança nas quantidades (%)", "safety_margin"),
          pctIn("Margem de lucro desejada (%)", "profit_margin"),
          input("Valor cobrado por pessoa (opcional)", numText(sim.charged_per_guest, 2), (v) => { const n = parseNum(v); sim.charged_per_guest = n === null || Number.isNaN(n) ? null : n; }, { inputmode: "decimal", placeholder: "arredonda o sugerido" })),
        err,
        h("h3", { class: "fin-h3" }, "Cardápio: consumo por convidado"),
        h("div", { class: "table-wrap" }, h("table", { class: "fin-table fin-table--edit" },
          h("thead", null, h("tr", null, ["Tipo", "Insumo", "Por convidado", "Quantidade total", "Custo", "Falta comprar", ""].map((t) => h("th", null, t)))), itemsBody)),
        h("div", { class: "form__actions fin-actions-row" },
          h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: () => { sim.items.push({ item_id: null, kind: "Comida", per_guest: 0 }); paintItems(); } }, "+ Item do cardápio"),
          h("span", { style: "flex:1" }),
          sim.id && h("button", { class: "btn btn--ghost btn--small fin-del", type: "button", onclick: remove }, "Apagar"),
          sim.id && h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: () => { current = { ...structuredClone(sim), id: null, name: `${sim.name} (cópia)` }; paintAll(); } }, "Duplicar"),
          h("button", { class: "btn btn--primary btn--small", type: "button", onclick: save }, "Salvar simulação"))),
      result);
    paintItems();

    const payload = () => ({ name: sim.name || "Simulação", event_type: sim.event_type || "", guests: sim.guests, safety_margin: sim.safety_margin,
      profit_margin: sim.profit_margin, charged_per_guest: sim.charged_per_guest, items: sim.items.filter((i) => i.item_id).map(({ item_id, kind, per_guest }) => ({ item_id, kind, per_guest })) });

    let seq = 0;
    async function calc() {
      const mine = ++seq;
      try {
        const out = await api.post(`${G}/precificacao/calcular`, payload());
        if (mine !== seq) return;
        err.textContent = "";
        lastResult = out.result;
        paintResult(out.result);
        paintItems();
      } catch (e) {
        if (mine === seq) err.textContent = e.errors?.length ? `${e.message} ${e.errors.map((x) => x.message).join(" ")}` : e.message;
      }
    }
    const recalc = debounce(calc, 350);

    function paintResult(r) {
      const row = (label, total, perGuest, share, strong) => h("tr", { class: strong ? "fin-strong" : null },
        h("th", { scope: "row" }, label), h("td", { class: "num" }, BRL.format(total)), h("td", { class: "num" }, BRL.format(perGuest)), h("td", { class: "num" }, share === null ? "" : pct(share)));
      const c = r.charged;
      fill(result,
        h("div", { class: "fin-price" },
          h("div", null, h("span", null, "Preço sugerido por pessoa"), h("strong", null, BRL.format(r.suggested_per_guest)), h("small", null, `${BRL.format(r.suggested_price)} no total`)),
          h("div", null, h("span", null, "Custo por pessoa"), h("strong", null, BRL.format(r.cost_per_guest)), h("small", null, `${BRL.format(r.cost_total)} no total`)),
          h("div", null, h("span", null, "Falta comprar"), h("strong", null, BRL.format(r.to_buy)), h("small", null, "pelo estoque atual"))),
        h("div", { class: "table-wrap" }, h("table", { class: "fin-table" },
          h("thead", null, h("tr", null, ["Custos e preço", "Total", "Por convidado", "% do preço"].map((t) => h("th", null, t)))),
          h("tbody", null,
            r.breakdown.map((b) => row(b.label, b.total, b.per_guest, b.share)),
            row("Custo total estimado da festa", r.cost_total, r.cost_per_guest, r.suggested_price ? r.cost_total / r.suggested_price : 0, true),
            row(`Impostos (${pct(r.tax_rate)})`, r.taxes, r.taxes / sim.guests, r.suggested_price ? r.taxes / r.suggested_price : 0),
            row("Lucro estimado", r.profit, r.profit / sim.guests, sim.profit_margin),
            row("Preço sugerido", r.suggested_price, r.suggested_per_guest, 1, true)))),
        h("div", { class: "table-wrap" }, h("table", { class: "fin-table" },
          h("thead", null, h("tr", null, h("th", { colspan: 2 }, `Simulação com ${BRL.format(c.per_guest)} por pessoa`))),
          h("tbody", null,
            h("tr", null, h("th", { scope: "row" }, "Receita prevista"), h("td", { class: "num" }, BRL.format(c.revenue))),
            h("tr", null, h("th", { scope: "row" }, "Custo total + impostos"), h("td", { class: "num" }, BRL.format(r.cost_total + c.taxes))),
            h("tr", { class: "fin-strong" }, h("th", { scope: "row" }, "Lucro estimado"), h("td", { class: `num${c.profit < 0 ? " is-neg" : ""}` }, `${BRL.format(c.profit)} (${pct(c.margin)})`)),
            h("tr", null, h("th", { scope: "row" }, "Diferença para o ticket médio do histórico"), h("td", { class: "num" }, `${BRL.format(c.vs_ticket)} por pessoa (histórico ${BRL.format(r.history.ticket)})`))))),
        h("p", { class: "muted fin-note" },
          `Referências de ${r.history.year}: mão de obra e custos diretos ${BRL.format(r.history.direct_per_guest)} por convidado; custos fixos ${BRL.format(r.history.fixed_per_month)}/mês ÷ ${numText(r.history.events_per_month, 1)} eventos/mês = ${BRL.format(r.history.fixed_per_event)} por evento.`));
    }

    async function save() {
      try {
        const saved = sim.id ? await api.put(`${G}/precificacao/${sim.id}`, payload()) : await api.post(`${G}/precificacao`, payload());
        sims = await api.get(`${G}/precificacao`);
        current = structuredClone(saved);
        toast("Simulação salva.");
        paintAll();
      } catch (e) {
        err.textContent = e.message;
      }
    }
    async function remove() {
      if (!confirm(`Apagar a simulação “${sim.name}”?`)) return;
      await api.del(`${G}/precificacao/${sim.id}`);
      sims = await api.get(`${G}/precificacao`);
      current = sims[0] ? structuredClone(sims[0]) : null;
      paintAll();
    }
    calc();
  }
  paintAll();
}

/* ---------- Cardápio: o que o buffet serve (o mesmo da página inicial) ---------- */

const MENU_PHOTOS = [
  ["/static/cardapio/buffet-1.jpg", "Mesa de frios (carpaccio)"],
  ["/static/cardapio/buffet-2.jpg", "Mesa de frios (frutas e queijos)"],
  ["/static/cardapio/buffet-3.jpg", "Comida de boteco (caprese)"],
  ["/static/cardapio/buffet-4.jpg", "Tábua de frios"],
  ["/static/cardapio/capa.jpg", "Camarão (capa do cardápio)"],
  ["/static/cardapio/mesa.jpg", "Mesa com favo de mel"],
];
// Texto de edição: "# Seção", "## Grupo" e um item por linha.
const sectionsToText = (sections) => sections.map((s) => [`# ${s.title}`,
  ...s.groups.flatMap((g) => [g.title ? `## ${g.title}` : null, ...g.items].filter((x) => x !== null))].join("\n")).join("\n\n");
function textToSections(text) {
  const out = [];
  for (const raw of String(text).split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("## ")) {
      if (!out.length) out.push({ title: "Itens", groups: [] });
      out[out.length - 1].groups.push({ title: line.slice(3).trim(), items: [] });
    } else if (line.startsWith("# ")) {
      out.push({ title: line.slice(2).trim(), groups: [] });
    } else {
      if (!out.length) out.push({ title: "Itens", groups: [] });
      const sec = out[out.length - 1];
      if (!sec.groups.length) sec.groups.push({ title: "", items: [] });
      sec.groups[sec.groups.length - 1].items.push(line.replace(/^[-•·]\s*/, ""));
    }
  }
  out.forEach((s) => { s.groups = s.groups.filter((g) => g.items.length); });
  return out.filter((s) => s.groups.length);
}
const linesOf = (text) => String(text).split("\n").map((x) => x.trim().replace(/^[-•·]\s*/, "")).filter(Boolean);

async function finCardapio(content) {
  let menu = await api.get("/admin/menu");
  const search = h("input", { class: "input", type: "search", placeholder: "Buscar prato (ex.: camarão, risoto, brie)", "aria-label": "Buscar prato" });
  const results = h("div", { class: "fin-menu__results", "aria-live": "polite" });
  const body = h("div", { class: "fin-menu" });

  function everyDish() {
    const all = [];
    menu.packages.forEach((p) => p.sections.forEach((s) => s.groups.forEach((g) => g.items.forEach((it) =>
      all.push({ name: it, where: [p.name, s.title, g.title].filter(Boolean).join(" › ") })))));
    menu.dishes.forEach((d) => d.items.forEach((it) => all.push({ name: it, where: `Pratos à escolha › ${d.title}` })));
    menu.cocktails.forEach((c) => all.push({ name: c.name, where: "Coquetéis" }));
    return all;
  }
  const norm = (s) => String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  search.addEventListener("input", debounce(() => {
    const q = norm(search.value.trim());
    if (q.length < 2) return fill(results);
    const found = everyDish().filter((d) => norm(d.name).includes(q));
    fill(results, h("div", { class: "box" },
      h("p", null, h("b", null, plural(found.length, "resultado", "resultados")), ` para “${search.value.trim()}”`),
      found.length ? h("ul", { class: "fin-menu__found" }, found.slice(0, 80).map((d) => h("li", null, h("span", null, d.name), h("small", null, d.where))))
        : h("p", { class: "muted" }, "Nenhum prato com esse nome.")));
  }, 150));

  function view() {
    const count = (p) => p.sections.reduce((n, s) => n + s.groups.reduce((m, g) => m + g.items.length, 0), 0);
    fill(body,
      h("div", { class: "fin-menu__packages" }, menu.packages.map((p) => h("details", { class: "box fin-menu__pkg" },
        h("summary", null,
          p.image && h("img", { src: media(p.image), alt: "", loading: "lazy" }),
          h("div", null,
            h("h2", null, p.name, p.subtitle && h("span", null, ` · ${p.subtitle}`)),
            h("p", { class: "muted" }, p.description),
            h("p", { class: "fin-menu__meta" },
              p.prices.map((x) => h("span", { class: "fin-pill fin-pill--muted" }, `${x.label} ${BRL0.format(x.value)}`)),
              h("span", { class: "muted" }, ` ${plural(count(p), "item", "itens")} · clique para ver`)))),
        h("div", { class: "fin-menu__sections" }, p.sections.map((s) => h("div", null,
          h("h3", { class: "fin-h3" }, s.title),
          s.groups.map((g) => [g.title && h("p", { class: "fin-menu__group" }, g.title), h("ul", null, g.items.map((it) => h("li", null, it)))]))))))),
      h("div", { class: "box" },
        h("div", { class: "box__head" }, h("h2", null, "Pratos à escolha"), h("span", { class: "muted" }, menu.dishes_note)),
        h("div", { class: "fin-menu__dishes" }, menu.dishes.map((d) => h("details", null,
          h("summary", null, d.title, h("small", null, ` ${d.items.length}`)),
          h("ul", null, d.items.map((it) => h("li", null, it))))))),
      h("div", { class: "form__row" },
        h("div", { class: "box" }, h("h2", null, "Coquetéis"),
          h("ul", { class: "fin-menu__found" }, menu.cocktails.map((c) => h("li", null, h("span", null, c.name), h("small", null, c.text))))),
        h("div", { class: "box" }, h("h2", null, "Incluso e observações"),
          h("ul", null, [...menu.included, ...menu.notes].map((t) => h("li", null, t))))));
  }

  function editor() {
    const area = (label, name, value, rows, hint) => field({ label, name, as: "textarea", rows, value, hint });
    const pkgBoxes = menu.packages.map((p, i) => {
      const photo = h("select", { class: "input", name: `p${i}_image`, "aria-label": "Foto" },
        h("option", { value: "" }, "Sem foto"),
        [...MENU_PHOTOS, ...(p.image.startsWith("/media/") ? [[p.image, "Foto enviada"]] : [])].map(([v, t]) => h("option", { value: v, selected: v === p.image }, t)));
      const upload = h("input", { type: "file", accept: "image/*", hidden: true });
      upload.addEventListener("change", async () => {
        const [id] = await uploadFiles(upload.files);
        upload.value = "";
        if (!id) return;
        photo.append(h("option", { value: `/media/${id}` }, "Foto enviada agora"));
        photo.value = `/media/${id}`;
        toast("Foto enviada. Salve o cardápio para usar.");
      });
      return h("fieldset", { class: "box fin-menu__edit" },
        h("legend", null, `Pacote ${i + 1}`),
        h("div", { class: "form__row" },
          field({ label: "Nome", name: `p${i}_name`, value: p.name, required: true, maxlength: 60 }),
          field({ label: "Subtítulo", name: `p${i}_subtitle`, value: p.subtitle, maxlength: 80 })),
        field({ label: "Descrição curta", name: `p${i}_description`, value: p.description, maxlength: 400 }),
        h("div", { class: "form__row" },
          area("Valores por pessoa", `p${i}_prices`, p.prices.map((x) => `${x.label}: ${numText(x.value, 2)}`).join("\n"), 3, "Um por linha. Ex.: Heineken: 240"),
          h("div", { class: "field" }, h("label", { class: "field__label" }, "Foto"), photo,
            h("button", { class: "link-btn", type: "button", style: "justify-self:start;margin-top:6px", onclick: () => upload.click() }, "Enviar outra foto"), upload)),
        area("O que vem no pacote", `p${i}_sections`, sectionsToText(p.sections), 14, "“# ” abre uma etapa (ex.: # Jantar), “## ” um grupo (ex.: ## Queijos) e cada linha é um item."),
        h("button", { class: "link-btn fin-del", type: "button", onclick: () => { if (confirm(`Tirar o ${p.name} do cardápio?`)) { collect(); menu.packages.splice(i, 1); editor(); } } }, "Tirar este pacote"));
    });
    const form = h("form", { class: "form fin-menu", novalidate: true },
      h("div", { class: "box" },
        h("h2", null, "Geral"),
        field({ label: "Frase de abertura", name: "intro", value: menu.intro, maxlength: 400 }),
        field({ label: "Observação dos valores", name: "price_note", value: menu.price_note, maxlength: 300 }),
        h("label", { class: "fin-check" }, h("input", { type: "checkbox", name: "show_prices", checked: menu.show_prices }), " Mostrar os valores no site (desmarque para mostrar só os pratos)")),
      pkgBoxes,
      h("button", { class: "btn btn--ghost btn--small", type: "button", style: "justify-self:start", onclick: () => {
        collect();
        menu.packages.push({ name: `Buffet ${menu.packages.length + 1}`, subtitle: "", description: "", image: "", prices: [], sections: [] });
        editor();
      } }, "+ Novo pacote"),
      h("div", { class: "box" },
        h("h2", null, "Bebidas, coquetéis e observações"),
        h("div", { class: "form__row" },
          area("Bebidas", "drinks", menu.drinks.join("\n"), 4, "Uma por linha."),
          area("Coquetéis", "cocktails", menu.cocktails.map((c) => (c.text ? `${c.name}: ${c.text}` : c.name)).join("\n"), 8, "Nome: ingredientes")),
        h("div", { class: "form__row" },
          area("Incluso em todos", "included", menu.included.join("\n"), 6, "Um por linha."),
          area("Bom saber (crianças, materiais…)", "notes", menu.notes.join("\n"), 6, "Um por linha."))),
      h("div", { class: "box" },
        h("h2", null, "Pratos à escolha"),
        field({ label: "Observação", name: "dishes_note", value: menu.dishes_note, maxlength: 300 }),
        area("Pratos", "dishes", menu.dishes.map((d) => [`# ${d.title}`, ...d.items].join("\n")).join("\n\n"), 18, "“# ” abre uma categoria (ex.: # Risotos) e cada linha é um prato.")),
      h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
      h("div", { class: "form__actions fin-menu__save" },
        h("button", { class: "btn btn--ghost", type: "button", onclick: async () => {
          if (!confirm("Voltar ao cardápio do PDF (2025)? As mudanças feitas aqui serão perdidas.")) return;
          menu = await api.post("/admin/menu/restaurar");
          toast("Cardápio do PDF restaurado.");
          editor();
        } }, "Voltar ao cardápio do PDF"),
        h("span", { style: "flex:1" }),
        h("button", { class: "btn btn--ghost", type: "button", onclick: view }, "Cancelar"),
        h("button", { class: "btn btn--primary", type: "submit" }, "Salvar cardápio")));

    function collect() {
      const v = formValues(form);
      menu.intro = v.intro || "";
      menu.price_note = v.price_note || "";
      menu.show_prices = !!form.elements.show_prices.checked;
      menu.packages = menu.packages.map((p, i) => ({
        name: v[`p${i}_name`] || p.name,
        subtitle: v[`p${i}_subtitle`] || "",
        description: v[`p${i}_description`] || "",
        image: v[`p${i}_image`] || "",
        prices: linesOf(v[`p${i}_prices`]).map((l) => {
          const [label, value] = l.split(/:(?=[^:]*$)/);
          const n = parseNum(value);
          return { label: (label || "").trim() || "Valor", value: n === null || Number.isNaN(n) ? NaN : n };
        }),
        sections: textToSections(v[`p${i}_sections`]),
      }));
      menu.drinks = linesOf(v.drinks);
      menu.cocktails = linesOf(v.cocktails).map((l) => {
        const i = l.indexOf(":");
        return i > 0 ? { name: l.slice(0, i).trim(), text: l.slice(i + 1).trim() } : { name: l, text: "" };
      });
      menu.included = linesOf(v.included);
      menu.notes = linesOf(v.notes);
      menu.dishes_note = v.dishes_note || "";
      menu.dishes = textToSections(v.dishes).map((s) => ({ title: s.title, items: s.groups.flatMap((g) => g.items) }));
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitting(form, async () => {
        collect();
        const bad = menu.packages.find((p) => p.prices.some((x) => Number.isNaN(x.value)));
        if (bad) throw Object.assign(new Error(`Confira os valores do ${bad.name}: use “Marca: 240”, um por linha.`), { errors: [] });
        const { updated_at, ...payload } = menu;
        menu = await api.put("/admin/menu", payload);
        toast("Cardápio salvo. Já aparece no site.");
        view();
      });
    });
    fill(body, form);
    form.querySelector("input")?.focus();
  }

  fill(content,
    h("div", { class: "fin-bar" },
      h("p", { class: "muted" }, "O cardápio do buffet, o mesmo que aparece na página inicial do site. Busque um prato para ver em que pacote ele está."),
      h("div", { class: "fin-filters" }, search,
        h("a", { class: "btn btn--ghost btn--small", href: "#/cardapio" }, "Ver no site"),
        h("button", { class: "btn btn--primary btn--small", type: "button", onclick: editor }, "Editar cardápio"))),
    results, body);
  view();
}

/* ---------- Configurações, importação e exportação ---------- */

async function finConfig(content, reload) {
  const c = gdata.config;
  const listArea = (label, name, values) => field({ label, name, as: "textarea", rows: 6, value: values.join("\n"), hint: "Um por linha." });
  const form = h("form", { class: "form box", novalidate: true },
    h("h2", null, "Alíquotas e listas"),
    h("div", { class: "form__row" },
      numField({ label: "Alíquota sobre o faturamento (%)", name: "tax_rate", value: c.tax_rate * 100, digits: 2, hint: "Simples Nacional / ISS / PIS-COFINS. Entra no DRE e na precificação." }),
      numField({ label: "IR/CSLL sobre o lucro (%)", name: "income_tax_rate", value: c.income_tax_rate * 100, digits: 2, hint: "Use 0 se for Simples Nacional." })),
    h("div", { class: "form__row" }, listArea("Categorias de insumo", "item_categories", c.item_categories), listArea("Unidades", "units", c.units)),
    h("div", { class: "form__row" }, listArea("Tipos de evento", "event_types", c.event_types), listArea("Formas de pagamento", "payment_methods", c.payment_methods)),
    h("p", { class: "form__error", role: "alert", tabindex: "-1" }),
    h("div", { class: "form__actions" }, h("button", { class: "btn btn--primary", type: "submit" }, "Salvar")));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submitting(form, async () => {
      const v = numbers(form, formValues(form), ["tax_rate", "income_tax_rate"]);
      const lines = (s) => [...new Set(String(s).split("\n").map((x) => x.trim()).filter(Boolean))];
      await api.put(`${G}/config`, { tax_rate: v.tax_rate / 100, income_tax_rate: v.income_tax_rate / 100,
        item_categories: lines(v.item_categories), units: lines(v.units), event_types: lines(v.event_types), payment_methods: lines(v.payment_methods) });
      toast("Configurações salvas.");
      reload();
    });
  });

  const catBody = h("tbody");
  const groupOptions = (value) => c.groups.map((g) => h("option", { value: g, selected: g === value }, g));
  const paintCats = () => fill(catBody, gdata.categories.map((cat) => {
    const name = h("input", { class: "input", value: cat.name, maxlength: 80, "aria-label": "Nome da categoria" });
    const group = h("select", { class: "input", "aria-label": "Grupo no DRE" }, groupOptions(cat.group));
    const saveCat = async () => {
      try {
        await api.put(`${G}/categorias/${cat.id}`, { name: name.value, group: group.value });
        toast("Categoria salva.");
      } catch (err) { toast(err.message, "error"); }
    };
    name.addEventListener("change", saveCat);
    group.addEventListener("change", saveCat);
    return h("tr", null, h("td", null, name), h("td", null, group),
      h("td", null, h("button", { class: "link-btn fin-del", type: "button", onclick: () => confirmDelete(`Apagar a categoria “${cat.name}”?`, `${G}/categorias/${cat.id}`, reload) }, "Apagar")));
  }));
  paintCats();
  const newName = h("input", { class: "input", placeholder: "Nova categoria", maxlength: 80, "aria-label": "Nova categoria" });
  const newGroup = h("select", { class: "input", "aria-label": "Grupo no DRE da nova categoria" }, groupOptions("Administrativa"));

  const importInput = h("input", { type: "file", accept: ".ods,.xlsx", hidden: true });
  importInput.addEventListener("change", async () => {
    const file = importInput.files[0];
    importInput.value = "";
    if (!file) return;
    try {
      const data = await readOldSpreadsheet(file);
      const counts = `${data.items.length} insumos, ${data.events.length} eventos, ${data.stock_in.length} compras, ${data.stock_out.length} saídas e ${data.expenses.length} despesas`;
      if (!confirm(`Encontrei ${counts} em “${file.name}”.\n\nImportar SUBSTITUI tudo o que já está lançado na gestão. Continuar?`)) return;
      const result = await api.post(`${G}/importar`, data);
      toast("Planilha importada.");
      if (result.warnings?.length) alert(result.warnings.join("\n\n"));
      go("/painel/gestao/resumo");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  fill(content,
    form,
    h("div", { class: "box" },
      h("div", { class: "box__head" }, h("h2", null, "Categorias de despesa")),
      h("p", { class: "muted" }, "O grupo define em que linha do DRE a despesa cai. As alterações são salvas na hora."),
      h("div", { class: "table-wrap" }, h("table", { class: "fin-table fin-table--edit" },
        h("thead", null, h("tr", null, h("th", null, "Categoria"), h("th", null, "Grupo no DRE"), h("th", null, ""))),
        catBody,
        h("tfoot", null, h("tr", null, h("td", null, newName), h("td", null, newGroup),
          h("td", null, h("button", { class: "btn btn--primary btn--small", type: "button", onclick: async () => {
            try {
              await api.post(`${G}/categorias`, { name: newName.value, group: newGroup.value });
              toast("Categoria criada.");
              reload();
            } catch (err) { toast(err.message, "error"); }
          } }, "Adicionar"))))))),
    h("div", { class: "box" },
      h("h2", null, "Planilha e cópia de segurança"),
      h("p", null, "Baixe tudo em uma planilha .xlsx (abre no LibreOffice e no Excel): DRE, estoque, compras, saídas, eventos e despesas. Serve de cópia de segurança e para mandar ao contador."),
      h("div", { class: "form__actions", style: "justify-content:flex-start" },
        h("button", { class: "btn btn--primary", type: "button", onclick: exportXlsx }, "Baixar planilha (.xlsx)"),
        h("button", { class: "btn btn--ghost", type: "button", onclick: () => importInput.click() }, "Importar planilha (.ods)"),
        importInput),
      h("p", { class: "field__hint" }, "Aceita o modelo simples (Planilha_Brunoise_simples.ods) e a planilha antiga. A importação lê o arquivo no seu computador e substitui todos os lançamentos da gestão pelos da planilha. Use uma vez, para trazer o que você já tinha.")));
}

/* Lê a planilha antiga (abas Parâmetros, Estoque, Entradas, Saídas, Eventos e Despesas). */
async function readOldSpreadsheet(file) {
  await loadLib(GESTAO_LIBS.xlsx);
  const wb = XLSX.read(await file.arrayBuffer(), { type: "array", cellDates: true });
  const norm = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const sheet = (name) => {
    const key = wb.SheetNames.find((n) => norm(n) === norm(name));
    if (!key) throw new Error(`Não encontrei a aba “${name}”. Este é o arquivo da planilha do buffet?`);
    const ws = wb.Sheets[key];
    if (!ws["!ref"]) return [];
    const rg = XLSX.utils.decode_range(ws["!ref"]);
    rg.s.r = 0; rg.s.c = 0;
    ws["!ref"] = XLSX.utils.encode_range(rg);
    return XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null, blankrows: true });
  };
  const g = (r, i) => (r[i] === undefined || r[i] === "" ? null : r[i]);
  const text = (v) => (v === null ? "" : String(v).trim());
  const num = (v) => (typeof v === "number" ? v : v === null ? 0 : parseNum(v) || 0);
  const day = (v) => {
    if (v instanceof Date) return new Date(v.getTime() + 12 * 3600e3).toISOString().slice(0, 10);
    if (typeof v === "number") return new Date(Math.round((v - 25569) * 864e5)).toISOString().slice(0, 10);
    const m = String(v ?? "").match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    return m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : String(v ?? "");
  };
  const data = (name, key = 0) => sheet(name).slice(4).filter((r) => g(r, key) !== null && !text(g(r, key)).startsWith("▸"));
  if (wb.SheetNames.some((n) => norm(n) === "1. estoque")) return readSimple({ sheet, g, text, num, day, norm });

  const P = sheet("Parâmetros");
  const col = (i) => P.slice(11).map((r) => text(g(r, i))).filter(Boolean);
  const findParam = (prefix) => P.find((r) => norm(g(r, 0)).startsWith(prefix)) || [];
  const config = {
    tax_rate: num(g(findParam("aliquota efetiva"), 1)), income_tax_rate: num(g(findParam("aliquota de ir"), 1)),
    item_categories: col(0), units: col(1), event_types: col(3), payment_methods: col(8),
  };
  const categories = P.slice(11).filter((r) => g(r, 5) && g(r, 6)).map((r) => ({ name: text(r[5]), group: text(r[6]) }));
  let pricing = [];
  if (wb.SheetNames.some((n) => norm(n) === "precificacao")) {
    const PR = sheet("Precificação");
    const at = (r, c) => g(PR[r] || [], c);
    pricing = [{ name: text(at(4, 3)) || "Simulação", event_type: text(at(5, 3)), guests: Math.max(1, Math.round(num(at(6, 3)) || 100)),
      safety_margin: num(at(7, 3)), profit_margin: num(at(8, 3)),
      items: PR.slice(27, 87).filter((r) => g(r, 1) && num(g(r, 4)) > 0).map((r) => ({ kind: text(r[0]), item: text(r[1]), per_guest: num(r[4]) })) }];
  }
  const STATUS = { orcamento: "orcamento", confirmado: "confirmado", realizado: "realizado", cancelado: "cancelado" };
  const KIND = { evento: "evento", "perda/quebra": "perda", "consumo interno": "consumo" };
  return {
    config, categories, pricing,
    items: data("Estoque").filter((r) => g(r, 1)).map((r) => ({ code: text(r[0]), name: text(r[1]), category: text(r[2]), unit: text(r[3]),
      min_stock: num(g(r, 4)), initial_stock: num(g(r, 5)), initial_cost: num(g(r, 6)) })),
    events: data("Eventos").filter((r) => g(r, 1)).map((r) => ({ code: text(r[0]), event_date: day(r[1]), client: text(r[2]), event_type: text(r[3]) || "Outro",
      guests: Math.max(1, Math.round(num(g(r, 4)))), price_per_guest: num(g(r, 5)), discount: num(g(r, 7)), status: STATUS[norm(g(r, 8))] || "confirmado" })),
    stock_in: data("Entradas").filter((r) => g(r, 1) && g(r, 5)).map((r) => ({ date: day(r[0]), item: text(r[1]), quantity: num(r[5]), unit_cost: num(g(r, 6)),
      supplier: text(g(r, 8)), invoice: text(g(r, 9)) })),
    stock_out: data("Saídas").filter((r) => g(r, 1) && g(r, 4)).map((r) => ({ date: day(r[0]), item: text(r[1]), quantity: num(r[4]),
      kind: KIND[norm(g(r, 5))] || "consumo", event: text(g(r, 6)), note: text(g(r, 11)) })),
    expenses: data("Despesas").filter((r) => g(r, 1) && g(r, 5)).map((r) => ({ date: day(r[0]), category: text(r[1]), description: text(g(r, 3)),
      supplier: text(g(r, 4)), amount: num(r[5]), payment: text(g(r, 6)), event: text(g(r, 7)) })),
  };
}

/* O modelo simples (abas “1. Estoque” … “5. Saídas” e “Listas”): dados a partir da linha 4. */
function readSimple({ sheet, g, text, num, day, norm }) {
  const rows = (name, key) => sheet(name).slice(3).filter((r) => g(r, key) !== null && text(g(r, key)) !== "");
  // “CAR001 · Picanha bovina (kg)” → CAR001; insumo novo sem código: “Nome (kg)” → Nome.
  const refOf = (label) => {
    const s = text(label);
    const i = s.indexOf(" · ");
    return i >= 0 ? s.slice(0, i) : s.replace(/\s*\([^)]*\)$/, "");
  };
  const L = sheet("Listas");
  const col = (i) => L.slice(1).map((r) => text(g(r, i))).filter(Boolean);
  const STATUS = { orcamento: "orcamento", confirmado: "confirmado", realizado: "realizado", cancelado: "cancelado" };
  const KIND = { evento: "evento", "perda ou quebra": "perda", "consumo interno": "consumo" };
  return {
    config: { tax_rate: num(g(L[1] || [], 11)), income_tax_rate: num(g(L[2] || [], 11)),
      item_categories: col(0), units: col(1), event_types: col(2), payment_methods: col(7) },
    categories: L.slice(1).filter((r) => g(r, 5) && g(r, 6)).map((r) => ({ name: text(r[5]), group: text(r[6]) })),
    items: rows("1. Estoque", 1).map((r) => ({ code: text(g(r, 0)), name: text(r[1]), category: text(g(r, 2)) || "Mercearia", unit: text(g(r, 3)) || "un",
      initial_stock: num(g(r, 4)), initial_cost: num(g(r, 5)), min_stock: num(g(r, 6)), active: norm(g(r, 7)) !== "nao" })),
    events: rows("2. Eventos", 1).map((r) => ({ code: text(g(r, 0)), event_date: day(r[1]), client: text(g(r, 2)) || "Cliente", event_type: text(g(r, 3)) || "Outro",
      guests: Math.max(1, Math.round(num(g(r, 4)))), price_per_guest: num(g(r, 5)), discount: num(g(r, 6)), status: STATUS[norm(g(r, 7))] || "confirmado" })),
    expenses: rows("3. Despesas", 1).filter((r) => g(r, 3)).map((r) => ({ date: day(r[0]), category: text(r[1]), description: text(g(r, 2)),
      amount: num(r[3]), payment: text(g(r, 4)), event: refOf(g(r, 5)), supplier: "" })),
    stock_in: rows("4. Compras", 1).filter((r) => g(r, 3)).map((r) => ({ date: day(r[0]), item: refOf(r[1]), quantity: num(r[3]), unit_cost: num(g(r, 4)),
      supplier: text(g(r, 6)), invoice: text(g(r, 7)) })),
    stock_out: rows("5. Saídas", 1).filter((r) => g(r, 3)).map((r) => ({ date: day(r[0]), item: refOf(r[1]), quantity: num(r[3]),
      kind: KIND[norm(g(r, 4))] || "consumo", event: refOf(g(r, 5)), note: text(g(r, 6)) })),
    pricing: [],
  };
}

async function exportXlsx() {
  try {
    const [d] = await Promise.all([api.get(`${G}/exportar`), loadLib(GESTAO_LIBS.xlsx)]);
    const wb = XLSX.utils.book_new();
    const add = (name, rows, widths) => {
      const ws = XLSX.utils.aoa_to_sheet(rows);
      if (widths) ws["!cols"] = widths.map((w) => ({ wch: w }));
      XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31));
    };
    const iso = (s) => (s ? new Date(`${s}T12:00:00Z`) : "");
    for (const rep of d.dre) {
      const rows = [[`DRE gerencial ${rep.year}`, ...MESES, "Total", "AV %"]];
      rep.lines.forEach((l) => rows.push(l.months ? [l.label, ...l.months, l.total, l.av ?? ""] : [l.label.toUpperCase()]));
      rows.push([], ["INDICADORES"]);
      rep.indicators.forEach((l) => rows.push([l.label, ...l.months, l.total]));
      add(`DRE ${rep.year}`, rows, [52, ...Array(14).fill(11)]);
    }
    add("Estoque", [["Código", "Insumo", "Categoria", "Unid.", "Mínimo", "Estoque inicial", "Custo inicial", "Entradas", "Saídas", "Saldo", "Custo médio", "Valor", "Situação", "Sugestão de compra"],
      ...d.items.map((i) => [i.code, i.name, i.category, i.unit, i.min_stock, i.initial_stock, i.initial_cost, i.total_in, i.total_out, i.balance, i.avg_cost, i.value, i.status, i.suggestion])], [9, 34, 20, 7, 9, 9, 10, 9, 9, 9, 10, 11, 12, 10]);
    add("Compras", [["Data", "Código", "Insumo", "Unid.", "Quantidade", "Valor unit.", "Total", "Fornecedor", "NF"],
      ...d.stock_in.map((r) => [iso(r.entry_date), r.item_code, r.item_name, r.unit, r.quantity, r.unit_cost, r.total, r.supplier, r.invoice])], [11, 9, 34, 7, 10, 10, 11, 20, 10]);
    add("Saídas", [["Data", "Código", "Insumo", "Unid.", "Quantidade", "Tipo", "Evento", "Custo unit.", "Custo total", "Obs."],
      ...d.stock_out.map((r) => [iso(r.entry_date), r.item_code, r.item_name, r.unit, r.quantity, TIPO_SAIDA[r.kind], r.event_code || "", r.unit_cost, r.total, r.note])], [11, 9, 34, 7, 10, 16, 8, 10, 11, 24]);
    add("Eventos", [["Código", "Data", "Cliente", "Tipo", "Convidados", "Valor por pessoa", "Desconto", "Situação", "Receita líquida", "CMV", "Custos diretos", "Margem s/ insumos"],
      ...d.events.map((e) => [e.code, iso(e.event_date), e.client, e.event_type, e.guests, e.price_per_guest, e.discount, STATUS_EVENTO[e.status], e.net, e.cmv, e.direct_costs, e.margin_on_inputs])], [8, 11, 34, 14, 10, 12, 10, 12, 13, 11, 12, 12]);
    add("Despesas", [["Data", "Categoria", "Grupo no DRE", "Descrição", "Fornecedor", "Valor", "Pagamento", "Evento"],
      ...d.expenses.map((r) => [iso(r.entry_date), r.category, r.group, r.description, r.supplier, r.amount, r.payment, r.event_code || ""])], [11, 34, 20, 30, 20, 11, 12, 8]);
    XLSX.writeFile(wb, `gestao-buffet-${d.exported_at}.xlsx`, { cellDates: true });
  } catch (err) {
    toast(err.message, "error");
  }
}

/* ---------- Na conversa do orçamento: ligar o pedido a um evento da gestão ---------- */

function quoteFinanceLink(quote) {
  const slot = h("div", { class: "fin-quote" });
  const paint = (event) => fill(slot, event
    ? h("a", { class: "btn btn--ghost btn--small", href: "#/painel/gestao/eventos" }, `Evento ${event.code} na gestão · ${STATUS_EVENTO[event.status]}`)
    : h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: async () => {
      try {
        const created = await api.post(`${G}/eventos/do-orcamento/${quote.id}`);
        toast(`Evento ${created.code} criado. Informe o valor por pessoa na aba Gestão › Eventos.`);
        paint(created);
      } catch (err) { toast(err.message, "error"); }
    } }, "Criar evento na gestão"));
  api.get(`${G}/eventos/do-orcamento/${quote.id}`).then(paint).catch(() => slot.remove());
  return slot;
}
