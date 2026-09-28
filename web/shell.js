/* Il telaio, e chi guida il modulo.
 *
 * Un modulo ES servito dal nodo: nessuna catena di build, nessun bundler,
 * nessuna dipendenza. Su un Raspberry Pi in cantiere una catena di build è una
 * cosa in più che può non installarsi, e questo file la evita per intero — il
 * browser lo carica come lo trova sul disco.
 *
 * Non parla al grafo. Parla al servizio attraverso `window.SG`, il seam che la
 * pagina dichiara, e la scrittura passa da `SG.send`, che è anche ciò che mette
 * una richiesta fallita nella coda offline.
 */

import {
  definitionFor, effectiveMode, keyField, payloadFor, proposeMode,
  refreshCompleteness, rememberMode, render, save, stepTo, thumbbarPlan,
  trenchFields, otherFields, wayBack,
} from "./scheda.js";
import { drawSheet, hasSheet, optionsFor, refreshSheet } from "./foglio.js";
import { mount as mountPhotos } from "./photos.js";
import { mount as mountRoom, postureOf, roomOf } from "./room.js";
import { mount as mountIndex } from "./indice.js";
import { arrivalPlan, readArrival } from "./arrivo.js";
import { bareNumber, loadRoom, orderedUnits, unitPrefix } from "./widgets.js";
import { mount as mountChat } from "./chat.js";

const $ = (id) => document.getElementById(id);
const SG = () => window.SG || {};

/* Ridisegna la striscia delle foto. Assegnata al montaggio: prima di allora
 * non c'è niente da ridisegnare, e una funzione che non fa niente sarebbe una
 * bugia comoda. */
let repaintPhotos = () => {};
/* …e la stessa cosa per l'elenco di cosa c'è già nella stanza. */
let repaintIndex = async () => {};

/* Le etichette sono CHIAVI: il chip si dipinge nella lingua dell'interfaccia
 * (`t()`), e l'inglese accanto è solo il ripiego di un modulo caricato senza
 * la pagina (i test). */
const MODES = [
  ["phone", "field.phone", "Phone"],
  ["tablet", "field.tablet", "Tablet"],
  ["desktop", "mode.desk", "Desk"],
];
const tr = (key, fallback, values) =>
  (SG().t ? SG().t(key, values) : fallback);
const THEME_KEY = "sg.theme.v1";

/* ── il tema ────────────────────────────────────────────────────────────────
 *
 * Tre stati e non due: chiaro, scuro, e **quello del sistema** — che è il
 * default e non è «chiaro». Il tema del tema (`brand/stratigraph-theme.css`)
 * segue `prefers-color-scheme` quando `data-sg-theme` non c'è, e cancellare
 * l'attributo è come si torna a quello. Un toggle a due stati costringerebbe
 * una scelta che il dispositivo ha già fatto. */
const THEMES = [null, "light", "dark"];

function applyTheme(value) {
  if (value) document.documentElement.dataset.sgTheme = value;
  else delete document.documentElement.dataset.sgTheme;
  try {
    if (value) localStorage.setItem(THEME_KEY, value);
    else localStorage.removeItem(THEME_KEY);
  } catch { /* private window: lasts the session */ }
}

function savedTheme() {
  try {
    const kept = localStorage.getItem(THEME_KEY);
    return THEMES.includes(kept) ? kept : null;
  } catch { return null; }
}

/* ── lo stato della superficie ───────────────────────────────────────────── */

const state = {
  mode: "tablet",
  // QUALE dei due pannelli è a schermo — «detta» o «scheda». Non si deduce da
  // `def`: una scheda può essere caricata e il pannello della voce davanti.
  panel: "voice",
  def: null,
  values: {},
  // le caselle che il ritorno ha riempito dal grafo (vedi `refill`)
  loaded: new Set(),
  authored: {},
  validated: new Set(),
  model: "",
  us: "",
  create: true,
  step: 0,
  keyField: null,
  showAll: false,
  onePage: false,
  // ── IL FOGLIO (16 ottobre) ────────────────────────────────────────────────
  // Quale vista sulle soglie grandi: «sheet» (il Foglio) o «fields» (Campi, la
  // vista a paragrafi). Default Foglio: alla scrivania la scheda si compila
  // sulla carta. Il telefono non la legge: lì c'è un campo per volta.
  view: "sheet",
  // Le facciate alla scrivania — «both», «recto», «verso». UNO stato per due
  // strade: il comando «Facciate» e il glifo sull'angolo lo scrivono entrambi.
  faces: "both",
  // In campo: quale facciata, e se i campi non da trincea si attenuano.
  fieldSide: "recto",
  trenchOnly: true,
  // LA POSTURA — «desk» o «field» — nel SOLO posto dove vive (spec §4 bis).
  // Non si deduce dalla larghezza: un tablet può stare al tavolo o in trincea.
  // Si legge da come il nodo è connesso alla stanza (`postureOf`, room.js, sul
  // `seated` di `/health`) a ogni battito di `ping()`. `postureForced` è la
  // leva per provarla a mano (`SGShell.forcePosture`), e non si ricorda.
  posture: "desk",
  postureForced: null,
  // La casella selezionata sul Foglio: il pannello a destra la mostra.
  selected: null,
  // QUALCOSA SCRITTO E NON ANCORA MANDATO (22 ottobre). Lo accende
  // `writeValue`, lo spegne `save()`: è ciò che decide se cambiare unità deve
  // salvare prima.
  dirty: false,
  // Dopo un salvataggio, mandato o in coda: la stanza ha un'unità in più, e
  // l'indirizzo impara il numero di una scheda nuova.
  onSaved: (sent, body) => afterSave(body),
  onChange: () => paintCompleteness(),
  onStep: (i, n) => { $("tb-step").textContent = n ? `${i + 1}/${n}` : ""; },
  onValidate: (field) => validateField(field),
  onClear: () => clearScheda(),
  // Lo stesso atto del bottone della barra dei pollici, chiamato dal piede
  // della scheda quando la barra non c'è. Una via sola verso `save`.
  onSave: () => save(state.def, state),
  // IL GLIFO SULL'ANGOLO: dalla vista d'insieme espande quella facciata, dalla
  // facciata espansa torna a fronte e retro. Il fuoco resta sul glifo della
  // stessa facciata — chi usa la tastiera non deve ricominciare da capo.
  onCorner: (side) => {
    state.faces = state.faces === "both" ? side : "both";
    draw();
    const back = $("scheda-host").querySelector(
      `.fo-corner[data-corner="${side}"]`);
    if (back) back.focus();
  },
};

