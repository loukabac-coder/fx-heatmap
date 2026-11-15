// public/js/app.js
import {
  computeCrossRate,
  computeCross24hChange,
  computeZScore24M,
  getDecimals,
  getHeatmapStyle
} from "./quant.js";
import { renderPairHistoryChart, renderDrawerChart } from "./charts.js";
import {
  initOrUpdateGlobe,
  focusGlobeRegion,
  focusGlobeCurrency,
  toggleGlobeSpin
} from "./globe3d.js";

const STATE = {
  currencies: {},
  history: { dates: [], series: {} },
  meta: {},
  liveStatus: "Snapshot",
  activeTab: "globe",
  globeMetric: "realRate",
  scope: "ALL",          // ALL | G10 | EM
  metric: "realRate",    // realRate | nominalRate | headlineCpi | coreCpi | inflationGap
  coreMode: false,       // true => Nominal - Core CPI
  sortBy: "desc",        // desc | asc | alpha | decision
  baseCur: "EUR",
  quoteCur: "USD",
  spreadType: "real",    // real | nominal
  rangeMonths: 60
};

const fmtPct = (v, sign = false) =>
  v == null ? "n.d." : `${sign && v > 0 ? "+" : ""}${v.toFixed(2)}%`;

const fmtBps = (v) =>
  v == null ? "n.d." : `${v > 0 ? "+" : ""}${Math.round(v * 100)} bps`;

// --- Chargement des données ---
async function bootstrap() {
  try {
    const [snapRes, histRes] = await Promise.all([
      fetch("./data/fx_macro_snapshot.json?t=" + Date.now()),
      fetch("./data/fx_history.json?t=" + Date.now())
    ]);
    const snapJson = await snapRes.json();
    const histJson = await histRes.json();

    // Enrichissement avec l'Inflation Gap (CPI - Cible) sur chaque devise
    for (const c of Object.values(snapJson.currencies)) {
      c.inflationGap =
        c.headlineCpi != null && c.target != null
          ? +(c.headlineCpi - c.target).toFixed(2)
          : null;
    }

    STATE.currencies = snapJson.currencies;
    STATE.meta = snapJson.meta;
    STATE.history = histJson;

    populatePairSelects();
    renderGlobePills();
    renderAll();
    updateSyncBadge();

    fetchLiveSpotRates();
  } catch (err) {
    document.getElementById("sync-status").textContent = "Erreur chargement données";
    console.error(err);
  }
}

async function fetchLiveSpotRates() {
  try {
    const res = await fetch("https://open.er-api.com/v6/latest/USD");
    if (!res.ok) return;
    const data = await res.json();
    if (data.result === "success" && data.rates) {
      for (const [cur, unitsPerUsd] of Object.entries(data.rates)) {
        if (STATE.currencies[cur] && unitsPerUsd > 0) {
          STATE.currencies[cur].usdRate = +(1.0 / unitsPerUsd).toFixed(6);
        }
      }
      const timeStr = new Date().toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit"
      });
      STATE.liveStatus = `Spot Live ${timeStr}`;
      updateSyncBadge();
      renderComparator();
      renderG10Matrix();
    }
  } catch {
    // Repli silencieux
  }
}

function updateSyncBadge() {
  const el = document.getElementById("sync-status");
  el.innerHTML = `
    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
    <span>${STATE.liveStatus} • Macro : ${STATE.meta.lastUpdatedUTC || "OK"}</span>
  `;
}

// --- Ruban de pilules sous le Globe (navigation rapide mobile) ---
function renderGlobePills() {
  const box = document.getElementById("globe-quick-pills");
  if (!box) return;
  box.innerHTML = Object.values(STATE.currencies)
    .map(
      c => `
      <button data-focus-cur="${c.currency}"
        class="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#0f172a] hover:bg-slate-800 border border-slate-800 text-xs font-mono text-slate-200 transition">
        <span>${c.flag}</span>
        <span class="font-bold">${c.currency}</span>
        <span class="${c.realRateStd >= 0 ? "text-emerald-400" : "text-rose-400"}">${fmtPct(c.realRateStd, true)}</span>
      </button>
    `
    )
    .join("");
}

// --- Extraction métrique active (Grille Heatmap) ---
function getActiveMetricValue(c) {
  if (STATE.metric === "realRate") {
    return STATE.coreMode ? c.realRateCore : c.realRateStd;
  }
  return c[STATE.metric];
}

