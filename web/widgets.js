/* I widget strutturati — un elemento per TIPO di valore (SPEC §1.5).
 *
 * ════════════════════════════════════════════════════════════════════════════
 * PERCHÉ ESISTONO
 *
 * Il generatore di operazioni (`app/operazioni.py`) accetta i valori
 * strutturati e **rifiuta per nome** il testo dove serve una lista: «3018, 3020»
 * in COPRE non lo spezza indovinando il separatore (referto del 19 ottobre).
 * Fino a stanotte il modulo mandava soltanto testo, quindi da una scheda nuova
 * COPRE e MISURE tornavano rifiutate. Questi widget compongono il valore nella
 * forma che la ricetta vuole, e la stessa funzione di scrittura (`writeValue`)
 * lo mette nello stesso `state.values` che `save()` manda.
 *
 * Il disegno è quello del mockup approvato da E.D. il 22 ottobre (chip con ×,
 * completamento dalla stanza, unità nuova tratteggiata «da compilare», righe
 * «che cosa · valore · unità»…). È un disegno, non codice copiato.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * UNA SOLA IMPLEMENTAZIONE, TRE POSTI
 *
 * Alla scrivania il widget vive nel pannello a destra del Foglio e la casella
 * mostra il risultato (`valueView`); nella vista «Campi» e sul telefono vive
 * nella casella stessa, al posto della textarea, con bersagli grandi. È lo
 * stesso `mountWidget` in tutti e tre: due copie di un selettore di unità
 * sarebbero due regole su che cosa è un'unità «da compilare».
 *
 * ════════════════════════════════════════════════════════════════════════════
 * NESSUNO STANDARD QUI DENTRO
 *
 * Che cosa un campo è lo dice il suo `type`; il vocabolario lo dice
 * `field.vocabulary`; le qualia di una riga di misura le dice il datamodel
 * attraverso il servizio (`field.measures`); il prefisso con cui si scrive
 * un'unità («US », «Contexto ») lo dice il pattern della chiave umana della
 * definizione. Periodi, attività e foto sono quelli della STANZA
 * (`GET /v1/room/choices`), le unità quelle di `GET /v1/room/units`.
 *
 * Puro al caricamento — niente `document` al primo livello — perché
 * `scheda.js` lo importa e i test importano `scheda.js` con node.
 */

import { unitNumber, writeValue } from "./scheda.js";

const SG = () => (typeof window !== "undefined" && window.SG) || {};
const tr = (key, values) => (SG().t ? SG().t(key, values) : key);

/** I tipi che hanno un widget. Gli altri restano l'elemento di sempre. */
export const STRUCTURED = new Set([
  "unit_ref_list", "record_ref_list", "resource_ref_list", "quantity_list",
  "term", "term_list", "person_ref", "epoch_ref", "activity_ref",
]);
export const isStructured = (field) => Boolean(field) && STRUCTURED.has(field.type);

/* ── ciò che la stanza ha già ───────────────────────────────────────────────
 *
 * UNO stato, letto dal servizio e condiviso: il completamento delle unità, la
 * navigazione ‹ › e i filtri dell'elenco guardano le stesse unità. Due letture
 * sarebbero due elenchi il giorno che una delle due è vecchia. */
export const room = {
  units: [],
  choices: { epochs: [], activities: [], photos: [] },
  read: false,
};

function authHeaders() {
  const seam = SG();
  return seam.token ? { Authorization: "Bearer " + seam.token } : {};
}

/** Le unità e le scelte della stanza, dal servizio. Senza rete resta quello che
 *  c'era: un completamento vecchio è meglio di nessuno, e non scrive niente. */
export async function loadRoom() {
  const seam = SG();
  if (!seam.node && seam.node !== "") return room;
  try {
    const [units, choices] = await Promise.all([
      fetch(`${seam.node || ""}/v1/room/units`, { headers: authHeaders() }),
      fetch(`${seam.node || ""}/v1/room/choices`, { headers: authHeaders() }),
    ]);
    if (units.ok) room.units = (await units.json()).units || [];
    if (choices.ok) {
      const said = await choices.json();
      room.choices = { epochs: said.epochs || [], activities: said.activities || [],
                       photos: said.photos || [] };
    }
    room.read = units.ok;
  } catch { /* offline: the last reading stays */ }
  return room;
}

