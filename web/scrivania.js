/* LA SCRIVANIA COME NEL MOCKUP (NIGHT 14 novembre 2026, «StratiField alla
 * scrivania» v7.2).
 *
 * Fino a stanotte la colonna di sinistra mescolava quattro cose diverse — la
 * navigazione (Detta, Unità, Mappa), le DEFINIZIONI di scheda come se fossero
 * luoghi (DAI, DEMO·UE, IAA, ICCD), «Dove scrivo / Le tue stanze» e i comandi
 * di vista. Alla scrivania ognuna va al suo posto:
 *
 *   barra        marchio · Scrivania / In campo · Detta · stato e salvataggio
 *                · lingua · chi firma · la stanza (un clic: la scelta)
 *   sezioni      Scheda · Unità (US) · Materiali · Foto · Scavo · Mappa
 *   striscia     nella Scheda: l'unità ‹ › e «Scheda», lingua, vista,
 *                facciate; nelle altre il titolo e l'azione principale
 *   colonna      «In questa stanza», e nient'altro
 *   ispettore    nella Scheda quello del Foglio; nelle altre «Altrove»
 *
 * IN CAMPO (telefono e tablet) NON CAMBIA: la colonna resta quella di prima,
 * con le sue voci. Qui si decide solo che cosa si vede alla scrivania, e i
 * nodi si SPOSTANO (come `placeControls`), non si copiano: un selettore in due
 * posti sono due stati.
 *
 * Questo modulo non parla al grafo: legge quello che il nodo ha già detto
 * (`room.units`, `/v1/room/choices`, `/v1/room/places`) e chiama la
 * conchiglia (`shell`) per aprire una scheda o una sezione. */

import { room } from "./widgets.js";
import { paint as paintPhotos } from "./photos.js";
import { openIn } from "./mappa.js";

const SG = () => window.SG || {};
const $ = (id) => document.getElementById(id);
const t = (k, v) => (SG().t ? SG().t(k, v) : k);

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(kid);
  return node;
}

/* ── i glifi delle sezioni: quelli del mockup (una prima passata di icone in
 *    linea sulla griglia 24, nello spirito del WP1) ───────────────────────── */