// --- Rendu de la Grille Heatmap ---
function renderHeatmap() {
  const grid = document.getElementById("heatmap-grid");
  let list = Object.values(STATE.currencies);

  if (STATE.scope !== "ALL") {
    list = list.filter(c => c.group === STATE.scope);
  }

  list.sort((a, b) => {
    if (STATE.sortBy === "alpha") return a.currency.localeCompare(b.currency);
    if (STATE.sortBy === "decision") {
      const rank = { HIKE: 3, CUT: 2, HOLD: 1 };
      return (rank[b.lastDecision] || 0) - (rank[a.lastDecision] || 0);
    }
    const va = getActiveMetricValue(a) ?? -999;
    const vb = getActiveMetricValue(b) ?? -999;
    return STATE.sortBy === "desc" ? vb - va : va - vb;
  });

  const validVals = list.map(getActiveMetricValue).filter(v => v != null);
  const minVal = validVals.length ? Math.min(...validVals) : 0;
  const maxVal = validVals.length ? Math.max(...validVals) : 5;

  grid.innerHTML = list
    .map(c => {
      const val = getActiveMetricValue(c);
      const style = getHeatmapStyle(val, minVal, maxVal, STATE.metric === "inflationGap" ? "headlineCpi" : STATE.metric);

      let badgeHtml = `<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700">PAUSE</span>`;
      if (c.lastDecision === "HIKE") {
        badgeHtml = `<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">▲ ${c.lastChange}</span>`;
      } else if (c.lastDecision === "CUT") {
        badgeHtml = `<span class="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">▼ ${c.lastChange}</span>`;
      }

      return `
        <button data-open-drawer="${c.currency}"
          style="background:${style.bg}; border-color:${style.border};"
          class="heat-card text-left rounded-xl border p-3.5 flex flex-col justify-between gap-3 cursor-pointer">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="text-base">${c.flag}</span>
                <span class="font-mono font-bold text-sm text-white">${c.currency}</span>
                <span class="text-[10px] font-mono px-1.5 py-0.2 rounded bg-black/30 text-slate-300">${c.group}</span>
              </div>
              <p class="text-[11px] text-slate-300/90 truncate max-w-[155px] mt-0.5">${c.bank}</p>
            </div>
            ${badgeHtml}
          </div>

          <div class="flex items-baseline justify-between pt-1">
            <span style="color:${style.text};" class="text-2xl font-mono font-bold tracking-tight">
              ${fmtPct(val, STATE.metric === "realRate" || STATE.metric === "inflationGap")}
            </span>
            <span class="text-[10px] font-mono text-slate-400">
              CPI ${c.cpiAsOf || "n.d."}
            </span>
          </div>

          <div class="grid grid-cols-3 gap-1 pt-2 border-t border-white/10 text-[10px] font-mono text-slate-300">
            <div><span class="text-slate-400 block">Nom.</span>${fmtPct(c.nominalRate)}</div>
            <div><span class="text-slate-400 block">CPI</span>${fmtPct(c.headlineCpi)}</div>
            <div><span class="text-slate-400 block">Gap</span>${fmtPct(c.inflationGap, true)}</div>
          </div>
        </button>
      `;
    })
    .join("");
}

