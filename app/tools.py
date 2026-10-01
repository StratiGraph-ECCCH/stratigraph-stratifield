"""The seven tools — the first clients of the contract.

Grown from Elisa Dalla Longa's field card (design note §4): a thick forex card
with colour-coded voice commands, an accessibility artefact that doubles as the
command specification. The commands on it ARE the intents below, in the words a
person says with their hands in the soil.

| said in the field | tool | what changes |
|---|---|---|
| "crea una nuova scheda" | `create_su` | a StratigraphicUnit in the graph |
| "in che progetto sto lavorando" | `which_project` | nothing — it answers |
| "questa foto è per la US 12" | `attach_photo_to_su` | bytes in the store, a resource on the unit |
| "ti passo delle foto" | `ingest_photos` | bytes in the store, queued to a unit |
| "cosa abbiamo registrato nel saggio B" | `query_kg` | nothing — it answers from the graph |
| "costruisci il modello 3D di questa US" | `build_model` | the node reconstructs; a model and its provenance appear |

The sixth is the newest and the odd one out: it is the only tool whose service
is not this process. It ASKS the node (`/v1/photogrammetry`) and reads the answer
back — which is what a voice should do with an act that takes minutes and needs
an engine.

**Every write goes through s3Dgraphy.** Not "mostly": the domain rule about what
a stratigraphic unit is, and what a resource attached to one means, lives in the
library and is not restated here. This module builds the delta by asking the
library to do the act on a scratch graph and reading what appeared — which is
also why a change in the library's node shape does not silently diverge from
what the field assistant writes.

**Everything is attributed.** The author is the ORCID of the token, stamped by
`invoke`; the act itself is a `crmdig:D7` process node, the same genesis record
the promotion arc uses. A record without a hand behind it is one nobody can
defend three years later, when it matters.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import authorship, exif
from .contract import (GraphDelta, Slot, ToolDescriptor, ToolRegistry,
                       ToolResult, stable_id)
from .spool import verify as spool_verify

#: The DTC term for "this was made by that act". Not a word invented here: it is
#: the one `s3dgraphy.publication` already uses for a genesis event.
DTC_PROCESS = "dtc_process"

def unit_id_for(number: str) -> str:
    """The id of a stratigraphic unit, from its number — in ONE place.

    `create_su` has always used `f"US{number}"`, a readable id rather than a
    `stable_id` hash, and that is kept: it is what is already in every graph
    this assistant has written, and re-minting would orphan them.

    IT LIVES HERE because `update_su` needs the SAME answer. Written twice it
    was wrong immediately: the second copy said `stable_id("us", number)`, and
    every update was refused with «non è in questo grafo» against a unit that
    had just been created two lines above. Caught by a test; it would have been
    a scheda that silently refused to save.

    KNOWN LIMIT, inherited and declared: the id does not carry `sito`/`area`,
    though `create_su` stores both in `data`. So two areas with a unit «1» are
    one node. That is pre-existing behaviour of this service, not a decision
    taken tonight, and changing it re-mints ids.
    """
    return f"US{str(number).strip()}"


def number_from_unit_id(node_id: str, name: str = "") -> str:
    """Il numero di un'unità, dal suo id — l'inverso di `unit_id_for`.

    STA QUI accanto al suo gemello per la stessa ragione che la docstring sopra
    racconta: scritto altrove sarebbe la seconda copia, e la seconda copia era
    già sbagliata la prima volta.

    Serve a riaprire una scheda su un'unità che esiste: la superficie ha un id e
    un nome, gli attrezzi vogliono il NUMERO, e `update_su` rifiuta un numero
    che non corrisponde a nessun nodo — che è la sua virtù, non un ostacolo da
    aggirare con un'euristica.

    `""` quando l'id non è stato coniato da `unit_id_for`: succede con i grafi
    importati, e allora il numero non si indovina. Chi chiama lo dice invece di
    proporre una scheda su un'unità sbagliata.
    """
    raw = str(node_id or "").strip()
    if raw.startswith("US") and raw[2:].strip():
        return raw[2:].strip()
    #: la forma che `create_su` dà al NOME, quando l'id viene da altrove
    label = str(name or "").strip()
    if label.upper().startswith("US ") and label[3:].strip():
        return label[3:].strip()
    return ""


#: What `update_su` will not change, though the CRDT would let it. `name` is
#: derived from the unit number and is mentioned in other people's nodes; `id`
#: is the identity itself. Refused by name rather than silently dropped, because
#: a form that sent one and got a success would have been told a lie.
_NOT_UPDATABLE = frozenset({"name", "id", "node_type"})


def _now() -> str:
    from s3dgraphy.editorial import now_iso
    return now_iso()


def _process_node(kind: str, author: Optional[str], about: str,
                  detail: str = "") -> Dict[str, Any]:
    """The `crmdig:D7` that records the act.

    Deterministic id from what the act is ABOUT, so the same act asked twice is
    the same act — which is what makes a retry on a flaky field network safe.
    """
    node_id = stable_id(kind, about)
    return {
        "id": node_id,
        "node_type": DTC_PROCESS,
        "name": kind,
        "description": detail or f"{kind} · {about}",
        "data": {"created_by": author, "created_at": _now(),
                 "tool": kind, "source": "stratigraph-chatbot",
                 # s3Dgraphy dev28 (decision 12): the language a node is born in
                 # travels in the op, decided by its producer. This description is
                 # written by THIS code, in Italian: it is born `it`.
                 "lang": PROCESS_TEXT_LANG},
    }


#: the language of the sentences this service writes into its D7 (`_process_node`)
PROCESS_TEXT_LANG = "it"



# ── LA RICETTA: la via unica da una scheda (o da una frase) alla stanza ─────
#
# Dal 19 ottobre `create_su`, `update_su` e `relate_su` non costruiscono più
# `data.<id_campo>`: passano i valori al generatore (`app/operazioni.py`) con la
# ricetta della scheda, e mandano la lista di operazioni che ne esce con
# `graph_writer.send`. Il vecchio percorso — `writer.addressable` che prefissava
# `data.` al nome della casella — è quello che l'audit del 17 ottobre ha
# misurato: 58 chiavi, 0 archi, e una proiezione RDF senza valori.

#: La scheda con cui la VOCE compila, quando l'unità non ne dichiara una sua.
#: Una cosa del NODO, come la lingua dei comandi: un nodo che serve la ficha
#: spagnola la nomina qui.
REFERENCE_SCHEDA_VARIABLE = "STRATIGRAPH_SCHEDA_RIFERIMENTO"
REFERENCE_SCHEDA_DEFAULT = "iccd-us-2021"


def reference_scheda():
    """La scheda di riferimento del nodo, o None se il nodo non ne serve."""
    import os

    from . import scheda as schede
    wanted = (os.environ.get(REFERENCE_SCHEDA_VARIABLE) or "").strip()
    return schede.find(wanted or REFERENCE_SCHEDA_DEFAULT)


def scheda_for(graph_writer, number: str, *, scheda_id: str = "",
               version: str = ""):
    """Con quale definizione si compila questa unità.

    Chiesta esplicitamente (la scheda aperta nel modulo) vince; altrimenti
    quella che l'unità DICHIARA (`data.scheda`, B5b) se il nodo la serve;
    altrimenti la scheda di riferimento del nodo. Torna `(scheda, perché)`.
    """
    from . import scheda as schede
    from .operazioni import MARK

    if scheda_id:
        return schede.find(scheda_id, version=version or None), "chiesta"
    node = graph_writer.node(unit_id_for(number)) if number else None
    declared = ((node or {}).get("data") or {}).get(MARK) or {}
    if isinstance(declared, dict) and declared.get("template") and not declared.get("stub"):
        found = schede.find(str(declared["template"]),
                            version=str(declared.get("version") or "") or None)
        if found is not None:
            return found, "dichiarata dall'unità"
    return reference_scheda(), "di riferimento del nodo"


def _through_the_recipe(graph_writer, scheda, values: Dict[str, Any], *,
                        number: str, create: bool, author: Optional[str],
                        kind: str, detail: str,
                        authored_by: Optional[Dict[str, str]] = None,
                        model: Optional[str] = None, additive: bool = False,
                        extra_ops: Optional[List[Dict[str, Any]]] = None,
                        relations: Optional[List[Tuple[str, str, str]]] = None,
                        lang: Optional[str] = None):
    """Valori → operazioni → stanza, e l'esito per campo. Una sola via.

    Il D7 dell'atto va IN CODA alla lista, per la ragione che `LocalWriter.update`
    racconta: un atto che la stanza rifiuta non deve lasciare un verbale che
    dice che è avvenuto.
    """
    from s3dgraphy import api

    from .operazioni import plan as make_plan

    stamp = _now()
    made = make_plan(scheda, values, number=number,
                     section=graph_writer.section(), ts=stamp, create=create,
                     authored_by=authored_by, model=model, additive=additive,
                     relations=relations, lang=lang)
    process = _process_node(kind, author, made.unit_id, detail)
    ops = list(made.ops) + list(extra_ops or [])
    fields_of = list(made.op_fields) + [""] * len(extra_ops or [])
    ops.append(api.make_op("add_node", id=process["id"], node=process, ts=stamp))
    fields_of.append("")
    outcomes = graph_writer.send(ops, author=author)

    landed, already, held = [], [], []
    for fid in made.written:
        mine = [o for i, (o, f) in enumerate(zip(outcomes, fields_of))
                if f == fid and i not in made.noop]
        if any(o["applied"] and o.get("changed", True) for o in mine):
            landed.append(fid)
        elif any(o.get("reason") == "stale" for o in mine):
            held.append({"field": fid, "applied": False, "reason": "stale"})
        else:
            already.append(fid)
    return made, process, outcomes, landed, already, held


def _what_happened(made, landed, already, held, number: str) -> str:
    """La frase, per chi ha salvato: che cosa è entrato, che cosa no, e perché."""
    said = f"US {number}: {len(landed)} campi aggiornati."
    if made.created:
        said += f" Creata come {made.node_type}."
    if already:
        said += f" {len(already)} erano già così."
    if held:
        said += (f" {len(held)} non applicati (qualcun altro li ha scritti più "
                 f"di recente): {', '.join(h['field'] for h in held)}.")
    if made.refused:
        said += " Non scritti: " + "; ".join(
            f"{k} ({v})" for k, v in sorted(made.refused.items())) + "."
    outside = sorted(k for k, v in made.silent.items()
                     if not v.startswith(("compone", "decide")))
    if outside:
        said += (" Fuori dal grafo per la definizione: " + ", ".join(outside) + ".")
    if made.stubs:
        said += (" Segnate da compilare, perché un rapporto le nomina: "
                 + ", ".join(s["name"].split(" — ")[0] for s in made.stubs) + ".")
    for note in made.notes:
        said += f" ({note}.)"
    return said


def _plan_data(made, outcomes, landed, already, held) -> Dict[str, Any]:
    return {"us": made.number, "node_id": made.unit_id,
            "created": made.created, "node_type": made.node_type,
            "updated": landed, "already": already, "not_applied": held,
            "refused": dict(made.refused), "silent": dict(made.silent),
            "stubs": list(made.stubs), "notes": list(made.notes),
            "operations": made.counts(),
            "queued": any(o.get("queued") for o in outcomes)}


def _box_for_slot(scheda, slot: str) -> str:
    """La casella della scheda che uno slot della voce riempie — dalla ricetta."""
    entries = (scheda.recipe or {}).get("fields") or {}
    if slot == "description":
        for fid, entry in entries.items():
            steps = entry.get("steps") or []
            if (len(steps) == 1 and steps[0]["emit"]["op"] == "update_field"
                    and steps[0]["emit"].get("field") == "description"):
                return fid
        return ""
    if slot == "sito":
        context = [f for f in scheda.human_key if f != scheda.unit_field]
        return context[0] if context else ""
    if slot in scheda._by_id:
        return slot
    for fid, entry in entries.items():
        if (entry.get("property") or {}).get("property_type") == slot:
            return fid
    return ""


# ── 1 · create_su ────────────────────────────────────────────────────────────

def make_create_su(graph_writer) -> ToolDescriptor:
    """A new stratigraphic unit, by voice.

    `graph_writer` is how this node writes: a room client, or the local
    container when the excavation is offline. The tool does not know which, and
    that is the point of §5 — convergence on the graph, not coupling.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        from .operazioni import MARK, OperazioniError

        number = str(slots.get("us") or "").strip()
        unit_id = unit_id_for(number)
        if not number:
            return ToolResult(ok=False, message="Mi manca il numero dell'unità.")

        # ── GIÀ PRESENTE — a meno che sia soltanto SEGNATA da un rapporto ────
        #
        # Una US che un'altra scheda ha nominato («copre 3018») esiste come
        # stub (`app/operazioni.py`, decisione 1). Crearla davvero non è
        # crearne una seconda: è darle la sua scheda, e il generatore la
        # promuove.
        present = graph_writer.node(unit_id)
        if present is not None and not (
                ((present.get("data") or {}).get(MARK) or {}).get("stub")):
            return ToolResult(
                ok=True,
                message=f"US {number} già presente, non l'ho creata di nuovo.",
                delta=GraphDelta(),
                data={"us": number, "node_id": unit_id, "created": False})

        scheda = reference_scheda()
        if scheda is None:
            return ToolResult(
                ok=False,
                message=("Questo nodo non serve una scheda di riferimento "
                         f"({REFERENCE_SCHEDA_VARIABLE}): senza una ricetta "
                         "non so che tipo di nodo sia un'unità, né dove vadano "
                         "le cose che mi dici."),
                data={"us": number, "reason": "no-scheda"})

        # ── GLI SLOT DELLA VOCE (e degli adattatori), come caselle della scheda
        #
        # Derivati dalla ricetta, non da una tabella scritta qui:
        #   description    → la casella che la ricetta scrive in `description`
        #   interpretation → la casella la cui proprietà è `interpretation`
        #   sito           → il primo campo di contesto della chiave umana
        #                    (localita · yacimiento · lelohely: il più largo)
        #   area           → la casella che si chiama `area`, se c'è
        #
        # Il 21 agosto `interpretation` era stata decisa NOTA DI CAMPO
        # (`data.interpretation`) perché una frase non ha una catena di
        # evidenza. La ricetta ICCD dice invece `interpretazione` →
        # PropertyNode `interpretation`, e la ricetta è la fonte: la decisione
        # si è rovesciata DOVE si decide, nella definizione, non qui.
        values: Dict[str, Any] = {}
        for slot, value in (("description", slots.get("description")),
                            ("interpretation", slots.get("interpretation")),
                            ("sito", slots.get("sito")),
                            ("area", slots.get("area"))):
            if value in (None, ""):
                continue
            box = _box_for_slot(scheda, slot)
            if box:
                values[box] = str(value).strip()

        # ── ciò che gli adattatori portano e nessuno ha mappato ──────────────
        #
        # PyArchInit's `rapporti`, its `unita_misura`, whatever ATRIUM adds next
        # release. Kept under one key rather than spread across `data`, so a
        # reader can always tell what this service UNDERSTOOD from what it
        # merely carried. NOT a scheda field — which is why it is the one
        # `update_field data.…` this tool still writes by name.
        extra_ops: List[Dict[str, Any]] = []
        extra = slots.get("extra")
        if isinstance(extra, dict) and extra:
            from s3dgraphy import api
            extra_ops.append(api.make_op("update_field", node_id=unit_id,
                                         field="data.source_fields",
                                         value=dict(extra), ts=_now()))
        try:
            made, process, outcomes, landed, already, held = _through_the_recipe(
                graph_writer, scheda, values, number=number, create=True,
                author=author, kind="create_su",
                detail=f"US {number} creata a voce sul campo",
                extra_ops=extra_ops, lang=slots.get("lang"))
        except OperazioniError as wrong:
            return ToolResult(ok=False, message=str(wrong),
                              data={"us": number, "node_id": unit_id})
        unit_node = next((o["node"] for o in made.ops
                          if o["op"] == "add_node" and o.get("id") == unit_id), None)
        message = f"Ho creato la US {number}."
        if made.refused or made.stubs:
            message += " " + _what_happened(made, landed, already, held,
                                            number).split(": ", 1)[1]
        data = _plan_data(made, outcomes, landed, already, held)
        data["created"] = True
        return ToolResult(
            ok=True,
            # Said out loud. "US 12 creata" is what a person needs to hear to
            # know the record exists and keep digging.
            message=message,
            delta=GraphDelta(nodes=[unit_node] if unit_node else [],
                             process=process, author=author),
            data=data)

    return ToolDescriptor(
        name="create_su",
        intents=["crea una nuova scheda", "nuova scheda", "nuova unità",
                 "nuova us", "crea una us"],
        input_schema=[
            Slot("us", "string", True, "il numero dell'unità"),
            # Optional, all of them: a unit dictated in three words is still a
            # unit. What the adapters carry, this now honours.
            Slot("description", "string", False, "cosa c'è (crm:P3_has_note)"),
            Slot("interpretation", "string", False,
                 "cosa si pensa che sia — nota di campo, non ancora una "
                 "property con la sua catena di evidenza"),
            Slot("extra", "id", False,
                 "i campi che l'adattatore non mappa: portati, non buttati"),
            Slot("sito", "string", False, "il sito, quando il record lo dice"),
            Slot("area", "string", False, "l'area: una US è unica dentro la sua"),
        ],
        description="Una nuova unità stratigrafica nel grafo condiviso.",
        service="s3dgraphy", handler=handler)


