/* Il Foglio — la scheda compilata SUL FOGLIO, le due facciate dell'A4.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * PERCHÉ ESISTE, E PERCHÉ NON È UNA SECONDA SCHEDA
 *
 * Deciso con E.D. il 27 settembre su mockup: alla scrivania (soglie tablet e
 * desktop, mai il telefono) la scheda si compila sulla carta. È skeuomorfismo
 * voluto: un archeologo sa dove sta ogni casella della sua scheda, e il layout
 * della stampa è anche quello dell'ingestione.
 *
 * NON è una seconda implementazione dello standard, e questa è la riga che lo
 * tiene vero: **la griglia viene dal dato**. `def.sheet` è la geometria che la
 * definizione già dichiara (`stratigraph-templates/SPEC.md` §4) — righe in mm,
 * celle in % della riga, blocchi annidati — e il servizio la spedisce così com'è
 * (`Scheda._sheet_for_browser`). Qui non c'è una sola misura di una scheda
 * scritta a mano, non un'etichetta, non il nome di un campo o di uno standard:
 * `tests/test_il_foglio.py` lo sorveglia sul sorgente.
 *
 * E non è un secondo record: le caselle scrivono con `writeValue`, la stessa
 * via della vista «Campi», nello stesso `state.values`, e si salva con lo
 * stesso `save()`. Le due viste sono due modi di guardare la stessa scheda.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * UN RENDERER, TRE OPZIONI — E NESSUNA POSTAZIONE QUI DENTRO
 *
 * Lo stesso foglio serve la scrivania (fronte e retro affiancati, il glifo
 * sull'angolo) e il tablet in campo (una facciata per volta, i campi non da
 * trincea attenuati). La differenza sta in TRE opzioni, e il disegno legge solo
 * quelle:
 *
 *     sides        "both" | "recto" | "verso"   quali facciate
 *     corner       true | false                 il glifo sull'angolo
 *     trenchFocus  true | false                 attenuare i campi non da trincea
 *
 * Da quale postura vengono lo decide `optionsFor`, che è pura e sta FUORI dal
 * disegno. Un `if (postura)` dentro `drawSheet` sarebbe due renderer nello
 * stesso file, e il giorno che uno cambia l'altro non lo sa.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * UNA SCALA SOLA
 *
 * `--mm` è quanti pixel vale un millimetro, e tutto il CSS del foglio è scritto
 * in `calc(var(--mm) * N)`. Le misure della definizione restano in mm e non si
 * convertono mai a mano: la sola conversione è quella variabile, calcolata
 * dalla larghezza del piano (`scaleFor`). Sotto la scala minima il piano scorre
 * in orizzontale invece di impilare, perché fronte e retro stanno SEMPRE
 * affiancati — sulla carta non vanno a capo.
 *
 * Puro al caricamento: nessun `document` al primo livello, così le funzioni
 * che si possono sbagliare in silenzio (la scala, le opzioni, chi è attenuato)
 * si interrogano con node, come `thumbbarPlan`.
 */

import { authorshipOf, isFilled, shown as asText, writeValue } from "./scheda.js";
import { isStructured, mountWidget, valueView } from "./widgets.js";

const SG = () => (typeof window !== "undefined" && window.SG) || {};
const tr = (key, values) => (SG().t ? SG().t(key, values) : key);

/* ── le misure, in un posto ────────────────────────────────────────────────
 *
 * Quelle del mockup approvato, non inventate: il foglio A4 (210 × 297), lo
 * spazio fra le due facciate, la scala minima della vista d'insieme (0,95 px per
 * mm: sotto, le etichette smettono di leggersi e si scorre), e la facciata
 * espansa, che si allarga fino a ~1000 px e non meno di 1,25 px per mm. */
export const PAGE_W_MM = 210;
export const PAGE_H_MM = 297;
export const GAP_PX = 22;
export const MIN_SCALE_BOTH = 0.95;
export const MIN_SCALE_ONE = 1.25;
export const MAX_ONE_PX = 1000;

export const hasSheet = (def) =>
  Boolean(def && def.sheet && (def.sheet.sides || []).length);