// --- Tiroir Latéral (Fiche d'Identité Monétaire) ---
function openCountryDrawer(cur) {
  const c = STATE.currencies[cur];
  const h = STATE.history.series[cur];
  if (!c || !h) return;

  const drawer = document.getElementById("country-drawer");
  const backdrop = document.getElementById("drawer-backdrop");

  drawer.innerHTML = `
    <div class="flex items-start justify-between border-b border-slate-800 pb-4">
      <div>
        <div class="flex items-center gap-2">
          <span class="text-2xl">${c.flag}</span>
          <h2 class="text-lg font-bold text-white">${c.name} (${c.currency})</h2>
          <span class="text-xs font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">${c.group}</span>
        </div>
        <p class="text-xs text-slate-300 mt-1">${c.bank}</p>
        <p class="text-[11px] text-slate-400 mt-0.5">Gouverneur : <strong class="text-slate-200">${c.governor}</strong> • Réf : ${c.rateLabel}</p>
      </div>
      <button id="close-drawer-btn" class="text-slate-400 hover:text-white text-lg px-2 py-1 rounded bg-slate-800/60">✕</button>
    </div>

    <div class="grid grid-cols-2 gap-3">
      <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3">
        <span class="text-[10px] font-mono uppercase text-slate-400 block">Taux Réel (Standard)</span>
        <span class="text-xl font-mono font-bold text-sky-400 mt-0.5 block">${fmtPct(c.realRateStd, true)}</span>
        <span class="text-[10px] text-slate-500">Nominal - Headline CPI</span>
      </div>
      <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3">
        <span class="text-[10px] font-mono uppercase text-slate-400 block">Taux Réel (Core)</span>
        <span class="text-xl font-mono font-bold text-emerald-400 mt-0.5 block">${fmtPct(c.realRateCore, true)}</span>
        <span class="text-[10px] text-slate-500">Nominal - Core CPI</span>
      </div>
      <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3">
        <span class="text-[10px] font-mono uppercase text-slate-400 block">Taux Directeur</span>
        <span class="text-lg font-mono font-bold text-white mt-0.5 block">${fmtPct(c.nominalRate)}</span>
        <span class="text-[10px] text-slate-400">Dernier : ${c.lastChange} (${c.lastChangeMonth || "Pause"})</span>
      </div>
      <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3">
        <span class="text-[10px] font-mono uppercase text-slate-400 block">Inflation Gap</span>
        <span class="text-lg font-mono font-bold ${c.inflationGap > 0 ? "text-amber-400" : "text-sky-400"} mt-0.5 block">${fmtPct(c.inflationGap, true)}</span>
        <span class="text-[10px] text-slate-400">Cible : ${fmtPct(c.target)}</span>
      </div>
    </div>

    <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3.5 grid grid-cols-2 gap-3 text-xs">
      <div>
        <span class="text-slate-400 block text-[11px]">Inflation Headline / Core</span>
        <span class="font-mono font-semibold text-white">${fmtPct(c.headlineCpi)} / ${fmtPct(c.coreCpi)}</span>
        <span class="text-[10px] text-slate-500 block">Publication : ${c.cpiAsOf || "n.d."}</span>
      </div>
      <div>
        <span class="text-slate-400 block text-[11px]">Calendrier Réunions</span>
        <span class="font-mono text-slate-300 block">Dernière : ${c.lastMeeting}</span>
        <span class="font-mono text-sky-400 font-semibold block">Prochaine : ${c.nextMeeting}</span>
      </div>
    </div>

    <div class="bg-[#0f172a] border border-slate-800 rounded-xl p-3.5 flex-1 flex flex-col min-h-[260px]">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-semibold text-slate-200">Trajectoire 24 Mois : Taux vs Inflation</span>
        <button data-compare-with="${c.currency}" class="text-[11px] font-mono text-sky-400 hover:underline">
          Comparer ${c.currency} →
        </button>
      </div>
      <div id="drawer-chart" class="w-full h-[220px]"></div>
    </div>
  `;

  backdrop.classList.remove("hidden");
  drawer.classList.remove("translate-x-full");

  document.getElementById("close-drawer-btn").onclick = closeCountryDrawer;
  drawer.querySelector("[data-compare-with]").onclick = () => {
    STATE.baseCur = c.currency;
    STATE.quoteCur = c.currency === "USD" ? "EUR" : "USD";
    document.getElementById("pair-base").value = STATE.baseCur;
    document.getElementById("pair-quote").value = STATE.quoteCur;
    closeCountryDrawer();
    switchTab("comparator");
  };

  setTimeout(() => {
    renderDrawerChart("drawer-chart", STATE.history.dates, h.rate, h.cpi, h.core);
  }, 40);
}

function closeCountryDrawer() {
  document.getElementById("country-drawer").classList.add("translate-x-full");
  document.getElementById("drawer-backdrop").classList.add("hidden");
}

// --- Comparateur Universel de Paires ---
function populatePairSelects() {
  const baseSel = document.getElementById("pair-base");
  const quoteSel = document.getElementById("pair-quote");
  const opts = Object.values(STATE.currencies)
    .map(c => `<option value="${c.currency}">${c.flag} ${c.currency} — ${c.name} (${c.bank})</option>`)
    .join("");
  baseSel.innerHTML = opts;
  quoteSel.innerHTML = opts;
  baseSel.value = STATE.baseCur;
  quoteSel.value = STATE.quoteCur;
}

