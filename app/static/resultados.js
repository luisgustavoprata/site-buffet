/* Resultados: lê a planilha do buffet (.ods/.xlsx) no navegador e mostra os números no painel.
 *
 * - No computador (Chrome/Edge), a dona conecta o arquivo uma vez; a cada Ctrl+S no
 *   LibreOffice o painel relê a planilha, atualiza os gráficos e envia o resumo ao site.
 * - No celular, o painel mostra o último resumo enviado (GET /admin/dashboard).
 *
 * Usa h(), fill(), api, toast(), loading() e onLeave() de app.js.
 */
"use strict";

/* Lê as abas da planilha (arrays de linhas) e devolve os dados do painel. */
function parseBuffet(S) {
  const norm = s => String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  const num = v => (typeof v === "number" && isFinite(v)) ? v : (typeof v === "string" && v.trim() !== "" && !isNaN(+v.replace(",", ".")) ? +v.replace(",", ".") : 0);
  const toDate = v => {
    if (v instanceof Date) return isNaN(v) ? null : v;
    if (typeof v === "number" && v > 20000 && v < 80000) return new Date(Math.round((v - 25569) * 864e5));
    if (typeof v === "string") {
      let m = v.match(/^(\d{4})-(\d{2})-(\d{2})/); if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
      m = v.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); if (m) return new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
    }
    return null;
  };
  const sheet = name => {
    const k = Object.keys(S).find(x => norm(x) === norm(name));
    return k ? S[k] : [];
  };
  const cell = (rows, r, c) => (rows[r] || [])[c];
  const findRow = (rows, col, prefix, from = 0) => {
    const p = norm(prefix);
    for (let r = from; r < rows.length; r++) if (norm(cell(rows, r, col)).startsWith(p)) return r;
    return -1;
  };
  const out = { ok: true };

  // Parâmetros
  const P = sheet("Parâmetros");
  out.empresa = (cell(P, findRow(P, 0, "nome da empresa"), 1)) || "Buffet";
  out.ano = num(cell(P, findRow(P, 0, "ano do dre"), 1)) || new Date().getFullYear();

  // DRE
  const D = sheet("DRE");
  const line = label => {
    const r = findRow(D, 0, label);
    if (r < 0) return { m: Array(12).fill(0), t: 0 };
    const m = []; for (let c = 1; c <= 12; c++) m.push(num(cell(D, r, c)));
    return { m, t: num(cell(D, r, 13)) };
  };
  out.dre = {
    receitaBruta: line("receita bruta"), receitaLiquida: line("receita liquida"),
    cmv: line("(-) cmv"), custosDiretos: line("(-) custos diretos"),
    lucroBruto: line("lucro bruto"), despOp: line("total despesas operacionais"),
    ebitda: line("ebitda"), lucroLiquido: line("lucro liquido"), margemLiquida: line("margem liquida"),
    eventos: line("eventos realizados"), convidados: line("convidados atendidos"),
    ticket: line("ticket medio"), cmvConv: line("cmv por convidado"), compras: line("compras de insumos"),
  };
  out.despesasGrupo = [
    ["Custo direto", "(-) custos diretos"], ["Pessoal", "(-) pessoal"], ["Ocupação", "(-) ocupacao"],
    ["Utilidades", "(-) utilidades"], ["Comercial", "(-) comerciais"], ["Administrativa", "(-) administrativas"],
    ["Manutenção", "(-) manutencao"], ["Perdas", "(-) perdas"], ["Depreciação", "(-) depreciacao"],
    ["Financeiras", "(-) despesas financeiras"],
  ].map(([n, l]) => ({ nome: n, valor: Math.abs(line(l).t) })).filter(x => x.valor > 0);

  // Estoque
  const E = sheet("Estoque");
  out.estoque = [];
  for (let r = 0; r < E.length; r++) {
    const code = String(cell(E, r, 0) || "");
    if (!/^[A-Z]{2,4}\d{2,4}$/.test(code)) continue;
    out.estoque.push({
      code, nome: cell(E, r, 1) || "", cat: cell(E, r, 2) || "", un: cell(E, r, 3) || "",
      min: num(cell(E, r, 4)), saldo: num(cell(E, r, 9)), custo: num(cell(E, r, 10)),
      valor: num(cell(E, r, 11)), status: String(cell(E, r, 12) || ""), sug: num(cell(E, r, 13)),
    });
  }
  const porTipo = {};
  out.estoque.forEach(i => { porTipo[i.cat] = (porTipo[i.cat] || 0) + i.valor; });
  out.estoqueTipo = Object.entries(porTipo).map(([nome, valor]) => ({ nome, valor })).filter(x => x.valor > 0).sort((a, b) => b.valor - a.valor);
  out.valorEstoque = out.estoque.reduce((s, i) => s + i.valor, 0);
  out.alertas = out.estoque.filter(i => i.status && i.status !== "OK")
    .sort((a, b) => (a.status === "REPOR") - (b.status === "REPOR") || (a.saldo / (a.min || 1)) - (b.saldo / (b.min || 1)));

  // Eventos
  const V = sheet("Eventos");
  out.eventos = [];
  for (let r = 4; r < V.length; r++) {
    const code = cell(V, r, 0); const d = toDate(cell(V, r, 1));
    if (!code || !d) continue;
    out.eventos.push({
      code: String(code), data: d, cliente: cell(V, r, 2) || "", tipo: cell(V, r, 3) || "",
      convidados: num(cell(V, r, 4)), vpp: num(cell(V, r, 5)), bruto: num(cell(V, r, 6)),
      status: String(cell(V, r, 8) || ""), receita: num(cell(V, r, 9)), cmv: num(cell(V, r, 10)),
      margem: typeof cell(V, r, 12) === "number" ? cell(V, r, 12) : null,
    });
  }

  // Movimentações
  const EN = sheet("Entradas"), SA = sheet("Saídas");
  out.movs = [];
  for (let r = 4; r < EN.length; r++) {
    const d = toDate(cell(EN, r, 0)); if (!d || !cell(EN, r, 1)) continue;
    out.movs.push({ tipo: "Entrada", data: d, code: cell(EN, r, 1), nome: cell(EN, r, 2) || "", qtd: num(cell(EN, r, 5)), un: cell(EN, r, 4) || "", valor: num(cell(EN, r, 7)), obs: cell(EN, r, 8) || "" });
  }
  for (let r = 4; r < SA.length; r++) {
    const d = toDate(cell(SA, r, 0)); if (!d || !cell(SA, r, 1)) continue;
    out.movs.push({ tipo: "Saída", data: d, code: cell(SA, r, 1), nome: cell(SA, r, 2) || "", qtd: num(cell(SA, r, 4)), un: cell(SA, r, 3) || "", valor: num(cell(SA, r, 8)), obs: [cell(SA, r, 5), cell(SA, r, 6)].filter(Boolean).join(" · ") });
  }
  out.movs.sort((a, b) => b.data - a.data);

  // Precificação
  const PR = sheet("Precificação");
  const pv = (label, col = 5, valCol = 8) => { const r = findRow(PR, col, label); return r < 0 ? 0 : num(cell(PR, r, valCol)); };
  const pp = (label) => { const r = findRow(PR, 5, label); return r < 0 ? 0 : num(cell(PR, r, 9)); };
  out.prec = {
    convidados: pv("nº de convidados", 0, 3) || pv("n de convidados", 0, 3),
    tipo: (() => { const r = findRow(PR, 0, "tipo de evento"); return r < 0 ? "" : cell(PR, r, 3) || ""; })(),
    margemDesejada: pv("margem de lucro desejada", 0, 3),
    comp: [["Comida", "comida"], ["Bebidas", "bebidas"], ["Descartáveis", "descartaveis"], ["Mão de obra", "mao de obra"], ["Custos fixos", "rateio"], ["Impostos", "impostos"], ["Lucro", "lucro estimado"]]
      .map(([n, l]) => ({ nome: n, valor: pp(l) })),
    custoTotal: pv("custo total estimado"), custoPessoa: pp("custo total estimado"),
    precoSugerido: pv("preco sugerido"), precoPessoa: pp("preco sugerido"),
    cobrado: pv("valor cobrado por pessoa"), lucro: pv("lucro estimado", 5, 8),
  };
  { // lucro e margem da simulação (segunda ocorrência)
    const r1 = findRow(PR, 5, "simulacao"); const r = findRow(PR, 5, "lucro estimado", r1 < 0 ? 0 : r1);
    if (r >= 0) out.prec.lucroSim = num(cell(PR, r, 8));
    const rm = findRow(PR, 5, "margem de lucro", r1 < 0 ? 0 : r1); if (rm >= 0) out.prec.margemSim = num(cell(PR, rm, 8));
    const rr = findRow(PR, 5, "receita prevista"); if (rr >= 0) out.prec.receitaSim = num(cell(PR, rr, 8));
  }
  out.ok = out.estoque.length > 0 || out.dre.receitaBruta.t !== 0;
  return out;
}