/* LA POSTURA CHE VALE: quella forzata, se qualcuno la sta provando, altrimenti
 * quella letta dal nodo. */
const posture = () => state.postureForced || state.posture;

/** Il battito di `ping()` porta la salute; cambia la postura solo se cambia, e
 *  ridisegna solo se la scheda è a schermo sul foglio. */
function takePosture(health) {
  const now = postureOf(health);
  if (now === state.posture) return;
  state.posture = now;
  if (!state.def || state.postureForced) return;
  // MAI SOTTO LE DITA: se qualcuno sta scrivendo in una casella, ridisegnare
  // gli toglierebbe il cursore a metà parola. Si aspetta che esca.
  const host = $("scheda-host");
  if (host.contains(document.activeElement)) {
    host.addEventListener("focusout", function later() {
      setTimeout(() => {
        if (host.contains(document.activeElement)) return;
        host.removeEventListener("focusout", later);
        draw();
      }, 0);
    });
    return;
  }
  draw();
}

/* ── il modo ─────────────────────────────────────────────────────────────── */

function paintModes() {
  const proposed = proposeMode(window.innerWidth);
  const bar = $("modes");
  bar.replaceChildren();
  for (const [value, key, fallback] of MODES) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = tr(key, fallback);
    chip.setAttribute("aria-pressed", String(value === state.mode));
    if (value === proposed) chip.dataset.proposed = "true";
    chip.addEventListener("click", () => {
      // Scegliere SCRIVE la scelta: è ciò che la fa sopravvivere a un
      // ricaricamento, e il puntino sul chip proposto resta a dire che la
      // larghezza ne suggerirebbe un altro.
      // …E LA SCELTA PORTA LA FINESTRA SU CUI È STATA FATTA. `rememberMode` è
      // l'unico posto che scrive: qui prima c'era una `setItem` per conto suo,
      // cioè un secondo scrittore della stessa chiave.
      rememberMode(value, window.innerWidth);
      setMode(value);
    });
    bar.append(chip);
  }
}

/* SUL TELEFONO LA BARRA IN ALTO NON CI STA — e non è una questione di gusto:
 * marchio, tre chip, tema, lingua, ORCID e stato su 375 px si accavallano.
 *
 * I nodi si SPOSTANO nella colonna, che sul telefono si apre col pollice: non
 * si duplicano. Due copie di un selettore di modo sono due stati il giorno che
 * qualcuno ne tocca uno, e sarebbe lo stesso difetto delle due caselle «US».
 *
 * E c'è una ragione oltre allo spazio: quei controlli stanno in cima, cioè dove
 * una mano sola NON arriva. Nella colonna che si apre dal basso ci arriva. */
const MOVABLE = ["modes", "theme", "lang"];

function placeControls(mode) {
  const home = mode === "phone" ? $("nav-controls-host") : null;
  $("nav-controls").hidden = mode !== "phone";
  for (const id of MOVABLE) {
    const node = $(id);
    if (!node) continue;
    const wanted = home || $("topbar-controls");
    if (node.parentElement !== wanted) wanted.append(node);
  }
}

/* L'UNICO posto che decide se la barra dei pollici c'è. Prima erano quattro
 * righe sparse in quattro funzioni, e la porta murata è nata da lì: `setMode`,
 * `draw`, `openScheda` e il bottone «Detta» la nascondevano ognuno per conto
 * suo, e nessuna delle quattro sapeva che dentro c'era l'unica maniglia della
 * colonna. La decisione è in `thumbbarPlan`, che è pura e provata. */
function paintThumbbar() {
  const plan = thumbbarPlan(state.mode, state.panel, state.def);
  $("thumbbar").hidden = !plan.bar;
  for (const id of ["tb-prev", "tb-step", "tb-next", "tb-save"]) {
    $(id).hidden = !plan.steps;
  }
  paintWayBack();
  paintUnav();
}

/* LA VIA D'USCITA, VISIBILE SENZA SAPERE GIÀ DOV'È.
 *
 * Il 24 settembre la maniglia è tornata a esistere; stanotte è stato misurato
 * che esistere non basta — su una finestra da 1574 i tre chip stavano a y=1372,
 * fuori dallo schermo, e l'unico bersaglio visibile era un ☰ che dice
 * «navigazione» e non «questa finestra ne proporrebbe un altro».
 *
 * Quindi il ritorno sta in barra, che sul telefono c'è sempre, e nomina il modo
 * verso cui torna invece di essere un'altra icona da indovinare. */
function paintWayBack() {
  const bottone = $("tb-back");
  if (!bottone) return;
  const verso = wayBack(state.mode, window.innerWidth);
  bottone.hidden = !verso;
  if (!verso) return;
  const voce = MODES.find(([value]) => value === verso);
  const nome = voce ? tr(voce[1], voce[2]) : verso;
  bottone.textContent = SG().t
    ? SG().t("mode.back", { mode: nome }) : `↔ ${nome}`;
  bottone.setAttribute("aria-label", bottone.textContent);
  bottone.dataset.mode = verso;
}