function renderComparator() {
  const base = STATE.currencies[STATE.baseCur];
  const quote = STATE.currencies[STATE.quoteCur];
  if (!base || !quote) return;

  const dec = getDecimals(quote.currency);
  const spot = computeCrossRate(base, quote);
  const chg24h = computeCross24hChange(base, quote);

  const realBase = STATE.coreMode ? base.realRateCore : base.realRateStd;
  const realQuote = STATE.coreMode ? quote.realRateCore : quote.realRateStd;
  const realSpread = realBase != null && realQuote != null ? +(realBase - realQuote).toFixed(2) : null;
  const nomSpread = base.nominalRate != null && quote.nominalRate != null ? +(base.nominalRate - quote.nominalRate).toFixed(2) : null;

  document.getElementById("kpi-pair-label").textContent = `${base.currency}/${quote.currency} SPOT`;
  document.getElementById("kpi-spot").textContent = spot != null ? spot.toFixed(dec) : "n.d.";

  const chgEl = document.getElementById("kpi-spot-chg");
  chgEl.textContent = `${chg24h >= 0 ? "+" : ""}${chg24h.toFixed(2)}%`;
  chgEl.className = `text-xs font-mono font-semibold ${chg24h >= 0 ? "text-emerald-400" : "text-rose-400"}`;

  const pipFactor = dec <= 3 ? 100 : 10000;
  const pips = spot != null ? Math.round((spot * (chg24h / 100)) * pipFactor) : 0;
  document.getElementById("kpi-spot-pips").textContent = `Var. 24h : ${pips >= 0 ? "+" : ""}${pips} pips`;

  const colorSpread = (el, val) => {
    el.textContent = val != null ? `${fmtPct(val, true)} (${fmtBps(val)})` : "n.d.";
    el.className = `text-xl font-mono font-bold mt-1 block ${val == null ? "text-slate-400" : val >= 0 ? "text-emerald-400" : "text-rose-400"}`;
  };

  colorSpread(document.getElementById("kpi-real-spread"), realSpread);
  document.getElementById("kpi-real-detail").textContent = `${base.currency} (${fmtPct(realBase, true)}) vs ${quote.currency} (${fmtPct(realQuote, true)})`;

  colorSpread(document.getElementById("kpi-nom-spread"), nomSpread);
  document.getElementById("kpi-nom-detail").textContent = `${fmtPct(base.nominalRate)} vs ${fmtPct(quote.nominalRate)}`;

  const hBase = STATE.history.series[base.currency];
  const hQuote = STATE.history.series[quote.currency];
  const allDates = STATE.history.dates;

  const fullSpotHist = allDates.map((_, i) => {
    const a = hBase.fxUsd[i];
    const b = hQuote.fxUsd[i];
    return a && b ? +(a / b).toFixed(dec) : null;
  });

  const fullRealSpreadHist = allDates.map((_, i) => {
    const infB = STATE.coreMode ? hBase.core[i] : hBase.cpi[i];
    const infQ = STATE.coreMode ? hQuote.core[i] : hQuote.cpi[i];
    if (hBase.rate[i] == null || infB == null || hQuote.rate[i] == null || infQ == null) return null;
    return +((hBase.rate[i] - infB) - (hQuote.rate[i] - infQ)).toFixed(2);
  });

  const fullNomSpreadHist = allDates.map((_, i) =>
    hBase.rate[i] != null && hQuote.rate[i] != null ? +(hBase.rate[i] - hQuote.rate[i]).toFixed(2) : null
  );

  const quant = computeZScore24M(fullSpotHist, fullRealSpreadHist);
  const zEl = document.getElementById("kpi-zscore");
  zEl.textContent = quant.zScore != null ? `${quant.zScore > 0 ? "+" : ""}${quant.zScore.toFixed(2)} σ` : "n.d.";
  zEl.className = `text-2xl font-mono font-bold mt-1 block ${
    quant.zScore == null ? "text-slate-400" : Math.abs(quant.zScore) >= 1.5 ? "text-amber-400" : "text-sky-400"
  }`;
  document.getElementById("kpi-zscore-signal").textContent = `${quant.signal} (R²=${quant.r2 ?? "--"})`;

  const sliceStart = Math.max(0, allDates.length - STATE.rangeMonths);
  const datesSlice = allDates.slice(sliceStart);
  const spotSlice = fullSpotHist.slice(sliceStart);

  const spreadSlice =
    STATE.spreadType === "nominal"
      ? fullNomSpreadHist.slice(sliceStart)
      : fullRealSpreadHist.slice(sliceStart);
  const spreadLabel = STATE.spreadType === "nominal" ? "Spread Nominal" : "Spread Taux Réel";

  renderPairHistoryChart(
    "pair-history-chart",
    datesSlice,
    spotSlice,
    spreadSlice,
    base.currency,
    quote.currency,
    spreadLabel
  );
}