const RESULTS_LIBS = {
  xlsx: "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js",
  chart: "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js",
};
const loadedScripts = {};
function loadScript(src) {
  if (!loadedScripts[src]) {
    loadedScripts[src] = new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.onload = resolve;
      el.onerror = () => { delete loadedScripts[src]; reject(new Error("Não foi possível carregar os gráficos. Confira a internet e recarregue.")); };
      document.head.append(el);
    });
  }
  return loadedScripts[src];
}

// A conexão com o arquivo continua valendo ao trocar de aba do painel.
const liveFile = { handle: null, lastMod: 0, name: "" };

function reviveDashboard(data) {
  (data.eventos || []).forEach((e) => { e.data = new Date(e.data); });
  return data;
}

async function readSpreadsheet(file) {
  await loadScript(RESULTS_LIBS.xlsx);
  const wb = XLSX.read(await file.arrayBuffer(), { type: "array", cellDates: true });
  const sheets = {};
  wb.SheetNames.forEach((n) => {
    const ws = wb.Sheets[n];
    if (!ws || !ws["!ref"]) { sheets[n] = []; return; }
    const rg = XLSX.utils.decode_range(ws["!ref"]);
    rg.s.r = 0; rg.s.c = 0;
    ws["!ref"] = XLSX.utils.encode_range(rg);
    sheets[n] = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null, blankrows: true });
  });
  const data = parseBuffet(sheets);
  if (!data.ok) throw new Error("Este arquivo não parece ser a planilha do buffet: não encontrei as abas Estoque e DRE.");
  delete data.movs; // não aparecem no painel
  return data;
}