function setMode(mode) {
  state.mode = mode;
  $("surface").dataset.sgMode = mode;
  placeControls(mode);
  paintThumbbar();
  $("sidenav").dataset.open = "false";
  $("nav-onepage").hidden = mode !== "desktop";
  paintModes();
  if (state.def) draw();
}

/* ── le schede che il nodo serve ─────────────────────────────────────────── */

async function loadSchede() {
  const host = $("nav-schede");
  host.replaceChildren();
  let listing;
  try {
    const answer = await fetch(`${SG().node}/v1/schede`,
                               { headers: { Accept: "application/json" } });
    listing = await answer.json();
    try { localStorage.setItem("sg.schede.v1", JSON.stringify(listing)); }
    catch { /* full */ }
  } catch {
    // Offline: quello che il telefono ha già visto. E se non ha visto niente,
    // lo dice — non finge una lista.
    try { listing = JSON.parse(localStorage.getItem("sg.schede.v1") || "null"); }
    catch { listing = null; }
  }
  if (!listing || !listing.schede || !listing.schede.length) {
    host.append(Object.assign(document.createElement("p"), {
      className: "help",
      textContent: listing
        ? tr("schede.none", "This node serves no sheets.")
        : tr("schede.noCache",
             "No sheet in the cache: the first time needs a connection."),
    }));
    return;
  }
  // UNA VOCE PER DEFINIZIONE, dalla lista. È il vincolo del §3: una
  // definizione nuova compare perché il NODO la dichiara, senza che questo
  // file la conosca. Non c'è un elenco di schede in questo codice.
  for (const item of listing.schede) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "navitem";
    button.dataset.scheda = item.id;
    button.textContent = item.id;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = `${item.recorded_in.trench}/${item.fields}`;
    count.title = tr("schede.countTitle", "trench fields out of all fields");
    button.append(count);
    button.addEventListener("click", () => openScheda(item.id));
    host.append(button);
  }
}

/* ── aprire una scheda ───────────────────────────────────────────────────── */

/* LA LINGUA DELLA SCHEDA non è quella dell'interfaccia (nota dell'xlsx: «from
 * the sheet definition, not the UI»). Una definizione dichiara le sue lingue e
 * una lingua che non ha è un rifiuto (SPEC §1.5): quindi si chiede quella già
 * scelta per QUESTA scheda, poi quella dell'interfaccia se la definizione la
 * ha, poi la prima che la definizione dichiara. Prima di stanotte si chiedeva
 * sempre la lingua dell'interfaccia, e la ficha spagnola (es · it) con
 * l'interfaccia in inglese diceva «non ho la definizione». */
function cardLanguageFor(id, wanted) {
  let declared = [];
  try {
    const listing = JSON.parse(localStorage.getItem("sg.schede.v1") || "null");
    const item = ((listing && listing.schede) || []).find((x) => x.id === id);
    declared = (item && item.languages) || [];
  } catch { /* nessuna lista: si prova con la lingua dell'interfaccia */ }
  const ui = SG().locale || "it";
  if (wanted && (!declared.length || declared.includes(wanted))) return wanted;
  if (state.def && state.def.id === id && state.def.lang) return state.def.lang;
  if (!declared.length || declared.includes(ui)) return ui;
  return declared[0];
}

async function openScheda(id, su = null, lang = null) {
  const says = $("scheda-says");
  // LA STANZA SI RILEGGE a ogni apertura, insieme alla definizione: il
  // completamento delle unità, «da compilare» e ‹ › guardano quello che c'è
  // ADESSO, non quello che c'era quando la pagina è partita.
  const reading = loadRoom();
  state.panel = "scheda";
  $("scheda").hidden = false;
  $("work").hidden = true;
  $("index").hidden = true;
  says.hidden = true;
  markNav(id);
  try {
    const { def, from } = await definitionFor(id, cardLanguageFor(id, lang));
    // CAMBIARE SCHEDA SVUOTA CIÒ CHE C'ERA, e non è pulizia: i campi di uno
    // standard non sono i campi di un altro. Trovato nel giro offline —
    // aprendo prima la scheda ungherese e poi la US ICCD, il payload in coda
    // portava `ertelmezes`, che l'ICCD non ha. `POST /v1/scheda` lo avrebbe
    // rifiutato al momento della consegna (ed è giusto che lo faccia), ma la
    // scheda sarebbe rimasta in coda a fallire per sempre.
    //
    // Ricaricare la STESSA scheda invece non perde niente: è la stessa scheda.
    if (!state.def || state.def.id !== def.id) {
      state.values = {};
      state.loaded = new Set();
      state.authored = {};
      state.validated = new Set();
      state.us = "";
      state.model = "";
      state.selected = null;
      // …E UNA SCHEDA SENZA UNITÀ È NUOVA. Trovato il 22 ottobre: aperta la
      // US 3020 (esistente, `create` falso) e poi un'altra definizione vuota,
      // `create` restava falso e il primo salvataggio tornava «non posso
      // aggiornare una scheda che non esiste». C'era già prima, dalla colonna;
      // il salto per indirizzo lo rendeva facile da incontrare.
      if (!su) state.create = true;
    }
    if (!state.def || state.def.id !== def.id || su) state.dirty = false;
    state.def = def;
    state.keyField = keyField(def);
    state.step = 0;
    // APERTA SU UN'UNITÀ CHE ESISTE GIÀ: il numero non si riscrive a memoria, e
    // `create` è falso perché l'atto è correggere e non inventare. È la
    // differenza che `update_su` esiste per tenere: un `add_node` su un id che
    // non c'è lo CREA, quindi un numero sbagliato diventerebbe una US nuova.
    if (su && su.us) {
      state.us = String(su.us);
      state.create = false;
      // IL RITORNO (19 ottobre): i valori si RILEGGONO dal grafo, attraverso
      // la stessa ricetta che li ha scritti. Fino a ieri una scheda riaperta
      // mostrava solo il numero — e quello che il browser ricordava.
      const reread = await refill(def, String(su.us));
      if (reread && reread.other && !su.reread) {
        // l'unità dice di essere stata compilata con un'ALTRA definizione: si
        // riapre con quella, perché le sue caselle non sono queste
        return openScheda(reread.other, { ...su, reread: true }, lang);
      }
      if (reread && reread.note) {
        says.hidden = false;
        says.textContent = reread.note;
      }
    }
    if (from === "cache") {
      says.hidden = false;
      says.textContent = "Definizione dalla cache: il nodo non risponde, " +
        "ma questa scheda l'avevi già aperta.";
    }
    await reading;
    draw();
    writeHash(def.id, state.us);
  } catch (err) {
    // LA DEFINIZIONE CHE IL TELEFONO NON HA MAI VISTO E NON PUÒ SCARICARE **SI
    // DICE**. Improvvisare un modulo per una scheda di cui non si conoscono le
    // etichette sarebbe inventare uno standard.
    state.def = null;
    $("scheda-host").replaceChildren();
    paintStrip();
    paintThumbbar();
    says.hidden = false;
    says.textContent = tr("scheda.noDefinition",
      `I do not have the definition of «${id}».`, { id });
  }
}

