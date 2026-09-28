/* Dove scrive chi è firmato, e con quale ruolo — visto dalla pagina.
 *
 * ════════════════════════════════════════════════════════════════════════════
 * ## PERCHE' UNA SUPERFICIE E NON SOLO UNA ROTTA
 *
 * Un nodo che ha cambiato stanza e non lo mostra e' la stessa famiglia di
 * difetti di tutta questa settimana: il lavoro finisce in un posto e chi lo
 * detta crede sia finito in un altro. Le due domande che decidono se quello che
 * scrivi conta sono **dove sei** e **chi sei**, e l'intestazione le tiene
 * accanto da sempre — `#room-name` esisteva nel DOM dal 23 settembre e nessuno
 * lo riempiva.
 *
 * ## E PERCHE' NELLA COLONNA E NON SOTTO IL BOTTONE GRANDE
 *
 * La regola del telefono di questo progetto: *UI minimale, niente che inviti a
 * uscire dall'app*. Puntare il nodo a una stanza e' un gesto raro — si fa una
 * volta la mattina — mentre dettare e fotografare si fanno tutto il giorno.
 * Quello che si fa una volta sta dietro; quello che si fa sempre sta davanti.
 *
 * Il NOME della stanza pero' sta davanti, nell'intestazione, perche' quello si
 * legge in continuazione: e' la riga che dice se stai scrivendo dove credi.
 *
 * ## DAL 25 OTTOBRE IL POSTO È DI CHI FIRMA, NON DEL NODO
 *
 * Il nodo ha uno scrivano per persona e stanza (`app/scrivani.py`), e il posto
 * lo tiene QUESTA PAGINA (`SG.where`) e lo manda con ogni richiesta. «Scrivi
 * qui» non sposta più il nodo di nessun altro: prova la porta per chi è
 * firmato, e se si apre il posto si ricorda. La risposta dice anche il RUOLO,
 * che è la stanza a decidere (`GET /v1/room`): la pagina lo mostra e basta.
 */

const $ = (id) => document.getElementById(id);
const SG = () => window.SG || {};

/* Dove scrive chi è firmato, col ruolo che la stanza gli dà: `/v1/room`, che
 * vuole una firma. `/health` è pubblica e il ruolo è di una persona. */
export async function look() {
  const seam = SG();
  if (!seam.signed) return null;
  try {
    const risposta = await seam.request("/v1/room", {});
    return risposta.ok ? await risposta.json() : null;
  } catch { return null; }
}

/** In quale stanza scrive il nodo, secondo la salute — o "" per il container.
 *  È la stanza DEL NODO (quella della sua configurazione): la propria la dice
 *  `look()`. */
export function roomOf(health) {
  const dove = String((health && health.writes_to) || "");
  return dove.startsWith("room ") ? dove.slice(5).split(" at ")[0] : "";
}

/** LA POSTURA di questo dispositivo, dalla salute del nodo (spec del Foglio
 *  §4 bis): seduto nella stanza = scrivania, no = in campo. */
export function postureOf(health) {
  return health && health.seated === true ? "desk" : "field";
}

/** La riga dell'intestazione: dove finisce quello che dici. La stanza è quella
 *  di chi è firmato quando si sa (`access`), quella del nodo altrimenti. */
export function headline(health, t, access) {
  const stanza = (access && access.room) || roomOf(health);
  if (!stanza) return t("room.local");
  return t("room.in", { room: stanza });
}

/** Le code rimaste indietro sul NODO, dette in una frase. */
export function leftBehind(health, t) {
  const code = (health && health.queues) || [];
  if (!code.length) return "";
  const quante = code.reduce((a, q) => a + q.pending, 0);
  return t(quante === 1 ? "room.left.one" : "room.left.many",
           { n: quante, rooms: code.length });
}

export function paintHeader(health, access) {
  const seam = SG();
  const riga = $("room-name");
  if (riga) riga.textContent = headline(health, seam.t, access);
}

/* ── la colonna ───────────────────────────────────────────────────────────── */

