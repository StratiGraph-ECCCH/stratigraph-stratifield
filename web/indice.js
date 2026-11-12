/* Cosa c'è già in questa stanza — l'elenco delle schede, e come riaprirne una.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * ## PERCHÉ QUESTA SUPERFICIE È IL PRIMO POSTO E NON UNO IN PIÙ
 *
 * Chi arriva dal link di una stanza ha già scelto la stanza: **sta continuando
 * un lavoro, non ne comincia uno**. Fino al 6 ottobre atterrava sul microfono,
 * cioè sull'inizio di qualcosa di nuovo, e per riprendere in mano una US doveva
 * aprire una scheda vuota e riscriverne il numero a memoria.
 *
 * ## DUE TOCCHI, E IL SECONDO NON SI PUÒ SALTARE
 *
 * Un'unità **non registra con quale scheda è stata compilata** (misurato:
 * `create_su` scrive `node_type`, `name`, `description` e i campi, e nient'altro
 * che dica lo standard). Quindi il secondo tocco — quale standard — non è un
 * gesto in più che si potrebbe togliere con un default: è una domanda a cui
 * solo chi riapre sa rispondere. Una US registrata con l'ICCD non è una US
 * registrata col foglio ungherese, e indovinarlo sarebbe la stessa famiglia di
 * errori del numero mistypato che `update_su` esiste per rifiutare.
 *
 * Zero colori letterali: tutto dalle variabili del tema.
 */

import { room } from "./widgets.js";

const $ = (id) => document.getElementById(id);
const SG = () => window.SG || {};

/* ── I FILTRI (22 ottobre) ─────────────────────────────────────────────────
 *
 * E.D., 27 settembre: «nelle liste di US i filtri sono molto utili». Quattro,
 * che si COMBINANO: la ricerca su numero e definizione, un gettone per area
 * (le aree dello scavo, lette dalle unità e non da un elenco scritto qui), «AI
 * da confermare», «compilate meno della metà». Vivono QUI, al livello del
 * modulo e non del disegno: aprire una scheda e tornare li ritrova com'erano.
 *
 * Pure le due funzioni che decidono (`matches`, `filled`), perché sono quelle
 * che si possono sbagliare in silenzio: un contatore giusto su un elenco
 * sbagliato sembra giusto. */
export const filters = { q: "", area: null, ai: false, inc: false, place: null,
                         refine: false };

/* IL LUOGO (12 novembre): un clic su un saggio della mappa apre l'elenco
 * filtrato su quel luogo — `{id, name}`, l'id perché due luoghi possono
 * chiamarsi «1» (l'area 1 e il settore 1). Le unità lo dicono in `places`
 * (`is_in_location`, `app/writer.py::units_of`). */

/** IL NOME DI UNO STANDARD PER PERSONE (SF-06, D4). Quello che la definizione
 *  dichiara (`standard.short`, una stringa o un dizionario per lingua); se non
 *  lo dichiara, autorità · codice, più l'anno quando la versione è un anno.
 *  L'identificativo (`iccd-us-2021`) resta per le macchine. */
export function standardName(item, lang) {
  if (!item) return "";
  const std = item.standard || {};
  const short = std.short;
  if (short && typeof short === "object") {
    const said = short[lang] || short.en || Object.values(short)[0];
    if (said) return String(said);
  } else if (short) {
    return String(short);
  }
  const head = [std.authority, std.code].filter(Boolean).join(" · ");
  const year = /^\d{4}$/.test(String(std.version || "")) ? ` ${std.version}` : "";
  return head ? head + year : String(item.id || "");
}

/** Le unità in ordine di NUMERO, non di testo: «US 2» prima di «US 10». */
export function byNumber(a, b) {
  return String(a.number || a.name || a.id || "")
    .localeCompare(String(b.number || b.name || b.id || ""), undefined, { numeric: true });
}