/** I valori di un'unità, riletti dal nodo (`GET /v1/scheda/{id}/unita`).
 *
 *  Riempie `state.values` e l'autorialità con ciò che il GRAFO dice, e ricorda
 *  quali caselle erano piene (`state.loaded`): una casella riletta e poi
 *  svuotata va mandata come `null`, altrimenti salvare non la svuoterebbe mai.
 *  Torna `{other}` se l'unità dichiara un'altra definizione, `{note}` se c'è
 *  qualcosa da dire, `null` se il nodo non risponde (e allora la scheda si
 *  apre col solo numero, e lo si dice). */
async function refill(def, us) {
  const seam = SG();
  state.values = {};
  state.authored = {};
  state.validated = new Set();
  state.loaded = new Set();
  if (state.keyField) state.values[state.keyField] = us;
  let read;
  try {
    const path = `/v1/scheda/${encodeURIComponent(def.id)}/unita?us=${encodeURIComponent(us)}`;
    // chi E DOVE, col token rinnovato (`SG.request`); il ripiego è per un
    // modulo caricato senza la pagina
    const answer = seam.request
      ? await seam.request(path, {})
      : await fetch(`${seam.node || ""}${path}`,
                    { headers: seam.token ? { Authorization: "Bearer " + seam.token } : {} });
    if (!answer.ok) {
      return { note: tr("scheda.noReread", `US ${us}: ${answer.status}`,
                        { us, status: answer.status }) };
    }
    read = await answer.json();
  } catch {
    return { note: tr("scheda.nodeSilent", `US ${us}: no answer`, { us }) };
  }
  const withId = read.read_with && read.read_with.template;
  if (withId && withId !== def.id) return { other: withId };
  for (const [key, value] of Object.entries(read.values || {})) {
    state.values[key] = value;
    state.loaded.add(key);
  }
  for (const [key, who] of Object.entries(read.authored_by || {})) {
    if (who === "ai") state.authored[key] = "ai";
  }
  for (const key of read.validated || []) state.validated.add(key);
  return read.note ? { note: read.note } : {};
}

function markNav(id) {
  for (const item of document.querySelectorAll(".sidenav .navitem")) {
    item.setAttribute("aria-current",
                      String(item.dataset.scheda === id));
  }
}

/* QUALE VISTA, in un posto: il Foglio sulle soglie grandi quando è scelto e la
 * definizione ne dichiara uno; altrimenti i Campi. Il telefono non ha foglio. */
const sheetActive = () => state.mode !== "phone" && state.view === "sheet"
  && hasSheet(state.def);

/* LE TRE OPZIONI DEL FOGLIO, dalla postura: `optionsFor` è pura e vive in
 * foglio.js, fuori dal disegno. Qui si passano soltanto le scelte fatte. */
const sheetOptions = () => optionsFor(posture(), {
  faces: state.faces, side: state.fieldSide, trenchOnly: state.trenchOnly,
});

function draw() {
  const host = $("scheda-host");
  paintStrip();
  if (sheetActive()) {
    drawSheet(host, state.def, state, sheetOptions());
  } else {
    render(host, state.def, state);
    // FOGLIO CHIESTO, FOGLIO CHE NON C'È: si dice, e si mostrano i campi. Un
    // foglio vuoto sembrerebbe uno standard senza caselle.
    if (state.mode !== "phone" && state.view === "sheet") {
      const note = document.createElement("p");
      note.className = "saysit";
      note.dataset.why = "no-sheet";
      note.textContent = SG().t ? SG().t("view.sheet.none") : "";
      host.prepend(note);
    }
  }
  paintThumbbar();
  const shown = state.mode === "phone" && !state.showAll
    ? trenchFields(state.def) : state.def.fields;
  $("nav-all-count").textContent =
    `${shown.length}/${state.def.fields.length}`;
  $("nav-all").setAttribute("aria-pressed", String(state.showAll));
}

/* ── IN SOLA LETTURA (25 ottobre) ─────────────────────────────────────────────
 *
 * Un viewer apre una scheda e LEGGE: le caselle ci sono, e non si scrivono.
 * Non è la regola — la regola è della stanza, che rifiuterebbe comunque — è
 * l'interfaccia che non promette quello che non può dare. Un osservatore sul
 * `#scheda-host` perché la scheda si ridisegna da sé (il pannello del Foglio,
 * i widget, le righe aggiunte): bloccare una volta sola dopo `draw()` lascerebbe
 * aperte le caselle che nascono dopo. «Salva» e «Svuota» li toglie il CSS
 * (`data-access="read"`). */
