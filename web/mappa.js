/* LA MAPPA DELLA STANZA — i luoghi e i tagli, con la loro impronta.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * NIGHT «impronte di saggi e tagli» (E.D., 11 novembre 2026; disegno: il
 * mockup «StratiField alla scrivania» v7.2, sezione Mappa).
 *
 * NIENTE US POSITIVE. Si vedono i LUOGHI — sito, aree, saggi — con l'impronta
 * che sta nel grafo; i TAGLI (le US negative) come livello facoltativo, SPENTO
 * all'inizio; la posizione di chi guarda; una base di contesto scelta da un
 * catalogo con la sua licenza. Il rilievo, le piante e le ortofoto restano a
 * PyArchInit ed EMStudio: questa pagina li APRE, non li rifà.
 *
 * LE IMPRONTE SI LEGGONO, non si ricalcolano: arrivano dal nodo
 * (`GET /v1/room/map`), lette dal grafo, già in lon/lat accanto al loro CRS. Qui
 * si portano in Web Mercator — il piano dei tasselli — e basta. E restano SUL
 * DISPOSITIVO come il resto della stanza: l'ultima lettura sta in
 * `localStorage`, così senza rete la mappa delle impronte c'è, e la didascalia
 * dice che è la copia.
 *
 * Zero colori letterali: tutto dalle variabili del tema.
 */

import { room } from "./widgets.js";

const $ = (id) => document.getElementById(id);
const SG = () => window.SG || {};
const t = (k, v) => (SG().t ? SG().t(k, v) : k);

const R = 6378137;
const merc = ([lon, lat]) => {
  const x = R * lon * Math.PI / 180;
  const y = R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2));
  return [x, y];
};

/** Il livello del datamodel (la colonna di PyArchInit) → la chiave delle
 *  parole, quella che l'xlsx dei partner ha già (`lvl.site`, `lvl.trench`…). */
const LVL = { sito: "site", area: "area", settore: "sector", saggio: "trench", quadrato: "square" };
const lvlWord = (lvl) => t("lvl." + (LVL[lvl] || "place"));

/** I livelli, con il loro stato. I tagli SPENTI all'inizio (E.D.). */
export const layers = { places: true, cuts: false, base: true, me: true };
const BASE_KEY = "sg.map.base";
const CACHE_KEY = (room) => `sg.map.v1.${room || "local"}`;

let me = null;            // {lon, lat, acc}
let last = null;          // l'ultima lettura (dal nodo o dalla cache)