/** Px per mm, dalla larghezza del piano e da quante facciate ci stanno. */
export function scaleFor(width, count) {
  const w = Math.max(0, Number(width) || 0);
  if (count >= 2) {
    return Math.max((w - GAP_PX * (count - 1)) / count / PAGE_W_MM,
                    MIN_SCALE_BOTH);
  }
  return Math.max(Math.min(w, MAX_ONE_PX) / PAGE_W_MM, MIN_SCALE_ONE);
}

/** DALLA POSTURA ALLE TRE OPZIONI — l'unico posto dove la postura conta.
 *
 *  `desk`  (sessione tenuta, spec §4 bis): le facciate che ha scelto chi
 *          scrive, il glifo, nessuna attenuazione.
 *  `field` (il corrispondente REST): una facciata per volta, niente glifo —
 *          non c'è una vista d'insieme verso cui tornare — e «Solo i campi da
 *          trincea» acceso finché qualcuno non lo spegne. */
export function optionsFor(posture, choice = {}) {
  if (posture === "field") {
    return {
      sides: choice.side === "verso" ? "verso" : "recto",
      corner: false,
      trenchFocus: choice.trenchOnly !== false,
    };
  }
  return {
    sides: ["recto", "verso"].includes(choice.faces) ? choice.faces : "both",
    corner: true,
    trenchFocus: false,
  };
}

/** Le facciate da disegnare. Una definizione che ha solo il fronte e a cui si
 *  chiede il retro mostra quello che ha, invece di un piano vuoto. */
export function sidesShown(sheet, sides) {
  const all = (sheet && sheet.sides) || [];
  if (sides === "both") return all;
  const one = all.filter((s) => s.id === sides);
  return one.length ? one : all.slice(0, 1);
}

/** ATTENUATO, NON DISABILITATO: si può ancora scrivere, perché capita di avere
 *  il dato in mano. Un campo senza marcatore non è da trincea (SPEC §1.6), e
 *  quindi con il fuoco sulla trincea si attenua anche lui. */
export const isDimmed = (field, opts) =>
  Boolean(opts && opts.trenchFocus) && field.recorded_in !== "trench";

/** I campi che una facciata ha, nell'ordine della griglia. */
export function fieldsOn(side) {
  const out = [];
  const walk = (rows) => {
    for (const row of rows || []) {
      for (const cell of row.cells || []) {
        if (cell.rows) walk(cell.rows);
        else if (cell.field) out.push(cell.field);
      }
    }
  };
  walk(side && side.rows);
  return out;
}

/** La chiave umana dell'intestazione corrente, dal PATTERN della definizione
 *  (`identity.human_key.pattern`): i campi vuoti diventano «…», non spariscono,
 *  così si vede che cosa manca a dire di quale unità è il foglio. */
export function headKey(pattern, values) {
  if (!pattern) return "";
  return String(pattern).replace(/\{(\w+)\}/g, (_m, name) => {
    const v = values ? values[name] : undefined;
    return isFilled(v) ? asText(v).trim() : "…";
  });
}

/* ── che cosa si disegna per tipo (spec §4) ────────────────────────────────
 *
 * LA SOLA DECISIONE DI PRESENTAZIONE, come `ELEMENT` in `scheda.js`: quale
 * elemento per quale tipo. I tipi che non sono qui prendono un'area di testo,
 * che è il ripiego onesto. I valori STRUTTURATI (termini, liste, misure,
 * persone, periodi) dal 22 ottobre hanno il loro widget (`widgets.js`): la
 * casella ne mostra il risultato, il pannello a destra lo scrive. */
const CONTROL = {
  choice: "checks",
  checkbox: "checkbox",
  integer: "number",
  decimal: "number",
  date: "date",
  identifier: "line",
  longtext: "multiline",
};
// Una riga sola: `text` va a capo quando è lungo (la casella cresce), ma
// Invio non vi scrive un a-capo — è un campo di una riga.
const ONE_LINE = new Set(["text", "term", "person_ref",
                          "actor_ref", "epoch_ref", "activity_ref"]);

/* I due glifi dell'angolo: quattro frecce verso fuori (ingrandisci) e verso
 * dentro (torna). Tracciati di linea su una griglia di 24, dal mockup. */
const GLYPH = {
  expand: "M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7",
  collapse: "M20 10h-6V4M14 10l6-6M4 14h6v6M10 14l-6 6",
};