//: vero mentre l'elenco chiede «con quale standard?»: il controllo non ridisegna
//: sotto le dita di chi sta scegliendo
let asking = false;
export const isAsking = () => asking;

/** Quanto è piena un'unità, da 0 a 1 — o null se non si sa su quanti campi.
 *
 *  Il totale è quello della definizione con cui l'unità è stata compilata
 *  (`scheda.template`, audit B5b); un'unità che non lo dice (dettata,
 *  importata) si misura sulla definizione di `fallback` — quella aperta, o la
 *  prima che il nodo serve — ed è una stima dichiarata, non un fatto. */
export function filled(u, listing, fallback) {
  const declared = u.scheda && u.scheda.template;
  const item = (listing || []).find((x) => x.id === declared)
    || (listing || []).find((x) => x.id === fallback) || (listing || [])[0];
  const total = item && Number(item.fields);
  return total ? Number(u.fields || 0) / total : null;
}

export function matches(u, f, listing, fallback) {
  const q = String(f.q || "").trim().toLowerCase();
  if (q) {
    const bare = q.replace(/^[^\d]*(?=\d)/, "");
    const hit = String(u.number || "").toLowerCase().startsWith(bare || q)
      || String(u.name || "").toLowerCase().includes(q)
      || String(u.definition || "").toLowerCase().includes(q);
    if (!hit) return false;
  }
  if (f.area && !(u.area || []).includes(f.area)) return false;
  if (f.place && !(u.places || []).includes(f.place.id)) return false;
  if (f.ai && !(Number(u.ai) > 0)) return false;
  // DA RIFINIRE ALLA SCRIVANIA (14 novembre, CHNT): scritta solo in trincea e
  // sotto la soglia di parole. Lo decide il NODO (`to_refine`, una costante sola
  // in `app/unita.py`); un'unità di cui non si sa dove è stata scritta non entra.
  if (f.refine && !u.to_refine) return false;
  if (f.inc) {
    const share = filled(u, listing, fallback);
    if (share === null || share >= 0.5) return false;
  }
  return true;
}

/** Quante schede si mostrano prima di dire che ce n'è altre. Uno scavo vero ne
 *  ha migliaia, e una lista lunga su un telefono è una lista che non si legge. */
export const SHOWN = 40;
//: …alla scrivania la tabella ne tiene di più: è lo schermo grande, e la
//: riga è una riga sola (14 novembre)
export const SHOWN_DESK = 200;

