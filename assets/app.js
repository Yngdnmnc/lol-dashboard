/* LoL Dashboard — frontend
 * Carga data/players.json + data/<id>.json (generados por fetch.py o make_mock.py)
 * y arma player selector, rank cards, dos gráficas de LP e historial.
 */
"use strict";

const State = {
  meta: null,
  players: [],        // config de players.json
  data: {},           // { playerId: <objeto data/<id>.json> }
  currentPlayer: null,
  lpQueue: "solo",    // gráfica LP total: solo | flex
  lpGamesN: 10,       // gráfica LP por partida: 10 | 20 | 30
  historyFilter: "ALL",
  champSelected: null, // campeón elegido en el análisis
};

const TIER_SHORT = {
  IRON: "Fe", BRONZE: "Br", SILVER: "Ag", GOLD: "Au", PLATINUM: "Pt",
  EMERALD: "Em", DIAMOND: "Di", MASTER: "Ma", GRANDMASTER: "GM", CHALLENGER: "Ch",
};
const TIER_NAME = {
  IRON: "Hierro", BRONZE: "Bronce", SILVER: "Plata", GOLD: "Oro", PLATINUM: "Platino",
  EMERALD: "Esmeralda", DIAMOND: "Diamante", MASTER: "Maestro",
  GRANDMASTER: "Gran Maestro", CHALLENGER: "Retador",
};

let lpTotalChart = null;
let lpGamesChart = null;

/* ---------- carga ---------- */
async function loadData() {
  const cfg = await fetchJSON("data/players.json");
  State.meta = cfg.meta || {};
  State.players = cfg.players || [];
  try { State.meta = { ...State.meta, ...(await fetchJSON("data/meta.json")) }; } catch (e) {}
  if (State.meta.mock) document.getElementById("mockBanner").classList.remove("hide");
  State.data = {};
  for (const p of State.players) {
    try { State.data[p.id] = await fetchJSON(`data/${p.id}.json`); }
    catch (e) { console.warn(`Sin datos para ${p.id}`, e); }
  }
}

async function boot() {
  try {
    await loadData();
    State.currentPlayer = State.players.find(p => State.data[p.id])?.id || State.players[0]?.id;
    renderPlayerSwitch();
    renderUpdated();
    wireControls();
    renderAll();
  } catch (e) {
    document.getElementById("matchList").innerHTML =
      `<div class="empty">No se pudo cargar la config. ¿Existe <code>data/players.json</code>?<br><small>${e}</small></div>`;
  }
}

/* Recarga los datos ya publicados (los que dejó el último cron) sin recargar la página. */
async function refreshData() {
  const btn = document.getElementById("refreshBtn");
  const prev = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "Actualizando…";
  try {
    await loadData();
    if (!State.data[State.currentPlayer])
      State.currentPlayer = State.players.find(p => State.data[p.id])?.id || State.players[0]?.id;
    renderPlayerSwitch();
    renderUpdated();
    renderAll();
  } catch (e) {
    console.warn("refresh falló", e);
  } finally {
    btn.disabled = false;
    btn.innerHTML = prev;
  }
}