const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids) if (kid) node.append(kid);
  return node;
};

function glyph(name) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", GLYPH[name]);
  svg.append(path);
  return svg;
}

/** Un'area di testo che cresce con quello che contiene: la riga sotto scende,
 *  come la stampa, che non taglia mai ciò che qualcuno ha scritto. */
function grow(pad) {
  pad.style.height = "auto";
  pad.style.height = `${pad.scrollHeight}px`;
}

/* ── il foglio ─────────────────────────────────────────────────────────────── */

/* Il piano si ri-misura quando cambia larghezza (finestra, colonna, pannello):
 * UN osservatore alla volta, staccato al disegno successivo. */
let watching = null;

export function drawSheet(host, def, state, opts) {
  if (watching) { watching.disconnect(); watching = null; }
  host.replaceChildren();
  const byId = new Map((def.fields || []).map((f) => [f.id, f]));
  const shown = sidesShown(def.sheet, opts.sides);
  const ctx = { def, state, opts, byId };

  const root = el("div", { class: "fo", "data-sides": opts.sides });

  // IN CIMA, e non accanto a «Salva»: la stessa regola della vista «Campi» —
  // l'azione che svuota non sta a un centimetro da quella che salva.
  const head = el("header", { class: "fo-head" },
    el("h2", { text: def.title }));
  const clear = el("button", { class: "risky", type: "button",
                               text: tr("sheet.clear") });
  clear.addEventListener("click", () => state.onClear());
  head.append(clear);
  root.append(head);

  const body = el("div", { class: "fo-body" });
  const desk = el("div", { class: "fo-desk" });
  const pages = el("div", { class: "fo-pages",
                            "data-count": String(shown.length) });
  for (const side of shown) pages.append(pageFor(side, ctx));
  desk.append(pages);
  // Un clic sul piano, fuori dalle caselle, toglie la selezione: il pannello
  // torna a dire lo stato della scheda.
  desk.addEventListener("click", (event) => {
    if (!event.target.closest(".fo-f")) select(root, ctx, null);
  });
  const insp = el("aside", { class: "fo-insp", "aria-live": "polite" });
  body.append(desk, insp);
  root.append(body);

  const foot = el("footer", { class: "sheetfoot" });
  const saveIt = el("button", { class: "primary save", type: "button",
                                text: tr("sheet.save") });
  saveIt.addEventListener("click", () => state.onSave());
  foot.append(saveIt);
  root.append(foot);

  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.selected) select(root, ctx, null);
  });

  host.append(root);

  // IL PANNELLO PRIMA DELLA SCALA: è lui che decide quanto è alta la pagina, e
  // quindi se la finestra ha la barra di scorrimento verticale — 15 px di piano
  // in meno. Misurare prima di riempirlo misurava un piano che non esisteva più.
  if (state.selected && !byId.has(state.selected)) state.selected = null;
  select(root, ctx, state.selected || null);

  // LA SCALA, misurata sul piano vero e non sulla finestra: la colonna e il
  // pannello a destra ne prendono una parte, e cambiano con la soglia.
  // MISURATO il 16 ottobre a 1024 × 768: la scala si calcolava sulla larghezza
  // di PRIMA che il foglio facesse comparire la barra di scorrimento verticale
  // della pagina, e le due facciate uscivano dal piano di 15 px. Quindi
  // l'osservatore confronta con la larghezza usata dall'ultima misura, non con
  // quella letta quando è nato.
  let measuredAt = -1;
  const measure = () => {
    measuredAt = desk.clientWidth;
    const style = getComputedStyle(desk);
    const inner = desk.clientWidth - parseFloat(style.paddingLeft || 0)
      - parseFloat(style.paddingRight || 0);
    pages.style.setProperty("--mm", `${scaleFor(inner, shown.length)}px`);
    for (const pad of pages.querySelectorAll("textarea")) grow(pad);
  };
  measure();
  if (typeof ResizeObserver !== "undefined") {
    watching = new ResizeObserver(() => {
      if (desk.clientWidth !== measuredAt) measure();
    });
    watching.observe(desk);
  }

  return { shown };
}