/** Il numero, come la chiave lo scrive: il testo del pattern PRIMA del campo
 *  dell'unità («US {us} — …» → «US »). Vuoto quando il pattern non comincia
 *  con l'unità: allora si scrive il numero e basta. */
export function unitPrefix(def) {
  const pattern = String((def && def.human_key_pattern) || "");
  const slot = def && def.unit_field ? `{${def.unit_field}}` : "";
  if (!slot || !pattern.includes(slot)) return "";
  const before = pattern.slice(0, pattern.indexOf(slot));
  return /\{/.test(before) ? "" : before;
}

/** «US 3018», «us3018», «3018» → «3018». Il prefisso è quello della definizione. */
export function bareNumber(text, def) {
  let said = String(text || "").trim();
  const prefix = unitPrefix(def).trim();
  if (prefix && said.toLowerCase().startsWith(prefix.toLowerCase())) {
    said = said.slice(prefix.length).trim();
  }
  return said;
}

const byNumber = (a, b) => {
  const x = parseFloat(a), y = parseFloat(b);
  if (Number.isFinite(x) && Number.isFinite(y) && x !== y) return x - y;
  return String(a).localeCompare(String(b), undefined, { numeric: true });
};

/** Le unità della stanza con un numero, UNA per numero, in ordine numerico. È
 *  l'ordine di ‹ ›, quello del completamento e quello dei suggerimenti. */
export function orderedUnits(units = room.units) {
  const seen = new Map();
  for (const u of units || []) {
    if (!u || !u.number) continue;
    const held = seen.get(u.number);
    // una scheda vera batte uno stub con lo stesso numero
    if (!held || (held.stub && !u.stub)) seen.set(u.number, u);
  }
  return [...seen.values()].sort((a, b) => byNumber(a.number, b.number));
}

/** Un'unità nominata in un rapporto è «da compilare» se la stanza non la ha,
 *  o la ha soltanto come stub: è la regola già decisa (creata minima e
 *  segnata, operazioni.py decisione 1), mostrata invece che taciuta. */
export function toFill(number, units = room.units) {
  const found = orderedUnits(units).find((u) => u.number === String(number));
  return !found || Boolean(found.stub);
}

/* ── ORCID: il formato e la cifra di controllo ─────────────────────────────
 *
 * Il riferimento di una persona diventa l'id del suo nodo autore (la ricetta:
 * `find: {node_type: author, id: $value.ref}`), quindi un ORCID sbagliato non
 * è un refuso: è una seconda persona. Si controlla qui il formato e la cifra
 * di controllo (ISO 7064 11,2, quella che orcid.org pubblica), e un ORCID che
 * non passa NON entra nel valore: resta il nome, e il widget lo dice. */
export function orcidOk(text) {
  const bare = String(text || "").trim().replace(/^orcid:/i, "")
    .replace(/^https?:\/\/orcid\.org\//i, "");
  if (!/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(bare)) return null;
  const digits = bare.replace(/-/g, "");
  let total = 0;
  for (const ch of digits.slice(0, 15)) total = (total + Number(ch)) * 2;
  const check = (12 - (total % 11)) % 11;
  const want = check === 10 ? "X" : String(check);
  return digits[15] === want ? bare : null;
}

/* ── i vocabolari, in cache come le definizioni ─────────────────────────── */

const VOC_KEY = (scheme, lang) => `sg.voc.${scheme}.${lang}`;
const vocs = new Map();

export async function vocabularyFor(scheme, lang) {
  const key = VOC_KEY(scheme, lang);
  if (vocs.has(key)) return vocs.get(key);
  let found = null;
  try {
    const answer = await fetch(
      `${SG().node || ""}/v1/vocabolario/${encodeURIComponent(scheme)}?lang=${encodeURIComponent(lang)}`,
      { headers: { Accept: "application/json" } });
    if (answer.ok) {
      found = await answer.json();
      try { localStorage.setItem(key, JSON.stringify(found)); } catch { /* full */ }
    }
  } catch { /* offline: what the device kept */ }
  if (!found) {
    try { found = JSON.parse(localStorage.getItem(key) || "null"); } catch { found = null; }
  }
  if (found) vocs.set(key, found);
  return found;
}

/* ── le forme, e come si leggono ─────────────────────────────────────────── */

export function asList(value) {
  if (Array.isArray(value)) return value.slice();
  if (value === undefined || value === null || value === "") return [];
  // UN VALORE VECCHIO (una stringa riletta prima dei widget) resta UN elemento:
  // spezzarlo qui sarebbe indovinare il separatore che il generatore rifiuta.
  return [value];
}

const itemText = (item) => (item && typeof item === "object")
  ? String(item.label || item.name || item.value || item.concept || item.url || "")
  : String(item ?? "");

const tail = (text) => {
  const said = String(text || "");
  const cut = said.replace(/[?#].*$/, "").split(/[\\/]/).filter(Boolean);
  return cut.length ? cut[cut.length - 1] : said;
};

/** Una riga di misura come si legge sulla carta. */
export function quantityText(row, field) {
  if (!row || typeof row !== "object") return String(row ?? "");
  const q = ((field && field.measures && field.measures.qualia) || [])
    .find((x) => x.id === row.qualia);
  const what = row.label || (q ? (q.label || q.name) : row.qualia) || "";
  return [what, row.value, row.unit].filter((x) => x !== undefined && x !== "")
    .join(" ");
}

/* ── piccole mani ────────────────────────────────────────────────────────── */

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids) if (kid) node.append(kid);
  return node;
}

let serial = 0;
const fresh = (stem) => `w-${stem}-${++serial}`;

/* ── che cosa MOSTRA la casella del Foglio ────────────────────────────────
 *
 * Il risultato, non l'editor: chip per le liste, righe per le misure,
 * l'etichetta per un termine. Chi vuole cambiarlo seleziona la casella, e il
 * pannello a destra monta il widget. */
export function valueView(field, value, def) {
  const box = el("span", { class: "w-view" });
  const prefix = unitPrefix(def);
  if (field.type === "unit_ref_list") {
    for (const n of asList(value)) {
      const fill = toFill(n);
      box.append(el("span", { class: "w-chip" + (fill ? " w-new" : ""),
                              title: fill ? tr("w.to_fill") : null,
                              text: `${prefix}${itemText(n)}` }));
    }
  } else if (field.type === "record_ref_list" || field.type === "resource_ref_list"
             || field.type === "term_list") {
    for (const item of asList(value)) {
      box.append(el("span", { class: "w-chip" + (field.type === "resource_ref_list" ? " w-file" : ""),
                              text: field.type === "resource_ref_list" ? tail(itemText(item)) : itemText(item) }));
    }
  } else if (field.type === "quantity_list") {
    for (const row of asList(value)) {
      if (row && typeof row === "object" && (row.value === undefined || row.value === "")) continue;
      box.append(el("span", { class: "w-qline", text: quantityText(row, field) }));
    }
  } else if (field.type === "person_ref") {
    const v = value && typeof value === "object" ? value : { name: value };
    if (v.name) box.append(el("span", { text: String(v.name) }));
    if (v.ref) box.append(el("span", { class: "w-ref", text: String(v.ref).replace(/^orcid:/, "ORCID ") }));
  } else {
    const said = itemText(value);
    if (said) box.append(el("span", { text: said }));
  }
  return box;
}

/* ── il widget, montato ───────────────────────────────────────────────────
 *
 * `host` è dove disegnarlo (il pannello, la casella, il passo del telefono);
 * `opts.big` sono i bersagli da pollice (≥ 44 px, nel CSS); `opts.onWrite` è
 * ciò che chi lo ospita deve aggiornare dopo una scrittura (la casella del
 * Foglio che mostra il risultato). Ogni scrittura passa da `writeValue`.
 *
 * Ritorna la funzione che lo ridisegna. */
export function mountWidget(host, field, state, opts = {}) {
  const def = state.def || {};
  const put = (value) => {
    writeValue(state, field.id, value);
    if (opts.onWrite) opts.onWrite(value);
  };
  const ctx = { host, field, state, def, put, big: Boolean(opts.big), keep: {} };
  const draw = () => {
    // IL FUOCO RESTA DOV'ERA: un widget che si ridisegna togliendo il cursore
    // dal campo in cui si sta scrivendo si usa una volta sola.
    const active = host.contains(document.activeElement) ? document.activeElement : null;
    const where = active && active.dataset ? active.dataset.w : null;
    const caret = active && typeof active.selectionStart === "number" ? active.selectionStart : null;
    host.replaceChildren();
    host.classList.add("w");
    host.classList.toggle("w-big", ctx.big);
    (DRAW[field.type] || drawPlain)(ctx);
    if (where) {
      const again = host.querySelector(`[data-w="${where}"]`);
      if (again) {
        again.focus();
        if (caret !== null && typeof again.setSelectionRange === "function") {
          try { again.setSelectionRange(caret, caret); } catch { /* not a text field */ }
        }
      }
    }
  };
  ctx.draw = draw;
  draw();
  return draw;
}

const current = (ctx) => ctx.state.values[ctx.field.id];

function note(text) { return el("p", { class: "w-note", text }); }

function removeButton(label, onClick) {
  const b = el("button", { class: "w-x", type: "button", "aria-label": label, title: label, text: "×" });
  b.addEventListener("click", (event) => { event.stopPropagation(); onClick(); });
  return b;
}

/* ── unit_ref_list · record_ref_list ────────────────────────────────────── */

function drawUnits(ctx) {
  const { host, field, state, def, put } = ctx;
  const units = field.type === "unit_ref_list";
  const list = asList(current(ctx)).map(itemText).filter(Boolean);
  const prefix = units ? unitPrefix(def) : "";
  const chips = el("div", { class: "w-chips" });
  for (const n of list) {
    const fill = units && toFill(n);
    const chip = el("span", { class: "w-chip" + (fill ? " w-new" : ""),
                              title: fill ? tr("w.to_fill") : null },
      el("span", { text: `${prefix}${n}` }));
    if (fill) chip.append(el("em", { text: tr("w.to_fill") }));
    chip.append(removeButton(`${tr("w.remove")} ${prefix}${n}`,
      () => { put(list.filter((x) => x !== n)); ctx.draw(); }));
    chips.append(chip);
  }
  host.append(chips);

  const self = unitNumber(state);
  const candidates = units
    ? orderedUnits().filter((u) => u.number !== self && !list.includes(u.number)) : [];
  const listId = fresh("units");
  const add = el("div", { class: "w-add" });
  const input = el("input", { type: "text", "data-w": "add", list: units ? listId : null,
                              inputmode: units ? "numeric" : null, autocomplete: "off",
                              placeholder: tr("w.add_unit"), "aria-label": tr("w.add_unit") });
  const go = () => {
    const n = units ? bareNumber(input.value, def) : String(input.value || "").trim();
    if (!n || list.includes(n) || n === self) { input.value = ""; return; }
    put([...list, n]);
    ctx.draw();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); go(); }
  });
  // scegliere dal completamento È aggiungere: non c'è un secondo gesto da fare
  input.addEventListener("change", () => { if (input.value) go(); });
  const plus = el("button", { class: "w-btn", type: "button", "aria-label": tr("w.add_unit"),
                              title: tr("w.add_unit"), text: "+" });
  plus.addEventListener("click", go);
  add.append(input, plus);
  if (units) {
    const options = el("datalist", { id: listId });
    for (const u of candidates) {
      options.append(el("option", { value: u.number, label: u.definition || u.name || "" }));
    }
    add.append(options);
  }
  host.append(add);

  if (units && candidates.length) {
    // I SUGGERIMENTI: le unità più VICINE di numero a quella aperta, che è dove
    // stanno di solito le sue compagne di rapporto. Non un ordine qualunque.
    const here = parseFloat(self);
    const near = candidates.slice().sort((a, b) => Number.isFinite(here)
      ? Math.abs(parseFloat(a.number) - here) - Math.abs(parseFloat(b.number) - here)
      : 0).slice(0, ctx.big ? 6 : 8).sort((a, b) => byNumber(a.number, b.number));
    const sugg = el("div", { class: "w-sugg" });
    for (const u of near) {
      const b = el("button", { type: "button", "data-number": u.number,
                               title: u.definition || null, text: u.number });
      b.addEventListener("click", () => { put([...list, u.number]); ctx.draw(); });
      sugg.append(b);
    }
    host.append(sugg);
  }
  if (units) host.append(note(tr("w.unit_note")));
}