async function fetchJSON(url) {
  const r = await fetch(url + "?t=" + Date.now());
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

/* ---------- header ---------- */
function renderPlayerSwitch() {
  const el = document.getElementById("playerSwitch");
  el.innerHTML = "";
  for (const p of State.players) {
    const b = document.createElement("button");
    b.textContent = p.name || p.id;
    b.className = p.id === State.currentPlayer ? "active" : "";
    b.disabled = !State.data[p.id];
    if (b.disabled) b.title = "Sin datos aún";
    b.onclick = () => { State.currentPlayer = p.id; renderPlayerSwitch(); renderAll(); };
    el.appendChild(b);
  }
}

function renderUpdated() {
  const u = State.meta.updated;
  document.getElementById("updated").textContent =
    u ? "Actualizado: " + new Date(u).toLocaleString("es-ES") : "";
}

/* ---------- render principal ---------- */
function renderAll() {
  const d = State.data[State.currentPlayer];
  if (!d) return;
  renderRankCards(d);
  renderLpTotalChart(d);
  renderLpGamesChart(d);
  renderChampPanel(d);
  renderMatches(d);
}

/* ---------- análisis por campeón ---------- */
function championAggregates(matches) {
  const map = new Map();
  for (const m of matches) {
    if (!m.champion) continue;
    let a = map.get(m.champion);
    if (!a) {
      a = { champion: m.champion, championId: m.championId, games: 0, wins: 0, losses: 0,
            lp: 0, k: 0, d: 0, as: 0, statGames: 0, dmg: 0, dmgN: 0, dur: 0, durN: 0,
            cspm: 0, csN: 0, gpm: 0, gN: 0, vis: 0, visN: 0, roles: {} };
      map.set(m.champion, a);
    }
    a.games++;
    if (m.win === true) a.wins++; else if (m.win === false) a.losses++;
    const lp = matchLp(m); if (lp != null) a.lp += lp;
    if (m.position) a.roles[m.position] = (a.roles[m.position] || 0) + 1;
    if (m.kda != null) {  // partida enriquecida con la API
      a.statGames++;
      a.k += m.kills; a.d += m.deaths; a.as += m.assists;
      if (m.damage != null) { a.dmg += m.damage; a.dmgN++; }
      if (m.duration != null) { a.dur += m.duration; a.durN++; }
      if (m.csPerMin != null) { a.cspm += m.csPerMin; a.csN++; }
      if (m.goldPerMin != null) { a.gpm += m.goldPerMin; a.gN++; }
      if (m.visionScore != null) { a.vis += m.visionScore; a.visN++; }
    }
  }
  return [...map.values()].sort((x, y) => y.games - x.games);
}

function renderChampPanel(d) {
  const aggs = championAggregates(d.matches || []);
  const sel = document.getElementById("champSelect");
  if (!aggs.length) {
    document.getElementById("champTiles").innerHTML = `<div class="empty">Sin partidas.</div>`;
    sel.innerHTML = "";
    return;
  }
  // mantener selección si el campeón sigue existiendo, si no, el más jugado
  if (!State.champSelected || !aggs.some(a => a.champion === State.champSelected))
    State.champSelected = aggs[0].champion;

  sel.innerHTML = aggs.map(a =>
    `<option value="${a.champion}"${a.champion === State.champSelected ? " selected" : ""}>${a.champion} (${a.games})</option>`
  ).join("");

  renderChampStats(aggs.find(a => a.champion === State.champSelected));
}

function renderChampStats(a) {
  const ver = State.meta.ddragonVersion || "16.16.1";
  const decided = a.wins + a.losses;  // partidas con V/D conocido
  const wr = decided ? Math.round((a.wins / decided) * 100) : 0;
  const wrCls = wr >= 55 ? "good" : wr < 48 ? "bad" : "";
  const kdaAgg = ((a.k + a.as) / Math.max(1, a.d)).toFixed(2);
  const avg = (s, n) => (n ? s / n : 0);
  const dmgAvg = avg(a.dmg, a.dmgN), cspmAvg = avg(a.cspm, a.csN),
        gpmAvg = avg(a.gpm, a.gN), visAvg = avg(a.vis, a.visN);
  const totalMin = Math.round(a.dur / 60);
  const playtime = a.durN ? `${Math.floor(totalMin / 60)}h ${totalMin % 60}m` : "—";
  const lpCls = a.lp > 0 ? "pos" : a.lp < 0 ? "neg" : "neu";
  const lpSign = a.lp > 0 ? "+" : "";
  const topRole = Object.entries(a.roles).sort((x, y) => y[1] - x[1])[0];
  const kAvg = avg(a.k, a.statGames).toFixed(1), dAvg = avg(a.d, a.statGames).toFixed(1),
        aAvg = avg(a.as, a.statGames).toFixed(1);
  const detail = a.statGames ? `sobre ${a.statGames} con detalle` : "sin detalle aún";

  const img = document.getElementById("champImg");
  img.src = `https://ddragon.leagueoflegends.com/cdn/${ver}/img/champion/${a.champion}.png`;
  img.alt = a.champion;

  document.getElementById("champSub").textContent =
    `${a.games} partidas · ${a.wins}V ${a.losses}D${topRole ? " · " + topRole[0] : ""}`;

  const tile = (v, l, cls = "") => `<div class="tile"><div class="tv ${cls}">${v}</div><div class="tl">${l}</div></div>`;
  document.getElementById("champTiles").innerHTML =
    tile(`${wr}%`, `Winrate (${a.wins}V ${a.losses}D)`, wrCls) +
    tile(`${lpSign}${a.lp} LP`, "LP neto", lpCls) +
    tile(kdaAgg, `KDA · ${kAvg}/${dAvg}/${aAvg}`, kdaAgg >= 3 ? "good" : "") +
    tile(a.dmgN ? fmtK(Math.round(dmgAvg)) : "—", `Daño prom. (${detail})`) +
    tile(a.csN ? cspmAvg.toFixed(1) : "—", "CS/min prom.") +
    tile(a.gN ? Math.round(gpmAvg) : "—", "Oro/min prom.") +
    tile(a.visN ? Math.round(visAvg) : "—", "Visión prom.") +
    tile(playtime, "Tiempo jugado");
}

/* ---------- rank cards ---------- */
function renderRankCards(d) {
  const row = document.getElementById("rankRow");
  row.innerHTML = "";
  row.appendChild(rankCard("solo", "Solo/Duo", d.rank?.solo));
  row.appendChild(rankCard("flex", "Flex 5v5", d.rank?.flex));
}

function rankCard(cls, label, r) {
  const div = document.createElement("div");
  div.className = `rank-card ${cls}`;
  if (!r || !r.tier) {
    div.innerHTML = `
      <div class="emblem">–</div>
      <div><div class="q-label">${label}</div><div class="tier">Unranked</div></div>`;
    return div;
  }
  const games = (r.wins || 0) + (r.losses || 0);
  const wr = games ? Math.round((r.wins / games) * 100) : 0;
  const wrCls = wr >= 55 ? "good" : wr < 48 ? "bad" : "";
  const isApex = ["MASTER", "GRANDMASTER", "CHALLENGER"].includes(r.tier);
  div.innerHTML = `
    <div class="emblem">${TIER_SHORT[r.tier] || "?"}</div>
    <div>
      <div class="q-label">${label}</div>
      <div class="tier">${TIER_NAME[r.tier] || r.tier}${isApex ? "" : " " + (r.rank || "")}</div>
      <div class="lp">${r.lp} LP</div>
    </div>
    <div class="wl">
      <div class="wr ${wrCls}">${wr}%</div>
      <div class="games">${r.wins}V ${r.losses}D · ${games} partidas</div>
    </div>`;
  return div;
}

/* ---------- gráfica LP total (por índice de partida) ---------- */
function renderLpTotalChart(d) {
  const hist = (d.lpHistory && d.lpHistory[State.lpQueue]) || [];
  const canvas = document.getElementById("lpTotalChart");
  const color = State.lpQueue === "solo" ? "#4c8dff" : "#c084fc";

  if (lpTotalChart) lpTotalChart.destroy();

  if (!hist.length) {
    lpTotalChart = null;
    emptyCanvas(canvas, "Sin datos de LP para esta cola.");
    document.getElementById("lpTotalSub").textContent = "";
    return;
  }

  const labels = hist.map((_, i) => i + 1);
  const values = hist.map(h => h.lp);
  document.getElementById("lpTotalSub").textContent =
    `${hist.length} partidas ranked · ${lpToRankLabel(hist[0].lp)} → ${lpToRankLabel(hist[hist.length - 1].lp)}`;

  lpTotalChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [{
      label: "LP total", data: values, borderColor: color,
      backgroundColor: color + "22", fill: true, tension: .25,
      pointRadius: 0, pointHoverRadius: 5, borderWidth: 2,
    }] },
    options: baseLineOpts({
      yCallback: v => lpToRankLabel(v),
      titleFn: (items) => "Partida #" + items[0].label,
      labelFn: (ctx) => {
        const h = hist[ctx.dataIndex];
        const champ = h.champion ? " · " + h.champion : "";
        const res = h.win === true ? " · Victoria" : h.win === false ? " · Derrota" : "";
        return `${rankLabelFromHist(h)}${res}${champ}`;
      },
    }),
  });
}