function pageFor(side, ctx) {
  const { def, state, opts } = ctx;
  const m = (def.sheet && def.sheet.margins_mm) || {};
  // LA CARTA NELLA DIREZIONE DELLA SUA SCHEDA, non dell'interfaccia: una US
  // ICCD è italiana e si scrive da sinistra a destra anche con l'interfaccia in
  // ebraico (2026-10-24). `lang` perché la sillabazione e la voce la seguano.
  const page = el("article", {
    class: "fo-page",
    lang: def.lang || "",
    dir: SG().scriptDir ? SG().scriptDir(def.lang) : "ltr",
    "data-side": side.id,
    "aria-label": side.label,
    style: `--fo-mt:${m.top || 0};--fo-mr:${m.right || 0};` +
           `--fo-mb:${m.bottom || 0};--fo-ml:${m.left || 0}`,
  });

  if (opts.corner) {
    // IL GLIFO: un bottone vero, raggiungibile da tastiera, col nome dal
    // dizionario. Fa la stessa cosa del comando «Facciate»: due strade verso lo
    // stesso stato, e lo stato è uno (`state.faces`, in `shell.js`).
    const expand = opts.sides === "both";
    const words = tr(expand ? "page.expand" : "page.collapse");
    const corner = el("button", { class: "fo-corner", type: "button",
                                  "data-corner": side.id,
                                  "aria-label": words, title: words },
      glyph(expand ? "expand" : "collapse"));
    corner.addEventListener("click", (event) => {
      event.stopPropagation();
      state.onCorner(side.id);
    });
    page.append(corner);
  }
  if (def.standard && def.standard.invented) {
    page.append(el("span", { class: "fo-fixture", text: "FIXTURE · demo" }));
  }

  const std = def.standard || {};
  page.append(el("div", { class: "fo-pagehead" },
    el("b", { text: [std.authority, std.code, std.version]
                      .filter(Boolean).join(" ") }),
    el("span", { class: "fo-key",
                 text: `${String(side.label || "").toUpperCase()} · ` +
                       headKey(def.human_key_pattern, state.values) })));

  const grid = el("div", { class: "fo-grid" });
  rowsInto(grid, side.rows, ctx);
  page.append(grid);
  return page;
}

function rowsInto(parent, rows, ctx) {
  for (const row of rows || []) {
    const line = el("div", { class: "fo-row", style: `--fo-h:${row.h || 0}` });
    for (const cell of row.cells || []) line.append(cellFor(cell, ctx));
    parent.append(line);
  }
}

function cellFor(cell, ctx) {
  const width = `flex-basis:${cell.w || 0}%;max-width:${cell.w || 0}%`;
  if (cell.rows) {
    // UN BLOCCO: una griglia annidata. Ruotato, l'etichetta sta in verticale su
    // una striscia a sinistra (SEQUENZA FISICA); senza etichetta, niente.
    const block = el("div", { class: "fo-cell fo-block" +
                                     (cell.rotated ? " fo-rotated" : ""),
                              "data-block": cell.block, style: width });
    if (cell.label) {
      block.append(el("div", { class: "fo-blab", text: cell.label }));
    }
    const inner = el("div", { class: "fo-inner" });
    rowsInto(inner, cell.rows, ctx);
    block.append(inner);
    return block;
  }
  const field = cell.field ? ctx.byId.get(cell.field) : null;
  if (!field) {
    // UNO SPAZIO: una cella vuota che nessuno scrive.
    return el("div", { class: "fo-cell fo-space", style: width,
                       "aria-hidden": "true" });
  }
  return fieldCell(field, cell, width, ctx);
}

function fieldCell(field, cell, width, ctx) {
  const { state, opts } = ctx;
  const id = `fo-${field.id}`;
  const dim = isDimmed(field, opts);
  const box = el("div", {
    class: "fo-cell fo-f" + (dim ? " fo-dim" : ""),
    "data-field": field.id,
    "data-recorded-in": field.recorded_in,
    style: width,
    title: dim ? tr("f.later") : null,
  });

  const named = cell.label !== "none";
  if (named) {
    const label = el("label", { class: "fo-lab", for: id, text: field.label });
    if (field.required) {
      label.append(el("span", { class: "fo-req", "aria-hidden": "true",
                                text: " *" }));
    }
    label.append(el("span", { class: "fo-stamp", hidden: true }));
    box.append(label);
  }

  box.append(controlFor(field, id, named, ctx));
  paintStamp(box, field.id, state);

  // Toccare una casella la SELEZIONA: il pannello a destra la mostra.
  box.addEventListener("focusin", () => {
    if (state.selected !== field.id) select(box.closest(".fo"), ctx, field.id);
  });
  box.addEventListener("click", (event) => {
    if (event.target === box) {
      const control = box.querySelector("textarea, input, button");
      if (control) control.focus();
    }
  });
  return box;
}