function lockForReading(host) {
  if (!host || !SG().readOnly) return;
  for (const box of host.querySelectorAll("input, textarea")) {
    if (!box.readOnly) box.readOnly = true;
  }
  for (const control of host.querySelectorAll(
      "select, button:not(.fo-corner):not(.fo-struct)")) {
    if (!control.disabled) control.disabled = true;
  }
  for (const editable of host.querySelectorAll("[contenteditable='true']")) {
    editable.setAttribute("contenteditable", "false");
  }
}

let readingWatch = null;
function watchReading() {
  const host = $("scheda-host");
  if (!host) return;
  if (SG().readOnly && !readingWatch) {
    readingWatch = new MutationObserver(() => lockForReading(host));
    readingWatch.observe(host, { childList: true, subtree: true });
    lockForReading(host);
  } else if (!SG().readOnly && readingWatch) {
    readingWatch.disconnect();
    readingWatch = null;
    if (state.def) draw();             // di nuovo scrivibili: si ridisegna
  }
}

function paintCompleteness() {
  if (!state.def) return;
  const here = document.querySelector("#scheda-unav .unav-here");
  if (here) here.textContent = `${unitPrefix(state.def)}${state.us || "…"}`;
  if (sheetActive()) refreshSheet($("scheda-host"), state.def, state);
  else refreshCompleteness($("scheda-host"), state.def, state);
}

/* ── la fascia comandi della scheda ────────────────────────────────────────
 *
 * Come nel mockup, sotto la riga delle sezioni: «Lingua della scheda», «Vista»
 * e, con il Foglio, «Facciate». In campo «Facciate» diventa «Facciata» (una per
 * volta) e compare «Solo i campi da trincea». Sul telefono niente: là non c'è
 * foglio e non ci sono comandi nuovi.
 *
 * I testi vengono dal dizionario (`STRINGS`, chiavi dell'xlsx del WP1); le
 * lingue della scheda vengono dalla DEFINIZIONE e si scrivono come codici,
 * perché sono le sue. */
function paintStrip() {
  const strip = $("scheda-strip");
  if (!strip) return;
  strip.replaceChildren();
  strip.hidden = state.mode === "phone" || !state.def;
  if (strip.hidden) return;
  const t = (key) => (SG().t ? SG().t(key) : key);
  const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);

  const control = (labelKey, name, items, current, pick) => {
    const box = make("div", { className: "fo-ctl" });
    box.dataset.ctl = name;
    const label = make("span", { className: "fo-ctl-label", textContent: t(labelKey) });
    label.id = `ctl-${name}`;
    const seg = make("span", { className: "fo-seg" });
    seg.setAttribute("role", "group");
    seg.setAttribute("aria-labelledby", label.id);
    for (const [value, text, disabled] of items) {
      const button = make("button", { type: "button", textContent: text });
      button.dataset.value = value;
      button.setAttribute("aria-pressed", String(value === current));
      if (disabled) button.disabled = true;
      button.addEventListener("click", () => pick(value));
      seg.append(button);
    }
    box.append(label, seg);
    strip.append(box);
  };

  const def = state.def;
  if ((def.languages || []).length > 1) {
    control("ctl.cardlang", "cardlang",
      def.languages.map((l) => [l, l]), def.lang,
      (l) => { if (l !== def.lang) void openScheda(def.id, null, l); });
  }
  control("ctl.view", "view",
    [["sheet", t("view.sheet"), !hasSheet(def)], ["fields", t("view.fields")]],
    hasSheet(def) ? state.view : "fields",
    (v) => { state.view = v; draw(); });
  if (!sheetActive()) return;

  if (posture() === "field") {
    control("f.side", "side",
      [["recto", t("faces.recto")], ["verso", t("faces.verso")]],
      state.fieldSide, (v) => { state.fieldSide = v; draw(); });
    const box = make("div", { className: "fo-ctl" });
    box.dataset.ctl = "trench";
    const toggle = make("button", { type: "button", className: "fo-toggle",
                                    textContent: t("f.trench_only") });
    toggle.setAttribute("aria-pressed", String(state.trenchOnly));
    toggle.addEventListener("click", () => {
      state.trenchOnly = !state.trenchOnly;
      draw();
    });
    box.append(toggle);
    strip.append(box);
  } else {
    control("ctl.faces", "faces",
      [["both", t("faces.both")], ["recto", t("faces.recto")],
       ["verso", t("faces.verso")]],
      state.faces, (v) => { state.faces = v; draw(); });
  }
}

/* ── MUOVERSI FRA LE UNITÀ senza tornare all'elenco (22 ottobre) ───────────
 *
 * E.D., 27 settembre: «da dentro la scheda US poter cercare le altre per
 * saltarvi dentro per numero, oppure andare alla prossima o alla precedente».
 * Tre gesti, una via: `goUnit`. L'ordine è quello NUMERICO delle unità della
 * stanza (`orderedUnits`), il salto accetta il numero o la definizione, e ‹ ›
 * si fermano ai due estremi invece di ricominciare dall'altro capo — arrivare
 * in fondo si deve vedere.
 *
 * CAMBIARE UNITÀ NON PERDE NIENTE. Chiudere una scheda oggi la lascia in
 * memoria; cambiare unità invece ne rilegge un'altra, quindi quello che non è
 * ancora partito parte PRIMA (`save`, cioè la stanza o la coda). Una scheda
 * che non si può salvare — senza numero — non si lascia: lo dice `save`.
 *
 * La vista, la lingua della scheda e le facciate restano: sono stato di questa
 * superficie, non dell'unità. */

