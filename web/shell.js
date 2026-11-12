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
  datamodelNotice, definitionFor, effectiveMode, keyField, payloadFor, proposeMode,
  refreshCompleteness, rememberMode, render, save, stepTo, thumbbarPlan,
  trenchFields, otherFields, wayBack,
} from "./scheda.js";
import { drawSheet, hasSheet, optionsFor, paintInspector, refreshSheet } from "./foglio.js";
import { mount as mountPhotos } from "./photos.js";
import { mount as mountRoom, point as pointRoom, postureOf, roomOf } from "./room.js";
import { filters as indexFilters, isAsking as indexAsking, mount as mountIndex, standardName } from "./indice.js";
import { openIn, paintMap } from "./mappa.js";
import { arrivalPlan, readArrival } from "./arrivo.js";
import { loadRoom, numberOf, opensById, orderedUnits, unitFor, unitPrefix } from "./widgets.js";
import { mount as mountChat } from "./chat.js";
import { mount as mountDesk, openingSection, SECTION_KEY, sectionOf, sectionToKeep } from "./scrivania.js";
import { valueView } from "./widgets.js";
import { fieldStateLine, mount as mountField } from "./campo.js";

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
  // LA LENTE (26 ottobre): la stessa unità letta con la scheda di un ALTRO
  // standard. `null` quando no; altrimenti ciò che il nodo ha detto
  // (`lens`: con che cosa è stata scritta, quali caselle riempie, quali no).
  lens: null,
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
  // ── LA SCRIVANIA (14 novembre) ─────────────────────────────────────────────
  // Un'unità aperta DAL SUO ID (importata, senza numero): dal 15 novembre SI
  // SCRIVE dal suo id (`payloadFor` manda `node`), e la testata dice che il
  // numero manca, senza imporlo. L'indirizzo la dice con `nodo=`.
  nodeId: "",
  byId: false,
  // il NOME di un'unità aperta dal suo id (`1.US2`): si mostra al posto di
  // «US n»; `state.us` resta il numero, vuoto finché nessuno lo scrive
  unitName: "",
  // il numero che un'unità aperta dal suo id HA già: c'è solo se è anche di
  // un'altra unità (un conflitto), e allora si legge
  idNumber: "",
  // quante unità hanno la sua chiave (tipo, numero, area): più di una è un
  // conflitto, e un'unità aperta dal suo id allora si LEGGE (12 novembre)
  idConflict: 0,
  // Ciò che il nodo dice della descrizione dell'unità aperta: dove è stata
  // scritta e quante parole ha (`/v1/scheda/…/unita`), per «Dettata in trincea».
  unitInfo: null,
  // Dove il Foglio disegna il suo ispettore alla scrivania (la colonna di
  // destra della pagina); `null` altrove, e il pannello sta accanto al piano.
  inspHost: null,
  onRefine: (fieldId) => refine(fieldId),
  // QUALCOSA SCRITTO E NON ANCORA MANDATO (22 ottobre). Lo accende
  // `writeValue`, lo spegne `save()`: è ciò che decide se cambiare unità deve
  // salvare prima.
  dirty: false,
  // Dopo un salvataggio, mandato o in coda: la stanza ha un'unità in più, e
  // l'indirizzo impara il numero di una scheda nuova.
  onSaved: (sent, body) => afterSave(body),
  onChange: () => paintCompleteness(),
  // «1/25» non diceva cosa conta (SF-10): sono i campi, uno per volta
  onStep: (i, n) => {
    $("tb-step").textContent = n
      ? tr("step.of", `field ${i + 1} of ${n}`, { i: i + 1, n }) : "";
  },
  onValidate: (field) => validateField(field),
  onTranslate: (field) => translateField(field),
  // «VERIFICA» (dev28): firmare, nella stanza, ciò che aspetta una persona
  onVerify: (nodeId) => verifyNode(nodeId),
  review: [],
  unitId: "",
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
const posture = () => state.postureForced
  // LA POSTURA È L'INTERRUTTORE DELLA BARRA (14 novembre la scrivania, 15
  // novembre il campo): «Scrivania» vuol dire fronte e retro, «In campo» una
  // facciata per volta e «Solo i campi da trincea», come nel mockup. Prima in
  // campo valeva quella letta dal nodo (`seated`), e un tablet «in campo» su un
  // nodo seduto mostrava i comandi della scrivania: due cose dette in due modi.
  || (state.mode === "desktop" ? "desk" : "field");

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

/* ── QUALE PANNELLO È DAVANTI, in un posto (14 novembre) ─────────────────────
 *
 * Prima ogni funzione nascondeva gli altri per conto suo — `openScheda`,
 * `showIndex`, `showMap`, «Detta» — e una sezione nuova voleva dire quattro
 * righe in quattro posti. Adesso le sezioni sono sette e la riga è una. */
const PANELS = ["work", "scheda", "index", "map", "finds", "photos-sec", "excavation", "deliver"];

function only(panel) {
  for (const id of PANELS) {
    const node = $(id);
    if (!node) continue;
    // la voce («work») resta alla porta della firma: decide `render()` nella
    // pagina, che sa chi è firmato
    if (id === "work") node.hidden = panel !== "work" || !SG().signed;
    else node.hidden = id !== panel;
  }
  state.panel = panel === "work" ? "voice" : panel;
  keepSection();
  if (panel === "work") $("nav-voice").setAttribute("aria-current", "true");
  else $("nav-voice").removeAttribute("aria-current");
  for (const [id, p] of [["nav-units", "index"], ["nav-map", "map"]]) {
    if (state.panel === p) $(id).setAttribute("aria-current", "true");
    else $(id).removeAttribute("aria-current");
  }
  placeDesk();
}

/* ── DOVE SI APRE LA SCRIVANIA (MICRO, 14 novembre) ──────────────────────────
 *
 * Alla scrivania, all'avvio e passando da «In campo» a «Scrivania», la sezione è
 * la Scheda se ce n'è una aperta o un'unità toccata per ultima, altrimenti
 * Unità (`openingSection`, pura, in scrivania.js). «Detta» si apre solo
 * premendola. In campo non cambia niente: telefono e tablet partono su «Detta».
 *
 * `opened` dice che l'avvio è finito: prima, i pannelli li sceglie l'indirizzo o
 * il link della stanza, non una persona, e non si ricordano. */
let opened = false;

/** Ricorda la sezione scelta alla scrivania, sul dispositivo (try/catch come
 *  la lingua: una finestra privata la tiene per la sessione). */
function keepSection() {
  if (!opened || state.mode !== "desktop") return;
  const sec = sectionToKeep(state.panel);
  if (!sec) return;
  try { localStorage.setItem(SECTION_KEY, sec); } catch { /* private window */ }
}

/** Apri la scrivania sulla sua sezione. `useSaved`: all'avvio vale la scelta
 *  ricordata; passando da «In campo» no — si arriva al tavolo, non si ricarica. */
async function openDesk(useSaved) {
  if (state.mode !== "desktop") return;
  let saved = null;
  if (useSaved) {
    try { saved = localStorage.getItem(SECTION_KEY); } catch { saved = null; }
  }
  const hasDef = Boolean(state.def);
  const hasRecent = !hasDef && (((await loadRoom()) || {}).units || []).length > 0;
  const pick = openingSection({ saved, hasDef, hasRecent });
  if (state.mode !== "desktop") return;       // la finestra è cambiata intanto
  if (pick === "voice") { only("work"); paintThumbbar(); markNav(""); return; }
  await showSection(pick, false);
}

