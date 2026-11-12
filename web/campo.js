/* «IN CAMPO» COME NEL MOCKUP (NIGHT 15 novembre 2026, v7.2).
 *
 * Fino a stanotte «In campo» su uno schermo largo mostrava la vecchia
 * architettura: la colonna con Stanza (Detta, Unità, Mappa), l'ELENCO delle
 * definizioni di scheda, «Dove scrivo», «Tutti i campi»; al centro «Tocca e
 * parla» largo e il resto vuoto. Nel mockup in campo ci sono quattro voci —
 *
 *     Detta · Scheda · Foto · Consegna (col numero da consegnare)
 *
 * — in basso sul telefono, in alto sul tablet (e su uno schermo largo la
 * cornice del tablet, centrata). Ognuna va a ciò che l'app ha già:
 *
 *   Detta      il pannello della voce di sempre (`#work`)
 *   Scheda     la scheda aperta, o l'ultima unità toccata (la regola della
 *              Scheda alla scrivania); le definizioni nel menu «Scheda»
 *   Foto       la sezione Foto della scrivania (`scrivania.js`): quelle che
 *              aspettano su questo dispositivo e quelle della stanza
 *   Consegna   la coda di QUESTO dispositivo (`SG.queued`), l'ultima consegna
 *              confermata (`SG.savedAt`), «Consegna ora» (`SG.flush`) e
 *              «Prendi dalla stanza»
 *
 * Questo modulo non parla al grafo e non inventa una funzione: dipinge le
 * quattro voci e la Consegna, e per tutto il resto chiama la conchiglia. */

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

/** LE QUATTRO VOCI, in ordine: chiave · pannelli per cui la voce è «qui». La
 *  Scheda è qui anche sull'elenco delle unità e sulla mappa: sono la strada per
 *  arrivare a una scheda, e in campo non hanno una voce loro. */
export const FIELD_TABS = [
  ["voice", ["voice"]],
  ["sheet", ["scheda", "index", "map"]],
  ["photos", ["photos-sec"]],
  ["deliver", ["deliver"]],
];

/** Quale voce è accesa per il pannello davanti. Pura. */
export function fieldTabOf(panel) {
  const hit = FIELD_TABS.find(([, panels]) => panels.includes(panel));
  return hit ? hit[0] : null;
}

/** La riga dello stato IN CAMPO, come nel mockup: «REST · n da consegnare».
 *  Il dispositivo in campo è un corrispondente (REST): entra, consegna, esce.
 *  Senza rete la prima parola lo dice. Pura. */
export function fieldStateLine({ online = true, pending = 0, tr = t, short = false } = {}) {
  // SUL TELEFONO, IN RETE, solo il numero («3 da consegnare», come il gettone
  // del mockup): la barra è una riga sola. Senza rete la prima parola resta.
  if (short && online) return tr("f.queue", { n: pending });
  const head = online ? "REST" : tr("node.offline");
  return `${head} · ${tr("f.queue", { n: pending })}`;
}

function hhmm(when) {
  return new Date(when).toLocaleTimeString(SG().locale || undefined,
                                           { hour: "2-digit", minute: "2-digit" });
}

export function mount(shell) {
  let delivering = false;
  let delivered = "";
  let pulled = "";

  /** Le voci: quale è accesa, e il numero sulla Consegna. */
  function paintTabs() {
    const here = fieldTabOf(shell.state.panel);
    for (const b of document.querySelectorAll("#field-tabs [data-ftab]")) {
      b.setAttribute("aria-current", String(b.dataset.ftab === here));
    }
    const n = SG().pending || 0;
    const badge = $("tb-deliver-n");
    if (badge) {
      badge.hidden = !n;
      badge.textContent = n ? String(n) : "";
    }
  }

  /** «PRENDI DALLA STANZA»: prima di scendere in trincea, ciò che serve per
   *  lavorare senza rete — l'elenco delle definizioni, ogni definizione nella
   *  sua lingua (finiscono nella cache del dispositivo, `definitionFor`) e le
   *  unità della stanza. Le stesse letture che l'app fa già, tutte insieme. */
  async function pull() {
    pulled = t("f.pulling");
    paintDeliver();
    const got = await shell.pullRoom();
    pulled = got ? t("f.pulled", { s: got.schede, u: got.units }) : t("f.need_net");
    paintDeliver();
  }

  async function deliver() {
    if (delivering) return;
    delivering = true;
    delivered = "";
    paintDeliver();
    const before = SG().pending || 0;
    try { await (SG().flush ? SG().flush() : null); } catch { /* resta in coda */ }
    const after = SG().pending || 0;
    delivering = false;
    delivered = before > after ? t("f.delivered", { n: before - after }) : "";
    paintDeliver();
    paintTabs();
  }

  /** CONSEGNA: ciò che aspetta, l'ultima consegna, i due gesti. */
  function paintDeliver() {
    const host = $("deliver");
    if (!host || host.hidden) return;
    const online = !(($("state") || {}).classList || { contains: () => false }).contains("off");
    const items = SG().queued || [];
    const saved = SG().savedAt || 0;
    const wrap = el("div", { class: "sheetwrap fld-deliver" });
    if (delivered) wrap.append(el("div", { class: "okmsg", role: "status", text: delivered }));
    const card = el("div", { class: "dcard" },
      el("div", { class: "qitem" }, el("span", { text: t("f.last") }),
        el("span", { class: "k", text: saved ? hhmm(saved) : "—" })));
    for (const q of items) {
      card.append(el("div", { class: "qitem" },
        el("span", { text: q.describe || q.path || "" }),
        el("span", { class: "k", text: q.refused ? q.refused : t("f.pending") })));
    }
    wrap.append(card);
    const go = el("button", { type: "button", class: "primary bigq", "data-pact": "deliver",
                              text: t(delivering ? "f.delivering" : "f.deliver_now"),
                              disabled: !online || !items.length || delivering });
    go.addEventListener("click", () => { void deliver(); });
    wrap.append(go);
    // IL PERCHÉ DI UN BOTTONE SPENTO SI LEGGE, non si cerca passandoci sopra
    if (!online) wrap.append(el("p", { class: "why", text: t("f.need_net") }));
    else if (!items.length) wrap.append(el("p", { class: "why", text: t("f.nothing") }));
    const take = el("button", { type: "button", "data-pact": "pull", class: "pbtn",
                                text: t("f.pull"), disabled: !online });
    take.addEventListener("click", () => { void pull(); });
    wrap.append(el("div", { class: "dcard" }, take,
      el("p", { class: "why", text: pulled || t("f.pull_note") })));
    host.replaceChildren(wrap);
  }

  function paint() {
    paintTabs();
    paintDeliver();
  }

  return { paint, paintTabs, paintDeliver };
}