function el(tag, attrs = {}, ...kids) {
  const ns = ["svg", "g", "polygon", "image", "text", "circle", "title", "rect", "clipPath"]
    .includes(tag) ? "http://www.w3.org/2000/svg" : null;
  const n = ns ? document.createElementNS(ns, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}

/** La lettura: dal nodo, e in cache; senza nodo, la cache. */
export async function readMap() {
  const seam = SG();
  const room = (seam.where && seam.where() && seam.where().room) || "";
  try {
    const answer = await seam.request("/v1/room/map", {});
    if (answer.ok) {
      const body = await answer.json();
      body.from = "node";
      body.read_at = new Date().toISOString();
      try { localStorage.setItem(CACHE_KEY(body.room || room), JSON.stringify(body)); }
      catch { /* pieno: si disegna lo stesso */ }
      last = body;
      return body;
    }
    if (answer.status === 403) {
      const said = await answer.json().catch(() => ({}));
      return { refused: said.detail || t("index.unreachable") };
    }
  } catch { /* nessun nodo: la copia */ }
  try {
    const kept = JSON.parse(localStorage.getItem(CACHE_KEY(room)) || "null");
    if (kept) { kept.from = "cache"; last = kept; return kept; }
  } catch { /* niente */ }
  return { refused: t("index.unreachable") };
}

/** La base scelta, o quella che il catalogo propone. */
function baseOf(m) {
  const bases = m.bases || [];
  let want = null;
  try { want = localStorage.getItem(BASE_KEY); } catch { /* */ }
  return bases.find((b) => b.id === want) || bases.find((b) => b.offline) || bases[0] || null;
}

/** Tutti i vertici che si disegnano, nel piano della vista. */
function frame(m) {
  const projected = m.projected;
  const pts = [];
  const shapes = [];
  const add = (list, kind) => {
    for (const p of list) {
      if (!p.has_footprint) continue;
      const src = projected ? p.lonlat : p.rings;
      if (!src) continue;
      const rings = src.map((poly) => poly.map((ring) => ring.map(
        (v) => (projected ? merc(v) : [v[0], v[1]]))));
      rings.flat(2).forEach((v) => pts.push(v));
      shapes.push({ p, kind, rings });
    }
  };
  add(m.places || [], "place");
  add(m.cuts || [], "cut");
  if (!pts.length) return null;
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  let pad = Math.max(x1 - x0, y1 - y0) * 0.12 || 10;
  // UN MINIMO DI CONTESTO: uno scavo di 14 m non dice dove sta
  const span = Math.max(x1 - x0, y1 - y0) + 2 * pad;
  if (span < MIN_SPAN) pad += (MIN_SPAN - span) / 2;
  const box = [x0 - pad, y0 - pad, x1 + pad, y1 + pad];
  // L'ORIGINE LOCALE: in Web Mercator le coordinate sono milioni di metri, e
  // il browser disegna in float a 32 bit — misurato il 12 novembre, i nomi
  // dei saggi (corpo 2 m a 5·10⁶ m dall'origine) sparivano. Tutto si disegna
  // rispetto all'angolo in alto a sinistra del riquadro.
  const at = ([x, y]) => [x - box[0], box[3] - y];
  return { shapes, box, projected, at };
}

//: il lato minimo della vista, in unità del CRS (metri)
const MIN_SPAN = 40;

const pointsOf = (ring, at) => ring.map((v) => at(v).map((n) => n.toFixed(3)).join(",")).join(" ");

/** I tasselli che coprono il riquadro, alla risoluzione dello schermo. */
function tiles(box, widthPx, base) {
  const world = 2 * Math.PI * R;
  const w = box[2] - box[0];
  let z = Math.round(Math.log2((world * widthPx) / (256 * w)));
  z = Math.max(base.minZoom || 0, Math.min(base.maxZoom || 19, z));
  const n = 2 ** z;
  const size = world / n;
  const tx = (x) => Math.floor((x + world / 2) / size);
  const ty = (y) => Math.floor((world / 2 - y) / size);
  const out = [];
  for (let x = tx(box[0]); x <= tx(box[2]); x++) {
    for (let y = ty(box[3]); y <= ty(box[1]); y++) {
      if (x < 0 || y < 0 || x >= n || y >= n) continue;
      out.push({ z, x, y, X: -world / 2 + x * size, Y: world / 2 - y * size, size });
    }
  }
  return out.length > 64 ? [] : out;       // mai una pioggia di richieste
}

function tileUrl(base, tl) {
  // `k=1` dice al service worker che questa fonte si può tenere sul
  // dispositivo (`offline: true` nel catalogo); OSM no — la policy lo vieta.
  return `${SG().node || ""}/v1/tiles/${encodeURIComponent(base.id)}/${tl.z}/${tl.x}/${tl.y}`
    + `.${base.format || "png"}${base.offline ? "?k=1" : ""}`;
}

/** Disegna la mappa in `host`. `onPlace(place)` apre l'elenco filtrato. */
export async function paintMap(host, { onPlace, onOpen } = {}) {
  if (!host) return;
  host.replaceChildren(el("p", { class: "hint", text: t("map.reading") }));
  const m = await readMap();
  host.replaceChildren();
  if (m.refused) { host.append(el("p", { class: "hint", text: m.refused })); return; }
  draw(host, m, { onPlace, onOpen });
}

function draw(host, m, { onPlace, onOpen }) {
  host.replaceChildren();
  const base = baseOf(m);
  const f = frame(m);
  const online = m.from === "node" && navigator.onLine !== false;

  // ── i livelli ──
  const bar = el("div", { class: "mappa-livelli", role: "group", "aria-label": t("map.layers") });
  bar.append(el("span", { class: "eyebrow", text: t("map.layers") }));
  for (const [k, label] of [["places", "map.l.places"], ["cuts", "map.l.cuts"],
                            ["base", "map.l.base"], ["me", "map.l.me"]]) {
    const b = el("button", { type: "button", class: "indice-chip", "data-layer": k,
                             "aria-pressed": String(layers[k]), text: t(label) });
    b.addEventListener("click", () => { layers[k] = !layers[k]; draw(host, m, { onPlace, onOpen }); });
    bar.append(b);
  }
  if ((m.bases || []).length) {
    const sel = el("select", { id: "map-base", "aria-label": t("map.l.base") });
    for (const b of m.bases) {
      sel.append(el("option", { value: b.id, selected: base && b.id === base.id,
                                text: b.label + (b.offline ? "" : " · " + t("map.online_only")) }));
    }
    sel.addEventListener("change", () => {
      try { localStorage.setItem(BASE_KEY, sel.value); } catch { /* */ }
      draw(host, m, { onPlace, onOpen });
    });
    bar.append(el("label", { class: "mappa-base", text: t("map.l.base") + " " }, sel));
  }
  host.append(bar);

  // ── la tavola ──
  const box = el("div", { class: "mappa-tavola" });
  host.append(box);
  if (!f) {
    box.append(el("p", { class: "hint", text: t("map.none") }));
  } else {
    const [x0, y0, x1, y1] = f.box;
    const W = Math.max(320, Math.min(host.clientWidth || 720, 1100));
    const at = f.at;
    const svg = el("svg", { viewBox: `0 0 ${(x1 - x0).toFixed(3)} ${(y1 - y0).toFixed(3)}`, role: "img",
                            "aria-label": t("map.title"), preserveAspectRatio: "xMidYMid meet",
                            class: "mappa-svg", id: "map-svg" });
    const baseOn = layers.base && base && f.projected;
    if (baseOn) {
      const g = el("g", { class: "mappa-base-tiles" });
      for (const tl of tiles(f.box, W, base)) {
        const [ix, iy] = at([tl.X, tl.Y]);
        g.append(el("image", { href: tileUrl(base, tl), x: ix, y: iy,
                               width: tl.size, height: tl.size, preserveAspectRatio: "none" }));
      }
      svg.append(g);
    }
    // i luoghi: prima il sito, poi aree e saggi sopra
    if (layers.places) {
      for (const s of f.shapes.filter((x) => x.kind === "place")) {
        const lvl = s.p.level || "";
        const g = el("g", { class: `mappa-luogo mappa-${lvl || "luogo"}`, "data-place": s.p.id,
                            "data-level": lvl, tabindex: lvl === "sito" ? null : "0",
                            role: lvl === "sito" ? null : "button",
                            "aria-label": `${s.p.name} · ${lvlWord(lvl)}` });
        g.append(el("title", { text: `${s.p.name} · ${lvlWord(lvl)} · ${s.p.crs || ""}` }));
        for (const poly of s.rings) for (const ring of poly) g.append(el("polygon", { points: pointsOf(ring, at) }));
        if (lvl !== "sito") {
          const go = () => onPlace && onPlace(s.p, (m.units_by_place || {})[s.p.id] || []);
          g.addEventListener("click", go);
          g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
        }
        svg.append(g);
        const top = at(s.rings[0][0].reduce((a, v) => (v[1] > a[1] ? v : a)));
        const fs = (x1 - x0) / 45;
        svg.append(el("text", { class: "mappa-nome", x: top[0], y: top[1] - fs * 0.4,
                                "font-size": fs.toFixed(2), text: s.p.name }));
      }
    }
    if (layers.cuts) {
      for (const s of f.shapes.filter((x) => x.kind === "cut")) {
        const g = el("g", { class: "mappa-taglio", "data-cut": s.p.id });
        g.append(el("title", { text: `${s.p.name} · ${t("map.cut")}` }));
        for (const poly of s.rings) for (const ring of poly) g.append(el("polygon", { points: pointsOf(ring, at) }));
        svg.append(g);
      }
    }
    if (layers.me && me && f.projected) {
      const [mx, my] = at(merc([me.lon, me.lat]));
      const r = Math.max(me.acc || 4, (x1 - x0) / 120);
      svg.append(el("g", { class: "mappa-io" },
        el("circle", { cx: mx, cy: my, r }), el("circle", { cx: mx, cy: my, r: r / 3 }),
        el("title", { text: `${t("map.l.me")} · ±${Math.round(me.acc || 0)} m` })));
    }
    box.append(svg);
  }

  // ── la didascalia ──
  const bits = [];
  if (f && !f.projected) bits.push(t("map.native", { crs: m.crs || "?" }));
  else if (layers.base && base) bits.push(base.attribution + (online ? "" : " · " + t("map.base_cache")));
  else bits.push(t("map.base_off"));
  bits.push(m.from === "cache" ? t("map.footprints_cached") : t("map.footprints"));
  if (m.crs) bits.push(m.crs);
  host.append(el("p", { class: "mappa-didascalia", id: "map-caption", text: bits.join(" · ") }));

  // ── i luoghi senza impronta, e «Dove sono» ──
  const missing = (m.places || []).filter((p) => !p.has_footprint && p.level);
  if (missing.length) {
    host.append(el("p", { class: "hint", text: t("map.no_footprint",
      { list: missing.map((p) => p.name).join(", ") }) }));
  }
  const where = el("button", { type: "button", id: "map-where", class: "indice-chip", text: t("map.where") });
  where.addEventListener("click", () => {
    navigator.geolocation?.getCurrentPosition((pos) => {
      me = { lon: pos.coords.longitude, lat: pos.coords.latitude, acc: pos.coords.accuracy };
      layers.me = true;
      draw(host, m, { onPlace, onOpen });
    }, () => SG().show && SG().show(false, t("map.where_no")), { enableHighAccuracy: true, timeout: 8000 });
  });

  // ── «Apri in…» ──
  const open = el("div", { class: "mappa-apri" }, where);
  const target = (m.places || []).find((p) => p.level === "sito") || (m.places || [])[0];
  for (const [tool, label] of [["pyarchinit", "act.open_pyarchinit"], ["emstudio", "act.open_room_em"],
                               ["heriverse", "act.open_hv"]]) {
    const b = el("button", { type: "button", class: "indice-chip", "data-open": tool, text: t(label) });
    if (tool === "heriverse") {
      b.disabled = true;
      b.title = t("map.heriverse_none");
    } else {
      b.addEventListener("click", () => onOpen && onOpen(tool, target, m));
    }
    open.append(b);
  }
  open.append(el("span", { class: "hint", text: t("map.gis_note") }));
  host.append(open);
  host.append(el("p", { class: "hint", text: t("map.pick_place") }));
}

/** I comandi «Apri in…», uguali dalla mappa e dall'ispettore. */
export async function openIn(tool, node, m) {
  const seam = SG();
  const server = (m && m.server) || (seam.where && seam.where() && seam.where().server) || "";
  const room = (m && m.room) || (seam.where && seam.where() && seam.where().room) || "";
  if (tool === "emstudio") {
    // il contratto del server (`stratigraph://open`), con `node` (EMStudio
    // handoff.ts E4): il luogo selezionato all'arrivo. Un posto, mai un permesso.
    if (!server || !room) { seam.show && seam.show(false, t("map.open_noroom")); return; }
    const q = new URLSearchParams({ server, room });
    if (node && node.id) q.set("node", node.id);
    window.location.href = `stratigraph://open?${q.toString()}`;
    return;
  }
  if (tool === "pyarchinit") {
    if (!node || !node.id) return;
    try {
      const answer = await seam.request(`/v1/room/map/pyarchinit/${encodeURIComponent(node.id)}`, {});
      if (!answer.ok) throw new Error(String(answer.status));
      const blob = await answer.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `pyarchinit-open-${(node.name || node.id).replace(/[^\w.-]/g, "_")}.json`;
      document.body.append(a);
      a.click();
      a.remove();
      seam.show && seam.show(true, t("map.pyarchinit_file"));
    } catch {
      seam.show && seam.show(false, t("index.unreachable"));
    }
  }
}

export const lastMap = () => last;

/** «APRI IN…» NELL'ISPETTORE della scheda (12 novembre), accanto a quello
 *  della mappa e con gli stessi comandi: l'unità di questa scheda, se la
 *  stanza la ha già. PyArchInit dà il file di scambio, EMStudio il link della
 *  stanza con il nodo; Heriverse non ha ancora un indirizzo misurato. Qui e
 *  non in `foglio.js`: il foglio non nomina niente di uno standard, nemmeno il
 *  numero dell'unità (`tests/test_il_foglio.py`). */
export function openSection(state, mk, tr) {
  const number = state && state.us ? String(state.us) : "";
  const unit = (room.units || []).find((u) => number && u.number === number);
  // «ALTROVE» (14 novembre, mockup v7.2): EMStudio · Heriverse · PyArchInit,
  // nell'ordine del mockup e con la logica di sempre
  const sec = mk("section", { class: "fo-apri" },
    mk("p", { class: "fo-eyebrow", text: tr("insp.elsewhere") }));
  for (const [tool, key] of [["emstudio", "act.open_em_unit"],
                             ["heriverse", "act.open_hv"],
                             ["pyarchinit", "act.open_pyarchinit"]]) {
    const b = mk("button", { type: "button", class: "indice-chip", "data-open": tool,
                             text: tr(key) });
    if (tool === "heriverse" || !unit) {
      b.disabled = true;
      b.title = tr(tool === "heriverse" ? "map.heriverse_none" : "insp.open_unsaved");
    } else {
      b.addEventListener("click", () => openIn(tool, { id: unit.id, name: unit.name }, last));
    }
    sec.append(b);
  }
  return sec;
}