export function paintPanel(host, health, stato) {
  const t = SG().t;
  host.textContent = "";

  const dove = document.createElement("p");
  dove.className = "hint";
  dove.textContent = headline(health, t, stato);
  host.append(dove);

  // LA CODA DI QUESTA PERSONA per questa stanza, sul nodo — e perché non parte
  if (stato && stato.pending) {
    const coda = document.createElement("p");
    coda.className = "hint";
    coda.id = "room-pending";
    coda.textContent = t(stato.pending === 1 ? "room.pending.one" : "room.pending.many",
                         { n: stato.pending })
      + (stato.pending_refused ? " — " + stato.pending_refused : "");
    const manda = document.createElement("button");
    manda.type = "button";
    manda.id = "room-deliver";
    manda.textContent = t("f.deliver_now");
    manda.addEventListener("click", async () => {
      manda.disabled = true;
      manda.textContent = t("f.delivering");
      $("room-says").textContent = await deliver(t);
      await refresh(host, health);
    });
    host.append(coda, manda);
  }
  const rimaste = leftBehind(health, t);
  if (rimaste) {
    const coda = document.createElement("p");
    coda.className = "hint";
    coda.textContent = rimaste;
    host.append(coda);
  }

  const campo = document.createElement("input");
  campo.type = "text";
  campo.id = "room-target";
  campo.placeholder = t("room.placeholder");
  campo.enterKeyHint = "go";
  const vai = document.createElement("button");
  vai.type = "button";
  vai.id = "room-go";
  vai.textContent = t("room.point");
  const torna = document.createElement("button");
  torna.type = "button";
  torna.id = "room-back";
  torna.textContent = t("room.back");

  const esito = document.createElement("p");
  esito.className = "hint";
  esito.id = "room-says";

  const punta = async () => {
    const detto = campo.value.trim();
    if (!detto) return;
    esito.textContent = t("room.pointing");
    const corpo = detto.includes("://")
      ? { link: detto }
      : { room: detto, server: (health && health.server_hint) || "" };
    esito.textContent = await point(corpo, t);
    await refresh(host, health);
  };
  vai.addEventListener("click", punta);
  campo.addEventListener("keydown", (e) => { if (e.key === "Enter") punta(); });
  torna.addEventListener("click", async () => {
    esito.textContent = await unpoint(t);
    await refresh(host, health);
  });

  const riga = document.createElement("div");
  riga.className = "row";
  riga.append(vai, torna);
  host.append(campo, riga, esito);
}

/** Prova la porta per chi è firmato; se si apre, il posto si ricorda QUI. */
export async function point(corpo, t) {
  const seam = SG();
  try {
    // senza il posto di adesso: si sta chiedendo di un ALTRO posto
    const risposta = await fetch(seam.node + "/v1/room", {
      method: "POST",
      headers: { "Content-Type": "application/json",
                 Authorization: "Bearer " + await seam.freshToken() },
      body: JSON.stringify(corpo),
    });
    const detto = await risposta.json();
    if (risposta.ok) {
      seam.setWhere({ server: detto.server, room: detto.room });
      seam.setAccess(detto);
    }
    return risposta.ok ? (detto.message || t("room.pointed"))
                       : (detto.detail || t("room.refused"));
  } catch { return t("room.unreachable"); }
}

async function unpoint(t) {
  const seam = SG();
  try {
    const risposta = await seam.request("/v1/room", { method: "DELETE" });
    const detto = await risposta.json();
    if (risposta.ok) {
      seam.setWhere(null);
      seam.setAccess(await look());
    }
    return risposta.ok ? (detto.message || t("room.went.back"))
                       : (detto.detail || t("room.refused"));
  } catch { return t("room.unreachable"); }
}

/** «Consegna ora» — la coda di chi è firmato, sul nodo, col token di adesso. */
async function deliver(t) {
  const seam = SG();
  try {
    const risposta = await seam.request("/v1/room/deliver", { method: "POST" });
    const detto = await risposta.json();
    return detto.message || detto.detail || t("room.refused");
  } catch { return t("room.unreachable"); }
}

async function refresh(host, _health) {
  const seam = SG();
  try {
    const salute = await (await fetch(seam.node + "/health",
                                      { cache: "no-store" })).json();
    const stato = await look();
    seam.setAccess(stato);
    paintHeader(salute, stato);
    paintPanel(host, salute, stato);
  } catch { /* il nodo non c'e': la riga di prima resta, ed e' onesta */ }
}

/** Aggancia il pannello. Ridisegnato a ogni `ping`, come il resto — e a ogni
 *  `ping` si rilegge il RUOLO: un accesso tolto mentre si lavora si vede entro
 *  un battito, invece che al prossimo rifiuto. */
export function mount(host) {
  return async (health) => {
    const stato = await look();
    SG().setAccess?.(stato);
    paintHeader(health, stato);
    if (host && !host.hidden) paintPanel(host, health, stato);
  };
}