const IC = {
  sheet: '<path d="M4 4.5h7v15H4zM13 4.5h7v15h-7z"/><path d="M6 8h3M6 11h3M15 8h3M15 11h3M15 14h2"/>',
  units: '<path d="M3 7c3-1.6 6 1.2 9 0s6-1.4 9 0M3 12c3-1.4 6 1.4 9 0s6-1.2 9 .2M3 17c3-1.2 6 1.6 9 .2s6-1 9 0"/>',
  finds: '<path d="M5 16.5 9.5 5l6 2.2 3.5 7.3-5 4.5z"/><path d="M9.5 5 12 12l7 2.5M12 12l2 6.8"/>',
  photos: '<path d="M3.5 7.5h4l1.5-2h6l1.5 2h4v11h-17z"/><circle cx="12" cy="13" r="3.4"/>',
  excavation: '<path d="M3 8.5h18v10H3z"/><path d="M9 8.5v10M15 8.5v10M3 13.5h18"/><path d="M6 5.5l1.5 3M18 5.5l-1.5 3"/>',
  map: '<path d="M12 21s6-5.7 6-10.5a6 6 0 1 0-12 0C6 15.3 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.2"/>',
  voice: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  em: '<circle cx="6" cy="6" r="2.6"/><circle cx="18" cy="6" r="2.6"/><circle cx="12" cy="18" r="2.6"/><path d="M7.4 8.3 10.6 15.7M16.6 8.3 13.4 15.7"/>',
  hv: '<path d="M12 2.8 20 7v10l-8 4.2L4 17V7z M4 7l8 4.2L20 7M12 11.2v10"/>',
  pin: '<path d="M12 21s6-5.7 6-10.5a6 6 0 1 0-12 0C6 15.3 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.2"/>',
};
function glyph(name, size = 18) {
  const span = document.createElement("span");
  span.className = "dk-glyph";
  span.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${IC[name] || ""}</svg>`;
  return span;
}

/** LE SEZIONI, in ordine: chiave · stringa · pannello della conchiglia. */
export const SECTIONS = [
  ["sheet", "nav.sheet", "scheda"],
  ["units", "nav.units", "index"],
  ["finds", "nav.finds", "finds"],
  ["photos", "nav.photos", "photos-sec"],
  ["excavation", "nav.excavation", "excavation"],
  ["map", "nav.map", "map"],
];

/** Quale sezione corrisponde al pannello che la conchiglia ha davanti. */
export function sectionOf(panel) {
  const hit = SECTIONS.find(([, , p]) => p === panel);
  return hit ? hit[0] : null;
}

/* Ciò che la stanza ha, letto una volta per giro e tenuto qui: i conteggi
 * delle sezioni lo leggono. */
const known = { choices: null, places: null };

async function readJSON(path) {
  const seam = SG();
  if (!seam.request) return null;
  try {
    const answer = await seam.request(path, {});
    return answer.ok ? await answer.json() : null;
  } catch { return null; }
}

/** I REPERTI della stanza: le unità di tipo reperto (SF, VSF, RSF — i tipi
 *  `…SpecialFind…` del datamodel, che il nodo riporta in `node_type`). Una
 *  SCHEDA MATERIALI (ICCD RA, TMA) questo nodo non la serve: lo stato vuoto lo
 *  dice, e non se ne inventa una. */
export function findsOf(units) {
  return (units || []).filter((u) => ["SF", "VSF", "RSF"].includes(String(u.node_type || "")));
}

/** Le foto della stanza (da `/v1/room/choices`), con l'unità a cui sono
 *  legate se lo sono. */
function roomPhotos() {
  return ((known.choices && known.choices.photos) || []);
}

export function mount(shell) {
  const isDesk = () => shell.state.mode === "desktop";

  /* ── la barra: Scrivania / In campo, Detta ─────────────────────────────── */
  function paintBar() {
    const seg = $("posture-seg");
    if (seg) {
      seg.replaceChildren();
      seg.setAttribute("aria-label", t("mode.label"));
      seg.hidden = shell.state.mode === "phone";
      for (const [place, key] of [["desk", "mode.desk"], ["field", "mode.field"]]) {
        const b = el("button", { type: "button", text: t(key),
                                 "aria-pressed": String((place === "desk") === isDesk()) });
        b.dataset.place = place;
        b.addEventListener("click", () => shell.choosePlace(place));
        seg.append(b);
      }
    }
    const voice = $("bar-voice");
    if (voice) {
      voice.replaceChildren(glyph("voice", 16), el("span", { text: t("tab.dictate") }));
      voice.hidden = !isDesk();
      voice.setAttribute("aria-current", String(shell.state.panel === "voice"));
    }
  }

  /* ── le sezioni ────────────────────────────────────────────────────────── */
  function counts() {
    const units = room.units || [];
    return {
      sheet: "",
      units: room.read ? String(units.length) : "",
      finds: room.read ? String(findsOf(units).length) : "",
      photos: known.choices ? String(roomPhotos().length) : "",
      excavation: known.places ? String(known.places.length) : "",
      map: "",
    };
  }

  function paintTabs() {
    const bar = $("desk-tabs");
    if (!bar) return;
    bar.hidden = !isDesk();
    if (bar.hidden) return;
    const n = counts();
    const here = shell.state.panel === "voice" ? null : sectionOf(shell.state.panel);
    bar.replaceChildren(...SECTIONS.map(([key, label]) => {
      const b = el("button", { type: "button", "data-sec": key,
                               "aria-current": String(here === key) },
        glyph(key), el("span", { text: t(label) }),
        el("span", { class: "cnt", text: n[key] }));
      b.addEventListener("click", () => shell.showSection(key));
      return b;
    }));
  }

  /* ── la striscia, fuori dalla Scheda ───────────────────────────────────── */
  function paintStrip() {
    const strip = $("desk-strip");
    if (!strip) return;
    strip.hidden = !isDesk() || shell.state.panel === "voice";
    if (strip.hidden) return;
    const sec = sectionOf(shell.state.panel);
    const onSheet = sec === "sheet";
    strip.dataset.sec = sec || "";
    $("desk-strip-sheet").hidden = !onSheet;
    const box = $("desk-strip-sec");
    box.hidden = onSheet;
    if (onSheet) return;
    const where = SG().where ? SG().where() : null;
    const ctx = (where && where.room) || t("room.local");
    const action = {
      units: ["act.new_unit", () => shell.newUnit()],
      photos: ["act.add_photos", () => { const c = $("camera"); if (c) c.click(); }],
    }[sec];
    box.replaceChildren(
      el("div", { class: "unitname" },
        el("h1", { text: t(SECTIONS.find(([k]) => k === sec)?.[1] || "") }),
        el("span", { class: "ctx", text: ctx })),
      el("span", { class: "grow" }));
    if (action) {
      box.append(el("button", { type: "button", class: "primary", "data-act": action[0],
                                text: t(action[0]), onclick: action[1] }));
    } else if (sec === "excavation" || sec === "finds") {
      // L'AZIONE CHE NON C'È SI DICE, non si finge: «Nuova area» e «Nuova
      // scheda materiali» questo nodo non le sa fare ancora.
      const key = sec === "excavation" ? "act.new_area" : "act.new_find";
      const b = el("button", { type: "button", class: "primary", "data-act": key,
                               text: t(key), disabled: true,
                               title: t(sec === "excavation" ? "exc.cannot" : "finds.cannot") });
      box.append(b);
    }
  }

  /* ── la colonna: «In questa stanza» ────────────────────────────────────── */
  //: quante unità nella colonna: è l'elenco BREVE; l'elenco intero è Unità
  const INROOM = 12;
  function paintInRoom() {
    const box = $("nav-inroom-box");
    if (!box) return;
    box.hidden = !isDesk();
    if (box.hidden) return;
    const host = $("nav-inroom");
    const units = room.units || [];
    const listing = shell.listing();
    host.replaceChildren();
    if (!units.length) {
      host.append(el("p", { class: "hint", text: room.read ? t("index.empty") : "…" }));
      return;
    }
    // le più recenti in cima: quelle su cui si sta lavorando
    const recent = units.slice().sort((a, b) =>
      String(b.modified_at || "").localeCompare(String(a.modified_at || "")));
    for (const u of recent.slice(0, INROOM)) {
      const declared = u.scheda && u.scheda.template;
      const item = listing.find((x) => x.id === declared)
        || listing.find((x) => shell.state.def && x.id === shell.state.def.id)
        || listing[0];
      const total = item ? Number(item.fields) || 0 : 0;
      const current = shell.state.panel === "scheda"
        && ((u.number && u.number === shell.state.us) || (shell.state.nodeId === u.id));
      const b = el("button", { type: "button", class: "navitem", "data-unit": u.id,
                               "aria-current": String(Boolean(current)) },
        el("span", { text: u.number ? `${shell.prefix(u)}${u.number}` : (u.name || u.id) }),
        el("span", { class: "count", text: total ? `${u.fields || 0}/${total}` : String(u.fields || 0) }));
      b.addEventListener("click", () => shell.openUnit(u));
      host.append(b);
    }
  }

  /* ── l'ispettore, fuori dalla Scheda: «Altrove» ────────────────────────── */
  function elsewhere() {
    const where = SG().where ? SG().where() : null;
    const sec = el("section", { class: "fo-apri dk-elsewhere" },
      el("p", { class: "fo-eyebrow", text: t("insp.elsewhere") }));
    const roomName = where && where.room;
    const rows = [
      ["emstudio", "act.open_room_em", "em"],
      ["heriverse", "act.open_hv", "hv"],
      ["pyarchinit", "act.open_pyarchinit", "pin"],
    ];
    for (const [tool, key, ic] of rows) {
      const b = el("button", { type: "button", class: "dk-open", "data-open": tool },
        glyph(ic, 16), el("span", { text: t(key) }));
      // GLI STESSI DELLA MAPPA, STESSA LOGICA (`mappa.js::openIn`): EMStudio
      // vuole una stanza; Heriverse non ha ancora un indirizzo misurato;
      // PyArchInit apre un LUOGO o un'unità, quindi dalla Scheda o dalla mappa.
      if (tool === "emstudio" && roomName) {
        b.addEventListener("click", () => openIn("emstudio", null, null));
      } else {
        b.disabled = true;
        b.title = t(tool === "emstudio" ? "map.open_noroom"
                    : tool === "heriverse" ? "map.heriverse_none" : "insp.open_pick");
      }
      sec.append(b);
    }
    return sec;
  }

  function paintInspector() {
    const insp = $("desk-insp");
    if (!insp) return;
    insp.hidden = !isDesk() || shell.state.panel === "voice";
    if (insp.hidden) return;
    if (sectionOf(shell.state.panel) === "sheet") return;   // lo dipinge il Foglio
    insp.replaceChildren(elsewhere());
  }

  /* ── i tre pannelli nuovi ──────────────────────────────────────────────── */
  async function paintFinds() {
    const host = $("finds");
    const finds = findsOf(room.units);
    const wrap = el("div", { class: "sheetwrap" });
    if (!finds.length) {
      wrap.append(el("div", { class: "dk-empty" },
        glyph("finds", 28),
        el("h2", { text: t("finds.none") }),
        el("p", { text: t("finds.none_note") })));
    } else {
      const rows = finds.map((u) => el("tr", { "data-unit": u.id, onclick: () => shell.openUnit(u) },
        el("td", { class: "id", text: u.number ? `${shell.prefix(u)}${u.number}` : (u.name || u.id) }),
        el("td", { text: u.node_type }),
        el("td", { text: u.definition || u.description || "" }),
        el("td", { text: (u.area || []).join(", ") })));
      wrap.append(el("div", { class: "scroller" }, el("table", { class: "tbl" },
        el("thead", {}, el("tr", {},
          el("th", { text: t("col.unit") }), el("th", { text: t("col.class") }),
          el("th", { text: t("col.definition") }), el("th", { text: t("col.area") }))),
        el("tbody", {}, ...rows))));
    }
    host.replaceChildren(wrap);
  }

  //: il filtro delle foto (Tutte · US n · non legate), che resta fra un giro e l'altro
  let photoFilter = "all";
  async function paintPhotoSection() {
    const host = $("photos-sec");
    known.choices = (await readJSON("/v1/room/choices")) || known.choices;
    const wrap = el("div", { class: "sheetwrap" });
    // 1 · QUELLE DI QUESTO DISPOSITIVO, che aspettano: ciò che fa `photos.js`
    const waiting = el("div", { class: "waiting dk-waiting" });
    wrap.append(waiting);
    try { await paintPhotos(waiting, SG(), { proposeUs: () => shell.state.us || "" }); }
    catch { /* nessun archivio sul dispositivo */ }
    // 2 · QUELLE DELLA STANZA, legate a un'unità o no
    const photos = roomPhotos();
    const unitName = (id) => {
      const u = (room.units || []).find((x) => x.id === id);
      return u ? (u.number ? `${shell.prefix(u)}${u.number}` : (u.name || u.id)) : "";
    };
    const linkedTo = [...new Set(photos.map((p) => p.unit).filter(Boolean))];
    const bar = el("div", { class: "filters" });
    const chip = (value, text) => {
      const b = el("button", { type: "button", class: "indice-chip", "data-pf": value,
                               "aria-pressed": String(photoFilter === value), text });
      b.addEventListener("click", () => { photoFilter = value; void paintPhotoSection(); });
      bar.append(b);
    };
    chip("all", t("photos.all"));
    // un nodo che l'elenco non tiene (un documento importato come US): la coda
    // dell'id, non un uuid intero che riempie la riga
    for (const id of linkedTo) chip(id, unitName(id) || `…${id.slice(-6)}`);
    chip("none", t("photos.unlinked"));
    wrap.append(bar);
    const shown = photos.filter((p) => photoFilter === "all"
      || (photoFilter === "none" ? !p.unit : p.unit === photoFilter));
    if (!photos.length) {
      wrap.append(el("div", { class: "dk-empty" }, glyph("photos", 28),
        el("h2", { text: t("photos.none") }), el("p", { text: t("photos.none_note") })));
    } else {
      wrap.append(el("div", { class: "pgrid" }, ...shown.map((p) => el("div",
        { class: "ph" + (p.unit ? "" : " nolink"), title: p.url },
        el("div", { class: "img" }, el("span", { text: (p.name.split(".").pop() || "").toUpperCase() })),
        el("div", { class: "cap" }, el("span", { text: p.name }),
          el("span", { text: p.unit ? (unitName(p.unit) || `…${p.unit.slice(-6)}`) : "—" }))))));
    }
    host.replaceChildren(wrap);
    paintTabs();
  }

  async function paintExcavation() {
    const host = $("excavation");
    const read = await readJSON("/v1/room/places");
    known.places = read ? read.places || [] : known.places;
    const places = known.places || [];
    const wrap = el("div", { class: "sheetwrap" });
    if (!places.length) {
      wrap.append(el("div", { class: "dk-empty" }, glyph("excavation", 28),
        el("h2", { text: t("exc.none") }), el("p", { text: t("exc.cannot") })));
      host.replaceChildren(wrap);
      paintTabs();
      return;
    }
    const kids = new Map();
    for (const p of places) {
      const key = p.parent || "";
      if (!kids.has(key)) kids.set(key, []);
      kids.get(key).push(p);
    }
    const LV = { sito: "lvl.site", area: "lvl.area", saggio: "lvl.trench",
                 settore: "lvl.sector", quadrato: "lvl.square" };
    const branch = (parent, depth) => {
      const list = (kids.get(parent) || []).slice()
        .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      if (!list.length) return null;
      const ul = el("ul", { class: depth ? "" : "tree" });
      for (const p of list) {
        const row = el("button", { type: "button", class: "node", "data-place": p.id },
          el("span", { class: "lv", text: t(LV[p.level] || "lvl.place") }),
          el("span", { class: "nm", text: p.name }),
          el("span", { class: "cnt", text: p.units ? t("exc.units", { n: p.units }) : "" }));
        // UN LUOGO APRE L'ELENCO FILTRATO su di lui, come un saggio della mappa
        row.addEventListener("click", () => shell.unitsIn(p));
        ul.append(el("li", {}, row, branch(p.id, depth + 1)));
      }
      return ul;
    };
    // i luoghi funzionali (ambienti) non hanno un genitore: in fondo, a parte
    wrap.append(el("p", { class: "hint", text: t("exc.read_only") }), branch("", 0));
    host.replaceChildren(wrap);
    paintTabs();
  }

  async function paintPanel(panel) {
    if (panel === "finds") return paintFinds();
    if (panel === "photos-sec") return paintPhotoSection();
    if (panel === "excavation") return paintExcavation();
    return null;
  }

  /** Tutto ciò che dipende dalla sezione davanti e dal modo. */
  function paint() {
    paintBar();
    paintTabs();
    paintStrip();
    paintInRoom();
    paintInspector();
  }

  // i conteggi di Foto e Scavo, una volta all'avvio (e a ogni Foto/Scavo aperti)
  async function warm() {
    const [c, p] = await Promise.all([readJSON("/v1/room/choices"), readJSON("/v1/room/places")]);
    if (c) known.choices = c;
    if (p) known.places = p.places || [];
    paintTabs();
  }

  return { paint, paintPanel, paintTabs, paintInRoom, warm, known };
}