/* ── term · term_list ───────────────────────────────────────────────────── */

function drawTerm(ctx) {
  const { host, field, def, put } = ctx;
  const many = field.type === "term_list";
  const lang = def.lang || SG().locale || "en";
  const chosen = many ? asList(current(ctx)) : (current(ctx) ? [current(ctx)] : []);
  const same = (a, b) => (a.concept && b.concept) ? a.concept === b.concept
    : itemText(a).toLowerCase() === itemText(b).toLowerCase();

  if (many && chosen.length) {
    const chips = el("div", { class: "w-chips" });
    for (const term of chosen) {
      chips.append(el("span", { class: "w-chip" }, el("span", { text: itemText(term) }),
        removeButton(`${tr("w.remove")} ${itemText(term)}`,
          () => { put(chosen.filter((x) => !same(x, term))); ctx.draw(); })));
    }
    host.append(chips);
  }

  const search = el("input", { class: "w-search", type: "search", "data-w": "q",
                               autocomplete: "off", placeholder: tr("w.search"),
                               "aria-label": tr("w.search") });
  search.value = ctx.keep.q || "";
  host.append(search);
  const box = el("div", { class: "w-terms" });
  host.append(box);
  const said = el("p", { class: "w-note" });
  host.append(said);

  const pick = (term) => {
    ctx.keep.q = "";
    if (many) put(chosen.some((x) => same(x, term)) ? chosen.filter((x) => !same(x, term))
                                                    : [...chosen, term]);
    else put(chosen.some((x) => same(x, term)) ? null : term);
    ctx.draw();
  };
  const free = () => {
    // UNA PAROLA SENZA CONCETTO: SPEC §3 la chiama `uncontrolled`, il
    // generatore la scrive `{label}` e nessun concetto viene inventato.
    const word = String(search.value || "").trim();
    if (word) pick({ label: word });
  };
  search.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const first = box.querySelector("button.w-term");
    if (first && search.value.trim()) first.click(); else free();
  });

  const paint = (voc) => {
    box.replaceChildren();
    const q = String(search.value || "").trim().toLowerCase();
    const concepts = (voc && voc.concepts) || [];
    const shown = concepts.filter((c) => !q
      || String(c.label || c.label_there || "").toLowerCase().includes(q)
      || String(c.concept).toLowerCase().includes(q));
    for (const c of shown) {
      const label = c.label || c.label_there || tail(c.concept);
      const term = { concept: c.concept, label };
      const on = chosen.some((x) => same(x, term));
      const b = el("button", { class: "w-term" + (on ? " on" : ""), type: "button",
                               "aria-pressed": String(on) },
        el("span", { text: label }),
        c.label ? null : el("small", { text: c.label_lang || "" }),
        el("code", { text: `${voc.scheme}/${tail(c.concept)}` }));
      b.addEventListener("click", () => pick(term));
      box.append(b);
    }
    // il valore corrente, se non è un concetto di questo vocabolario: si vede
    for (const term of chosen) {
      if (term.concept && concepts.some((c) => c.concept === term.concept)) continue;
      const b = el("button", { class: "w-term on", type: "button", "aria-pressed": "true" },
        el("span", { text: itemText(term) }),
        el("code", { text: term.concept ? tail(term.concept) : tr("w.free_word") }));
      b.addEventListener("click", () => pick(term));
      box.append(b);
    }
    const q2 = String(search.value || "").trim();
    if (q2 && !shown.length) {
      const b = el("button", { class: "w-btn wide", type: "button", "data-free": "true",
                               text: `${tr("w.free_add")} «${q2}»` });
      b.addEventListener("click", free);
      box.append(b);
    }
    if (!voc) said.textContent = tr("w.no_vocab", { scheme: field.vocabulary || "" });
    else if (!concepts.length) said.textContent = tr("w.declared", { scheme: voc.scheme });
    else said.textContent = tr("w.term_note");
  };
  search.addEventListener("input", () => { ctx.keep.q = search.value; paint(ctx.voc); });
  if (ctx.voc !== undefined) paint(ctx.voc);
  else {
    paint(null);
    said.textContent = "…";
    if (field.vocabulary) {
      void vocabularyFor(field.vocabulary, lang).then((voc) => {
        ctx.voc = voc;
        if (ctx.host.isConnected) paint(voc);
      });
    } else { ctx.voc = null; paint(null); }
  }
}