async function leaveUnit() {
  if (!state.dirty || !state.def) return true;
  if (document.activeElement && $("scheda").contains(document.activeElement)) {
    document.activeElement.blur();
  }
  await save(state.def, state);
  return !state.dirty;
}

/** Il numero o la definizione di un'unità della stanza → l'unità, o null. */
function unitFor(asked) {
  const said = String(asked || "").trim();
  if (!said || !state.def) return null;
  const units = orderedUnits();
  const number = bareNumber(said, state.def);
  const exact = units.find((u) => u.number === number);
  if (exact) return exact;
  const q = said.toLowerCase();
  const byWords = units.filter((u) =>
    String(u.definition || "").toLowerCase().includes(q)
    || String(u.name || "").toLowerCase() === q);
  return byWords.length === 1 ? byWords[0] : null;
}

async function goUnit(asked) {
  if (!state.def) return false;
  const found = unitFor(asked);
  if (!found) {
    const t = SG().t || ((k) => k);
    SG().show(false, `${t("nav.no_unit")} ${bareNumber(asked, state.def)}.`, "",
              SG().locale);
    return false;
  }
  if (found.number === state.us && !state.create) return true;
  if (!(await leaveUnit())) return false;
  await openScheda(state.def.id, { us: found.number }, state.def.lang);
  return true;
}

async function stepUnit(delta) {
  const order = orderedUnits();
  if (!order.length || !state.def) return false;
  const at = order.findIndex((u) => u.number === state.us);
  const target = at < 0 ? (delta > 0 ? order[0] : order[order.length - 1])
    : order[at + delta];
  if (!target) return false;             // un estremo: ci si ferma
  return goUnit(target.number);
}

const TEXTY = new Set(["text", "search", "number", "email", "url", "tel",
                       "password", "date", "datetime-local", "time", ""]);
function typing(target) {
  if (!target || !target.tagName) return false;
  if (target.isContentEditable || target.tagName === "TEXTAREA") return true;
  return target.tagName === "INPUT"
    && TEXTY.has(String(target.getAttribute("type") || "").toLowerCase());
}

function paintUnav() {
  const bar = $("scheda-unav");
  if (!bar) return;
  bar.hidden = !state.def || state.panel !== "scheda";
  bar.replaceChildren();
  if (bar.hidden) return;
  const t = SG().t || ((k) => k);
  const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);
  bar.classList.toggle("big", state.mode === "phone");
  const order = orderedUnits();
  const at = order.findIndex((u) => u.number === state.us);

  const arrow = (delta, glyph, key) => {
    const b = make("button", { type: "button", textContent: glyph });
    b.dataset.unav = String(delta);
    b.setAttribute("aria-label", t(key));
    b.title = t(key);
    // AGLI ESTREMI il bottone c'è e non fa niente, e lo dice
    b.disabled = !order.length
      || (at >= 0 && !order[at + delta]);
    b.addEventListener("click", () => { void stepUnit(delta); });
    return b;
  };
  const here = make("span", { className: "unav-here",
                              textContent: `${unitPrefix(state.def)}${state.us || "…"}` });
  const listId = "unav-units";
  const jump = make("input", { type: "text", placeholder: t("nav.jump"),
                               autocomplete: "off" });
  jump.setAttribute("list", listId);
  jump.setAttribute("aria-label", t("nav.jump"));
  jump.setAttribute("enterkeyhint", "go");
  const options = make("datalist", { id: listId });
  for (const u of order) {
    const o = make("option", { value: u.number });
    o.label = u.definition || u.name || "";
    options.append(o);
  }
  let going = false;
  const go = async () => {
    if (going || !jump.value.trim()) return;
    going = true;
    const ok = await goUnit(jump.value);
    going = false;
    if (!ok) { jump.select(); }
  };
  jump.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); void go(); }
  });
  // SCEGLIERE DAL COMPLETAMENTO È SALTARE: il browser mette il valore senza un
  // tasto (`insertReplacementText`, o nessun `inputType`), e un secondo gesto
  // sarebbe un gesto in più con i guanti.
  jump.addEventListener("input", (event) => {
    if (!event.inputType || event.inputType === "insertReplacementText") {
      if (order.some((u) => u.number === jump.value.trim())) void go();
    }
  });
  bar.append(arrow(-1, "‹", "nav.prev_unit"), here, jump, options,
             arrow(1, "›", "nav.next_unit"));
}

/* ── L'UNITÀ NELL'INDIRIZZO ──────────────────────────────────────────────────
 *
 * `#scheda=<definizione>&us=<numero>`, così avanti/indietro del browser e un
 * link riaprono la stessa scheda; `#unita` è l'elenco. Nell'hash e non nella
 * query: la query è del link della stanza (`?server=…&room=…`, `arrivo.js`),
 * e cambiarla ricaricherebbe la pagina. Un numero, non un nome: un link non
 * porta mai il valore di una casella. */
function hashFor(id, number) {
  const p = new URLSearchParams();
  p.set("scheda", id);
  if (number) p.set("us", number);
  return `#${p.toString()}`;
}

function writeHash(id, number, replace = false) {
  const want = hashFor(id, number);
  if (window.location.hash === want) return;
  if (replace) history.replaceState(null, "", want);
  else history.pushState(null, "", want);
}

function readHash() {
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "unita") return { index: true };
  const p = new URLSearchParams(raw);
  return { scheda: p.get("scheda") || "", us: p.get("us") || "" };
}