function controlFor(field, id, named, ctx) {
  const { state } = ctx;
  const kind = CONTROL[field.type] || "multiline";
  const current = state.values[field.id];
  const aria = named ? {} : { "aria-label": field.label };

  if (isStructured(field)) {
    // UN VALORE STRUTTURATO (22 ottobre): la casella MOSTRA il risultato —
    // chip, righe, l'etichetta del concetto — e si scrive nel pannello a
    // destra, dove il widget ha lo spazio. Un bottone vero: da tastiera la si
    // raggiunge e Invio la apre, come un clic.
    const shows = el("button", { class: "fo-val fo-struct", id, type: "button",
                                 "data-struct": field.type, ...aria });
    shows.append(valueView(field, current, state.def));
    shows.addEventListener("click", (event) => {
      event.stopPropagation();
      select(shows.closest(".fo"), ctx, field.id);
      const first = document.querySelector(".fo-insp .w input, .fo-insp .w select, .fo-insp .w button");
      if (first) first.focus();
    });
    return shows;
  }

  if (kind === "checks") {
    // Le caselle da barrare, mutuamente esclusive, con l'etichetta
    // dell'opzione: come sulla carta. Ribarrare quella segnata la toglie.
    const group = el("div", { class: "fo-checks", role: "group",
                              "aria-label": field.label, id });
    for (const option of field.options || []) {
      const on = current === option.value;
      const button = el("button", { class: "fo-chk", type: "button",
                                    "data-value": option.value,
                                    "aria-pressed": String(on) },
        el("i", { "aria-hidden": "true" }), el("span", { text: option.label }));
      button.addEventListener("click", () => {
        const now = state.values[field.id] === option.value ? "" : option.value;
        writeValue(state, field.id, now);
        for (const b of group.querySelectorAll(".fo-chk")) {
          b.setAttribute("aria-pressed", String(b.dataset.value === now));
        }
      });
      group.append(button);
    }
    return group;
  }

  if (kind === "checkbox") {
    const box = el("input", { class: "fo-box", type: "checkbox", id, ...aria });
    box.checked = Boolean(current);
    box.addEventListener("input", () => writeValue(state, field.id, box.checked));
    return box;
  }

  let input;
  if (kind === "number" || kind === "date") {
    input = el("input", { class: "fo-val", id, type: kind, ...aria,
                          step: field.type === "decimal" ? "any" : null });
  } else if (kind === "line") {
    // UN IDENTIFICATIVO NON SI SPEZZA. Misurato alla scrivania a 1280: in
    // un'area di testo il numero dell'unità, nella sua casella stretta, andava
    // a capo a metà («301 / 4»). Un campo di una riga lo tiene intero.
    input = el("input", { class: "fo-val", id, type: "text", ...aria,
                          spellcheck: "false", autocomplete: "off" });
  } else {
    // UN'AREA DI TESTO che cresce, anche per i campi di una riga: un valore
    // lungo va a capo dentro la sua casella invece di scorrere nascosto.
    input = el("textarea", { class: "fo-val", id, rows: 1, spellcheck: "false",
                             ...aria });
    if (ONE_LINE.has(field.type)) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") event.preventDefault();
      });
    }
    input.addEventListener("input", () => grow(input));
  }
  // IL NUMERO DELL'UNITÀ, in evidenza: quale casella sia lo dice la
  // definizione (`keyField`), non questo file.
  if (field.id === state.keyField) input.classList.add("fo-big");
  if (field.required) input.setAttribute("aria-required", "true");
  if (field.max_len && input.tagName !== "SELECT") {
    const digits = String(field.max_len).match(/\d+/g);
    if (digits) input.setAttribute("maxlength", digits[digits.length - 1]);
  }
  if (field.vocabulary) input.title = field.vocabulary;
  input.value = asText(current);
  input.addEventListener("input", () => {
    writeValue(state, field.id, input.value);
    // Il pannello, se mostra QUESTO campo, segue: stesso valore, due caselle
    // che guardano la stessa cosa.
    const mirror = document.getElementById("fo-insp-write");
    if (mirror && mirror.dataset.field === field.id && mirror !== input) {
      mirror.value = input.value;
    }
  });
  return input;
}