/* ── quantity_list ──────────────────────────────────────────────────────── */

function drawQuantities(ctx) {
  const { host, field, put } = ctx;
  const measures = field.measures || { qualia: [], default: null };
  const qualia = measures.qualia || [];
  const rows = asList(current(ctx)).map((r) => (r && typeof r === "object")
    ? { ...r } : { label: String(r), value: "" });
  const write = () => put(rows.map((r) => ({ ...r })));
  const table = el("div", { class: "w-qty" });

  rows.forEach((row, i) => {
    const line = el("div", { class: "w-qrow" });
    const what = el("select", { "data-w": `q${i}`, class: "w-qwhat", "aria-label": tr("w.what") });
    const groups = new Map();
    for (const q of qualia) {
      // LE PAROLE DELLA SCHEDA, dal datamodel attraverso il nodo (`label`,
      // `group_label`, nella lingua della definizione); `name` è l'inglese, il
      // ripiego di una definizione messa in cache prima del 24 ottobre.
      if (!groups.has(q.group)) {
        groups.set(q.group, el("optgroup", { label: q.group_label || q.group }));
      }
      const o = el("option", { value: q.id, text: q.label || q.name });
      if (q.label_lang) o.setAttribute("lang", q.label_lang);
      if (q.id === row.qualia) o.selected = true;
      groups.get(q.group).append(o);
    }
    if (!row.qualia) what.append(el("option", { value: "", text: "—", selected: true }));
    else if (!qualia.some((q) => q.id === row.qualia)) {
      what.append(el("option", { value: row.qualia, text: row.qualia, selected: true }));
    }
    for (const g of groups.values()) what.append(g);
    what.addEventListener("change", () => {
      row.qualia = what.value;
      const q = qualia.find((x) => x.id === what.value);
      if (q && !q.units.includes(row.unit)) row.unit = q.units.includes("m") ? "m" : q.units[0];
      write(); ctx.draw();
    });
    const label = el("input", { type: "text", "data-w": `l${i}`, class: "w-qlab",
                                placeholder: tr("w.label"), "aria-label": tr("w.label") });
    label.value = row.label || "";
    label.addEventListener("input", () => { row.label = label.value; write(); });
    const value = el("input", { type: "text", "data-w": `v${i}`, class: "w-qval",
                                inputmode: "decimal", autocomplete: "off",
                                "aria-label": tr("w.value"), placeholder: tr("w.value") });
    value.value = row.value ?? "";
    value.addEventListener("input", () => { row.value = value.value; write(); });
    const q = qualia.find((x) => x.id === row.qualia);
    const units = q ? q.units : (row.unit ? [row.unit] : []);
    const unit = el("select", { "data-w": `u${i}`, class: "w-qunit", "aria-label": tr("w.unit") });
    for (const u of units) {
      const o = el("option", { value: u, text: u });
      if (u === row.unit) o.selected = true;
      unit.append(o);
    }
    unit.addEventListener("change", () => { row.unit = unit.value; write(); });
    const drop = removeButton(tr("w.remove"), () => { rows.splice(i, 1); write(); ctx.draw(); });
    drop.classList.add("w-qdel");
    line.append(what, label, value, unit, drop);
    table.append(line);
  });
  host.append(table);

  const addRow = el("button", { class: "w-btn wide", type: "button", "data-w": "addrow",
                                text: `+ ${tr("w.add_row")}` });
  addRow.addEventListener("click", () => {
    // LA RIGA NUOVA propone la qualia del default della casella (QUOTE:
    // elevation), poi la successiva a quella dell'ultima riga — lunghezza,
    // larghezza, spessore — e l'unità dell'ultima riga, se quella qualia la ha.
    const last = rows[rows.length - 1];
    const at = last ? qualia.findIndex((x) => x.id === last.qualia) : -1;
    const q = !last ? (qualia.find((x) => x.id === measures.default) || qualia[0])
      : (qualia[at + 1] || qualia[0]);
    const unit = q ? (last && q.units.includes(last.unit) ? last.unit
      : q.units.includes("m") ? "m" : q.units[0]) : "";
    rows.push({ qualia: q ? q.id : "", value: "", unit });
    write(); ctx.draw();
    const fresh2 = host.querySelector(`[data-w="v${rows.length - 1}"]`);
    if (fresh2) fresh2.focus();
  });
  host.append(addRow);
}