/* ── il modo ─────────────────────────────────────────────────────────────── */

function paintModes() {
  const proposed = proposeMode(viewWidth());
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
      rememberMode(value, viewWidth());
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
const MOVABLE = ["modes", "theme", "skin", "lang"];

/* DAL 31 OTTOBRE (D5) i controlli di aspetto stanno nel foglio «Tu e
 * l'aspetto», dietro le iniziali, su TUTTE le soglie: la barra in alto dice
 * stanza, stato e chi firma. Si spostano lì, non si copiano — uno stato per
 * controllo, come sempre. Senza il foglio (una pagina vecchia) tornano dove
 * erano. */
function placeControls(mode) {
  const home = $("me-controls")
    || (mode === "phone" ? $("nav-controls-host") : $("topbar-controls"));
  if ($("nav-controls")) $("nav-controls").hidden = true;
  for (const id of MOVABLE) {
    const node = $(id);
    if (!node) continue;
    // LA LINGUA DELL'INTERFACCIA STA NELLA BARRA (14 novembre alla scrivania, 15
    // novembre anche in campo, mockup v7.2): la si cambia guardando lo schermo,
    // non aprendo un foglio — e un dispositivo che passa di mano la cambia lì
    // …TRANNE SUL TELEFONO (MICRO il campo rifinito, 15 novembre): a 390 px la
    // barra è una riga sola come nel mockup — marchio e stanza, il numero da
    // consegnare, le iniziali — e il selettore non ci sta (misurato). Resta a
    // un tocco: nel foglio delle iniziali, il primo controllo.
    const target = id === "lang" && $("bar-lang") && mode !== "phone" ? $("bar-lang") : home;
    if (node.parentElement !== target) target.append(node);
  }
}

/* ── LA SCRIVANIA: i nodi che vi si SPOSTANO (14 novembre) ────────────────────
 *
 * Alla scrivania la striscia sotto le sezioni tiene l'unità ‹ › e i comandi
 * della scheda; la scelta della stanza sta sotto il nome della stanza nella
 * barra. Sono gli STESSI nodi della colonna e della scheda, spostati (come
 * `placeControls`): due copie sarebbero due stati. In campo tornano dov'erano. */
function placeDesk() {
  const desk = state.mode === "desktop";
  const move = (id, there) => {
    const node = $(id);
    if (node && there && node.parentElement !== there) there.append(node);
  };
  // LA SCELTA DELLA STANZA sta sotto il nome della stanza, nella barra, in
  // OGNI modo (15 novembre): in campo la colonna che la teneva non c'è più
  move("nav-room", $("room-pop-host"));
  if (desk) {
    move("scheda-unav", $("desk-strip-sheet"));
    move("scheda-strip", $("desk-strip-sheet"));
  } else {
    const scheda = $("scheda");
    if (scheda && $("scheda-unav") && $("scheda-unav").parentElement !== scheda) {
      scheda.prepend($("scheda-unav"), $("scheda-strip"));
    }
  }
  // LE QUATTRO VOCI IN CAMPO: in basso sul telefono (nella barra dei pollici),
  // in alto sul tablet e sugli schermi larghi. La stessa `<nav>`, spostata.
  const top = $("field-tabs-top");
  if (top) {
    top.hidden = state.mode !== "tablet";
    move("field-tabs", state.mode === "tablet" ? top : $("thumbbar"));
  }
  state.inspHost = desk && state.panel === "scheda" ? $("desk-insp") : null;
  $("surface").dataset.desk = desk ? "true" : "false";
  if (deskUI) deskUI.paint();
  if (fieldUI) fieldUI.paint();
}

/** LA POSTURA DI CHI SCRIVE, per il segno accanto alla descrizione: l'interruttore
 *  della barra. «Scrivania» è il modo da scrivania; telefono e tablet sono «In
 *  campo». È una dichiarazione, e il referto dice quanto vale. */
function writingPosture() {
  return state.mode === "desktop" ? "desk" : "trench";
}

/** SCRIVANIA / IN CAMPO dalla barra: una scelta come quella dei chip, scritta
 *  con la finestra su cui è fatta (`rememberMode`). In campo è il modo che la
 *  finestra propone fra telefono e tablet — su uno schermo da scrivania, il
 *  tablet. */
function choosePlace(place) {
  const width = viewWidth();
  const proposed = proposeMode(width);
  const mode = place === "desk" ? "desktop" : (proposed === "desktop" ? "tablet" : proposed);
  rememberMode(mode, width);
  setMode(mode);
}

let deskUI = null;
let fieldUI = null;

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
  // LE QUATTRO VOCI IN CAMPO (15 novembre, mockup v7.2): Detta · Scheda · Foto ·
  // Consegna, SEMPRE — anche dentro la scheda, sotto i passi, come nel mockup.
  // La colonna (☰) non c'è più: la stanza è nella barra, le definizioni nel menu
  // «Scheda», le soglie e «Esci» nel foglio delle iniziali, e il ritorno qui.
  $("thumbbar").dataset.tabs = String(plan.bar);
  paintWayBack();
  const back = $("tb-back");
  $("tb-steps").hidden = !plan.steps && !(back && !back.hidden);
  if (fieldUI) fieldUI.paintTabs();
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
  const verso = wayBack(state.mode, viewWidth());
  bottone.hidden = !verso;
  if (!verso) return;
  const voce = MODES.find(([value]) => value === verso);
  const nome = voce ? tr(voce[1], voce[2]) : verso;
  bottone.textContent = SG().t
    ? SG().t("mode.back", { mode: nome }) : `↔ ${nome}`;
  bottone.setAttribute("aria-label", bottone.textContent);
  bottone.dataset.mode = verso;
}

/* IL CASSETTO, aperto o chiuso, in UN posto (31 ottobre, iPhone vero: si
 * apriva da «Stanza» e non si chiudeva più — copriva la barra che lo apre). Sul
 * telefono ha un velo dietro, che chiude, e un «Chiudi» in cima; scegliere una
 * voce lo chiude da sé. */
function setNavOpen(open) {
  $("sidenav").dataset.open = open ? "true" : "false";
  const velo = $("nav-scrim");
  if (velo) velo.hidden = !(open && state.mode === "phone");
}

/** LA LARGHEZZA DELLO SCHERMO, non quella che il contenuto ha spinto.
 *  Misurato il 31 ottobre (iPhone vero, nodo irraggiungibile): la pastiglia
 *  «nodo assente · riprovo fra 5 s · 1 in coda», che non va a capo, allargava
 *  la pagina; un browser da telefono allora allarga la finestra di layout
 *  (`innerWidth` 700 su uno schermo da 390), la soglia diceva «tablet» e il
 *  telefono perdeva barra e cassetto. Lo schermo è il tetto. */
function viewWidth() {
  //  iOS dice lo schermo sempre in verticale: in orizzontale vale il lato lungo
  const sc = window.screen || {};
  const sides = [sc.width || Infinity, sc.height || Infinity];
  const landscape = window.matchMedia
    && window.matchMedia("(orientation: landscape)").matches;
  const screenWide = landscape ? Math.max(...sides) : Math.min(...sides);
  return Math.min(window.innerWidth, screenWide);
}