/** Il bollo AI / AI✓ accanto all'etichetta, dalla stessa provenienza che usa la
 *  vista «Campi» (`authorshipOf`). */
function paintStamp(box, fieldId, state) {
  const stamp = box.querySelector(".fo-stamp");
  if (!stamp) return;
  const who = authorshipOf(fieldId, state);
  stamp.hidden = !who;
  stamp.className = "fo-stamp" + (who === "ai" ? " ai" : who ? " aiok" : "");
  stamp.textContent = who === "ai" ? "AI" : who ? "AI✓" : "";
}

/* ── scrivendo: si aggiorna quello che dipende dai valori, non tutto ───────
 *
 * Ridisegnare il foglio a ogni tasto perderebbe il fuoco e il cursore: come
 * `refreshCompleteness` per la vista «Campi», si toccano solo l'intestazione
 * corrente (la chiave umana), i bolli e il riepilogo del pannello. */
export function refreshSheet(host, def, state) {
  const root = host.querySelector(".fo");
  if (!root) return;
  const key = headKey(def.human_key_pattern, state.values);
  for (const span of root.querySelectorAll(".fo-pagehead .fo-key")) {
    const side = span.closest(".fo-page");
    const label = side ? side.getAttribute("aria-label") || "" : "";
    span.textContent = `${label.toUpperCase()} · ${key}`;
  }
  for (const box of root.querySelectorAll(".fo-f")) {
    paintStamp(box, box.dataset.field, state);
  }
  if (!state.selected) {
    const insp = root.querySelector(".fo-insp");
    if (insp) paintSummary(insp, def, state);
  }
}

/* ── il pannello a destra (spec §5, solo la parte di stanotte) ─────────────
 *
 * Con una casella selezionata: etichetta, paragrafo, dove si compila e, per i
 * testi, un'area di scrittura più comoda con la conferma se un modello l'ha
 * proposto. Senza selezione: lo stato della scheda. Il mini-grafo dei rapporti,
 * le miniature delle foto e «Apri in EMStudio / Heriverse» sono pacchetti
 * successivi: il posto resta, qui non si costruiscono. */

function select(root, ctx, fieldId) {
  if (!root) return;
  const { state, def } = ctx;
  state.selected = fieldId;
  for (const box of root.querySelectorAll(".fo-f")) {
    box.classList.toggle("fo-sel", box.dataset.field === fieldId);
  }
  const insp = root.querySelector(".fo-insp");
  if (!insp) return;
  if (fieldId && ctx.byId.has(fieldId)) paintField(insp, ctx.byId.get(fieldId), ctx);
  else paintSummary(insp, def, state);
}

const TEXTS = new Set(["text", "longtext"]);