/* ---------- gráfica LP por partida (últimas N) ---------- */
function renderLpGamesChart(d) {
  const canvas = document.getElementById("lpGamesChart");
  const hist = (d.lpHistory && d.lpHistory[State.lpQueue]) || [];
  const tail = hist.slice(-State.lpGamesN);

  if (lpGamesChart) lpGamesChart.destroy();

  if (!tail.length) {
    lpGamesChart = null;
    emptyCanvas(canvas, "Sin datos de LP para esta cola.");
    return;
  }

  const labels = tail.map((_, i) => "P" + (i + 1));
  const values = tail.map(h => h.lp);
  const segColors = tail.map(h => (h.win === true ? "#3fb27f" : h.win === false ? "#e05a5a" : "#8b98a5"));

  lpGamesChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [{
      label: "LP", data: values, borderColor: "#c8aa6e",
      backgroundColor: "#c8aa6e22", fill: true, tension: .25, borderWidth: 2,
      pointRadius: 4, pointHoverRadius: 6,
      pointBackgroundColor: segColors, pointBorderColor: segColors,
    }] },
    options: baseLineOpts({
      yCallback: v => lpToRankLabel(v),
      titleFn: (items) => items[0].label,
      labelFn: (ctx) => {
        const h = tail[ctx.dataIndex];
        const res = h.win === true ? "Victoria" : h.win === false ? "Derrota" : "—";
        const dlt = h.delta == null ? "" : ` (${h.delta > 0 ? "+" : ""}${h.delta} LP)`;
        const champ = h.champion ? " · " + h.champion : "";
        return `${rankLabelFromHist(h)} · ${res}${dlt}${champ}`;
      },
    }),
  });
}