const handleStore = (mode, value) => new Promise((resolve) => {
  try {
    const rq = indexedDB.open("brunoise-resultados", 1);
    rq.onupgradeneeded = () => rq.result.createObjectStore("h");
    rq.onsuccess = () => {
      try {
        const st = rq.result.transaction("h", mode).objectStore("h");
        const r = mode === "readwrite" ? st.put(value, "planilha") : st.get("planilha");
        r.onsuccess = () => resolve(r.result || null);
        r.onerror = () => resolve(null);
      } catch { resolve(null); }
    };
    rq.onerror = () => resolve(null);
  } catch { resolve(null); }
});

async function adminResults(main) {
  const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const BRL0 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  const INT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const TIME = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const pct = (v) => (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  const short = (v) => (Math.abs(v) >= 1000 ? `R$ ${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil` : BRL0.format(v));
  const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const COLORS = { line: "rgba(214,150,108,.14)", muted: "#c4a493", copper: "#d9925f", wine: "#b8261b", wineLight: "#e0604a", cream: "#fbf3ea", ok: "#7fd6a4", panel: "#1d0a08" };
  const PAL = ["#d9925f", "#b8261b", "#f2c48d", "#fbf3ea", "#e0604a", "#8c3a2b", "#c9a27e", "#ff9f7a", "#7fd6a4", "#a8746b", "#e8d5c4", "#d4483a", "#6e4b3e"];
  const alpha = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };
  const canPick = "showOpenFilePicker" in window;

  // ---------- Estrutura ----------
  const statusChip = h("span", { class: "dash-chip" }, h("span", { class: "dash-chip__dot" }), h("span", null, "Carregando"));
  const info = h("span", { class: "dash-info" }, "");
  const fileInput = h("input", { type: "file", accept: ".ods,.xlsx,.xls", hidden: true });
  const btnConnect = h("button", { class: "dash-btn", type: "button" }, canPick ? "Conectar planilha" : "Enviar planilha");
  const btnReconnect = h("button", { class: "dash-btn dash-btn--ghost", type: "button", hidden: true }, "Reconectar");
  const btnRefresh = h("button", { class: "dash-btn dash-btn--ghost", type: "button", hidden: true }, "Atualizar agora");
  const errorBox = h("p", { class: "dash-error", role: "alert", hidden: true });

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
  const card = (title, wide, canvasLabel, center) => {
    const note = h("small", null, "");
    const canvas = h("canvas", { "aria-label": canvasLabel, role: "img" });
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
  const alertsList = h("div", { class: "dash-alerts" });
  const alertsNote = h("small", null, "");
  const alertsCard = h("article", { class: "dash-card" }, h("h2", null, h("span", null, "Itens para repor"), alertsNote), alertsList);

  const board = h("div", { class: "dash-board" },
    h("section", { class: "dash-kpis", "aria-label": "Resumo do ano" }, Object.values(K).map((k) => k.el)),
    h("section", { class: "dash-grid" }, C.mes.el, C.desp.el, C.ev.el, C.prec.el, C.est.el, alertsCard));
  const empty = h("div", { class: "dash-empty", hidden: true },
    h("p", { class: "dash-empty__title" }, "Nenhuma planilha enviada ainda"),
    h("p", null, canPick
      ? "Clique em “Conectar planilha” e escolha o arquivo .ods da Brunoise. A partir daí, cada vez que você salvar no LibreOffice, os números aparecem aqui e ficam disponíveis no celular."
      : "Abra o painel no computador (Chrome ou Edge) para conectar a planilha. Aqui aparecem os últimos números enviados."));

  fill(main,
    h("div", { class: "admin__head" },
      h("div", null, h("p", { class: "eyebrow" }, "Painel"), h("h1", null, "Resultados"))),
    h("div", { class: "dash" },
      h("div", { class: "dash-bar" },
        h("div", { class: "dash-brand" },
          h("img", { src: "/static/icone-192.png", alt: "", width: 44, height: 44 }),
          h("div", null, h("strong", null, "Central de resultados"), h("span", null, "planilha de estoque, DRE e precificação"))),
        h("div", { class: "dash-controls" }, statusChip, info, btnConnect, btnReconnect, btnRefresh, fileInput)),
      errorBox, empty, board));

  const setStatus = (kind, text) => {
    statusChip.className = `dash-chip${kind ? ` dash-chip--${kind}` : ""}`;
    statusChip.lastChild.textContent = text;
  };
  const showError = (msg) => { errorBox.textContent = msg || ""; errorBox.hidden = !msg; };

  try {
    await loadScript(RESULTS_LIBS.chart);
  } catch (err) {
    showError(err.message);
  }
  if (window.Chart) {
    Chart.defaults.color = COLORS.muted;
    Chart.defaults.borderColor = COLORS.line;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    Chart.defaults.plugins.legend.labels.boxHeight = 10;
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(18,6,5,.96)";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(217,146,95,.45)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
  }
  const charts = {};
  const draw = (key, cfg) => {
    if (!window.Chart) return;
    if (charts[key]) { charts[key].data = cfg.data; charts[key].options = cfg.options; charts[key].update(); return; }
    charts[key] = new Chart(C[key].canvas, cfg);
  };
  onLeave(() => Object.values(charts).forEach((c) => c.destroy()));

  // ---------- Desenho ----------
  function render(d) {
    empty.hidden = true;
    board.hidden = false;
    const R = d.dre;
    K.receita.val.textContent = BRL0.format(R.receitaBruta.t);
    K.receita.sub.textContent = `líquida: ${BRL0.format(R.receitaLiquida.t)}`;
    K.lucro.val.textContent = BRL0.format(R.lucroLiquido.t);
    K.lucro.val.className = `dash-kpi__val ${R.lucroLiquido.t >= 0 ? "is-pos" : "is-neg"}`;
    K.lucro.sub.textContent = `margem: ${pct(R.margemLiquida.t)}`;
    K.eventos.val.textContent = INT.format(R.eventos.t);
    K.eventos.sub.textContent = `${INT.format(R.convidados.t)} convidados`;
    K.ticket.val.textContent = BRL.format(R.ticket.t);
    K.ticket.sub.textContent = `insumos: ${BRL.format(R.cmvConv.t)} por pessoa`;
    K.estoque.val.textContent = BRL0.format(d.valorEstoque);
    K.estoque.sub.textContent = d.alertas.length ? `${d.alertas.length} itens para repor` : "nada para repor";
    K.estoque.sub.className = `dash-kpi__sub ${d.alertas.length ? "is-warn" : ""}`;
    const P = d.prec;
    K.preco.val.textContent = BRL.format(P.precoPessoa);
    K.preco.sub.textContent = `${INT.format(P.convidados)} convidados · lucro ${BRL0.format(P.lucroSim ?? P.lucro)}`;

    // Mês a mês: do primeiro mês com receita até o último com movimento.
    const used = R.receitaBruta.m.map((v, i) => (v || R.lucroLiquido.m[i] ? i : -1)).filter((i) => i >= 0);
    const idx = [];
    if (used.length) for (let i = used[0]; i <= used[used.length - 1]; i++) idx.push(i);
    const pick = (arr) => idx.map((i) => arr[i]);
    C.mes.note.textContent = idx.length ? `${MESES[idx[0]]}–${MESES[idx[idx.length - 1]]} ${d.ano}` : "sem lançamentos";
    draw("mes", {
      data: {
        labels: idx.map((i) => MESES[i]),
        datasets: [
          { type: "bar", label: "Receita", data: pick(R.receitaBruta.m), backgroundColor: alpha(COLORS.copper, 0.8), borderColor: COLORS.copper, borderWidth: 1, borderRadius: 6, order: 2 },
          { type: "bar", label: "Custos e despesas", data: idx.map((i) => Math.abs(R.cmv.m[i]) + Math.abs(R.custosDiretos.m[i]) + Math.abs(R.despOp.m[i])), backgroundColor: alpha(COLORS.wine, 0.75), borderColor: COLORS.wineLight, borderWidth: 1, borderRadius: 6, order: 3 },
          { type: "line", label: "Lucro líquido", data: pick(R.lucroLiquido.m), borderColor: COLORS.ok, backgroundColor: alpha(COLORS.ok, 0.14), pointBackgroundColor: COLORS.ok, pointRadius: 5, tension: 0.35, fill: true, order: 1 },
        ],
      },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${BRL0.format(c.parsed.y)}` } } },
        scales: { y: { ticks: { callback: (v) => short(v) } }, x: { grid: { display: false } } } },
    });

    const dg = d.despesasGrupo.slice().sort((a, b) => b.valor - a.valor);
    const totalDesp = dg.reduce((s, x) => s + x.valor, 0);
    C.desp.centerVal.textContent = short(totalDesp);
    C.desp.note.textContent = "despesas do ano";
    draw("desp", {
      type: "doughnut",
      data: { labels: dg.map((x) => x.nome), datasets: [{ data: dg.map((x) => x.valor), backgroundColor: dg.map((_, i) => PAL[i % PAL.length]), borderColor: COLORS.panel, borderWidth: 2, hoverOffset: 6 }] },
      options: { maintainAspectRatio: false, cutout: "68%", plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${BRL0.format(c.parsed)} (${pct(c.parsed / (totalDesp || 1))})` } } } },
    });

    const ev = d.eventos.filter((e) => e.status === "Realizado").sort((a, b) => a.data - b.data);
    C.ev.note.textContent = ev.length ? "passe o mouse para ver a margem" : "nenhum evento realizado";
    draw("ev", {
      type: "bar",
      data: { labels: ev.map((e) => e.code), datasets: [
        { label: "Receita", data: ev.map((e) => e.receita), backgroundColor: alpha(COLORS.copper, 0.8), borderColor: COLORS.copper, borderWidth: 1, borderRadius: 5 },
        { label: "Insumos (CMV)", data: ev.map((e) => e.cmv), backgroundColor: alpha(COLORS.wine, 0.8), borderColor: COLORS.wineLight, borderWidth: 1, borderRadius: 5 },
      ] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: {
          title: (it) => `${ev[it[0].dataIndex].code} · ${ev[it[0].dataIndex].cliente}`,
          label: (c) => ` ${c.dataset.label}: ${BRL0.format(c.parsed.y)}`,
          footer: (it) => { const e = ev[it[0].dataIndex]; return e.margem != null ? `Margem sobre insumos: ${pct(e.margem)}` : ""; },
        } } },
        scales: { y: { ticks: { callback: (v) => short(v) } }, x: { grid: { display: false } } } },
    });

    const comp = P.comp.filter((x) => x.valor > 0);
    const compColor = { Comida: "#d9925f", Bebidas: "#b8261b", "Descartáveis": "#f2c48d", "Mão de obra": "#fbf3ea", "Custos fixos": "#e0604a", Impostos: "#8a6f66", Lucro: COLORS.ok };
    C.prec.centerVal.textContent = BRL.format(P.precoPessoa);
    C.prec.note.textContent = `${P.tipo || "festa"} · ${INT.format(P.convidados)} convidados`;
    draw("prec", {
      type: "doughnut",
      data: { labels: comp.map((x) => x.nome), datasets: [{ data: comp.map((x) => x.valor), backgroundColor: comp.map((x) => compColor[x.nome] || "#a8746b"), borderColor: COLORS.panel, borderWidth: 2, hoverOffset: 6 }] },
      options: { maintainAspectRatio: false, cutout: "66%", plugins: { legend: { position: "right" }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${BRL.format(c.parsed)} (${pct(c.parsed / (P.precoPessoa || 1))})` } } } },
    });

    const et = d.estoqueTipo;
    C.est.note.textContent = `total ${BRL0.format(d.valorEstoque)}`;
    draw("est", {
      type: "bar",
      data: { labels: et.map((x) => x.nome), datasets: [{ label: "Valor em estoque", data: et.map((x) => x.valor), backgroundColor: et.map((_, i) => alpha(PAL[i % PAL.length], 0.75)), borderColor: et.map((_, i) => PAL[i % PAL.length]), borderWidth: 1, borderRadius: 5 }] },
      options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${BRL.format(c.parsed.x)}` } } },
        scales: { x: { ticks: { callback: (v) => short(v) } }, y: { grid: { display: false } } } },
    });

    const al = d.alertas;
    alertsNote.textContent = al.length ? `${al.length} itens` : "tudo em dia";
    fill(alertsList,
      al.length ? null : h("p", { class: "dash-muted" }, "Nenhum item abaixo do estoque mínimo."),
      al.slice(0, 9).map((i) => {
        const zero = i.status !== "REPOR";
        return h("div", { class: "dash-alert" },
          h("span", { class: "dash-alert__name", title: i.nome }, i.nome),
          h("span", { class: "dash-alert__qty" }, `${i.saldo.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}/${i.min.toLocaleString("pt-BR")} ${i.un}`),
          h("span", { class: `dash-pill${zero ? " dash-pill--zero" : ""}` }, zero ? "SEM ESTOQUE" : "REPOR"));
      }),
      al.length > 9 ? h("p", { class: "dash-muted" }, `+ ${al.length - 9} itens na aba Estoque da planilha`) : null);
  }

  // ---------- Dados do site ----------
  let serverStamp = "";
  async function loadFromSite(quiet) {
    try {
      const saved = await api.get("/admin/dashboard");
      if (saved.updated_at === serverStamp) return;
      serverStamp = saved.updated_at;
      render(reviveDashboard(saved.data));
      if (!liveFile.handle) {
        setStatus("site", "Últimos números enviados");
        info.textContent = `${saved.file_name || "planilha"} · enviada em ${TIME.format(new Date(saved.updated_at))}`;
      }
    } catch (err) {
      if (err.status === 404) {
        if (!quiet) { board.hidden = true; empty.hidden = false; setStatus("", "Sem planilha"); }
      } else if (!quiet) {
        showError(err.message);
      }
    }
  }

  async function publish(data, name) {
    try {
      const saved = await api.put("/admin/dashboard", { file_name: name, data });
      serverStamp = saved.updated_at;
      return saved;
    } catch (err) {
      showError(`Os números aparecem aqui, mas não foram enviados ao site: ${err.message}`);
      return null;
    }
  }

  async function useFile(file) {
    const data = await readSpreadsheet(file);
    render(reviveDashboard(JSON.parse(JSON.stringify(data))));
    showError("");
    const saved = await publish(data, file.name);
    const when = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    info.textContent = `${file.name} · ${saved ? "enviada ao site" : "lida"} às ${when}`;
  }

  // ---------- Ao vivo (Chrome/Edge no computador) ----------
  let reading = false;
  async function check(force) {
    if (!liveFile.handle || reading) return;
    reading = true;
    try {
      const file = await liveFile.handle.getFile();
      if (force || file.lastModified !== liveFile.lastMod) {
        liveFile.lastMod = file.lastModified;
        await useFile(file);
      }
      setStatus("live", "Ao vivo");
    } catch (err) {
      if (err?.name === "NotAllowedError") {
        liveFile.handle = null;
        setStatus("", "Conexão pausada");
        btnReconnect.hidden = false;
      } else if (err instanceof Error && !/NotReadable|NotFound/.test(err.name)) {
        showError(err.message);
      }
      // NotReadable/NotFound: o LibreOffice está salvando; tenta no próximo ciclo.
    } finally {
      reading = false;
    }
  }

  function startLive() {
    btnConnect.textContent = "Trocar planilha";
    btnRefresh.hidden = false;
    btnReconnect.hidden = true;
    setStatus("live", "Ao vivo");
    const timer = setInterval(() => check(false), 2000);
    onLeave(() => clearInterval(timer));
  }

  async function connect() {
    if (canPick) {
      try {
        const [handle] = await window.showOpenFilePicker({
          multiple: false,
          types: [{ description: "Planilha", accept: {
            "application/vnd.oasis.opendocument.spreadsheet": [".ods"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
          } }],
        });
        liveFile.handle = handle;
        liveFile.lastMod = 0;
        await handleStore("readwrite", handle);
        await check(true);
        startLive();
        return;
      } catch (err) {
        if (err?.name === "AbortError") return;
      }
    }
    fileInput.click();
  }

  btnConnect.addEventListener("click", connect);
  btnRefresh.addEventListener("click", () => (liveFile.handle ? check(true) : fileInput.click()));
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    try {
      await useFile(file);
      setStatus("site", "Planilha enviada");
      btnRefresh.hidden = false;
    } catch (err) {
      showError(err.message);
    }
  });
  btnReconnect.addEventListener("click", async () => {
    const handle = liveFile.handle || (await handleStore("readonly"));
    if (!handle?.requestPermission) return connect();
    try {
      if ((await handle.requestPermission({ mode: "read" })) === "granted") {
        liveFile.handle = handle;
        liveFile.lastMod = 0;
        await check(true);
        startLive();
      }
    } catch {
      connect();
    }
  });

  await loadFromSite(false);
  if (liveFile.handle) {
    await check(true);
    startLive();
  } else {
    if (canPick && (await handleStore("readonly"))) btnReconnect.hidden = false;
    // Celular ou outro computador: busca números novos a cada 30 s.
    const timer = setInterval(() => { if (!liveFile.handle) loadFromSite(true); }, 30000);
    onLeave(() => clearInterval(timer));
  }
}