// --- Matrice Croisée G10 ---
function renderG10Matrix() {
  const g10 = Object.values(STATE.currencies).filter(c => c.group === "G10");
  const container = document.getElementById("g10-matrix-container");

  let html = `<table class="w-full text-xs font-mono border-collapse"><thead><tr><th class="p-2 border border-slate-800 bg-[#080c14] text-slate-400">BASE \\ COTÉE</th>`;
  for (const col of g10) {
    html += `<th class="p-2 border border-slate-800 bg-[#080c14] text-white">${col.flag} ${col.currency}</th>`;
  }
  html += `</tr></thead><tbody>`;

  for (const row of g10) {
    html += `<tr><th class="p-2 border border-slate-800 bg-[#080c14] text-white text-left whitespace-nowrap">${row.flag} ${row.currency}</th>`;
    for (const col of g10) {
      if (row.currency === col.currency) {
        html += `<td class="p-2 border border-slate-800 bg-slate-900/50 text-center text-slate-600">—</td>`;
        continue;
      }
      const cross = computeCrossRate(row, col);
      const dec = Math.min(getDecimals(col.currency), 4);
      const rRow = STATE.coreMode ? row.realRateCore : row.realRateStd;
      const rCol = STATE.coreMode ? col.realRateCore : col.realRateStd;
      const spread = rRow != null && rCol != null ? +(rRow - rCol).toFixed(2) : null;
      const spreadColor = spread == null ? "text-slate-500" : spread >= 0 ? "text-emerald-400" : "text-rose-400";

      html += `
        <td data-matrix-pair="${row.currency}/${col.currency}"
            class="p-2 border border-slate-800 hover:bg-sky-500/15 cursor-pointer text-center transition">
          <div class="font-bold text-slate-100">${cross != null ? cross.toFixed(dec) : "n.d."}</div>
          <div class="text-[10px] ${spreadColor}">${spread != null ? `${spread > 0 ? "+" : ""}${spread.toFixed(2)}%` : "n.d."}</div>
        </td>
      `;
    }
    html += `</tr>`;
  }
  html += `</tbody></table>`;
  container.innerHTML = html;
}

// --- Navigation & Événements ---
function switchTab(tabName) {
  STATE.activeTab = tabName;
  document.querySelectorAll(".tab-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tabName);
    b.classList.toggle("text-slate-400", b.dataset.tab !== tabName);
  });
  ["globe", "heatmap", "comparator", "matrix"].forEach(v => {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== tabName);
  });
  if (tabName === "globe") {
    setTimeout(() => initOrUpdateGlobe("globe-container", STATE.currencies, STATE.globeMetric, openCountryDrawer), 30);
  } else if (tabName === "comparator") {
    setTimeout(renderComparator, 30);
  }
}

function renderAll() {
  initOrUpdateGlobe("globe-container", STATE.currencies, STATE.globeMetric, openCountryDrawer);
  renderHeatmap();
  renderComparator();
  renderG10Matrix();
}