# ── 1bis · update_su — THE EIGHTH, and the first one a SCHEDA needs ─────────

def make_update_su(graph_writer) -> ToolDescriptor:
    """Correct or complete a unit that already exists.

    ## WHY THIS COULD NOT BE `create_su` WITH MORE SLOTS

    Because of one measured line. `s3dgraphy.crdt.apply_op_to_section`:

        if kind == "add_node":
            existing = by_id.get(node_id)
            if existing is None:
                nodes.append(payload)
                return OpResult(True, "added", node_id)

    **`add_node` on an id that is not there CREATES it.** So a scheda that
    corrected «US 21» when the unit in the graph is «US 12» — a mistyped number,
    a form opened against the wrong study — would not fail: it would quietly
    mint a new unit with one field in it, under the author's name, and report a
    success. `update_field` refuses the same thing with «node '…' is not here»,
    and that refusal **is** the difference between correcting a record and
    inventing one.

    So this tool is not a convenience over `create_su`. It is the only verb that
    can say «this unit already exists and I am changing it», and a scheda — which
    is opened on a unit far more often than it creates one — needs exactly that.

    ## WHAT IT DOES NOT DO

    * **it does not create.** No `add_node` for the unit, ever. If the unit is
      not there the act is refused and the person is told to create it first;
    * **it does not rename.** `name` is addressable by the CRDT and is
      deliberately refused here: «US 12» is derived from the number, and renaming
      a unit is a different act with different consequences (every mention of it
      elsewhere). Refused by name, so nobody has to wonder;
    * **it does not decide what a field means.** The names arrive from the
      scheda's definition (`app/scheda.py`), which read them from the standard.
      This tool addresses them and nothing more.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        from .operazioni import OperazioniError

        number = str(slots.get("us") or "").strip()
        if not number:
            return ToolResult(ok=False, message="Mi manca il numero dell'unità.")

        fields = slots.get("fields")
        if not isinstance(fields, dict) or not fields:
            return ToolResult(
                ok=False,
                message=f"Non mi hai detto che cosa cambiare sulla US {number}.")

        refused = sorted(k for k in fields if str(k).strip() in _NOT_UPDATABLE)
        if refused:
            return ToolResult(
                ok=False,
                message=(f"Non cambio {', '.join(refused)} da qui: rinominare "
                         f"un'unità è un altro atto, perché tocca ogni posto "
                         f"che la nomina."))

        # ── QUALE RICETTA ────────────────────────────────────────────────────
        #
        # Fino al 19 ottobre qui i nomi dei campi diventavano `data.<nome>` e
        # basta. Adesso i nomi sono le caselle di UNA definizione, e la sua
        # ricetta dice che cosa ciascuna è nel grafo: la scheda aperta nel
        # modulo, oppure quella che l'unità dichiara, oppure quella di
        # riferimento del nodo (la voce).
        scheda, why = scheda_for(graph_writer, number,
                                 scheda_id=str(slots.get("scheda") or ""),
                                 version=str(slots.get("version") or ""))
        if scheda is None:
            return ToolResult(
                ok=False,
                message=("Questo nodo non serve la scheda con cui compilare "
                         f"la US {number}" + (f" («{slots.get('scheda')}» "
                                              f"{slots.get('version') or ''})"
                                              if slots.get("scheda") else "")
                         + ": senza una ricetta non so che cosa siano le "
                           "caselle nel grafo."),
                data={"us": number, "reason": "no-scheda"})

        # ── CHI HA COMPOSTO OGNI VALORE, accanto al valore ──────────────────
        #
        # Scritta nella STESSA lista di operazioni dei campi, non in un secondo
        # giro: un valore e la sua autorialità che atterrano separatamente sono
        # due scritture di cui una può fallire, e un campo AI senza il suo
        # marcatore ha l'aria di un campo qualunque — che è precisamente ciò
        # che non deve avere. È un `update_field data.authorship.<campo>` sul
        # nodo dell'unità: l'orologio per campo del CRDT, che c'era già.
        #
        # Il default è `human`: chi non dice niente ha scritto lui. Marcare AI
        # per difetto attribuirebbe a una macchina il lavoro di chi scava.
        try:
            made, process, outcomes, landed, already, held = _through_the_recipe(
                graph_writer, scheda, dict(fields), number=number,
                create=bool(slots.get("create")), author=author,
                kind="update_su",
                detail=f"US {number}: {len(fields)} campi · {scheda.id} "
                       f"{scheda.version}",
                authored_by=slots.get("authored_by"), model=slots.get("model"),
                lang=slots.get("lang"))
        except OperazioniError as wrong:
            return ToolResult(ok=False, message=str(wrong),
                              data={"us": number, "node_id": unit_id_for(number)})
        except Exception as exc:                                 # noqa: BLE001
            # `RoomRefused` («non puoi scrivere») arriva qui, e porta già una
            # frase per una persona: la si passa invece di sostituirla.
            return ToolResult(ok=False, message=str(exc),
                              data={"us": number, "node_id": unit_id_for(number)})

        data = _plan_data(made, outcomes, landed, already, held)
        data["scheda"] = {**scheda.ref, "why": why}
        return ToolResult(
            ok=True,
            message=_what_happened(made, landed, already, held, number),
            # The delta carries the ACT; the operations went on the wire.
            delta=GraphDelta(process=process, author=author),
            data=data)

    return ToolDescriptor(
        name="update_su",
        # LE FRASI SONO ANCHE QUELLE DEI CAMPI, prese dal vocabolario: la lista
        # È la mappa, per la stessa ragione per cui lo è in `relate_su` — due
        # elenchi scritti a mano divergono, e l'ho già pagato una volta con le
        # forme al femminile che la mappa conosceva e gli intenti no.
        intents=(["aggiorna la scheda", "correggi la us", "modifica la us",
                  "aggiorna la us", "correggi la scheda"]
                 + [phrase for phrases in SPOKEN_FIELDS.values()
                    for phrase in phrases]),
        input_schema=[
            Slot("us", "string", True, "il numero dell'unità da aggiornare"),
            Slot("fields", "id", True,
                 "i campi da cambiare, per nome — quelli della definizione "
                 "della scheda; un valore nullo svuota la casella"),
            Slot("authored_by", "id", False,
                 "chi ha COMPOSTO ciascun valore: `human` o `ai`. Assente "
                 "vuol dire human, perché chi non dice niente ha scritto lui"),
            Slot("model", "string", False,
                 "quale modello, per i campi marcati `ai` — è ciò che resta "
                 "leggibile dopo che una persona li ha validati"),
            Slot("scheda", "string", False,
                 "con quale definizione: assente vuol dire quella che l'unità "
                 "dichiara, o quella di riferimento del nodo"),
            Slot("version", "string", False, "quale versione di quella definizione"),
            Slot("create", "boolean", False,
                 "vero la prima volta, DETTO da chi chiama: «creala se manca» "
                 "è il modo in cui un numero sbagliato diventa un'unità nuova"),
        ],
        description="Compila i campi di un'unità attraverso la ricetta della "
                    "sua scheda.",
        service="s3dgraphy", handler=handler)


#: LE PAROLE CHE MANCAVANO — un campo detto a voce, e il campo che ne esce.
#:
#: ── LA SCOPERTA, e quanto era larga ────────────────────────────────────────
#:
#: Il 21 settembre si è visto che nessuno dei sette intenti permetteva di dire un
#: rapporto stratigrafico, ed è nato `relate_su`. **La scoperta era più larga**:
#: non c'era un modo di dire nemmeno `definizione` — che è **obbligatoria** — né
#: le quote, né le misure.
#:
#: Conseguenza misurata sulla US ICCD: i campi da trincea erano **8 su 59**. Una
#: scheda da trincea con otto caselle non è una scheda semplificata, è una scheda
#: quasi vuota. **Il collo di bottiglia non è il formato, sono le parole.**
#:
#: ── PERCHÉ NON UN TOOL NUOVO ───────────────────────────────────────────────
#:
#: `update_su` scrive già qualunque campo. Quello che mancava non era un verbo:
#: era il VOCABOLARIO che porta una frase a un campo. Un nono tool avrebbe
#: aggiunto una seconda via di scrittura per fare la stessa cosa.
#:
#: ── E IN CHE LINGUA ────────────────────────────────────────────────────────
#:
#: In quella che il nodo dichiara (`intent.COMMAND_LANGUAGE`, oggi `it`). Che
#: alcuni di questi nomi coincidano con gli id di campo della US ICCD non è
#: perché questo servizio abbia imparato l'ICCD: è perché sono le parole
#: italiane per le stesse cose. Un nodo che serve schede spagnole vorrà il suo
#: frasario, ed è una cosa del NODO — il che è già scritto in `intent.py`.
#: Ogni voce è una lista di FRASI, e il valore è ciò che le segue. Le frasi si
#: provano dalla più lunga, così «la definizione è» batte «definizione» e il
#: valore non comincia con « è ».
#:
#: L'attacco `(?:d\w+\s+(?:la\s+)?)?(?:us\s*\d+\s*)?` in mezzo è ciò che
#: regge «il colore DELLA US 12 è bruno»: fra il nome del campo e il valore una
#: persona infila il riferimento all'unità, e senza quel pezzo il valore
#: diventava «della us 12 è bruno».
SPOKEN_FIELDS: Dict[str, Tuple[str, ...]] = {
    "definizione":  ("la definizione è", "definizione", "è un", "è uno",
                     "è una"),
    "quote":        ("la quota è", "quota", "quote"),
    "misure":       ("le misure sono", "la misura è", "misure", "misura"),
    "colore":       ("il colore è", "colore"),
    "consistenza":  ("la consistenza è", "consistenza"),
}


# ── 1ter · relate_su — L'INTENTO CHE MANCAVA ────────────────────────────────
#
# Trovato marcando la scheda ICCD in `stratigraph-templates` il 22 settembre:
# **nessuno dei sette intenti permetteva di registrare un rapporto
# stratigrafico a voce.** Non era una dimenticanza — `create_su` mette
# `rapporti` di pyArchInit sotto `extra`, fra le cose «merely carried», e per
# un ingest ha ragione. Ma una persona in trincea dice «la 12 copre la 18»
# tutto il giorno, e non aveva un modo di dirlo a questo servizio.
#
# Per questo le dieci caselle dei rapporti della US ICCD sono rimaste
# `unknown` in quella definizione: marcarle `trench` senza un intento che le
# copra sarebbe stato inventare il criterio. Quando questo tool esiste, il
# marcatore si mette **là**, nella definizione, non qui.

#: I verbi che una persona dice, e l'arco che ne esce — DERIVATI DALLA RICETTA
#: della scheda di riferimento del nodo, dal 19 ottobre (audit B2).
#:
#: ── PERCHÉ NON PIÙ UN DIZIONARIO A SÉ ──────────────────────────────────────
#:
#: Fino a stanotte qui c'era una mappa scritta a mano, allineata a
#: `pyarchinit-mini/…/us_ops.py`, che diceva `copre → is_after`. La scheda ICCD
#: compilata dice `copre → overlies`, e l'audit ha misurato che la stessa frase
#: detta a voce e scritta sulla scheda produceva DUE archi diversi. E.D.:
#: **COPRE è `overlies`, POSTERIORE A è `is_after`, e non si mescolano** — le
#: relazioni fisiche giustificano quelle cronologiche, ma sono due cose.
#:
#: Quindi la frase è l'ETICHETTA della casella nella lingua dei comandi
#: («copre», «coperto da», «posteriore a»…, più il femminile dei participi),
#: e `(edge_type, direzione)` è il passo della ricetta: `$unit → $item` è
#: `forward`, `$item → $unit` è `swap`, un arco simmetrico è `symmetric`.
#:
#: ── PIÙ LE RELAZIONI DEL DATAMODEL (21 ottobre, decisione di E.D.) ────────
#:
#: Il 19 si era perso «contemporaneo a» (`has_same_time`): non è una casella
#: della US ICCD, e una frase senza casella non aveva una ricetta. Adesso la
#: voce accetta ANCHE le relazioni che s3Dgraphy dichiara fra unità
#: stratigrafiche, LETTE dal datamodel delle connessioni
#: (`operazioni.datamodel_relations`), con nomi e grafie canonici attraverso
#: `normalize_edge_name` / `spellings`. La ricetta vince sulla stessa frase: se
#: una scheda ha la casella, il rapporto passa per la casella.
#:
#: Che cosa si dice a voce resta del frasario del nodo (`RELATION_WORDS`): il
#: datamodel nomina le relazioni in inglese e per le macchine ("Has same time"),
#: non nella lingua dei comandi. Il frasario NON è un elenco di relazioni —
#: una parola legata a un nome che il datamodel non dichiara fra unità
#: stratigrafiche non entra, e `RELATIONS_REFUSED` lo dice.

#: Le parole della lingua dei comandi per le relazioni del datamodel che
#: NESSUNA casella della scheda di riferimento copre. Chiave: la frase (il
#: femminile dei participi si aggiunge da sé); valore: un nome che il datamodel
#: accetta (canonico, inverso o grafia vecchia — passa per `normalize_edge_name`).
RELATION_WORDS: Dict[str, str] = {
    "contemporaneo a": "has_same_time",
}


def _relations() -> Dict[str, Tuple[str, str]]:
    from .intent import COMMAND_LANGUAGE
    from .operazioni import (datamodel_relation_phrases, datamodel_relations,
                             relation_phrases, unsayable_words)

    scheda = reference_scheda()
    if scheda is None:
        # nessuna scheda di riferimento: nessuna via per scrivere (il
        # generatore timbra l'unità con la sua scheda), quindi nessuna frase
        return {}
    phrases = relation_phrases(scheda, COMMAND_LANGUAGE)
    for phrase, mapping in datamodel_relation_phrases(RELATION_WORDS).items():
        phrases.setdefault(phrase, mapping)
    RELATION_FIELDS.clear()
    RELATION_FIELDS.update({k: v[2] for k, v in phrases.items()})
    RELATIONS_REFUSED.clear()
    RELATIONS_REFUSED.update(unsayable_words(RELATION_WORDS))
    said = {v[0] for v in phrases.values()}
    RELATIONS_UNSAID[:] = sorted(set(datamodel_relations()) - said)
    return {k: (v[0], v[1]) for k, v in phrases.items()}


#: frase → la casella della scheda che quella frase compila ("" = nessuna:
#: una relazione del datamodel, scritta senza casella)
RELATION_FIELDS: Dict[str, str] = {}
#: parola del frasario → perché non entra (il datamodel non la dichiara così)
RELATIONS_REFUSED: Dict[str, str] = {}
#: le relazioni stratigrafiche del datamodel che nessuna frase dice ancora
RELATIONS_UNSAID: List[str] = []
RELATIONS: Dict[str, Tuple[str, str]] = _relations()


def _physical(edge_type: str) -> Optional[bool]:
    from .operazioni import datamodel_relations
    return (datamodel_relations().get(edge_type) or {}).get("physical")


def edge_id_for(source: str, edge_type: str, target: str) -> str:
    """`source__type__target` — la convenzione, non un'invenzione.

    `EMStudio/frontend/src/crdt.ts:622` compone esattamente questo quando un
    arco arriva senza id, e `us_ops.edge_id` fa lo stesso. Usare la stessa
    convenzione vuol dire che un arco detto a voce e lo stesso arco disegnato a
    mano nell'editor **sono un arco**, e il secondo si fonde invece di
    raddoppiare la freccia.
    """
    return f"{source}__{edge_type}__{target}"


def make_relate_su(graph_writer) -> ToolDescriptor:
    """«La 12 copre la 18» — un rapporto stratigrafico, a voce.

    Le due unità devono ESISTERE. Un arco fra due id che nessuno può risolvere
    è peggio di un arco che manca: la matrice lo disegna, e la freccia punta
    nel vuoto. Quindi si controlla, e se una delle due non c'è si dice quale.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        from .operazioni import OperazioniError

        left = str(slots.get("us") or "").strip()
        right = str(slots.get("other") or "").strip()
        said = str(slots.get("relation") or "").strip().lower()

        if not left or not right:
            return ToolResult(
                ok=False,
                message="Mi servono due unità: «la 12 copre la 18».")
        if left == right:
            return ToolResult(
                ok=False,
                message=f"La US {left} non può essere in rapporto con se stessa.")

        mapping = RELATIONS.get(said)
        if mapping is None:
            return ToolResult(
                ok=False,
                message=(f"Non conosco il rapporto «{said}». So: "
                         + ", ".join(sorted(RELATIONS)) + "."))
        edge_type, direction = mapping
        box = RELATION_FIELDS[said]

        # UNA RELAZIONE DEL DATAMODEL SENZA CASELLA («contemporaneo a»): la
        # stessa via del generatore, con un rapporto dichiarato invece che
        # una casella — stub, simmetrici ordinati, id e `noop` sono quelli.
        if not box:
            scheda = reference_scheda()
            try:
                made, process, outcomes, landed, already, held = _through_the_recipe(
                    graph_writer, scheda, {}, number=left, create=False,
                    author=author, kind="relate_su",
                    detail=f"US {left} {said} US {right}, detto sul campo",
                    relations=[(edge_type, direction, right)],
                    lang=slots.get("lang"))
            except OperazioniError as wrong:
                return ToolResult(ok=False, message=str(wrong),
                                  data={"missing": [left]})
            if made.refused:
                return ToolResult(ok=False, message="; ".join(made.refused.values()))
            box = ""
        else:
            made = None

        # LA STESSA VIA DELLA SCHEDA: «la 12 copre la 18» è la casella COPRE
        # della US 12 con dentro la 18 — e il generatore ne fa l'arco che la
        # ricetta dichiara. `additive`: una frase aggiunge UN rapporto, non
        # riscrive la casella togliendo gli altri.
        #
        # L'unità che FA l'azione deve esistere (`create=False`: è un
        # aggiornamento, e un numero sbagliato non diventa una US nuova).
        # L'ALTRA, se non c'è, si segna minima — la stessa decisione della
        # scheda (`operazioni.py`, decisione 1): un rapporto detto è
        # un'osservazione che quella unità esiste.
        if made is None:
            scheda = reference_scheda()
            try:
                made, process, outcomes, landed, already, held = _through_the_recipe(
                    graph_writer, scheda, {box: [right]}, number=left, create=False,
                    author=author, kind="relate_su",
                    detail=f"US {left} {said} US {right}, detto sul campo",
                    additive=True, lang=slots.get("lang"))
            except OperazioniError as wrong:
                return ToolResult(ok=False, message=str(wrong),
                                  data={"missing": [left]})
        edge = next((o for o in made.ops if o["op"] == "add_edge"), None)
        message = f"Registrato: US {left} {said} US {right}."
        if made.stubs:
            message += (f" La US {right} non c'era ancora: l'ho segnata da "
                        f"compilare.")
        return ToolResult(
            ok=True,
            message=message,
            delta=GraphDelta(edges=[{k: edge[k] for k in ("id", "source",
                                                         "target", "edge_type")}]
                             if edge else [], process=process, author=author),
            data={"edge_id": edge["id"] if edge else None,
                  "edge_type": edge_type,
                  "source": edge["source"] if edge else None,
                  "target": edge["target"] if edge else None,
                  # Cosa è stato DETTO, oltre a cosa è stato scritto: chi
                  # rilegge deve poter vedere che «coperta da» è diventata un
                  # `overlies` a capi scambiati e non un tipo inverso.
                  "said": said, "direction": direction, "field": box or None,
                  # fisica (AP11) o no: la distinzione che il datamodel fa
                  "physical": _physical(edge_type),
                  "stubs": list(made.stubs)})

    return ToolDescriptor(
        name="relate_su",
        # LE FRASI SONO LE CHIAVI DELLA MAPPA, non una seconda lista.
        #
        # Scritte a mano erano subito divergenti: la mappa conosceva «coperta
        # da», «riempita da» e «contemporanea a» — le forme al femminile, che
        # sono quelle che si dicono di una US — e la lista degli intenti no,
        # quindi «la 12 è coperta dalla 18» non veniva riconosciuta affatto.
        # Trovato provando le frasi vere, non leggendo il codice.
        intents=sorted(RELATIONS) + ["rapporto fra", "metti in rapporto"],
        input_schema=[
            Slot("us", "string", True, "la prima unità — quella che fa l'azione"),
            Slot("other", "string", True, "la seconda unità"),
            Slot("relation", "string", True,
                 "il rapporto, nelle parole dette: copre, tagliato da, "
                 "uguale a…"),
        ],
        description="Registra un rapporto stratigrafico fra due unità.",
        service="s3dgraphy", handler=handler)