/** La riga di un'unità: cosa è, quanto è piena, e chi l'ha toccata per ultimo. */
function line(u, t, onPick, listing, lang) {
  const riga = document.createElement("button");
  riga.type = "button";
  riga.className = "navitem indice-riga";
  riga.dataset.unit = u.id;

  const nome = document.createElement("span");
  nome.className = "indice-nome";
  nome.textContent = u.name || u.id;

  const quanti = document.createElement("span");
  quanti.className = "count";
  //  I CAMPI SCRITTI DA QUALCUNO, non le chiavi di `data`: i timbri e gli
  //  orologi sono del sistema, e contarli direbbe che una scheda vuota è piena.
  //  Uno e molti sono due frasi, come `room.left.one` / `room.left.many`: «1
  //  campi» è una traduzione che nessuna lingua accetta.
  quanti.textContent = t(u.fields === 1 ? "index.fields.one"
                                        : "index.fields.many", { n: u.fields });
  quanti.title = (u.field_names || []).join(", ");

  riga.append(nome, quanti);
  // LA DEFINIZIONE E L'AREA, sotto il nome: sono le due cose su cui si filtra,
  // e un filtro che sceglie per qualcosa che non si vede non si capisce.
  const detto = [u.definition, (u.area || []).join(", ")].filter(Boolean).join(" · ");
  if (detto) {
    const def = document.createElement("span");
    def.className = "indice-cosa indice-def";
    def.textContent = detto;
    riga.append(def);
  }
  if (Number(u.ai) > 0) {
    // accanto al nome, dove l'occhio lo trova scorrendo l'elenco
    const ai = document.createElement("span");
    ai.className = "indice-ai";
    ai.textContent = `AI ${u.ai}`;
    ai.title = t("flt.ai");
    nome.after(ai);
  }
  // CON QUALE STANDARD È STATA COMPILATA (SF-08): lo dichiara l'unità stessa
  // (`data.scheda`, audit B5b) quando è passata da una scheda; dettata o
  // importata non lo dice, e la riga lo scrive invece di lasciarlo scoprire.
  //  Solo quando c'è: ripetere «si sceglie alla prima apertura» su trenta righe
  //  dettate era rumore (visto sullo schermo, 31 ottobre); lo dice il
  //  suggerimento della riga.
  const declared = u.scheda && u.scheda.template;
  if (declared) {
    const con = document.createElement("span");
    con.className = "indice-cosa indice-std";
    con.textContent = t("index.with", {
      std: standardName((listing || []).find((x) => x.id === declared) || { id: declared }, lang) });
    riga.append(con);
  } else {
    riga.title = t("index.noStandard");
  }
  if (u.description) {
    const cosa = document.createElement("span");
    cosa.className = "indice-cosa";
    cosa.textContent = u.description;
    riga.append(cosa);
  }
  //  UN'UNITÀ SENZA NUMERO SI APRE DAL SUO ID (14 novembre), in lettura: un
  //  numero indovinato sarebbe lo stesso errore del numero mistypato, ma l'id
  //  è l'unità. Lo dice UNA riga sopra l'elenco, non ogni riga.
  if (!u.number) riga.dataset.byId = "true";
  riga.addEventListener("click", () => onPick(u));
  return riga;
}

/** DOVE È STATA SCRITTA, come la colonna lo dice: «in trincea», «alla
 *  scrivania», «trincea + scrivania», o «—» se non si sa. */
export function writtenLabel(u, t) {
  const key = { trench: "w.trench", desk: "w.desk", both: "w.both" }[u.written_in];
  return key ? t(key) : "—";
}

/** LA RIGA DELLA TABELLA, alla scrivania (mockup v7.2): Unità · Definizione ·
 *  Scritta · Parole · Area · Compilazione · AI · Ultima modifica. */
function row(u, t, onPick, listing, fallback, prefix) {
  const tr = document.createElement("tr");
  tr.dataset.unit = u.id;
  tr.tabIndex = 0;
  if (!u.number) tr.dataset.byId = "true";
  const td = (text, cls) => {
    const c = document.createElement("td");
    if (cls) c.className = cls;
    if (text instanceof Node) c.append(text); else c.textContent = text;
    tr.append(c);
    return c;
  };
  td(u.number ? `${prefix}${u.number}` : (u.name || u.id), "id");
  td(u.definition || u.description || "");
  const wr = document.createElement("span");
  wr.className = `wr ${u.written_in || "unknown"}`;
  wr.textContent = writtenLabel(u, t);
  td(wr);
  td(String(u.words || 0), "num" + (u.to_refine ? " short" : ""));
  td((u.area || []).join(", "));
  const share = filled(u, listing, fallback);
  const declared = u.scheda && u.scheda.template;
  const item = (listing || []).find((x) => x.id === declared)
    || (listing || []).find((x) => x.id === fallback) || (listing || [])[0];
  const total = item ? Number(item.fields) || 0 : 0;
  const mini = document.createElement("span");
  mini.className = "mini";
  const bar = document.createElement("i");
  bar.style.width = `${Math.round((share || 0) * 100)}%`;
  mini.append(bar);
  const comp = td(mini, "num");
  comp.append(` ${u.fields || 0}${total ? "/" + total : ""}`);
  const ai = document.createElement("span");
  if (Number(u.ai) > 0) { ai.className = "tag warn"; ai.textContent = String(u.ai); }
  td(ai);
  td(String(u.modified_at || "").slice(0, 10), "num");
  const go = () => onPick(u);
  tr.addEventListener("click", go);
  tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  return tr;
}

