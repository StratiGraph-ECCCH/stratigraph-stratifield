"""Uno scrivano per persona e per stanza — e ogni scrittura porta chi e dove.

════════════════════════════════════════════════════════════════════════════════
## COSA C'ERA, MISURATO

Lo scrivano era **uno per nodo** (`main.WRITER`), costruito dall'ambiente, con
il token del nodo. La firma del browser diceva CHI parla (`_author`) e non DOVE
arriva, e nella stanza l'identità la mette il relay **dal token di chi
consegna** (`stratigraph-server/app/ws.py`, «the author of every operation is
the token's identity»). Quindi su un nodo tenuto da Anna una scheda di Marco
entrava firmata Anna, e con i permessi di Anna. `holding.py` rendeva la cosa
onesta dicendola («un nodo, una persona alla volta»), ma la restrizione restava.

## LA FORMA SCELTA, E PERCHÉ È LA PIÙ SEMPLICE CHE REGGE

**Uno scrivano per (persona, server, stanza)**, costruito alla prima richiesta
di quella persona per quella stanza, con **il token di quella persona**, e
rinnovato a ogni richiesta (`RoomWriter.renew`). Le altre forme misurate:

* *uno scrivano per nodo col token della richiesta corrente* — non regge: la
  sessione websocket è aperta con UN token, e il relay firma tutto quello che
  passa da lì col nome di chi l'ha aperta. Riaprirla a ogni cambio di persona
  sarebbe uno scrivano per persona con un solo posto a sedere, cioè la presa
  sotto un altro nome;
* *lo scambio del token al realm* (`handoff.exchange`) — chiede al realm una
  funzione (token exchange) che il dev-stack non accende e che il realm
  istituzionale è di un altro; e il token che ne esce è comunque della persona.

Il token della persona viene presentato **solo** a un server che il NODO ha
nominato (`EM_ROOM_SERVERS`, o il suo `EM_SERVER_URL`). È l'argomento del
*confused deputy* che `_room_credential` faceva contro l'inoltro, e la sua
risposta: il pericolo era un LINK che sceglie il server, e un link ora può
scegliere solo fra i server che chi amministra il nodo ha scritto. Il token del
browser porta già `aud: em-server` (il realm lo conia così, `em-console` ha due
mapper di pubblico): è fatto per quella stanza, non è preso in prestito.

## QUELLO CHE SEGUE DALLA FORMA

* **la coda** è per (stanza, persona) (`bridge_for(…, who=)`): un'operazione in
  coda non porta l'autore, e consegnata col token di un altro diventerebbe sua;
* **la presenza** è vera: nella stanza siede chi scrive, non il nodo. E quando
  quella persona tace per `idle_after` secondi la sua sessione si chiude —
  il nodo non può rinnovarle il token, e sedere a nome di qualcuno che se n'è
  andato è la bugia che la presenza esiste per non dire;
* **il ruolo** è quello della persona (`RoomWriter.role`): un viewer si siede e
  legge, e la frase del rifiuto arriva quando prova a scrivere.

Il nodo senza persona — un servizio headless con `EM_CHATBOT_TOKEN` — resta
com'era: `main.WRITER`, seduto all'avvio. Lo usa chi non ha identità (il modo
sviluppo) e nessun altro.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .bridge import bridge_for
from .writer import RoomWriter

log = logging.getLogger("stratigraph.scrivani")

#: Dopo quanto silenzio di una persona la sua sessione si chiude. Lo stesso
#: numero della presa di prima (`EM_NODE_IDLE`, venti minuti): la pausa che
#: separa «sta scavando» da «ha messo giù il telefono».
IDLE_SECONDS = int(os.environ.get("EM_NODE_IDLE") or 20 * 60)


class NotTrusted(ValueError):
    """Un server che questo nodo non ha nominato: il token non ci va."""


@dataclass(frozen=True)
class Where:
    """Dove scrive una persona. `server` è come lo nomina chi lo dice (il link,
    il browser); `dial` è l'indirizzo che questo nodo compone davvero — in un
    container, il server pubblico e quello raggiungibile non sono lo stesso."""

    server: str
    room: str
    dial: str

    def key(self) -> Tuple[str, str]:
        return (self.dial, self.room)


def trusted_servers(environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """`{come lo si nomina: dove lo si compone}` per i server a cui questo nodo
    può presentare il token di una persona.

    `EM_ROOM_SERVERS` è una lista separata da virgole; ogni voce è un indirizzo,
    o `pubblico=raggiungibile` quando il nodo sta in un container e il nome che
    il link porta non si raggiunge da dentro:

        EM_ROOM_SERVERS=https://em.localhost:8443/em=http://stratigraph-server:8000

    `EM_SERVER_URL`, se c'è, è fidato per costruzione: l'ha scritto chi ha
    configurato il nodo, ed è già quello con cui il nodo si siede.
    """
    env = environ if environ is not None else os.environ
    found: Dict[str, str] = {}
    for item in (env.get("EM_ROOM_SERVERS") or "").split(","):
        item = item.strip()
        if not item:
            continue
        named, _, dial = item.partition("=")
        named = named.strip().rstrip("/")
        found[named] = (dial.strip() or named).rstrip("/")
    base = (env.get("EM_SERVER_URL") or "").strip().rstrip("/")
    if base:
        found.setdefault(base, base)
    return found


class Scrivani:
    """Il registro degli scrivani per persona. Uno per processo.

    `build_registry(writer)` è passato e non importato: il registro dei tool
    lega lo scrivano ai descrittori quando li costruisce, e ogni scrivano ne ha
    uno suo — costruito una volta, tenuto accanto.
    """

    def __init__(self, *, local: Any, spool: Any,
                 build_registry: Callable[[Any], Any],
                 trusted: Optional[Dict[str, str]] = None,
                 idle_after: int = IDLE_SECONDS,
                 make: Optional[Callable[..., Any]] = None) -> None:
        self.local = local
        self.spool = spool
        self.build_registry = build_registry
        self.trusted = dict(trusted if trusted is not None else trusted_servers())
        self.idle_after = idle_after
        self._make = make or RoomWriter
        self._lock = threading.Lock()
        #: (who, dial, room) → [writer, registry, last_used_monotonic]
        self._by: Dict[Tuple[str, str, str], List[Any]] = {}

    # ── dove ─────────────────────────────────────────────────────────────────

    def where(self, server: str, room: str) -> Where:
        """Un posto dichiarato, o `NotTrusted` con la frase."""
        named = (server or "").strip().rstrip("/")
        room = (room or "").strip()
        if not named or not room:
            raise ValueError("serve un server e una stanza")
        dial = self.trusted.get(named)
        if dial is None:
            known = ", ".join(sorted(self.trusted)) or "nessuno"
            raise NotTrusted(
                f"Questo nodo non presenta la tua firma a «{named}»: non è fra i "
                f"server che chi amministra il nodo ha nominato "
                f"(EM_ROOM_SERVERS). Quelli che conosce: {known}.")
        return Where(server=named, room=room, dial=dial)

    def configured(self, server: str, room: str) -> Where:
        """Il posto che il NODO ha nell'ambiente: fidato per costruzione."""
        base = server.rstrip("/")
        return Where(server=base, room=room, dial=self.trusted.get(base, base))

    # ── chi ─────────────────────────────────────────────────────────────────

    def writer(self, who: str, bearer: str, where: Where) -> Tuple[Any, Any]:
        """(scrivano, registro) di questa persona in questo posto.

        Il token si rinnova a ogni chiamata: è quello della richiesta che sta
        succedendo adesso, già verificato dall'autenticatore di questo nodo.
        """
        if not who:
            raise ValueError("uno scrivano per persona senza una persona")
        self.sweep()
        key = (who, where.dial, where.room)
        with self._lock:
            entry = self._by.get(key)
            if entry is None:
                writer = self._make(
                    where.dial, where.room, bearer, fallback=self.local,
                    spool=self.spool,
                    bridge=bridge_for(self.local.path, where.room, who=who))
                writer.public_server = where.server
                entry = [writer, self.build_registry(writer), time.monotonic()]
                self._by[key] = entry
                log.info("scrivano nuovo: %s in %s su %s", who, where.room,
                         where.dial)
            else:
                entry[0].renew(bearer)
                entry[2] = time.monotonic()
            return entry[0], entry[1]

    def mine(self, who: str) -> List[Any]:
        with self._lock:
            return [e[0] for k, e in self._by.items() if k[0] == who]

    def everyone(self) -> List[Any]:
        with self._lock:
            return [e[0] for e in self._by.values()]

    def seated(self) -> bool:
        """C'è almeno una sessione tenuta verso una stanza? È una proprietà
        della RETE fra questo nodo e la stanza, e la postura (scrivania o campo)
        la legge da qui."""
        return any(getattr(getattr(w, "session", None), "seated", False)
                   for w in self.everyone())

    # ── il silenzio ─────────────────────────────────────────────────────────

    def sweep(self, *, now: Optional[float] = None) -> int:
        """Chiude le sessioni di chi tace da più di `idle_after` secondi.

        Lo scrivano resta (la sua coda è su disco comunque): si chiude solo il
        posto a sedere, che il nodo non saprebbe tenere col token di una
        persona che non c'è più.
        """
        now = time.monotonic() if now is None else now
        closed = 0
        with self._lock:
            entries = list(self._by.values())
        for writer, _registry, last in entries:
            session = getattr(writer, "session", None)
            if session is not None and session.seated and now - last > self.idle_after:
                try:
                    session.close()
                    closed += 1
                except Exception:           # noqa: BLE001 — chiudere non fallisce
                    pass
        return closed

    def close_all(self) -> None:
        for writer in self.everyone():
            leave = getattr(writer, "close", None)
            if leave is not None:
                try:
                    leave()
                except Exception:           # noqa: BLE001
                    pass