# ── 1quater · validate_field — la conferma umana ────────────────────────────

def make_validate_field(graph_writer) -> ToolDescriptor:
    """Una persona guarda un campo che il modello ha composto, e se lo assume.

    **LA VALIDAZIONE TRASFERISCE L'AUTORIALITÀ**: da quel momento il campo è di
    chi l'ha confermato, e il grafo lo dice. Resta scritto che il valore
    l'aveva proposto una macchina (`composed_by`), perché cancellarlo
    trasformerebbe una validazione in una riscrittura della storia.

    Non tocca il VALORE. Correggere un campo è `update_su`, e sono due atti
    diversi: «ho letto e va bene» non è «ho cambiato». Un tool che facesse
    entrambe le cose renderebbe impossibile distinguerli nel record.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        number = str(slots.get("us") or "").strip()
        wanted = slots.get("fields")
        if isinstance(wanted, str):
            wanted = [wanted]
        if not number or not wanted:
            return ToolResult(
                ok=False,
                message="Mi servono l'unità e quali campi hai controllato.")

        unit_id = unit_id_for(number)
        if not graph_writer.has_node(unit_id):
            return ToolResult(
                ok=False,
                message=f"Non trovo la US {number} in questo grafo.")

        # Lo STATO DI PRIMA, letto dal grafo: la validazione conserva come il
        # valore era arrivato, e per conservarlo bisogna averlo letto.
        before = graph_writer.node(unit_id) or {}
        at = _now()
        marks: Dict[str, Any] = {}
        skipped: List[str] = []
        for field in wanted:
            said = authorship.read(before, field)
            if said["by"] != authorship.AI or said["validated"]:
                # Un campo che nessun modello ha composto non ha bisogno di
                # essere validato, e dirgli di sì sarebbe mettere una spunta
                # accanto a un'affermazione che nessuno ha messo in dubbio.
                skipped.append(field)
                continue
            marks[authorship.field_key(field)] = authorship.validated(
                said, by=author or "", at=at)

        if not marks:
            return ToolResult(
                ok=True,
                message=(f"Su US {number} non c'è niente da validare: "
                         f"{', '.join(skipped)} "
                         f"{'non è' if len(skipped) == 1 else 'non sono'} "
                         f"stat{'o' if len(skipped) == 1 else 'i'} "
                         f"compost{'o' if len(skipped) == 1 else 'i'} da un "
                         f"modello."),
                data={"us": number, "validated": [], "skipped": skipped})

        validated_names = [f for f in wanted if authorship.field_key(f) in marks]
        process = _process_node(
            "validate_field", author, unit_id,
            f"US {number}: {len(marks)} campi validati da una persona")
        try:
            graph_writer.update(unit_id, marks, author=author, process=process)
        except Exception as exc:                                 # noqa: BLE001
            return ToolResult(ok=False, message=str(exc))

        return ToolResult(
            ok=True,
            message=f"US {number}: {len(marks)} campi validati.",
            delta=GraphDelta(process=process, author=author),
            data={"us": number, "validated": validated_names,
                  "skipped": skipped})

    return ToolDescriptor(
        name="validate_field",
        intents=["valida", "confermo", "va bene così", "ho controllato",
                 "valida il campo", "confermo la scheda"],
        input_schema=[
            Slot("us", "string", True, "il numero dell'unità"),
            Slot("fields", "id", True, "i campi controllati"),
        ],
        description="Conferma i campi che un modello ha composto: "
                    "l'autorialità passa alla persona.",
        service="s3dgraphy", handler=handler)


# ── 2 · which_project ────────────────────────────────────────────────────────

def make_which_project(graph_writer) -> ToolDescriptor:
    """The question that orients somebody who has been digging for six hours."""

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        study = graph_writer.study_name()
        if not study:
            return ToolResult(
                ok=True,
                message="Non sto lavorando su nessuno studio: questo nodo non "
                        "ha ancora un progetto aperto.",
                data={"study": None})
        units = graph_writer.count_units()
        return ToolResult(
            ok=True,
            message=f"Stai lavorando su «{study}», "
                    f"{units} unità registrate finora.",
            data={"study": study, "units": units})

    return ToolDescriptor(
        name="which_project",
        intents=["in che progetto sto lavorando", "che progetto è questo",
                 "dove sono", "quale progetto"],
        description="Legge lo studio attivo e risponde a voce.",
        service="s3dgraphy", writes=False, handler=handler)


# ── 3 · attach_photo_to_su ───────────────────────────────────────────────────

def make_attach_photo(graph_writer, asset_store) -> ToolDescriptor:
    """A photo becomes a resource of a unit.

    Two acts, in this order and not the other: the bytes go to the store FIRST,
    then the graph points at them. If the node dies in between, there is an
    orphan object in a bucket — recoverable. The other order would put a
    reference in a shared graph to bytes that do not exist, which every client
    would then fail to load.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        number = str(slots.get("us") or "").strip()
        photo = slots.get("photo")
        if not isinstance(photo, (bytes, bytearray)) or not photo:
            return ToolResult(ok=False,
                              message="Non ho ricevuto nessuna foto.")

        # IL DIGEST CHE IL CLIENT DICHIARA, verificato PRIMA di scrivere.
        #
        # Misurato: un base64 troncato a un multiplo di 4 si decodifica pulito
        # e produce mezza foto — 200 007 byte su 400 014, senza il `FFD9` che
        # chiude un JPEG — con un `ref` perfettamente valido. Una probabilità
        # su quattro, e dopo non se ne accorge più nessuno, perché il
        # content-addressing rende quel mezzo file coerente con il proprio nome.
        #
        # Chi non dichiara niente passa come prima: rifiutare chi tace
        # romperebbe in una notte ogni client che oggi manda foto. È un
        # controllo che si può fare, non un cancello che si può chiudere —
        # e la differenza è dichiarata qui e in `/health`.
        try:
            spool_verify(bytes(photo), str(slots.get("sha256") or ""))
        except ValueError as storto:
            return ToolResult(ok=False, message=str(storto),
                              data={"us": number, "reason": "digest-mismatch"})
        unit_id = f"US{number}"
        if not graph_writer.has_node(unit_id):
            # Not an error, and not a silent creation either: saying it is what
            # lets somebody fix the number they just spoke.
            return ToolResult(
                ok=False,
                message=f"Non trovo la US {number}. Creala prima, "
                        f"o dimmi un altro numero.",
                data={"us": number, "reason": "unknown-unit"})

        stored = asset_store.put(bytes(photo),
                                 str(slots.get("media_type") or "image/jpeg"))
        digest = stored["sha256"]
        resource_id = f"{unit_id}.photo.{digest[:12]}"

        resource = {
            "id": resource_id, "node_type": "resource",
            "name": str(slots.get("filename") or f"foto US {number}"),
            "data": {"url": stored.get("url") or stored["ref"],
                     "checksum": stored["ref"], "residency": "reference",
                     "media_type": stored.get("media_type"),
                     "created_by": author, "created_at": _now()},
        }

        # ── quello che la foto porta con sé, TRASPORTATO e non capito ───────
        #
        # Stessa regola dei `rapporti` di pyArchInit qui sopra: sotto una chiave
        # sola, così chi legge distingue sempre quello che questo servizio ha
        # CAPITO da quello che ha soltanto portato. Nessuno di questi campi
        # diventa un campo del grafo, e la proposta su quali dovrebbero
        # diventarlo sta nel referto del 30 settembre — misurata su ventuno
        # foto vere, di cui **zero** avevano una posizione.
        #
        # `created_at` qui sopra è QUANDO LA RIGA È STATA SCRITTA. Non è la
        # stessa cosa di `DateTimeOriginal`, e sulla foto misurata stanotte
        # fra i due ci sono cinque anni.
        portati = exif.read(bytes(photo))
        if portati:
            resource["data"]["source_fields"] = {"exif": portati}
        edge = {"id": f"{unit_id}__has_linked_resource__{resource_id}",
                "source": unit_id, "target": resource_id,
                "edge_type": "has_linked_resource"}
        process = _process_node("attach_photo_to_su", author,
                                f"{unit_id}:{digest[:12]}",
                                f"foto legata alla US {number}")
        delta = GraphDelta(nodes=[resource], edges=[edge], process=process,
                           author=author)
        graph_writer.apply(delta)
        return ToolResult(
            ok=True,
            message=f"Foto allegata alla US {number}.",
            delta=delta,
            data={"us": number, "resource_id": resource_id,
                  "sha256": stored["ref"], "created": stored.get("created")})

    return ToolDescriptor(
        name="attach_photo_to_su",
        intents=["questa foto è per la us", "questa foto va sulla us",
                 "allega la foto alla us", "foto per la us"],
        input_schema=[Slot("us", "string", True, "il numero dell'unità"),
                      Slot("photo", "bytes", True, "i byte dell'immagine"),
                      Slot("filename", "string", False, "il nome del file"),
                      Slot("media_type", "string", False, "il tipo MIME"),
                      Slot("sha256", "string", False,
                           "il digest che il client si aspetta, verificato "
                           "prima di scrivere")],
        description="La foto va nell'object store e diventa una risorsa "
                    "dell'unità.",
        service="s3dgraphy", handler=handler)