function baseLineOpts({ yCallback, titleFn, labelFn }) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#0a0e13", borderColor: "#262f3a", borderWidth: 1,
        titleColor: "#e6edf3", bodyColor: "#e6edf3", padding: 10,
        callbacks: { title: titleFn, label: labelFn },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: "#8b98a5", maxTicksLimit: 10, autoSkip: true } },
      y: { grid: { color: "#1c232d" }, ticks: { color: "#8b98a5", callback: yCallback, maxTicksLimit: 6 } },
    },
  };
}

/* etiqueta de rango a partir de un punto del historial (usa su tier/rank exacto) */
function rankLabelFromHist(h) {
  const isApex = ["MASTER", "GRANDMASTER", "CHALLENGER"].includes(h.tier);
  return `${TIER_NAME[h.tier] || h.tier}${isApex ? "" : " " + h.rank} ${h.lpInDiv} LP`;
}

function emptyCanvas(canvas, msg) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#8b98a5";
  ctx.font = "13px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(msg, canvas.width / 2, canvas.height / 2);
}

/* Convierte LP absoluto → etiqueta de rango (Oro II 67) */
const TIERS = ["IRON","BRONZE","SILVER","GOLD","PLATINUM","EMERALD","DIAMOND"];
const DIV_LABEL = ["IV","III","II","I"];
function lpToRankLabel(abs) {
  abs = Math.max(0, Math.round(abs));
  const apexBase = TIERS.length * 400; // por encima de Diamante I
  if (abs >= apexBase) return "Maestro+ " + (abs - apexBase) + " LP";
  const ti = Math.min(TIERS.length - 1, Math.floor(abs / 400));
  const rem = abs - ti * 400;
  const div = Math.min(3, Math.floor(rem / 100));
  const lp = rem - div * 100;
  return `${TIER_NAME[TIERS[ti]]} ${DIV_LABEL[div]} ${lp}`;
}

/* ---------- historial ---------- */
function renderMatches(d) {
  const list = document.getElementById("matchList");
  let matches = d.matches || [];
  if (State.historyFilter !== "ALL")
    matches = matches.filter(m => m.queue === State.historyFilter);

  if (!matches.length) {
    list.innerHTML = `<div class="empty">Sin partidas para este filtro.</div>`;
    return;
  }

  const hasStats = matches.some(m => m.kda != null);
  const maxDmg = Math.max(...matches.map(m => m.damage || 0), 1);
  const note = !hasStats
    ? `<div class="seed-note">Mostrando cola, campeón, LP ganado/perdido y rango por partida (datos de u.gg).
       Los detalles (KDA, CS, oro, daño) aparecen al correr <code>fetch.py</code> con una API key válida.</div>`
    : "";
  list.innerHTML = note + matches.map(m => matchRow(m, maxDmg, hasStats)).join("");
}

function champImg(m) {
  const ver = State.meta.ddragonVersion || "16.16.1";
  return m.champion
    ? `<img src="https://ddragon.leagueoflegends.com/cdn/${ver}/img/champion/${m.champion}.png"
           alt="${m.champion}" loading="lazy"
           onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'noimg',textContent:'${m.champion.slice(0, 4)}'}))" />`
    : `<div class="noimg">?</div>`;
}

function resultClass(win) { return win === true ? "win" : win === false ? "loss" : "neutral"; }
function resultText(win) { return win === true ? "Victoria" : win === false ? "Derrota" : "—"; }
function queueName(q) { return q === "SOLO" ? "Solo/Duo" : q === "FLEX" ? "Flex" : q; }

/* LP por partida:
   - Si fetch.py ya calculó el LP real (m.lpReal, por diferencia de snapshots), se muestra ese.
   - Si no, se estima según el resultado real de Riot: +20 victoria / -20 derrota.
   - Sin V/D conocido (u.gg sin dato) se muestra el rango. */
const LP_PER_GAME = 20;
/* LP efectivo de una partida: real (por snapshots) si existe, si no ±20 según V/D.
   Devuelve null si no hay V/D conocido. */