async function followHash() {
  const asked = readHash();
  if (asked.index) { await showIndex(false); return; }
  if (!asked.scheda) return;
  const same = state.def && state.def.id === asked.scheda
    && state.panel === "scheda" && (state.us || "") === asked.us;
  if (same) return;
  if (!(await leaveUnit())) return;
  if (!asked.us && state.def && state.def.id === asked.scheda && state.us) {
    // DA UN'UNITÀ A UNA SCHEDA NUOVA: la stessa definizione, ma non gli stessi
    // valori — riaprirla «com'era» porterebbe i valori di un'altra unità.
    clearScheda();
    state.us = "";
    state.create = true;
  }
  await openScheda(asked.scheda, asked.us ? { us: asked.us } : null);
}

/** L'ELENCO, con i filtri com'erano (vivono in `indice.js`). */
async function showIndex(push = true) {
  state.panel = "index";
  $("work").hidden = true;
  $("scheda").hidden = true;
  $("index").hidden = false;
  markNav("");
  $("nav-voice").removeAttribute("aria-current");
  $("nav-units").setAttribute("aria-current", "true");
  paintThumbbar();
  if (push && window.location.hash !== "#unita") history.pushState(null, "", "#unita");
  await repaintIndex();
}

function afterSave(body) {
  // La stanza ora ha l'unità (o la coda ce l'ha): il completamento e ‹ › la
  // devono vedere, e una scheda NUOVA diventa, nell'indirizzo, la sua unità.
  if (state.def && body && body.us) writeHash(state.def.id, body.us, true);
  void loadRoom().then(() => paintUnav());
}

/* ── validare ────────────────────────────────────────────────────────────── */

async function validateField(field) {
  if (!state.us) {
    SG().show(false, "Serve il numero dell'unità per validare un campo.", "");
    return;
  }
  const ok = await SG().send("/v1/validate",
                             { us: state.us, fields: [field] }, "validate");
  if (ok !== false) {
    state.validated.add(field);
    draw();
  }
}

function clearScheda() {
  state.values = {};
  state.loaded = new Set();
  state.authored = {};
  state.validated = new Set();
  state.step = 0;
  if (state.def) draw();
}

/* ── il telefono: un campo per volta, coi pollici ────────────────────────── */

function wireThumbbar() {
  $("tb-nav").addEventListener("click", () => {
    const nav = $("sidenav");
    nav.dataset.open = nav.dataset.open === "true" ? "false" : "true";
  });
  $("tb-prev").addEventListener("click",
    () => stepTo($("scheda-host"), state, "prev"));
  $("tb-next").addEventListener("click",
    () => stepTo($("scheda-host"), state, "next"));
  $("tb-save").addEventListener("click", () => save(state.def, state));
  //  IL RITORNO: un tocco, e la scelta che si scrive porta questa finestra —
  //  così tornare non è un'eccezione temporanea ma una scelta come le altre.
  $("tb-back").addEventListener("click", () => {
    const verso = $("tb-back").dataset.mode;
    if (!verso) return;
    rememberMode(verso, window.innerWidth);
    setMode(verso);
  });
}

/* ── avvio ───────────────────────────────────────────────────────────────── */