# ── 4 · ingest_photos ────────────────────────────────────────────────────────

def make_ingest_photos(graph_writer, asset_store) -> ToolDescriptor:
    """Several photos at once, queued to a unit.

    The same act as `attach_photo_to_su`, repeated — and it reuses that tool's
    handler rather than growing a second write path, because two implementations
    of "a photo belongs to a unit" would eventually disagree about what one is.
    """
    single = make_attach_photo(graph_writer, asset_store)

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        photos = slots.get("photos") or []
        if not isinstance(photos, list) or not photos:
            return ToolResult(ok=False, message="Non ho ricevuto nessuna foto.")
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        stored = 0
        for index, photo in enumerate(photos):
            one = single.handler({**slots, "photo": photo,
                                  "filename": f"foto {index + 1} "
                                              f"US {slots.get('us')}"}, author)
            if not one.ok:
                return one            # the first refusal is the answer
            nodes.extend(one.delta.nodes)
            edges.extend(one.delta.edges)
            stored += 1
        number = str(slots.get("us") or "").strip()
        process = _process_node("ingest_photos", author,
                                f"US{number}:{stored}",
                                f"{stored} foto in coda alla US {number}")
        return ToolResult(
            ok=True,
            message=f"Ho messo {stored} foto sulla US {number}.",
            delta=GraphDelta(nodes=nodes, edges=edges, process=process,
                             author=author),
            data={"us": number, "stored": stored})

    return ToolDescriptor(
        name="ingest_photos",
        intents=["ti passo delle foto", "prendo delle foto",
                 "queste foto sono per la us"],
        input_schema=[Slot("us", "string", True, "il numero dell'unità"),
                      Slot("photos", "bytes", True, "le immagini")],
        description="Più foto nello store, in coda a un'unità.",
        service="s3dgraphy", handler=handler)