document.addEventListener("click", (e) => {
  const tabBtn = e.target.closest(".tab-btn");
  if (tabBtn) switchTab(tabBtn.dataset.tab);

  const globeMetricBtn = e.target.closest(".globe-metric-btn");
  if (globeMetricBtn) {
    STATE.globeMetric = globeMetricBtn.dataset.globeMetric;
    document.querySelectorAll(".globe-metric-btn").forEach(b => {
      b.classList.remove("active", "bg-sky-500/20", "text-sky-300");
      b.classList.add("text-slate-400");
    });
    globeMetricBtn.classList.add("active", "bg-sky-500/20", "text-sky-300");
    globeMetricBtn.classList.remove("text-slate-400");
    initOrUpdateGlobe("globe-container", STATE.currencies, STATE.globeMetric, openCountryDrawer);
  }

  const camBtn = e.target.closest(".cam-btn");
  if (camBtn) focusGlobeRegion(camBtn.dataset.cam);

  const focusCurBtn = e.target.closest("[data-focus-cur]");
  if (focusCurBtn) {
    const cur = focusCurBtn.dataset.focusCur;
    focusGlobeCurrency(cur);
    openCountryDrawer(cur);
  }

  if (e.target.id === "btn-toggle-spin") {
    const spinning = toggleGlobeSpin();
    e.target.textContent = spinning ? "⏸ Pause" : "▶ Rotation";
  }

  const scopeBtn = e.target.closest(".scope-btn");
  if (scopeBtn) {
    STATE.scope = scopeBtn.dataset.scope;
    document.querySelectorAll(".scope-btn").forEach(b => b.classList.remove("active", "text-slate-400"));
    scopeBtn.classList.add("active");
    renderHeatmap();
  }

  const metricBtn = e.target.closest(".metric-btn");
  if (metricBtn) {
    STATE.metric = metricBtn.dataset.metric;
    document.querySelectorAll(".metric-btn").forEach(b => b.classList.remove("active"));
    metricBtn.classList.add("active");
    renderHeatmap();
  }

  const drawerCard = e.target.closest("[data-open-drawer]");
  if (drawerCard) openCountryDrawer(drawerCard.dataset.openDrawer);

  if (e.target.id === "drawer-backdrop") closeCountryDrawer();

  const quickPair = e.target.closest(".quick-pair-btn");
  if (quickPair) {
    const [b, q] = quickPair.dataset.pair.split("/");
    STATE.baseCur = b;
    STATE.quoteCur = q;
    document.getElementById("pair-base").value = b;
    document.getElementById("pair-quote").value = q;
    renderComparator();
  }

  const matrixCell = e.target.closest("[data-matrix-pair]");
  if (matrixCell) {
    const [b, q] = matrixCell.dataset.matrixPair.split("/");
    STATE.baseCur = b;
    STATE.quoteCur = q;
    document.getElementById("pair-base").value = b;
    document.getElementById("pair-quote").value = q;
    switchTab("comparator");
  }

  const spreadBtn = e.target.closest(".spread-type-btn");
  if (spreadBtn) {
    STATE.spreadType = spreadBtn.dataset.spreadType;
    document.querySelectorAll(".spread-type-btn").forEach(b => {
      b.className = "spread-type-btn px-3 py-1 rounded-md font-medium text-slate-400 hover:text-white";
    });
    spreadBtn.className = "spread-type-btn active px-3 py-1 rounded-md font-medium bg-sky-500/20 text-sky-300 border border-sky-500/40";
    renderComparator();
  }

  const rangeBtn = e.target.closest(".range-btn");
  if (rangeBtn) {
    STATE.rangeMonths = Number(rangeBtn.dataset.range);
    document.querySelectorAll(".range-btn").forEach(b => {
      b.className = "range-btn px-2.5 py-1 rounded text-slate-400 hover:text-white";
    });
    rangeBtn.className = "range-btn active px-2.5 py-1 rounded bg-slate-800 text-white";
    renderComparator();
  }
});

document.getElementById("toggle-core-mode").addEventListener("change", (e) => {
  STATE.coreMode = e.target.checked;
  renderAll();
});

document.getElementById("sort-select").addEventListener("change", (e) => {
  STATE.sortBy = e.target.value;
  renderHeatmap();
});

document.getElementById("pair-base").addEventListener("change", (e) => {
  STATE.baseCur = e.target.value;
  renderComparator();
});

document.getElementById("pair-quote").addEventListener("change", (e) => {
  STATE.quoteCur = e.target.value;
  renderComparator();
});

document.getElementById("btn-invert-pair").addEventListener("click", () => {
  [STATE.baseCur, STATE.quoteCur] = [STATE.quoteCur, STATE.baseCur];
  document.getElementById("pair-base").value = STATE.baseCur;
  document.getElementById("pair-quote").value = STATE.quoteCur;
  renderComparator();
});

bootstrap();