/* ── resource_ref_list ──────────────────────────────────────────────────── */

function drawResources(ctx) {
  const { host, state, put } = ctx;
  const list = asList(current(ctx)).map(itemText).filter(Boolean);
  const chips = el("div", { class: "w-chips" });
  for (const ref of list) {
    chips.append(el("span", { class: "w-chip w-file", title: ref },
      el("span", { text: tail(ref) }),
      removeButton(`${tr("w.remove")} ${tail(ref)}`,
        () => { put(list.filter((x) => x !== ref)); ctx.draw(); })));
  }
  host.append(chips);

  const add = el("div", { class: "w-add" });
  const input = el("input", { type: "text", "data-w": "add", autocomplete: "off",
                              placeholder: tr("w.add_file"), "aria-label": tr("w.add_file") });
  const go = () => {
    const ref = String(input.value || "").trim();
    if (ref && !list.includes(ref)) put([...list, ref]);
    ctx.draw();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); go(); }
  });
  const plus = el("button", { class: "w-btn", type: "button", "aria-label": tr("w.add_file"),
                              title: tr("w.add_file"), text: "+" });
  plus.addEventListener("click", go);
  add.append(input, plus);
  host.append(add);

  // LE FOTO DELLA STANZA, prima quelle legate a QUESTA unità: sono quelle che
  // chi compila ha appena scattato.
  const unitId = unitNumber(state);
  const photos = (room.choices.photos || []).filter((p) => !list.includes(p.url))
    .sort((a, b) => Number(!String(b.unit).endsWith(unitId)) - Number(!String(a.unit).endsWith(unitId)))
    .slice(0, ctx.big ? 6 : 9);
  host.append(el("p", { class: "fo-eyebrow w-eyebrow", text: tr("w.pick_photos") }));
  if (!photos.length) {
    host.append(note(tr("w.no_photos")));
    return;
  }
  const pics = el("div", { class: "w-pics" });
  for (const p of photos) {
    const b = el("button", { type: "button", title: p.name || p.url },
      el("span", { text: tail(p.name || p.url) }));
    b.addEventListener("click", () => { put([...list, p.url]); ctx.draw(); });
    pics.append(b);
  }
  host.append(pics);
}