# ── 5 · query_kg ─────────────────────────────────────────────────────────────

def make_query_kg(graph_writer) -> ToolDescriptor:
    """A question, answered from the graph, out loud.

    Deliberately small: it answers what the graph plainly says (how many units,
    what is in an epoch or an activity, what a unit is). A retrieval model over
    the documentation is ARC's Document Analysis, and it plugs in as its OWN
    tool — which is exactly what the contract is for.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        question = str(slots.get("question") or "").strip()
        answer = graph_writer.answer(question)
        return ToolResult(ok=True, message=answer,
                          data={"question": question})

    return ToolDescriptor(
        name="query_kg",
        intents=["cosa abbiamo registrato", "quante unità",
                 "cosa c'è", "dimmi"],
        input_schema=[Slot("question", "string", False, "la domanda")],
        description="Una risposta parlata, letta dal grafo.",
        service="s3dgraphy", writes=False, handler=handler)


# ── 6 · build_model ──────────────────────────────────────────────────────────

def make_build_model(graph_writer, asset_store) -> ToolDescriptor:
    """"costruisci il modello 3D di questa US dalle foto" — said out loud.

    The voice does not reconstruct anything. It ASKS the node, which is the
    whole point of the three layers: the meaning of the act is s3Dgraphy's, the
    engine and the store are StratiGraph Server's, and what lives here is one
    sentence turned into one request and one answer read back to somebody whose
    hands are in the soil.

    **It refuses off a room, and says why.** Reconstruction needs the engine and
    the object store, both of which are the NODE's. A field assistant writing to
    its own local container has photographs and no engine — telling somebody
    "I'll build it" and silently doing nothing is the worst of the three
    possible answers.

    **It does not wait.** The engine takes minutes; a person standing over a
    trench does not hold a phone to their ear for them. The tool reports the job
    id, which is what the endpoint's 202 means. Asking «a che punto è il
    modello» OUT LOUD is a tool of its own and is not built here — the poll is
    `GET /v1/photogrammetry/{job_id}` for now, and saying otherwise would be
    promising a sentence that does nothing.

    `asset_store` is taken and not used, deliberately: every tool in this
    registry has the same signature, and the photographs are ALREADY in the
    node's store (that is what `ingest_photos` did). Staging them again from
    here would upload the same bytes twice.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        number = str(slots.get("us") or "").strip()
        cluster = str(slots.get("cluster") or "").strip()
        if not number and not cluster:
            return ToolResult(ok=False,
                              message="Di quale US devo costruire il modello?")
        unit_id = f"US{number}" if number else ""
        target = cluster or unit_id

        room = getattr(graph_writer, "room_id", None)
        caller = getattr(graph_writer, "call", None)
        if not room or caller is None:
            return ToolResult(
                ok=False,
                message="Da qui non posso: il modello lo costruisce il nodo, e "
                        "questo assistente sta scrivendo sul contenitore locale. "
                        "Collegati a una stanza e riprova.",
                data={"reason": "no-room", "target": target})

        mode = str(slots.get("mode") or "local").strip().lower()
        payload: Dict[str, Any] = {"room_id": room, "cluster": target,
                                   "mode": mode}
        if unit_id:
            payload["subject"] = unit_id
        gcps = slots.get("gcps")
        if gcps:
            # a control set arrives as data (from a survey, an import), never
            # dictated: pixels and coordinates are not things anybody says
            payload["gcps"] = gcps
            payload["mode"] = "absolute"

        answer = caller("/v1/photogrammetry", payload)
        if answer is None:
            return ToolResult(
                ok=False,
                message="Non riesco a raggiungere il nodo. Le foto sono al "
                        "sicuro: riprova quando torna la rete.",
                data={"reason": "unreachable", "target": target})
        if answer.get("detail"):
            # the endpoint's own refusal, read out in its own words rather than
            # replaced by a friendlier one that says less
            return ToolResult(ok=False,
                              message=f"Il nodo ha rifiutato: {answer['detail']}",
                              data={"reason": "refused", "target": target,
                                    "detail": answer["detail"]})

        job_id = str(answer.get("job_id") or "")
        count = int(answer.get("image_count") or 0)
        where = ("georeferenziato" if payload["mode"] == "absolute"
                 else "in coordinate locali")
        # NOT promising a phrase that does nothing: asking «a che punto è il
        # modello» out loud needs a tool of its own, and it is not this one. The
        # job id is reported instead, which is what the node's own poll takes.
        return ToolResult(
            ok=True,
            message=(f"Ho avviato la ricostruzione di {target} da {count} foto, "
                     f"{where}. Ci vogliono alcuni minuti; il lavoro è "
                     f"{job_id[:8]}."),
            data={"job_id": job_id, "target": target, "room": room,
                  "mode": payload["mode"], "image_count": count,
                  "status": answer.get("status")})

    return ToolDescriptor(
        name="build_model",
        intents=["costruisci il modello 3d", "costruisci il modello",
                 "fai il modello 3d", "ricostruisci la us",
                 "modello 3d di questa us", "modello dalle foto"],
        input_schema=[Slot("us", "string", False, "il numero dell'unità"),
                      Slot("cluster", "string", False,
                           "l'acquisizione o la risorsa da cui partire"),
                      Slot("mode", "string", False,
                           "local (scala) o absolute (georeferenziato con GCP)"),
                      Slot("gcps", "object", False,
                           "i punti di controllo, se ci sono")],
        description="Le foto già caricate diventano un modello 3D sul nodo, "
                    "con la sua provenienza nel grafo.",
        service="rest", handler=handler)