function matchLp(m) {
  if (m.lpReal && m.lpChange != null) return m.lpChange;
  if (m.win === true) return LP_PER_GAME;
  if (m.win === false) return -LP_PER_GAME;
  return null;
}
function lpChangeBadge(m) {
  const c = matchLp(m);
  if (c == null) return `<span class="lp-chip neu">${m.rankLabel || ""}</span>`;
  const cls = c > 0 ? "pos" : c < 0 ? "neg" : "neu", sign = c > 0 ? "+" : "";
  const title = m.lpReal ? "LP real (Riot)" : "Estimado (~20 LP)";
  return `<span class="lp-chip ${cls}" title="${title}">${sign}${c} LP</span>`;
}

function matchRow(m, maxDmg, hasStats) {
  const res = resultClass(m.win);
  const champ = m.champion || "";

  // Fila compacta cuando aún no hay stats de la API (datos de u.gg)
  if (!hasStats || m.kda == null) {
    return `
    <div class="match compact ${res}">
      <div class="champ">${champImg(m)}</div>
      <div class="meta-col">
        <div class="result ${res}">${resultText(m.win)}</div>
        <div class="qq">${queueName(m.queue)} · ${champ}</div>
      </div>
      <div class="lp-col">${lpChangeBadge(m)}</div>
      <div class="rank-col"><span class="badge">${m.rankLabel || ""}</span></div>
    </div>`;
  }

  // Fila completa (enriquecida con la API)
  const kdaRatioCls = m.kda >= 3 ? "good" : "";
  const dmgPct = Math.round((m.damage / maxDmg) * 100);
  const dur = m.duration ? `${Math.floor(m.duration / 60)}:${String(m.duration % 60).padStart(2, "0")}` : "";
  return `
  <div class="match ${res}">
    <div class="champ">${champImg(m)}</div>
    <div class="meta-col">
      <div class="result ${res}">${resultText(m.win)}</div>
      <div class="qq">${queueName(m.queue)}${dur ? " · " + dur : ""}</div>
      <div class="ago">${lpChangeBadge(m)}</div>
    </div>
    <div class="kda-col">
      <div class="kda-nums">${m.kills} / <span class="d">${m.deaths}</span> / ${m.assists}</div>
      <div class="kda-ratio ${kdaRatioCls}">${m.kda.toFixed(2)} KDA · ${m.killParticipation ?? "–"}% KP</div>
      <span class="badge">${m.position || ""}</span>
    </div>
    <div class="stat">
      <div class="v">${m.cs} <small style="color:var(--muted)">(${m.csPerMin})</small></div>
      <div class="l">CS / min</div>
    </div>
    <div class="stat">
      <div class="v">${m.goldPerMin}</div>
      <div class="l">Oro / min</div>
    </div>
    <div class="stat">
      <div class="v">${m.visionScore ?? "–"}</div>
      <div class="l">Visión</div>
    </div>
    <div class="stat">
      <div class="v">${fmtK(m.damage)}</div>
      <div class="l">Daño (${m.damagePerMin}/m)</div>
      <div class="dmg-bar"><span style="width:${dmgPct}%"></span></div>
    </div>
  </div>`;
}

/* ---------- controles ---------- */
function wireControls() {
  document.querySelectorAll("#lpQueueSeg button").forEach(b => {
    b.onclick = () => {
      document.querySelectorAll("#lpQueueSeg button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      State.lpQueue = b.dataset.q;
      renderLpTotalChart(State.data[State.currentPlayer]);
      renderLpGamesChart(State.data[State.currentPlayer]); // el toggle controla ambas gráficas
    };
  });
  document.querySelectorAll("#lpGamesSeg button").forEach(b => {
    b.onclick = () => {
      document.querySelectorAll("#lpGamesSeg button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      State.lpGamesN = Number(b.dataset.n);
      renderLpGamesChart(State.data[State.currentPlayer]);
    };
  });
  document.querySelectorAll("#queueTabs button").forEach(b => {
    b.onclick = () => {
      document.querySelectorAll("#queueTabs button").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      State.historyFilter = b.dataset.f;
      renderMatches(State.data[State.currentPlayer]);
    };
  });
  document.getElementById("champSelect").onchange = (e) => {
    State.champSelected = e.target.value;
    const aggs = championAggregates(State.data[State.currentPlayer].matches || []);
    renderChampStats(aggs.find(a => a.champion === State.champSelected));
  };
  document.getElementById("refreshBtn").onclick = refreshData;
}

/* ---------- utils ---------- */
function fmtK(n) { return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n); }
function timeAgo(ts) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 3600) return Math.floor(s / 60) + " min";
  if (s < 86400) return Math.floor(s / 3600) + " h";
  return Math.floor(s / 86400) + " d";
}

boot();