/* ── person_ref ─────────────────────────────────────────────────────────── */

function drawPerson(ctx) {
  const { host, put } = ctx;
  const v = current(ctx) && typeof current(ctx) === "object" ? current(ctx)
    : (current(ctx) ? { name: String(current(ctx)) } : {});
  // L'ORCID DIGITATO si tiene qui finché non è valido: nel valore entra solo un
  // ORCID che passa il controllo, perché diventerebbe l'id di una persona.
  if (ctx.keep.orcid === undefined) ctx.keep.orcid = String(v.ref || "").replace(/^orcid:/i, "");
  const nameId = fresh("name"), refId = fresh("orcid");
  const name = el("input", { id: nameId, type: "text", "data-w": "name", autocomplete: "name" });
  name.value = v.name || "";
  const orcid = el("input", { id: refId, type: "text", "data-w": "ref", inputmode: "numeric",
                              autocomplete: "off", placeholder: "0000-0000-0000-0000",
                              spellcheck: "false" });
  orcid.value = ctx.keep.orcid;
  const said = el("p", { class: "w-note", "aria-live": "polite" });
  const compose = () => {
    const ok = orcidOk(orcid.value);
    const out = {};
    if (name.value.trim()) out.name = name.value.trim();
    if (ok) out.ref = `orcid:${ok}`;
    put(Object.keys(out).length ? out : null);
    const typed = orcid.value.trim();
    said.textContent = ok ? "✓ ORCID" : typed ? tr("w.orcid_bad") : tr("w.orcid_note");
    said.classList.toggle("w-bad", Boolean(typed) && !ok);
  };
  name.addEventListener("input", compose);
  orcid.addEventListener("input", () => { ctx.keep.orcid = orcid.value; compose(); });
  host.append(el("label", { class: "w-lab", for: nameId, text: tr("exc.name") }), name,
              el("label", { class: "w-lab", for: refId, text: "ORCID" }), orcid, said);
  const typed = orcid.value.trim();
  const ok = orcidOk(typed);
  said.textContent = ok ? "✓ ORCID" : typed ? tr("w.orcid_bad") : tr("w.orcid_note");
  said.classList.toggle("w-bad", Boolean(typed) && !ok);
}