# ── 7 · open_in_emstudio ─────────────────────────────────────────────────────

def make_open_in_emstudio(graph_writer, asset_store) -> ToolDescriptor:
    """"apri questa stanza in EMStudio" — the round-trip, from the trench.

    Not a transfer and not an export: the graph lives in the ROOM, so opening it
    elsewhere is another client joining the same room. Somebody standing over a
    unit says this, and the person at the laptop finds the study already there.

    **The link names a place and never a permission.** It comes from the node's
    own handoff contract (`GET /v1/rooms/{id}/open`), asked for the room this
    assistant is connected to, and EMStudio signs itself in when it opens.

    Reads nothing and writes nothing — `writes=False`, so the core's no-author
    refusal does not fire: asking where a room can be opened is not an act on
    the record.
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        room = getattr(graph_writer, "room_id", None)
        reader = getattr(graph_writer, "read", None)
        if not room or reader is None:
            return ToolResult(
                ok=False,
                message="Non sono in una stanza: non c'è niente da aprire "
                        "altrove. Questo nodo sta scrivendo sul contenitore "
                        "locale.",
                data={"reason": "no-room"})

        answer = reader(f"/v1/rooms/{room}/open")
        if answer is None:
            return ToolResult(
                ok=False,
                message="Non riesco a raggiungere il nodo per chiedere come si "
                        "apre la stanza. Riprova quando torna la rete.",
                data={"reason": "unreachable", "room": room})
        if answer.get("detail"):
            return ToolResult(ok=False,
                              message=f"Il nodo ha rifiutato: {answer['detail']}",
                              data={"reason": "refused", "room": room})

        card = (answer.get("tools") or {}).get("emstudio") or {}
        # The browser door when the deployment hosts a web build, the desktop
        # scheme otherwise — the same two doors the room browser offers, and the
        # same rule: no door at all beats a door that fails after the click.
        browser = card.get("browser")
        scheme = card.get("scheme") or answer.get("scheme")
        link = browser or scheme
        if not link:
            return ToolResult(
                ok=False,
                message="Questo nodo non sa dire come aprire EMStudio.",
                data={"reason": "no-door", "room": room})

        where = "nel browser" if browser else "in EMStudio"
        return ToolResult(
            ok=True,
            message=f"Ecco il link per aprire la stanza {room} {where}. "
                    f"Non contiene nessun token: EMStudio ti fa entrare da sé.",
            data={"room": room, "link": link,
                  "kind": "browser" if browser else "scheme",
                  "web": answer.get("web"),
                  "carries_token": bool(answer.get("carries_token"))})

    return ToolDescriptor(
        name="open_in_emstudio",
        intents=["apri questa stanza in emstudio", "apri in emstudio",
                 "apri lo studio sul computer", "passa a emstudio"],
        input_schema=[],
        description="Il link per aprire la STESSA stanza in EMStudio — il grafo "
                    "è della stanza, quindi non si trasferisce niente.",
        service="rest", writes=False, handler=handler)


# ── 1quinquies · translate_text — «Traduci», accanto e mai sopra ────────────

def make_translate_text(graph_writer, translator=None) -> ToolDescriptor:
    """Il modello del nodo traduce un testo; nasce una TRADUZIONE, non un valore.

    Un `TranslationNode` con `method: ai` e `ai_assisted` (s3Dgraphy
    `api.add_translation`, via `app/traduzione.py`), raggiunto dall'originale
    con `has_translation` e firmato da chi l'ha chiesta. **L'originale non si
    tocca**: nessuna operazione della lista lo nomina. E la traduzione aspetta
    una persona (`api.to_review`, ragione `ai`) finché qualcuno non la firma —
    oggi in EMStudio (`api.verify`): `validate_field` qui accanto valida le
    CASELLE composte da un modello (`data.authorship.<casella>`), che è
    un'altra cosa, e non si allarga a un nodo per somiglianza.

    Senza un modello sul nodo il tool c'è e lo dice: «If the node has an AI you
    have functions; if it does not, you do not — and the surface says so.»
    """

    def handler(slots: Dict[str, Any], author: Optional[str]) -> ToolResult:
        from . import traduzione as T
        from .scheda import SchedaError

        lang = str(slots.get("lang") or "").strip()
        field = str(slots.get("field") or "").strip()
        number = str(slots.get("us") or "").strip()
        node_id = str(slots.get("node_id") or "").strip()
        if translator is None or not callable(getattr(translator, "translate", None)):
            return ToolResult(
                ok=False,
                message=("Questo nodo non ha un modello che traduca "
                         "(EM_CHATBOT_INTENT_MODEL, EM_CHATBOT_INTENT_ENDPOINT): "
                         "una traduzione la puoi scrivere tu, in EMStudio."),
                data={"reason": "no-model"})
        if not (number or node_id):
            return ToolResult(ok=False,
                              message="Mi serve l'unità, o il nodo, da tradurre.")

        section = graph_writer.section()
        try:
            if node_id:
                where, what = node_id, field
            else:
                unit_id = unit_id_for(number)
                if not graph_writer.has_node(unit_id):
                    return ToolResult(
                        ok=False,
                        message=f"Non trovo la US {number} in questo grafo.")
                try:
                    scheda, _why = scheda_for(
                        graph_writer, number,
                        scheda_id=str(slots.get("scheda") or ""),
                        version=str(slots.get("version") or ""))
                except SchedaError:
                    scheda = None
                if scheda is not None and field in scheda._by_id:
                    where, what = T.address_of_box(scheda, section, unit_id, field)
                else:
                    where, what = unit_id, field or "description"
            source = T.source_of(section, where, what)
        except T.TraduzioneError as wrong:
            return ToolResult(ok=False, message=str(wrong))

        said = translator.translate(source["text"], source=source["from_lang"] or "und",
                                    target=lang)
        if not said or not str(said).strip():
            return ToolResult(
                ok=False,
                message="Il modello non ha risposto: nessuna traduzione scritta.",
                data={"reason": "model-silent"})

        model = str(getattr(translator, "model", "") or type(translator).__name__)
        stamp = _now()
        try:
            made = T.plan_translation(section, where, source["field"], lang,
                                      str(said).strip(), orcid=author or "",
                                      model=model, ts=stamp)
        except T.TraduzioneError as wrong:
            return ToolResult(ok=False, message=str(wrong))

        data = {"translation_id": made.translation_id, "of": made.of,
                "field": made.field, "lang": made.lang,
                "from_lang": made.from_lang, "method": T.METHOD,
                "model": model, "text": str(said).strip(),
                "to_review": True, "already": made.already,
                "minted": list(made.minted)}
        if made.already:
            return ToolResult(
                ok=True,
                message=(f"Questa traduzione in {made.lang} c'è già: non ne "
                         f"scrivo un'altra."),
                data=data)

        from s3dgraphy import api
        process = _process_node(
            "translate_text", author, made.translation_id,
            f"{made.of}.{made.field} tradotto in {made.lang} da {model}")
        ops = list(made.ops) + [api.make_op("add_node", id=process["id"],
                                            node=process, ts=stamp)]
        try:
            outcomes = graph_writer.send(ops, author=author)
        except Exception as exc:                                 # noqa: BLE001
            return ToolResult(ok=False, message=str(exc))
        data["queued"] = any(o.get("queued") for o in outcomes)
        refused = [o for o in outcomes if not o.get("applied")
                   and o.get("reason") not in ("queued",)]
        if refused:
            data["refused"] = refused
            return ToolResult(ok=False, message=(
                f"La stanza non ha preso la traduzione: "
                f"{refused[0].get('reason')}."), data=data)
        return ToolResult(
            ok=True,
            message=(f"Tradotto in {made.lang}: «{data['text']}». L'ha fatto "
                     f"{model}: resta da verificare, e l'originale è com'era."),
            delta=GraphDelta(process=process, author=author),
            data=data)

    return ToolDescriptor(
        name="translate_text",
        intents=["traduci"],
        input_schema=[
            Slot("lang", "string", True, "la lingua in cui tradurre (it, en, he…)"),
            Slot("us", "string", False, "il numero dell'unità"),
            Slot("field", "string", False,
                 "la casella della scheda, o il campo del grafo "
                 "(description, data.<chiave>)"),
            Slot("node_id", "string", False, "il nodo, se non è un'unità"),
        ],
        description="Traduce un testo col modello del nodo: nasce una "
                    "traduzione AI accanto all'originale, da verificare.",
        service="s3dgraphy", handler=handler)


# ── the five, registered ─────────────────────────────────────────────────────

def build_registry(graph_writer, asset_store, *, translator=None) -> ToolRegistry:
    """The registry. Adding a partner's capability is one more line here plus a
    descriptor — which is the whole claim of the contract, and `build_model`
    (2026-08-29) is the first time somebody else's capability was added by
    exactly those two lines."""
    registry = ToolRegistry()
    registry.register(make_create_su(graph_writer))
    registry.register(make_update_su(graph_writer))
    registry.register(make_relate_su(graph_writer))
    registry.register(make_validate_field(graph_writer))
    registry.register(make_translate_text(graph_writer, translator))
    registry.register(make_which_project(graph_writer))
    registry.register(make_attach_photo(graph_writer, asset_store))
    registry.register(make_ingest_photos(graph_writer, asset_store))
    registry.register(make_query_kg(graph_writer))
    registry.register(make_build_model(graph_writer, asset_store))
    registry.register(make_open_in_emstudio(graph_writer, asset_store))
    return registry