function setMode(mode) {
  const was = state.mode;
  state.mode = mode;
  $("surface").dataset.sgMode = mode;
  placeControls(mode);
  placeDesk();
  paintThumbbar();
  setNavOpen(false);
  $("nav-onepage").hidden = mode !== "desktop";
  paintModes();
  if (state.def) draw();
  // la pastiglia dice cose diverse alla scrivania e in campo
  if (was !== mode && SG().paintState) SG().paintState();
  // DA «IN CAMPO» A «SCRIVANIA» con «Detta» davanti: la scrivania si apre sulla
  // sua sezione. Una sezione già scelta in campo (Unità, la Scheda) resta.
  if (opened && was !== "desktop" && mode === "desktop" && state.panel === "voice") {
    void openDesk(false);
  }
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
    // IL NOME PER PERSONE, e i numeri detti in una frase (SF-06): «25/59» non
    // lo spiegava nessuno. L'identificativo resta nel suggerimento.
    button.textContent = standardName(item, SG().locale);
    button.title = item.id;
    const count = document.createElement("span");
    count.className = "indice-cosa";
    count.textContent = tr("schede.count",
                           `${item.recorded_in.trench} in the trench of ${item.fields}`,
                           { t: item.recorded_in.trench, n: item.fields });
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
  only("scheda");
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
      state.nodeId = "";
      state.byId = false;
      state.unitName = "";
      state.idNumber = "";
      state.idConflict = 0;
      state.unitInfo = null;
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
    if (su && su.node && !su.us) {
      // DAL SUO ID (14 novembre): un'unità importata senza un numero si apre lo
      // stesso, e dal 15 novembre SI SCRIVE dal suo id: il numero è buona
      // pratica, non un obbligo, e non si indovina. La testata lo dice
      // (`paintNoNumber`). Si LEGGE soltanto se il numero che ha è anche di
      // un'altra unità: quello è un conflitto. L'indirizzo la dice con `nodo=`.
      state.create = false;
      const reread = await refill(def, "", Boolean(su.lens), su.node);
      if (reread && reread.other && !su.reread) {
        return openScheda(reread.other, { ...su, reread: true }, lang);
      }
      const note = state.idConflict ? tr("unit.conflict_read", "") : "";
      const said = [note, reread && reread.note].filter(Boolean).join(" ");
      if (said) {
        says.hidden = false;
        says.textContent = said;
      }
    } else if (su && su.us) {
      state.us = String(su.us);
      state.create = false;
      // IL RITORNO (19 ottobre): i valori si RILEGGONO dal grafo, attraverso
      // la stessa ricetta che li ha scritti. Fino a ieri una scheda riaperta
      // mostrava solo il numero — e quello che il browser ricordava.
      const reread = await refill(def, String(su.us), Boolean(su.lens));
      if (reread && reread.other && !su.reread) {
        // l'unità dice di essere stata compilata con un'ALTRA definizione: si
        // riapre con quella, perché le sue caselle non sono queste
        return openScheda(reread.other, { ...su, reread: true }, lang);
      }
      if (reread && reread.note) {
        says.hidden = false;
        says.textContent = reread.note;
      }
    } else {
      state.lens = null;
      state.nodeId = "";
      state.byId = false;
      state.unitName = "";
      state.idNumber = "";
      state.idConflict = 0;
      state.unitInfo = null;
    }
    if (from === "cache") {
      says.hidden = false;
      says.textContent = "Definizione dalla cache: il nodo non risponde, " +
        "ma questa scheda l'avevi già aperta.";
    }
    await reading;
    draw();
    if (deskUI) deskUI.paint();
    writeHash(def.id, state.us, false, Boolean(state.lens), state.byId ? state.nodeId : "");
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
async function refill(def, us, lens = false, node = "") {
  const seam = SG();
  state.lens = null;
  state.byId = Boolean(node && !us);
  state.nodeId = node || "";
  state.unitName = "";
  state.idNumber = "";
  state.idConflict = 0;
  state.unitInfo = null;
  state.values = {};
  state.authored = {};
  state.validated = new Set();
  state.loaded = new Set();
  if (state.keyField) state.values[state.keyField] = us;
  let read;
  try {
    const path = `/v1/scheda/${encodeURIComponent(def.id)}/unita?`
      + (us ? `us=${encodeURIComponent(us)}` : `node=${encodeURIComponent(node)}`)
      + (lens ? "&lente=1" : "");
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
  if (lens && read.lens) state.lens = read.lens;
  for (const [key, value] of Object.entries(read.values || {})) {
    state.values[key] = value;
    state.loaded.add(key);
  }
  for (const [key, who] of Object.entries(read.authored_by || {})) {
    if (who === "ai") state.authored[key] = "ai";
  }
  for (const key of read.validated || []) state.validated.add(key);
  state.unitId = read.node_id || "";
  if (state.byId) {
    // IL NOME si mostra, IL NUMERO resta il numero: vuoto se l'unità non ne
    // ha (la casella dell'identità non mostra il nome come se fosse un numero)
    // «US 2 · area 1» per un nome dell'importer (il nodo lo dice), il nome
    // altrimenti
    state.unitName = read.label || read.name || "";
    state.idNumber = String(read.number || "");
    state.idConflict = Number(read.conflict || 0);
    state.us = state.idNumber;
    if (state.keyField) {
      state.values[state.keyField] = state.idNumber;
      state.loaded.delete(state.keyField);
    }
  }
  // DOVE È STATA SCRITTA LA DESCRIZIONE, e quanto: il riquadro dell'ispettore
  state.unitInfo = { written_in: read.written_in || null, words: read.words || 0,
                     to_refine: Boolean(read.to_refine),
                     description_field: read.description_field || null };
  void loadReview();
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
  state.inspHost = state.mode === "desktop" && state.panel === "scheda" ? $("desk-insp") : null;
  paintStrip();
  if (state.mode === "desktop" && state.view === "unit") {
    // LA VISTA «UNITÀ» (14 novembre, mockup v7.2): la pagina dell'unità, in
    // lettura — ciò che il grafo dice, senza le caselle vuote
    drawUnitPage(host);
    paintDeskInspector();
  } else if (sheetActive()) {
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
    paintDeskInspector();
  }
  paintLens(host);
  paintThumbbar();
  const shown = state.mode === "phone" && !state.showAll
    ? trenchFields(state.def) : state.def.fields;
  $("nav-all-count").textContent =
    `${shown.length}/${state.def.fields.length}`;
  $("nav-all").setAttribute("aria-pressed", String(state.showAll));
}

/* ── LA LENTE (26 ottobre) ─────────────────────────────────────────────────────
 *
 * Una lente non disegna niente di suo: la scheda è quella di sempre, del suo
 * standard. Dopo il disegno si dice che cosa il grafo ha riempito e che cosa
 * no — `lens.holes` dal nodo, non ricalcolato qui — e le caselle vuote si
 * TRATTEGGIANO: il buco è il dato che la lente è venuta a mostrare. */
function paintLens(host) {
  document.documentElement.dataset.lens = state.lens ? "on" : "off";
  if (!state.lens) {
    if (readingWatch && !SG().readOnly) watchReading();   // lente chiusa: di nuovo scrivibile
    return;
  }
  const holes = new Set(state.lens.holes || []);
  for (const box of host.querySelectorAll("[data-field]")) {
    box.classList.toggle("lens-hole", holes.has(box.dataset.field));
  }
  const says = $("scheda-says");
  const written = state.lens.written_with;
  says.hidden = false;
  says.dataset.why = "lens";
  says.textContent = tr("lens.says", "", {
    us: state.us,
    written: written ? `${written.template} ${written.version || ""}`.trim() : "—",
    read: `${state.def.id} ${state.def.version || ""}`.trim(),
    filled: String((state.lens.filled || []).length),
    holes: String(holes.size),
  });
  // (28 settembre) ciò che l'unità dice e nessuna casella legge — una US ICCD
  // 1.0.2 riletta con la 2.0.0 porta `formation_mode`: detto, non perso
  const unread = state.lens.unread || [];
  if (unread.length) {
    says.textContent += " " + tr("lens.unread", "", {
      n: String(unread.length),
      list: unread.map((u) => `${u.property} = ${u.value ?? "—"}`
        + (u.field ? ` (${u.field})` : "")).join("; "),
    });
  }
  watchReading();
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
/* …E LA LENTE LEGGE SOLTANTO: le caselle di uno standard non si riscrivono su
 * un'unità compilata con un altro. Stesso blocco, stessa ragione. */
const reading = () => Boolean(SG().readOnly || state.lens
  // dal suo id si scrive (15 novembre); si legge solo un'unità in conflitto
  || (state.byId && state.idConflict));

function lockForReading(host) {
  if (!host || !reading()) return;
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
  if (reading() && !readingWatch) {
    readingWatch = new MutationObserver(() => lockForReading(host));
    readingWatch.observe(host, { childList: true, subtree: true });
    lockForReading(host);
  } else if (!reading() && readingWatch) {
    readingWatch.disconnect();
    readingWatch = null;
    if (state.def) draw();             // di nuovo scrivibili: si ridisegna
  }
}

function paintCompleteness() {
  if (!state.def) return;
  const here = document.querySelector("#scheda-unav .unav-here");
  if (here) here.textContent = state.byId ? state.unitName
    : `${unitPrefix(state.def)}${state.us || "…"}`;
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
/** «SOLO I CAMPI DA TRINCEA», in campo: sul Foglio attenua gli altri, sul
 *  telefono decide quali campi si percorrono (il «Tutti i campi» di prima, al
 *  contrario). Uno stato per la scelta, letto da tutte e due le strade. */
function trenchToggle() {
  const box = document.createElement("div");
  box.className = "fo-ctl";
  box.dataset.ctl = "trench";
  const toggle = Object.assign(document.createElement("button"), {
    type: "button", className: "fo-toggle", textContent: tr("f.trench_only", "Trench fields only") });
  toggle.setAttribute("aria-pressed", String(state.trenchOnly));
  toggle.addEventListener("click", () => {
    state.trenchOnly = !state.trenchOnly;
    state.showAll = !state.trenchOnly;
    state.step = 0;
    draw();
  });
  box.append(toggle);
  return box;
}

/* «UNITÀ (US)» E «MAPPA» SOTTO LA STRISCIA non ci sono più in campo (MICRO il
 * campo rifinito, 15 novembre): in campo non ci sono sezioni. A un'unità si
 * arriva con ‹ › e «Vai alla US…», dall'elenco breve sul tablet, o dalla voce
 * Scheda quando nessuna scheda è aperta (l'elenco delle unità). */

/** «ALTRO», in campo: la lingua della scheda e la vista Foglio/Campi stanno in
 *  un piccolo menu, non nella riga — il mockup del tablet non le disegna, ma
 *  sono funzioni che ci sono e non si tolgono. */
function moreMenu(make, t) {
  const more = make("details", { className: "fo-ctl fld-more" });
  more.dataset.ctl = "more";
  more.append(make("summary", { textContent: t("f.more") }));
  const inside = make("div", { className: "fld-more-body" });
  more.append(inside);
  return { more, inside };
}

function paintStrip() {
  const strip = $("scheda-strip");
  if (!strip) return;
  strip.replaceChildren();
  // SUL TELEFONO ANCHE (15 novembre): il menu «Scheda» e «Solo i campi da
  // trincea», che hanno preso il posto dell'elenco delle definizioni e di
  // «Tutti i campi» della colonna. Il resto (vista, facciate) là non serve.
  strip.hidden = !state.def;
  if (strip.hidden) return;
  const phone = state.mode === "phone";
  const field = state.mode !== "desktop";
  const t = (key) => (SG().t ? SG().t(key) : key);
  const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);

  const control = (labelKey, name, items, current, pick, into = strip) => {
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
    into.append(box);
  };

  const def = state.def;
  // «SCHEDA» (14 novembre, mockup v7.2): le definizioni che il nodo serve —
  // quelle che prima stavano nella colonna come se fossero luoghi — in un menu
  // della striscia, le demo marcate. È ANCHE la lente: su un'unità che esiste,
  // scegliere una definizione diversa da quella con cui è stata scritta la
  // legge con quella, e la lente lo dice; scegliere quella di compilazione la
  // chiude. Su una scheda nuova cambia la definizione con cui si compila.
  // …IN OGNI MODO (15 novembre): in campo l'elenco delle definizioni nella
  // colonna era un elenco per una scelta che si fa di rado; adesso è questo
  // stesso menu. In campo l'opzione porta, come testo secondario, quanti campi
  // la definizione dice da trincea («25 da trincea su 59»): un'informazione,
  // non una lista.
  {
    const box = make("div", { className: "fo-ctl" });
    box.dataset.ctl = "card";
    const label = make("label", { className: "fo-ctl-label", textContent: t("ctl.card") });
    label.htmlFor = "ctl-card-pick";
    const pick = make("select", { className: "std", id: "ctl-card-pick" });
    const written = state.lens && state.lens.written_with
      ? state.lens.written_with.template : def.id;
    for (const item of listing()) {
      const demo = item.standard && item.standard.invented;
      const trench = field && item.recorded_in
        ? ` — ${tr("schede.count", "", { t: item.recorded_in.trench, n: item.fields })}` : "";
      const o = make("option", { value: item.id,
        textContent: standardName(item, SG().locale) + (demo ? " · demo" : "")
          + (state.lens && item.id === written ? ` · ${t("lens.written")}` : "") + trench });
      o.selected = item.id === def.id;
      pick.append(o);
    }
    pick.addEventListener("change", () => {
      const chosen = pick.value;
      if (!chosen || chosen === def.id) return;
      const node = state.byId ? state.nodeId : "";
      if ((state.us || node) && !state.create) {
        window.location.hash = hashFor(chosen, state.us, chosen !== written, node);
      } else {
        clearScheda();
        state.us = "";
        state.create = true;
        window.location.hash = hashFor(chosen, "");
      }
    });
    box.append(label, pick);
    // L'AVVISO DEL DATAMODEL, IN CAMPO: una riga piccola sotto il menu
    // «Scheda» (MICRO il campo rifinito), non la fascia sopra il foglio — che
    // resta alla scrivania. Stessa funzione, stesse parole.
    const notice = field ? datamodelNotice(def) : null;
    if (notice) {
      notice.classList.add("dm-line");
      box.append(notice);
    }
    strip.append(box);
  }
  if (phone) {
    // IL TELEFONO: un campo per volta; «Solo i campi da trincea» decide quali
    // (era «Tutti i campi» nella colonna: la stessa scelta, al contrario)
    strip.append(trenchToggle());
    return;
  }
  // IN CAMPO lingua della scheda e vista vanno in «Altro», in fondo alla riga
  const { more, inside } = field ? moreMenu(make, t) : { more: null, inside: strip };
  if ((def.languages || []).length > 1) {
    control("ctl.cardlang", "cardlang",
      def.languages.map((l) => [l, l]), def.lang,
      (l) => { if (l !== def.lang) void openScheda(def.id, null, l); }, inside);
  }
  const views = [["sheet", t("view.sheet"), !hasSheet(def)], ["fields", t("view.fields")]];
  // la pagina dell'unità, alla scrivania: si legge un'unità che c'è
  if (state.mode === "desktop") views.push(["unit", t("view.unit"), !(state.us && !state.create)]);
  const view = state.view === "unit" && state.mode === "desktop" && state.us && !state.create
    ? "unit" : (hasSheet(def) && state.view !== "fields" ? "sheet" : "fields");
  control("ctl.view", "view", views, view,
    (v) => { state.view = v; draw(); }, inside);
  if (!sheetActive() || view === "unit") {
    if (more) strip.append(more);
    return;
  }

  if (posture() === "field") {
    control("f.side", "side",
      [["recto", t("faces.recto")], ["verso", t("faces.verso")]],
      state.fieldSide, (v) => { state.fieldSide = v; draw(); });
    strip.append(trenchToggle());
    if (more) strip.append(more);
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

async function goUnit(asked) {
  if (!state.def) return false;
  const said = String(asked || "").trim();
  // il numero lo dice il servizio (`numberOf`): la regola è una sola
  const number = said ? ((await numberOf(said, state.def)).number || said) : "";
  const found = unitFor(said, number);
  const t = SG().t || ((k) => k);
  if (!found) {
    SG().show(false, `${t("nav.no_unit")} ${said}.`, "", SG().locale);
    return false;
  }
  if (found.conflict) {
    SG().show(false, t("nav.conflict", {
      n: number, count: found.conflict.length,
      names: found.conflict.map((u) => u.name || u.id).join(", ") }), "",
    SG().locale);
    return false;
  }
  return openFound(found);
}

/** Un'unità dell'elenco, aperta: per numero, o DAL SUO ID, in lettura, se non
 *  ne ha uno o se il suo numero è anche di un'altra (15 novembre). */
async function openFound(found) {
  // dal suo id anche un'unità dal nome dell'importer (`by_id`): il numero da
  // solo non la indirizza (12 novembre, E.D.)
  const byId = opensById(found);
  if (!byId && found.number === state.us && !state.create) return true;
  if (byId && state.byId && state.nodeId === found.id) return true;
  if (!(await leaveUnit())) return false;
  await openScheda(state.def.id, byId ? { node: found.id } : { us: found.number },
                   state.def.lang);
  return true;
}

/** L'unità aperta, nell'elenco: dal suo id se aperta così, o per numero. */
const isHere = (u) => (state.byId ? u.id === state.nodeId : u.number === state.us);

async function stepUnit(delta) {
  const order = orderedUnits();
  if (!order.length || !state.def) return false;
  const at = order.findIndex(isHere);
  const target = at < 0 ? (delta > 0 ? order[0] : order[order.length - 1])
    : order[at + delta];
  if (!target) return false;             // un estremo: ci si ferma
  return opensById(target) ? openFound(target) : goUnit(target.number);
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
  paintNoNumber();
  if (bar.hidden) return;
  const t = SG().t || ((k) => k);
  const make = (tag, props = {}) => Object.assign(document.createElement(tag), props);
  bar.classList.toggle("big", state.mode === "phone");
  const order = orderedUnits();
  const at = order.findIndex(isHere);

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
                              textContent: state.byId ? state.unitName
                                : `${unitPrefix(state.def)}${state.us || "…"}` });
  const listId = "unav-units";
  const jump = make("input", { type: "text", placeholder: t("nav.jump"),
                               autocomplete: "off" });
  jump.setAttribute("list", listId);
  jump.setAttribute("aria-label", t("nav.jump"));
  jump.setAttribute("enterkeyhint", "go");
  const options = make("datalist", { id: listId });
  for (const u of order) {
    // un'unità dal nome dell'importer si cerca come la si dice: «US 2 · area 1»
    const o = make("option", { value: opensById(u) ? (u.label || u.name || u.number) : u.number });
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
  // LEGGI CON… — la lente — È IL MENU «SCHEDA» della striscia, in ogni modo
  // (14 novembre alla scrivania, 15 novembre sul tablet): la scheda con cui si
  // scrive e quella con cui si legge sono la stessa scelta, in un posto.
}

/* ── «IL NOME DI QUESTA UNITÀ NON PORTA UN NUMERO» (15 novembre 2026) ─────────
 *
 * Le regole di E.D. (12 novembre): i numeri non si cambiano né si inventano;
 * quando un numero manca l'app LO DICE, senza imporlo; e il numero di
 * un'unità SI LEGGE DAL SUO NOME — non si scrive in un'altra chiave (niente
 * `data.us`). Nella testata della scheda, sotto ‹ unità ›, un avviso discreto:
 * solo il testo, nessuna casella per aggiungerlo. La scheda si salva senza. */
function paintNoNumber() {
  const note = $("scheda-nonum");
  if (!note) return;
  const show = Boolean(state.def && state.panel === "scheda" && state.byId
                       && !state.idNumber && !state.lens && !SG().readOnly);
  note.hidden = !show;
  if (!show) { note.replaceChildren(); return; }
  if (note.dataset.unit === state.nodeId && note.childElementCount) return;
  const t = SG().t || ((k) => k);
  const text = Object.assign(document.createElement("span"),
                             { textContent: t("unit.no_number") });
  note.dataset.unit = state.nodeId;
  note.replaceChildren(text);
}

/* ── L'UNITÀ NELL'INDIRIZZO ──────────────────────────────────────────────────
 *
 * `#scheda=<definizione>&us=<numero>`, così avanti/indietro del browser e un
 * link riaprono la stessa scheda; `#unita` è l'elenco. Nell'hash e non nella
 * query: la query è del link della stanza (`?server=…&room=…`, `arrivo.js`),
 * e cambiarla ricaricherebbe la pagina. Un numero, non un nome: un link non
 * porta mai il valore di una casella. */
function hashFor(id, number, lens = false, node = "") {
  const p = new URLSearchParams();
  p.set("scheda", id);
  if (node) p.set("nodo", node);
  else if (number) p.set("us", number);
  if ((number || node) && lens) p.set("lente", "1");
  return `#${p.toString()}`;
}

function writeHash(id, number, replace = false, lens = false, node = "") {
  const want = hashFor(id, number, lens, node);
  if (window.location.hash === want) return;
  if (replace) history.replaceState(null, "", want);
  else history.pushState(null, "", want);
}

function readHash() {
  const raw = window.location.hash.replace(/^#/, "");
  if (raw === "unita") return { index: true };
  if (raw === "mappa") return { map: true };
  // le tre sezioni nuove della scrivania (14 novembre)
  if (raw === "materiali") return { section: "finds" };
  if (raw === "foto") return { section: "photos" };
  if (raw === "scavo") return { section: "excavation" };
  if (raw === "consegna") return { section: "deliver" };
  const p = new URLSearchParams(raw);
  return { scheda: p.get("scheda") || "", us: p.get("us") || "",
           node: p.get("nodo") || "", lens: p.get("lente") === "1" };
}

async function followHash() {
  const asked = readHash();
  if (asked.index) { await showIndex(false); return; }
  if (asked.map) { await showMap(false); return; }
  if (asked.section) { await showSection(asked.section, false); return; }
  if (!asked.scheda) return;
  const same = state.def && state.def.id === asked.scheda
    && state.panel === "scheda"
    && (asked.node ? state.byId && state.nodeId === asked.node
                   : !state.byId && (state.us || "") === asked.us)
    && Boolean(state.lens) === asked.lens;
  if (same) return;
  if (!(await leaveUnit())) return;
  if (!asked.us && state.def && state.def.id === asked.scheda && state.us) {
    // DA UN'UNITÀ A UNA SCHEDA NUOVA: la stessa definizione, ma non gli stessi
    // valori — riaprirla «com'era» porterebbe i valori di un'altra unità.
    clearScheda();
    state.us = "";
    state.create = true;
  }
  await openScheda(asked.scheda,
    asked.node ? { node: asked.node, lens: asked.lens }
      : asked.us ? { us: asked.us, lens: asked.lens } : null);
}

/** L'ELENCO, con i filtri com'erano (vivono in `indice.js`). */
async function showIndex(push = true) {
  only("index");
  markNav("");
  paintThumbbar();
  if (push && window.location.hash !== "#unita") history.pushState(null, "", "#unita");
  await repaintIndex();
}

/** LA MAPPA (12 novembre): i luoghi e i tagli con la loro impronta
 *  (`mappa.js`). Un clic su un saggio apre l'elenco filtrato su quel luogo. */
async function showMap(push = true) {
  only("map");
  markNav("");
  paintThumbbar();
  if (push && window.location.hash !== "#mappa") history.pushState(null, "", "#mappa");
  const title = $("map-title");
  if (title) title.textContent = SG().t ? SG().t("map.title") : "Map";
  await paintMap($("map-host"), {
    onPlace: (place) => {
      indexFilters.place = { id: place.id, name: place.name };
      void showIndex();
    },
    onOpen: (tool, node, m) => openIn(tool, node, m),
  });
}

function afterSave(body) {
  // UN'UNITÀ APERTA DAL SUO ID resta dov'è, dal suo id: il numero non le si
  // aggiunge (12 novembre, E.D.: si legge dal nome). La stanza si rilegge.
  if (body && body.node && state.byId && body.node === state.nodeId) {
    void loadRoom().then(() => { paintUnav(); if (deskUI) deskUI.paint(); });
    void loadReview();
    return;
  }
  // La stanza ora ha l'unità (o la coda ce l'ha): il completamento e ‹ › la
  // devono vedere, e una scheda NUOVA diventa, nell'indirizzo, la sua unità.
  if (state.def && body && body.us) writeHash(state.def.id, body.us, true);
  void loadRoom().then(() => { paintUnav(); if (deskUI) deskUI.paint(); });
  void loadReview();
}

/* ── verificare: ciò che aspetta una persona (dev28, parte G) ──────────────── */

async function loadReview() {
  try {
    const answer = await fetch(`${SG().node}/v1/to-review`,
                               { headers: { Accept: "application/json" } });
    if (!answer.ok) return;
    state.review = (await answer.json()).rows || [];
  } catch {
    return;                       // la stanza non risponde: il riquadro non c'è
  }
  if (state.def) draw();
}

async function verifyNode(nodeId) {
  const ok = await SG().send("/v1/verify", { node_id: nodeId }, "verify");
  if (ok !== false) await loadReview();
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

/* ── tradurre: una traduzione AI accanto all'originale ──────────────────── */

async function translateField(field) {
  if (!state.us) {
    SG().show(false, "Serve il numero dell'unità per tradurre un testo.", "");
    return;
  }
  // la lingua d'arrivo si chiede: quella da cui si parte la sa il dato
  const lang = (window.prompt("In che lingua? (en, he, de…)", "en") || "").trim();
  if (!lang) return;
  await SG().send("/v1/translate",
                  { us: state.us, field, lang,
                    scheda: state.def ? state.def.id : "" }, "translate");
  void loadReview();             // la traduzione AI aspetta una persona: si vede
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
  //  Le voci fanno quello che fanno i loro gemelli nella colonna, e niente di
  //  più: una sola strada per ciascun gesto.
  //  LE QUATTRO VOCI IN CAMPO: ciascuna va a ciò che l'app ha già.
  $("tb-voice")?.addEventListener("click", () => $("nav-voice").click());
  $("tb-sheet")?.addEventListener("click", () => { void showSection("sheet"); });
  //  FOTO apre le foto (quelle che aspettano e quelle della stanza), con
  //  «Scatta» in cima: scattare resta un tocco, collegare si fa lì.
  $("tb-photo")?.addEventListener("click", () => { void showSection("photos"); });
  $("tb-deliver")?.addEventListener("click", () => { void showSection("deliver"); });
  $("nav-scrim")?.addEventListener("click", () => setNavOpen(false));
  $("nav-close")?.addEventListener("click", () => setNavOpen(false));
  //  una voce scelta chiude il cassetto sul telefono: il gesto è fatto
  $("sidenav").addEventListener("click", (event) => {
    if (state.mode === "phone" && event.target.closest(".navitem")) setNavOpen(false);
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
    rememberMode(verso, viewWidth());
    setMode(verso);
  });
}

/* ── LA SCRIVANIA (14 novembre): le sezioni e ciò che la conchiglia fa per loro ─ */

/** Le definizioni che il nodo serve, dalla lista tenuta sul dispositivo. */
function listing() {
  try {
    return (JSON.parse(localStorage.getItem("sg.schede.v1") || "null") || {}).schede || [];
  } catch { return []; }
}

/** Il prefisso con cui si scrive un'unità: «US » — dalla definizione con cui è
 *  stata compilata se il nodo la serve, dalla aperta altrimenti. */
function prefixOf(u) {
  const declared = u && u.scheda && u.scheda.template;
  if (state.def && (!declared || declared === state.def.id)) return unitPrefix(state.def);
  return "US ";
}

/** Aprire un'unità dall'elenco, dalla colonna o da un reperto: con la
 *  definizione che dichiara, se il nodo la serve; con quella aperta o la prima
 *  altrimenti. Un'unità senza numero si apre dal suo id. */
async function openUnit(u) {
  if (!u) return;
  const declared = u.scheda && u.scheda.template;
  const items = listing();
  const def = (declared && items.some((x) => x.id === declared) && declared)
    || (state.def && state.def.id) || (items[0] && items[0].id);
  if (!def) { SG().show(false, tr("index.noSchede", "")); return; }
  if (!(await leaveUnit())) return;
  // un numero che è anche di un'altra unità (15 novembre) non apre per numero
  // (e dal 12 novembre nemmeno un'unità dal nome dell'importer: `opensById`)
  const byNumber = !opensById(u);
  window.location.hash = byNumber ? hashFor(def, u.number) : hashFor(def, "", false, u.id);
}

/** «Nuova US»: la stessa porta dell'elenco (`#index-new`). */
function newUnit() {
  const go = () => { const b = $("index-new"); if (b) b.click(); };
  if (state.panel === "index") { go(); return; }
  void showIndex().then(go);
}

/** Un luogo dello Scavo → l'elenco filtrato su di lui, come un saggio della
 *  mappa. */
function unitsIn(place) {
  indexFilters.place = { id: place.id, name: place.name };
  void showIndex();
}

/** UNA SEZIONE DELLA SCRIVANIA, dal suo nome. La Scheda torna all'ultima unità
 *  aperta; se non ce n'è, apre quella su cui si è lavorato per ultimi, o una
 *  scheda nuova con la definizione che la stanza usa di più. */
async function showSection(key, push = true) {
  if (key === "units") { await showIndex(push); return; }
  if (key === "map") { await showMap(push); return; }
  if (key === "sheet") {
    if (state.def) {
      only("scheda");
      draw();
      writeHash(state.def.id, state.us, false, Boolean(state.lens), state.byId ? state.nodeId : "");
      return;
    }
    const units = ((await loadRoom()) || {}).units || [];
    const recent = units.slice().sort((a, b) =>
      String(b.modified_at || "").localeCompare(String(a.modified_at || "")));
    if (recent.length) { await openUnit(recent[0]); return; }
    const first = listing()[0];
    if (first) window.location.hash = hashFor(first.id, "");
    return;
  }
  const panel = { finds: "finds", photos: "photos-sec", excavation: "excavation",
                  deliver: "deliver" }[key];
  if (!panel) return;
  only(panel);
  markNav("");
  paintThumbbar();
  const tag = { finds: "#materiali", photos: "#foto", excavation: "#scavo",
                deliver: "#consegna" }[key];
  if (push && window.location.hash !== tag) history.pushState(null, "", tag);
  if (panel === "deliver") { if (fieldUI) fieldUI.paintDeliver(); return; }
  if (deskUI) await deskUI.paintPanel(panel);
}

/** «PRENDI DALLA STANZA» (Consegna, in campo): le letture che l'app fa già,
 *  tutte insieme, perché il dispositivo scenda in trincea con ciò che serve —
 *  l'elenco delle definizioni, ciascuna nella lingua in cui si apre (nella
 *  cache del dispositivo, `definitionFor`), e le unità della stanza. Torna i
 *  conteggi, o null se la rete non c'è. */
async function pullRoom() {
  await loadSchede();
  const items = listing();
  let schede = 0;
  for (const item of items) {
    try { await definitionFor(item.id, cardLanguageFor(item.id)); schede += 1; }
    catch { /* quella definizione non scende: le altre sì */ }
  }
  const read = await loadRoom();
  if (!schede && !(read && read.read)) return null;
  if (deskUI) deskUI.paint();
  return { schede, units: ((read && read.units) || []).length };
}

/** «Rifinisci la descrizione»: porta al campo. Sul Foglio lo sceglie (l'ispettore
 *  mostra la scrittura), nei Campi lo mette a fuoco. */
function refine(fieldId) {
  if (!fieldId) return;
  if (state.view === "unit") { state.view = "sheet"; draw(); }
  const host = $("scheda-host");
  const box = host.querySelector(`.fo-f[data-field="${CSS.escape(fieldId)}"]`)
    || host.querySelector(`[data-field="${CSS.escape(fieldId)}"]`);
  if (!box) return;
  box.scrollIntoView({ block: "center", behavior: "smooth" });
  box.click();
  const pad = $("fo-insp-write") || box.querySelector("textarea, input, [contenteditable='true']");
  if (pad) { pad.focus(); if (pad.setSelectionRange) pad.setSelectionRange(pad.value.length, pad.value.length); }
}

/** L'ispettore della scrivania per le viste che non sono il Foglio (Campi,
 *  Unità): lo stesso pannello del Foglio, senza un campo scelto. */
function paintDeskInspector() {
  const insp = $("desk-insp");
  if (!insp || state.mode !== "desktop" || state.panel !== "scheda" || !state.def) return;
  insp.replaceChildren();
  const box = document.createElement("div");
  insp.append(box);
  paintInspector(box, state.def, state);
}

/** LA PAGINA DELL'UNITÀ (vista «Unità»): il titolo, poi ciò che il grafo dice
 *  dell'unità, paragrafo per paragrafo, senza le caselle vuote. Una lettura;
 *  scrivere è il Foglio o i Campi. */
function drawUnitPage(host) {
  const def = state.def;
  const make = (tag, props = {}, ...kids) => {
    const n = Object.assign(document.createElement(tag), props);
    for (const k of kids) if (k) n.append(k);
    return n;
  };
  const filled = (v) => !(v === undefined || v === null || v === ""
    || (Array.isArray(v) && !v.length));
  const byId = new Map((def.fields || []).map((f) => [f.id, f]));
  const text = (v) => (v && typeof v === "object" && !Array.isArray(v)
    ? (v.label || v.name || "") : String(v || ""));
  const definition = Object.entries(state.values).find(([k, v]) =>
    byId.get(k) && byId.get(k).type === "term" && /defin/i.test(k) && filled(v));
  const title = (state.byId ? state.unitName : `${unitPrefix(def)}${state.us}`)
    + (definition ? ` · ${text(definition[1])}` : "");
  const page = make("article", { className: "unitpage" },
    make("header", { className: "hero" }, make("h2", { textContent: title })));
  for (const para of def.paragraphs || []) {
    const rows = (para.fields || []).map((id) => byId.get(id))
      .filter((f) => f && f.id !== state.keyField && filled(state.values[f.id]));
    if (!rows.length) continue;
    const sec = make("section", { className: "card" }, make("h3", { textContent: para.label }));
    for (const f of rows) {
      const value = make("div", { className: "up-v" });
      value.append(valueView(f, state.values[f.id], def));
      sec.append(make("div", { className: "up-row" },
        make("span", { className: "up-l", textContent: f.label }), value));
    }
    page.append(sec);
  }
  if (page.childElementCount === 1) {
    page.append(make("p", { className: "hint", textContent: tr("unit.empty", "") }));
  }
  // SOTTO CIÒ CHE È SCRITTO, CIÒ CHE MANCA (revisione C.3, 15 novembre): una
  // vista con due righe e poi una pagina vuota non diceva che il resto c'è, da
  // compilare. Quante caselle sono vuote, e la strada per il Foglio.
  const empty = (def.fields || []).filter((f) => f.id !== state.keyField
    && !filled(state.values[f.id])).length;
  if (empty) {
    const go = make("button", { type: "button", className: "linkish",
                                textContent: tr("unit.open_sheet", "open the Sheet") });
    go.dataset.go = "sheet";
    go.addEventListener("click", () => { state.view = "sheet"; draw(); });
    page.append(make("p", { className: "unit-left" },
      make("span", { textContent: tr("unit.left", `${empty} empty boxes`, { n: empty }) }),
      document.createTextNode(" · "), go));
  }
  host.replaceChildren(page);
}

/* ── avvio ───────────────────────────────────────────────────────────────── */

function wireShell() {
  applyTheme(savedTheme());
  // LA STANZA NELLA BARRA: un clic apre la scelta (`#room-pop`, dove sta «Dove
  // scrivo»), alla scrivania e in campo (15 novembre: la colonna non c'è più).
  $("room-name")?.addEventListener("click", () => {
    const pop = $("room-pop");
    pop.hidden = !pop.hidden;
    $("room-name").setAttribute("aria-expanded", String(!pop.hidden));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("room-pop") && !$("room-pop").hidden) {
      $("room-pop").hidden = true;
      $("room-name").setAttribute("aria-expanded", "false");
    }
  });
  $("bar-voice")?.addEventListener("click", () => $("nav-voice").click());
  $("theme").addEventListener("click", () => {
    const now = savedTheme();
    applyTheme(THEMES[(THEMES.indexOf(now) + 1) % THEMES.length]);
  });

  $("nav-voice").addEventListener("click", () => {
    // LA DETTATURA SOLO A CHI FIRMA (31 ottobre, dal telefono vero): con la
    // voce «Detta» in barra il pannello si apriva anche senza firma, e una
    // dettatura finiva in coda come «nota senza firma». Senza firma resta la
    // porta: decide `render()` nella pagina, che sa chi è firmato (`only`).
    only("work");
    paintThumbbar();
    markNav("");
    // ALLA SCRIVANIA «Detta» non ha un indirizzo suo: se restasse `#unita`,
    // ricaricando l'indirizzo vincerebbe sulla scelta ricordata (MICRO, 14
    // novembre). Si toglie, e l'avvio legge `sg.section.v1`. In campo no.
    if (state.mode === "desktop" && window.location.hash) {
      history.pushState(null, "", window.location.pathname + window.location.search);
    }
  });

  $("nav-units").addEventListener("click", () => { void showIndex(); });
  $("nav-map").addEventListener("click", () => { void showMap(); });
  $("nav-map").textContent = SG().t ? SG().t("nav.map") : "Map";
  // la voce «Detta» della barra si accende con il suo gemello
  $("nav-voice").addEventListener("click", () => paintThumbbar());
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
    // alla scrivania: la tabella, la colonna e i conteggi delle sezioni
    isDesk: () => state.mode === "desktop",
    prefix: (u) => prefixOf(u),
    onRead: () => { if (deskUI) deskUI.paint(); },
    schede: () => {
      try { return (JSON.parse(localStorage.getItem("sg.schede.v1") || "null")
                    || {}).schede || []; } catch { return []; }
    },
  });
  //  IL SEAM E BASTA: la conchiglia dichiara `window.SG` e questo modulo non
  //  conosce altro. `t` e `show` vengono da lì, come per ogni altra superficie.
  window.SGChat = mountChat({ t: (k, v) => SG().t(k, v),
                              toast: (m) => SG().show(true, m) });

  // LA SCRIVANIA (14 novembre): la cornice delle sezioni, che chiama la
  // conchiglia per aprire e legge quello che la stanza ha già detto
  deskUI = mountDesk({ state, choosePlace, showSection, newUnit, openUnit, unitsIn,
                       listing, prefix: prefixOf });
  void deskUI.warm();
  // IN CAMPO (15 novembre): le quattro voci e la Consegna
  fieldUI = mountField({ state, pullRoom });
  // la riga dello stato in campo, per la pagina (`checkSays`)
  window.SGField = { stateLine: fieldStateLine };

  // Il modo si RIPROPONE quando la finestra cambia, ma non sovrascrive una
  // scelta: `effectiveMode` guarda prima cosa è stato scelto.
  window.addEventListener("resize", () => {
    const wanted = effectiveMode(viewWidth());
    if (wanted !== state.mode) setMode(wanted);
    else paintModes();
  });

  setMode(effectiveMode(viewWidth()));
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
  // LA FIRMA PRIMA DELL'ARRIVO (SF-01, 31 ottobre): l'indirizzo con la stanza
  // torna da Keycloak solo dopo che `index.html` ha scambiato il codice, e
  // decidere prima voleva dire leggere `?code=…` e atterrare nel posto sbagliato.
  if (window.SGReady) await window.SGReady;
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

  if (piano.do === "offer" && SG().signed) {
    // DAL 25 OTTOBRE IL POSTO È DI CHI FIRMA (`app/scrivani.py`), non del nodo:
    // puntare la stanza del link non la toglie a nessun altro. Chi ha aperto il
    // link di una stanza ci vuole scrivere, quindi si punta da solo — e se la
    // stanza dice di no (nessun ruolo, server non fidato) si dice e si resta.
    const corpo = { room: piano.room,
                    server: piano.server || (salute && salute.server_hint) || "" };
    const detto = await pointRoom(corpo, SG().t);
    const mioOra = SG().where ? SG().where() : null;
    if (mioOra && mioOra.room === piano.room) {
      SG().show(true, SG().t("arrival.pointed", { room: piano.room }));
      await showIndex(false);
      return;
    }
    SG().show(false, detto);
  }

  if (piano.do === "offer") {
    // La colonna, aperta sul pannello che punta il nodo, con la stanza già
    // scritta: il gesto resta uno, e resta di chi lo fa. SUL TELEFONO NO: la
    // colonna è un foglio che copre il messaggio (SF-03), e il messaggio basta.
    if (state.mode !== "phone" && $("room-pop")) {
      $("room-pop").hidden = false;
      $("room-name").setAttribute("aria-expanded", "true");
    }
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
// …E SE NÉ L'INDIRIZZO NÉ IL LINK HANNO SCELTO UN PANNELLO, alla scrivania si
// apre la sua sezione (`openDesk`); in campo resta «Detta».
void land().then(() => schedeLoaded).then(() => followHash())
  .then(() => (state.panel === "voice" && !window.location.hash.replace(/^#/, "")
    ? openDesk(true) : null))
  .finally(() => { opened = true; });

// Esposto per la verifica dal browser: è quello che una cattura non può
// dimostrare (dove stanno i bersagli, quale modo è attivo, quanti campi).
window.SGShell = { state, openScheda, setMode, draw, trenchFields, otherFields,
                   writingPosture, choosePlace,
                   showSection: (k) => showSection(k),
                   payloadFor, paintThumbbar, thumbbarPlan, land,
                   // FORZARE LA POSTURA, per provarla: «desk», «field», o null
                   // per tornare a quella che il nodo dice. Non si ricorda.
                   forcePosture: (p) => {
                     state.postureForced = p === "desk" || p === "field" ? p : null;
                     if (state.def) draw();
                   },
                   onAccess: () => watchReading(),
                   // la coda è cambiata (la pagina, `renderQueue`): il numero
                   // sulla Consegna e la Consegna stessa
                   onQueue: () => { if (fieldUI) fieldUI.paint(); },
                   onLocale: () => {
                     $("nav-units").textContent = SG().t("nav.units");
                     $("nav-map").textContent = SG().t("nav.map");
                     if (state.panel === "map") void showMap(false);
                     if (deskUI) {
                       deskUI.paint();
                       const sec = sectionOf(state.panel);
                       if (["finds", "photos", "excavation"].includes(sec)) {
                         void deskUI.paintPanel(state.panel);
                       }
                     }
                     paintModes();
                     paintWayBack();
                     if (fieldUI) fieldUI.paint();
                     if (state.def) draw();
                   },
                   goUnit: (n) => goUnit(n), stepUnit: (d) => stepUnit(d),
                   showIndex: () => showIndex(),
                   showMap: () => showMap(),
                   repaintPhotos: () => repaintPhotos(),
                   repaintIndex: () => repaintIndex(),
                   // per il CONTROLLO: ridisegna l'elenco, ma non mentre chi lo
                   // usa sta scegliendo lo standard
                   refreshIndex: () => (indexAsking() ? null : repaintIndex()) };