/* ── epoch_ref · activity_ref ───────────────────────────────────────────── */

function drawChoice(ctx) {
  const { host, field, put } = ctx;
  const pool = field.type === "epoch_ref" ? room.choices.epochs : room.choices.activities;
  const v = current(ctx);
  const nameOf = (x) => (x && typeof x === "object") ? String(x.name || x.label || "") : String(x || "");
  const now = nameOf(v);
  const box = el("div", { class: "w-terms" });
  for (const item of pool || []) {
    const on = now && item.name === now;
    const b = el("button", { class: "w-term" + (on ? " on" : ""), type: "button",
                             "aria-pressed": String(Boolean(on)) },
      el("span", { text: item.name }));
    // SCELTO DALLA STANZA porta il suo id: la ricetta lo cerca per `ref`, e
    // così non nasce un secondo periodo con lo stesso nome.
    b.addEventListener("click", () => { put(on ? null : { name: item.name, ref: item.id }); ctx.draw(); });
    box.append(b);
  }
  if (now && !(pool || []).some((x) => x.name === now)) {
    const b = el("button", { class: "w-term on", type: "button", "aria-pressed": "true" },
      el("span", { text: now }), el("code", { text: tr("w.to_fill") }));
    b.addEventListener("click", () => { put(null); ctx.draw(); });
    box.append(b);
  }
  host.append(box);
  if (!(pool || []).length) host.append(note(tr("w.none_in_room")));
  const add = el("div", { class: "w-add" });
  const input = el("input", { type: "text", "data-w": "new", autocomplete: "off",
                              placeholder: tr("w.new_epoch"), "aria-label": tr("w.new_epoch") });
  const go = () => {
    const word = String(input.value || "").trim();
    if (word) { put({ name: word }); ctx.draw(); }
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); go(); }
  });
  const plus = el("button", { class: "w-btn", type: "button", "aria-label": tr("w.new_epoch"),
                              title: tr("w.new_epoch"), text: "+" });
  plus.addEventListener("click", go);
  add.append(input, plus);
  host.append(add);
}