function wireShell() {
  applyTheme(savedTheme());
  $("theme").addEventListener("click", () => {
    const now = savedTheme();
    applyTheme(THEMES[(THEMES.indexOf(now) + 1) % THEMES.length]);
  });

  $("nav-voice").addEventListener("click", () => {
    state.panel = "voice";
    $("scheda").hidden = true;
    $("index").hidden = true;
    $("work").hidden = false;
    paintThumbbar();
    markNav("");
    $("nav-voice").setAttribute("aria-current", "true");
  });

  $("nav-units").addEventListener("click", () => { void showIndex(); });
  $("nav-units").textContent = SG().t ? SG().t("nav.units") : "Units";

  // ‹ › DA TASTIERA: Alt+← / Alt+→, quando il fuoco non è in un campo di testo
  // (lì Alt+freccia sposta il cursore di una parola, ed è di chi scrive).
  document.addEventListener("keydown", (event) => {
    if (!event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    if (state.panel !== "scheda" || !state.def || typing(event.target)) return;
    event.preventDefault();
    // IN RTL «PRECEDENTE» STA A DESTRA: la freccia verso l'inizio della riga è
    // la freccia verso destra, come ‹ che il browser specchia da sé (è un
    // carattere Bidi_Mirrored). La barra è dell'interfaccia: la direzione è
    // quella del documento, non quella della scheda.
    const back = document.documentElement.dir === "rtl" ? "ArrowRight" : "ArrowLeft";
    void stepUnit(event.key === back ? -1 : 1);
  });
  // AVANTI E INDIETRO DEL BROWSER, e un link: l'indirizzo dice quale unità.
  window.addEventListener("hashchange", () => { void followHash(); });

  $("nav-all").addEventListener("click", () => {
    state.showAll = !state.showAll;
    state.step = 0;
    if (state.def) draw();
  });
  $("nav-onepage").addEventListener("click", () => {
    state.onePage = !state.onePage;
    $("nav-onepage").setAttribute("aria-pressed", String(state.onePage));
    if (state.def) draw();
  });

  wireThumbbar();

  // LE FOTO. Montate da qui e non dalla pagina perché è qui che si sa quale
  // scheda è aperta — e la scheda aperta è il CONTESTO da cui esce la
  // proposta. `proposeUs` è una funzione e non un valore: la proposta è quella
  // del momento in cui si tocca la miniatura, non quella dello scatto.
  repaintPhotos = mountPhotos({
    shoot: $("shoot"), camera: $("camera"), host: $("photos"),
    seam: SG(), proposeUs: () => state.us || "",
  });
  repaintPhotos();

  // DOVE SCRIVE IL NODO. Esposto su `window` perché a chiamarlo è `ping()`,
  // che vive nella pagina e non in un modulo: la conchiglia dichiara un seam
  // sola (`window.SG`) e questa è la sua controparte nell'altro verso.
  window.SGRoom = mountRoom($("nav-room"));
  // …e la POSTURA dallo stesso battito (vedi `takePosture`).
  window.SGPosture = takePosture;
  // COSA C'È GIÀ. `schede` è una funzione e non un valore: la lista delle
  // definizioni arriva dal nodo dopo l'avvio, e passarla adesso vorrebbe dire
  // passarne una vuota per sempre.
  repaintIndex = mountIndex({
    t: (k, v) => SG().t(k, v),
    openScheda,
    // la definizione aperta: su quanti campi si misura «meno della metà» per
    // un'unità che non dichiara con quale è stata compilata
    current: () => (state.def ? state.def.id : null),
    schede: () => {
      try { return (JSON.parse(localStorage.getItem("sg.schede.v1") || "null")
                    || {}).schede || []; } catch { return []; }
    },
  });
  //  IL SEAM E BASTA: la conchiglia dichiara `window.SG` e questo modulo non
  //  conosce altro. `t` e `show` vengono da lì, come per ogni altra superficie.
  window.SGChat = mountChat({ t: (k, v) => SG().t(k, v),
                              toast: (m) => SG().show(true, m) });

  // Il modo si RIPROPONE quando la finestra cambia, ma non sovrascrive una
  // scelta: `effectiveMode` guarda prima cosa è stato scelto.
  window.addEventListener("resize", () => {
    const wanted = effectiveMode(window.innerWidth);
    if (wanted !== state.mode) setMode(wanted);
    else paintModes();
  });

  setMode(effectiveMode(window.innerWidth));
}

/* ── SI ARRIVA DA UNA STANZA ───────────────────────────────────────────────
 *
 * Il link del server porta un posto — `?server=…&room=…` — e mai un modo. Fino
 * al 6 ottobre quei due parametri non li leggeva nessuno: chi arrivava da
 * `/em/rooms/` atterrava sul microfono e riscriveva a mano il nome della stanza
 * che era già nell'indirizzo.
 *
 * I tre esiti li decide `arrivalPlan`, che è pura e provata. Qui c'è solo cosa
 * si mostra, e la riga che conta è la terza: **ripuntare il nodo lo decide una
 * persona**. Farlo da soli vorrebbe dire togliere un nodo condiviso a chi ce
 * l'ha, in silenzio, per aver aperto un link.
 */
async function land() {
  const arrivo = readArrival(window.location.search);
  if (arrivo.refused.length) {
    // RIFIUTATO A VOCE, come fa `FORBIDDEN` in `app/handoff.py`: accettarne uno
    // insegna a chi ha costruito il link che mandarlo funziona.
    SG().show(false, SG().t("index.refused", { what: arrivo.refused.join(", ") }));
  }
  let salute = null;
  try {
    salute = await (await fetch(SG().node + "/health",
                                { cache: "no-store" })).json();
  } catch { /* il nodo non risponde: si resta dove si è, ed è onesto */ }
  // IL POSTO DI CHI È FIRMATO, se questa pagina ne ricorda uno; quello del nodo
  // altrimenti. Dal 25 ottobre non è la stessa cosa (`app/scrivani.py`).
  const mio = SG().where ? SG().where() : null;
  const piano = arrivalPlan(arrivo, (mio && mio.room) || roomOf(salute));
  if (piano.do === "nothing") return;

  if (piano.do === "offer") {
    // La colonna, aperta sul pannello che punta il nodo, con la stanza già
    // scritta: il gesto resta uno, e resta di chi lo fa.
    $("sidenav").dataset.open = "true";
    const campo = $("room-target");
    if (campo) campo.value = piano.server
      ? `${piano.server.replace(/\/+$/, "")}/open?room=${encodeURIComponent(piano.room)}`
      : piano.room;
    SG().show(true, SG().t("index.offer", { room: piano.room }));
    return;
  }

  await showIndex(false);
}

wireShell();
// L'ELENCO PRIMA DELL'INDIRIZZO: `cardLanguageFor` legge da lì le lingue che la
// scheda dichiara. Senza aspettarlo, un link `#scheda=…` aperto su un
// dispositivo nuovo chiedeva la definizione nella lingua dell'INTERFACCIA, e
// con l'interfaccia in `he` o `de` la US ICCD (it · en) veniva rifiutata: «non
// ho la definizione». Misurato il 24 ottobre; con `it` non si vedeva.
const schedeLoaded = loadSchede();
// L'INDIRIZZO VINCE sull'arrivo: un link a una scheda (`#scheda=…&us=…`) la
// riapre, anche se il link della stanza avrebbe mostrato l'elenco.
void land().then(() => schedeLoaded).then(() => followHash());

// Esposto per la verifica dal browser: è quello che una cattura non può
// dimostrare (dove stanno i bersagli, quale modo è attivo, quanti campi).
window.SGShell = { state, openScheda, setMode, draw, trenchFields, otherFields,
                   payloadFor, paintThumbbar, thumbbarPlan, land,
                   // FORZARE LA POSTURA, per provarla: «desk», «field», o null
                   // per tornare a quella che il nodo dice. Non si ricorda.
                   forcePosture: (p) => {
                     state.postureForced = p === "desk" || p === "field" ? p : null;
                     if (state.def) draw();
                   },
                   onAccess: () => watchReading(),
                   onLocale: () => {
                     $("nav-units").textContent = SG().t("nav.units");
                     paintModes();
                     paintWayBack();
                     if (state.def) draw();
                   },
                   goUnit: (n) => goUnit(n), stepUnit: (d) => stepUnit(d),
                   showIndex: () => showIndex(),
                   repaintPhotos: () => repaintPhotos(),
                   repaintIndex: () => repaintIndex() };