function paintField(insp, field, ctx) {
  const { def, state } = ctx;
  insp.replaceChildren();
  const para = (def.paragraphs || []).find((p) => (p.fields || []).includes(field.id));
  const top = el("section", {},
    el("p", { class: "fo-eyebrow", text: para ? para.label : "" }),
    el("h2", { text: field.label }));
  const tags = el("p", { class: "fo-tags" });
  if (field.recorded_in === "trench") {
    tags.append(el("span", { class: "fo-tag ok", text: tr("insp.trench") }));
  } else if (field.recorded_in === "lab") {
    tags.append(el("span", { class: "fo-tag", text: tr("insp.lab") }));
  }
  if (field.required && !isFilled(state.values[field.id])) {
    tags.append(el("span", { class: "fo-tag warn", text: tr("insp.required") }));
  }
  const who = authorshipOf(field.id, state);
  if (who) {
    tags.append(el("span", { class: "fo-tag " + (who === "ai" ? "warn" : "ok"),
                             text: tr(who === "ai" ? "insp.ai_todo" : "insp.ai_ok") }));
  }
  if (tags.childElementCount) top.append(tags);
  if (field.help) top.append(el("p", { text: field.help }));
  insp.append(top);

  if (isStructured(field)) {
    // IL WIDGET, nel pannello: lo stesso di «Campi» e del telefono. Scrivendo,
    // la casella del foglio si ridisegna col risultato.
    const write = el("section", { class: "fo-write" },
      el("p", { class: "fo-eyebrow", text: tr("insp.write") }));
    const host = el("div", { class: "w-host", "data-field": field.id });
    mountWidget(host, field, state, {
      onWrite: () => {
        const cell = document.getElementById(`fo-${field.id}`);
        if (cell) cell.replaceChildren(valueView(field, state.values[field.id], state.def));
      },
    });
    write.append(host);
    if (who === "ai") {
      const confirm = el("button", { class: "fo-confirm", type: "button",
                                     text: tr("act.confirm") });
      confirm.addEventListener("click", () => state.onValidate(field.id));
      write.append(confirm);
    }
    insp.append(write);
    return;
  }

  if (TEXTS.has(field.type)) {
    const write = el("section", { class: "fo-write" },
      el("label", { class: "fo-eyebrow", for: "fo-insp-write",
                    text: tr("insp.write") }));
    const pad = el("textarea", { id: "fo-insp-write",
                                  "data-field": field.id, rows: 6 });
    pad.value = asText(state.values[field.id]);
    pad.addEventListener("input", () => {
      writeValue(state, field.id, pad.value);
      const cell = document.getElementById(`fo-${field.id}`);
      if (cell && cell !== pad) { cell.value = pad.value; grow(cell); }
    });
    write.append(pad);
    if (who === "ai") {
      // CONFERMARE È UN GESTO, e lo stesso della vista «Campi» («Ho
      // controllato»): `state.onValidate`, che manda `/v1/validate`.
      const confirm = el("button", { class: "fo-confirm", type: "button",
                                     text: tr("act.confirm") });
      confirm.addEventListener("click", () => state.onValidate(field.id));
      write.append(confirm);
    }
    insp.append(write);
  }
}

function paintSummary(insp, def, state) {
  insp.replaceChildren();
  const fields = def.fields || [];
  const filled = (f) => isFilled(state.values[f.id]);
  const meter = el("div", { class: "fo-meter" });
  const bar = (key, list, quiet) => {
    const done = list.filter(filled).length;
    const share = list.length ? (done / list.length) * 100 : 0;
    const track = el("span", { class: "fo-track" },
      el("i", { class: quiet ? "quiet" : null, style: `width:${share}%` }));
    meter.append(el("span", { text: tr(key) }), track,
                 el("span", { class: "fo-num", text: `${done}/${list.length}` }));
  };
  bar("insp.all", fields);
  bar("insp.trench", fields.filter((f) => f.recorded_in === "trench"));
  bar("insp.lab", fields.filter((f) => f.recorded_in === "lab"), true);
  insp.append(el("section", {},
    el("p", { class: "fo-eyebrow", text: tr("insp.thiscard") }),
    el("h2", { text: def.title }), meter));

  const check = el("section", {},
    el("p", { class: "fo-eyebrow", text: tr("insp.check") }));
  for (const f of fields.filter((x) => x.required && !filled(x))) {
    check.append(el("div", { class: "fo-item" }, el("span", { text: f.label }),
      el("span", { class: "fo-tag warn", text: tr("insp.required") })));
  }
  for (const f of fields) {
    const who = authorshipOf(f.id, state);
    if (!who) continue;
    check.append(el("div", { class: "fo-item" }, el("span", { text: f.label }),
      el("span", { class: "fo-tag " + (who === "ai" ? "warn" : "ok"),
                   text: tr(who === "ai" ? "insp.ai_todo" : "insp.ai_ok") })));
  }
  check.append(el("div", { class: "fo-item" },
    el("span", { text: tr("insp.empty") }),
    el("span", { class: "fo-num", text: String(fields.filter((f) => !filled(f)).length) })));
  insp.append(check);
}