function drawPlain(ctx) {
  const input = el("input", { type: "text", "data-w": "plain" });
  input.value = itemText(current(ctx));
  input.addEventListener("input", () => ctx.put(input.value));
  ctx.host.append(input);
}

const DRAW = {
  unit_ref_list: drawUnits,
  record_ref_list: drawUnits,
  term: drawTerm,
  term_list: drawTerm,
  quantity_list: drawQuantities,
  resource_ref_list: drawResources,
  person_ref: drawPerson,
  epoch_ref: drawChoice,
  activity_ref: drawChoice,
};

/* ── salvare: le righe a metà non partono ─────────────────────────────────
 *
 * Una riga di misura aggiunta e non ancora scritta ha la qualia e non il
 * valore: è un modulo a metà, non una misura, e il generatore la
 * rifiuterebbe («ogni riga di una misura è … con un valore»). Si toglie qui,
 * al momento di mandare, e resta a schermo finché qualcuno non la riempie. */
export function sendable(field, value) {
  if (!field) return value;
  if (field.type === "quantity_list" && Array.isArray(value)) {
    return value.filter((r) => r && typeof r === "object"
      && r.value !== undefined && String(r.value).trim() !== "")
      .map((r) => Object.fromEntries(Object.entries(r)
        .filter(([, x]) => x !== undefined && x !== "")));
  }
  if (Array.isArray(value)) return value.filter((x) => itemText(x).trim() !== "");
  return value;
}
