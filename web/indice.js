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
export const filters = { q: "", area: null, ai: false, inc: false };

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
  if (f.ai && !(Number(u.ai) > 0)) return false;
  if (f.inc) {
    const share = filled(u, listing, fallback);
    if (share === null || share >= 0.5) return false;
  }
  return true;
}

/** Quante schede si mostrano prima di dire che ce n'è altre. Uno scavo vero ne
 *  ha migliaia, e una lista lunga su un telefono è una lista che non si legge. */
export const SHOWN = 40;

/** La riga di un'unità: cosa è, quanto è piena, e chi l'ha toccata per ultimo. */
function line(u, t, onPick) {
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
  if (u.description) {
    const cosa = document.createElement("span");
    cosa.className = "indice-cosa";
    cosa.textContent = u.description;
    riga.append(cosa);
  }
  if (!u.number) {
    //  UN'UNITÀ DI CUI NON SI SA IL NUMERO NON SI RIAPRE. Succede con i grafi
    //  importati, e proporre una scheda su un numero indovinato sarebbe la
    //  stessa famiglia di errori del numero mistypato.
    riga.disabled = true;
    riga.title = t("index.noNumber");
    const perche = document.createElement("span");
    perche.className = "indice-cosa";
    perche.textContent = t("index.noNumber");
    riga.append(perche);
    return riga;
  }
  riga.addEventListener("click", () => onPick(u));
  return riga;
}

export function mount({ t, openScheda, schede, current = () => null }) {
  const host = $("index-list");
  const nota = $("index-note");
  const titolo = $("index-title");
  if (!host) return async () => {};

  /** Il secondo tocco: con quale standard si riapre questa unità. */
  function askStandard(u) {
    const lista = schede();
    host.replaceChildren();
    const detto = document.createElement("p");
    detto.className = "hint";
    detto.textContent = t("index.which", { unit: u.name || u.id });
    host.append(detto);
    for (const item of lista) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "navitem";
      b.textContent = item.id;
      //  IL NUMERO, non il nome: gli attrezzi vogliono «12» e non «US 12», e
      //  `update_su` rifiuta un numero che non corrisponde a nessun nodo — che
      //  è la sua virtù. Il numero lo dice il nodo (`number_from_unit_id`),
      //  non questa pagina.
      b.addEventListener("click", () => openScheda(item.id, { us: u.number }));
      host.append(b);
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

  async function repaint() {
    const seam = SG();
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
    const unita = letto.units || [];
    // LE STESSE UNITÀ del completamento e di ‹ ›: una lettura, condivisa.
    room.units = unita;
    room.read = true;
    if (!unita.length) { nota.textContent = t("index.empty"); return; }
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
    chip(t("flt.ai"), filters.ai, () => { filters.ai = !filters.ai; }, "ai");
    chip(t("flt.incomplete"), filters.inc, () => { filters.inc = !filters.inc; }, "inc");
    const conta = document.createElement("span");
    conta.className = "indice-conta";
    conta.id = "index-count";
    bar.append(conta);

    const elenco = document.createElement("div");
    elenco.className = "indice-elenco";
    const riempi = () => {
      const visti = unita.filter((u) => matches(u, filters, listing, fallback));
      conta.textContent = t("flt.count", { n: visti.length, t: unita.length });
      elenco.replaceChildren(...visti.slice(0, SHOWN).map((u) => line(u, t, pick)));
      if (!visti.length) {
        const vuoto = document.createElement("p");
        vuoto.className = "hint";
        vuoto.textContent = t("flt.none");
        elenco.append(vuoto);
        nota.textContent = "";
        return;
      }
      const oltre = visti.length - Math.min(visti.length, SHOWN);
      nota.textContent = oltre > 0
        ? t("index.more", { n: oltre, total: visti.length })
        : t(unita.length === 1 ? "index.total.one" : "index.total.many",
            { n: unita.length });
    };
    cerca.addEventListener("input", () => { filters.q = cerca.value; riempi(); });
    const focused = document.activeElement && document.activeElement.id === "index-search";
    host.replaceChildren(bar, elenco);
    riempi();
    if (focused) cerca.focus();
  }

  /** Un'unità che DICHIARA con quale definizione è stata compilata si riapre
   *  con quella, se il nodo la serve: è il motivo per cui la dichiara (audit
   *  B5b). Le altre chiedono, come prima — il secondo tocco resta dove serve. */
  function pick(u) {
    const declared = u.scheda && u.scheda.template;
    if (declared && schede().some((x) => x.id === declared)) {
      openScheda(declared, { us: u.number });
      return;
    }
    askStandard(u);
  }

  return repaint;
}