/** Gli standard divisi: quelli già usati nella stanza (dal più usato) e gli
 *  altri, nell'ordine del nodo. Pura, per poterla provare. */
export function splitByUse(lista, unita) {
  const conta = new Map();
  for (const u of unita) {
    const id = u && u.scheda && u.scheda.template;
    if (id) conta.set(id, (conta.get(id) || 0) + 1);
  }
  const used = lista.filter((x) => conta.has(x.id))
    .sort((a, b) => conta.get(b.id) - conta.get(a.id));
  const others = lista.filter((x) => !conta.has(x.id));
  return { used, others };
}

export function mount({ t, openScheda, schede, current = () => null,
                        onRead = () => {}, isDesk = () => false,
                        prefix = () => "US " }) {
  const host = $("index-list");
  const nota = $("index-note");
  const titolo = $("index-title");
  if (!host) return async () => {};

  /** Il secondo tocco: con quale standard si riapre questa unità — o, senza
   *  unità, con quale si compila una US NUOVA («+ Nuova US»). */
  function askStandard(u) {
    const lista = schede();
    asking = true;
    host.replaceChildren();
    const detto = document.createElement("p");
    detto.className = "hint";
    detto.textContent = u ? t("index.which", { unit: u.name || u.id })
                           : t("index.newWhich");
    host.append(detto);
    // GLI STANDARD DI QUESTA STANZA PER PRIMI (31 ottobre: «le schede
    // internazionali così sono dispersive»). Quelli con cui la stanza ha già
    // compilato, dal più usato; gli altri dietro «Altri standard». Una stanza
    // che non ha ancora compilato niente li mostra tutti.
    const { used, others } = splitByUse(lista, room.units || []);
    const voce = (item) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "navitem";
      b.textContent = standardName(item, SG().locale);
      b.title = item.id;
      const quanti = document.createElement("span");
      quanti.className = "count";
      quanti.textContent = t("index.fields.many", { n: item.fields });
      b.append(quanti);
      //  IL NUMERO, non il nome: gli attrezzi vogliono «12» e non «US 12», e
      //  `update_su` rifiuta un numero che non corrisponde a nessun nodo — che
      //  è la sua virtù. Il numero lo dice il nodo (`number_from_unit_id`),
      //  non questa pagina.
      b.addEventListener("click",
        () => openScheda(item.id, u ? (u.number ? { us: u.number } : { node: u.id }) : null));
      return b;
    };
    if (used.length) {
      host.append(...used.map(voce));
      if (others.length) {
        const altri = document.createElement("details");
        altri.className = "indice-altri";
        const apri = document.createElement("summary");
        apri.textContent = t("index.otherStandards", { n: others.length });
        altri.append(apri, ...others.map(voce));
        host.append(altri);
      }
    } else {
      host.append(...others.map(voce));
    }
    if (!lista.length) {
      const vuoto = document.createElement("p");
      vuoto.className = "hint";
      vuoto.textContent = t("index.noSchede");
      host.append(vuoto);
    }
    const indietro = document.createElement("button");
    indietro.type = "button";
    indietro.className = "navitem";
    indietro.textContent = t("index.back");
    indietro.addEventListener("click", () => void repaint());
    host.append(indietro);
  }

  /** «+ Nuova US»: compilare una scheda nuova parte DA QUI, dall'elenco delle
   *  unità, e non da una voce «Schede» che sul telefono nessuno capiva
   *  (31 ottobre). Un nodo che serve un solo standard non chiede. */
  function newButton() {
    const b = document.createElement("button");
    b.type = "button";
    b.id = "index-new";
    b.className = "indice-nuova";
    b.textContent = t("index.new");
    b.addEventListener("click", () => {
      const lista = schede();
      if (lista.length === 1) { openScheda(lista[0].id, null); return; }
      askStandard(null);
    });
    return b;
  }

  let lastRead = null;

  async function repaint() {
    const seam = SG();
    asking = false;
    host.replaceChildren();
    if (!seam.signed) { nota.textContent = t("index.signin"); return; }
    let letto;
    try {
      const risposta = await seam.request("/v1/room/units", {});
      if (risposta.status === 403) {
        // UNA PORTA CHIUSA SI DICE CON LA SUA FRASE, non come una rete che manca
        nota.textContent = (await risposta.json().catch(() => ({}))).detail
          || t("index.unreachable");
        return;
      }
      if (!risposta.ok) { nota.textContent = t("index.unreachable"); return; }
      letto = await risposta.json();
    } catch { nota.textContent = t("index.unreachable"); return; }

    if (titolo) {
      titolo.textContent = letto.room
        ? t("index.head.room", { room: letto.room }) : t("index.head.local");
    }
    const unita = (letto.units || []).slice().sort(byNumber);
    // LE STESSE UNITÀ del completamento e di ‹ ›: una lettura, condivisa.
    room.units = unita;
    room.read = true;
    lastRead = letto;
    onRead(letto);
    if (!unita.length) {
      host.replaceChildren(newButton());
      nota.textContent = t("index.empty");
      return;
    }
    paintList(unita);
  }

  /** La barra dei filtri e l'elenco filtrato. Ridisegnare la barra a ogni
   *  tasto toglierebbe il cursore dalla ricerca: si ridisegna l'elenco, e la
   *  barra solo quando cambia un gettone. */
  function paintList(unita) {
    const listing = schede();
    const fallback = current();
    const bar = document.createElement("div");
    bar.className = "indice-filtri";
    const cerca = document.createElement("input");
    cerca.type = "search";
    cerca.id = "index-search";
    cerca.value = filters.q;
    cerca.placeholder = t("flt.search");
    cerca.setAttribute("aria-label", t("flt.search"));
    cerca.autocomplete = "off";
    bar.append(cerca);
    const chip = (text, pressed, onClick, extra) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "indice-chip";
      b.textContent = text;
      b.setAttribute("aria-pressed", String(Boolean(pressed)));
      if (extra) b.dataset.filter = extra;
      b.addEventListener("click", () => { onClick(); paintList(unita); });
      bar.append(b);
      return b;
    };
    const aree = [...new Set(unita.flatMap((u) => u.area || []))]
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    if (aree.length) {
      chip(t("photos.all"), !filters.area, () => { filters.area = null; }, "area:");
      for (const a of aree) {
        chip(a, filters.area === a,
             () => { filters.area = filters.area === a ? null : a; }, `area:${a}`);
      }
    }
    if (filters.place) {
      // il luogo scelto sulla mappa, come gettone: un tocco lo toglie
      chip(t("map.place_filter", { place: filters.place.name }), true,
           () => { filters.place = null; }, "place");
    }
    chip(t("flt.ai"), filters.ai, () => { filters.ai = !filters.ai; }, "ai");
    chip(t("flt.incomplete"), filters.inc, () => { filters.inc = !filters.inc; }, "inc");
    const ref = chip(`✎ ${t("flt.refine")}`, filters.refine,
                     () => { filters.refine = !filters.refine; }, "refine");
    ref.classList.add("ref");
    ref.title = t("flt.refine_note", { n: (lastRead && lastRead.refine_under_words) || 30 });
    const conta = document.createElement("span");
    conta.className = "indice-conta";
    conta.id = "index-count";
    bar.append(conta);

    const desk = isDesk();
    const elenco = document.createElement(desk ? "div" : "div");
    elenco.className = desk ? "indice-tabella scroller" : "indice-elenco";
    // CIÒ CHE RESTA FUORI E CIÒ CHE SI APRE DALL'ID, detto UNA volta, in
    // grigio (14 novembre): prima «l'id di questa unità non porta un numero»
    // stava su ogni riga, e documenti ed estrattori sembravano unità.
    const fuori = document.createElement("p");
    fuori.className = "hint indice-fuori";
    const said = [];
    const left = (lastRead && lastRead.left_out) || [];
    if (left.length) {
      said.push(t("index.leftOut", {
        n: left.reduce((a, x) => a + x.count, 0),
        list: left.map((x) => `${x.label} ${x.count}`).join(", ") }));
    }
    const senza = unita.filter((u) => !u.number).length;
    if (senza) said.push(t("index.byIdNote", { n: senza }));
    // una frase per riga: due frasi in una riga, in ebraico con il ripiego
    // inglese, si mescolano (misurato)
    fuori.replaceChildren(...said.map((x) => Object.assign(document.createElement("span"),
                                                            { textContent: x })));
    fuori.hidden = !said.length;
    const riempi = () => {
      const visti = unita.filter((u) => matches(u, filters, listing, fallback));
      conta.textContent = t("flt.count", { n: visti.length, t: unita.length });
      if (desk) {
        const head = document.createElement("thead");
        const hr = document.createElement("tr");
        for (const k of ["col.unit", "col.definition", "col.written", "col.words",
                         "col.area", "col.complete", "AI", "col.edited"]) {
          const th = document.createElement("th");
          th.textContent = k === "AI" ? "AI" : t(k);
          hr.append(th);
        }
        head.append(hr);
        const body = document.createElement("tbody");
        body.append(...visti.slice(0, SHOWN_DESK)
          .map((u) => row(u, t, pick, listing, fallback, prefix(u))));
        const table = document.createElement("table");
        table.className = "tbl";
        table.append(head, body);
        elenco.replaceChildren(table);
      } else {
        elenco.replaceChildren(...visti.slice(0, SHOWN)
          .map((u) => line(u, t, pick, listing, SG().locale)));
      }
      if (!visti.length) {
        const vuoto = document.createElement("p");
        vuoto.className = "hint";
        vuoto.textContent = t("flt.none");
        elenco.append(vuoto);
        nota.textContent = "";
        return;
      }
      const oltre = visti.length - Math.min(visti.length, desk ? SHOWN_DESK : SHOWN);
      nota.textContent = oltre > 0
        ? t("index.more", { n: oltre, total: visti.length })
        : t(unita.length === 1 ? "index.total.one" : "index.total.many",
            { n: unita.length });
    };
    cerca.addEventListener("input", () => { filters.q = cerca.value; riempi(); });
    const focused = document.activeElement && document.activeElement.id === "index-search";
    // alla scrivania «Nuova US» sta nella striscia (`scrivania.js`): qui resta
    // il bottone, nascosto, perché è la stessa porta
    const nuova = newButton();
    if (desk) nuova.hidden = true;
    host.replaceChildren(nuova, bar, fuori, elenco);
    riempi();
    if (focused) cerca.focus();
  }

  /** Un'unità che DICHIARA con quale definizione è stata compilata si riapre
   *  con quella, se il nodo la serve: è il motivo per cui la dichiara (audit
   *  B5b). Le altre chiedono, come prima — il secondo tocco resta dove serve. */
  function pick(u) {
    const declared = u.scheda && u.scheda.template;
    const su = u.number ? { us: u.number } : { node: u.id };
    if (declared && schede().some((x) => x.id === declared)) {
      openScheda(declared, su);
      return;
    }
    // senza numero e con una sola definizione, o con quella aperta: si apre
    const lista = schede();
    if (!u.number && (lista.length === 1 || current())) {
      openScheda(current() || lista[0].id, su);
      return;
    }
    askStandard(u);
  }

  return repaint;
}
