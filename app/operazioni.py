"""LA SCHEDA DIVENTA OPERAZIONI — valori + ricetta → la lista che va nella stanza.

════════════════════════════════════════════════════════════════════════════════
## IL DIFETTO CHE QUESTO FILE CHIUDE

L'audit del 17 ottobre (`stratigraph-templates/.claude/wip/reports/
2026-10-17-AUDIT-dalla-norma-alla-stanza.md`) ha misurato la US 3014 intera
salvata dal modulo: **1 nodo `US` con 58 chiavi `data.<id_campo>` e 0 archi**, e
una proiezione RDF che non conteneva nessuno dei valori. I verdetti sul grafo
erano dichiarati, validati, e **non li leggeva nessuno** quando si scriveva.

Da allora `stratigraph-templates build` compila ogni definizione con una
RICETTA: per ogni campo, quali delle cinque operazioni di s3Dgraphy mandare
(`add_node`, `update_field`, `remove_node`, `add_edge`, `remove_edge`) e con
quali riferimenti al posto dei valori (templates SPEC §9.3).

**La correzione decisa con E.D. il 27 settembre:** l'orchestratore è StratiGraph
Server. Chi entra nella stanza manda operazioni, come EMStudio. Quindi qui non
c'è un importer e non c'è un applicatore a blocco: c'è **una funzione pura** che
dato ciò che il modulo ha raccolto, l'identità dell'unità e la ricetta, dice
**quali operazioni, in che ordine**. Chi le consegna (il socket, la porta REST,
il container locale) è un altro mestiere, e sta in `writer.py`.

════════════════════════════════════════════════════════════════════════════════
## LE DECISIONI CHE LA RICETTA NON PRENDE, E PERCHÉ QUESTE

La ricetta dichiara ciò che non decide (`open`, `when_missing: not decided by
the definition`). Qui una decisione serve per consegnare, e la si scrive:

1. **L'unità bersaglio di un rapporto che non c'è ancora → si crea MINIMA e
   SEGNATA** (`data.scheda.stub`). Non si rimanda l'arco. Rimandare vuol dire
   tenerlo da qualche parte, e l'unico posto sarebbe una chiave `data.copre` —
   il difetto che questo file esiste per togliere — o la memoria di un
   browser, che si svuota. E un arco verso un id che nessuno risolve è la
   «freccia nel vuoto» che `relate_su` rifiuta da settembre. Un rapporto è
   un'osservazione fatta ADESSO: chi scrive «copre 3018» sta dicendo che la
   3018 esiste. Lo stub porta il nome nella stessa chiave umana (lo stesso
   contesto: località, area), l'id che il servizio conia per quel numero, e
   chi l'ha nominato. Quando la 3018 riceve la SUA scheda lo stub viene
   **promosso**: un `add_node` più recente fonde e decide il tipo (`crdt.
   merge_payloads`: «the newer node stamp decides»).
   * Un **reperto** (`special_find_record`) che non c'è diventa un `SF`:
     la definizione non dà un tipo a quella chiave, e il datamodel di
     `is_part_of` nomina lo Special Find come ciò che sta DENTRO un'unità.
2. **`$anchor.<nome>` non definito → la proprietà si appende all'UNITÀ**, e la
   PropertyNode porta `data.scheda.anchor`. `anno` è l'anno della campagna in
   cui la US è stata scavata: detto dell'unità è approssimato, non falso; il
   segno dice a chi definirà l'atto quali nodi spostare. Lasciarlo cadere
   sarebbe perdere un campo che la persona ha compilato.
3. **Verdetto con passi vuoti (`open`, oggi `definizione`) → nessuna
   operazione, DETTO.** Qui non c'è un posto onesto: la definizione non dice di
   quale proprietà il concetto sia valore, e inventarlo sarebbe decidere al
   posto della definizione. Il campo torna in `silent` con la ragione, e la
   risposta a chi salva lo nomina.
4. **Il tipo dell'unità, quando la scheda non lo decide** (`formazione_segno`
   vuoto, o una definizione senza `node_type`) → `US`, **detto**: è il tipo che
   `create_su` ha sempre dato, e un'unità senza tipo non si crea. Un'unità che
   esiste già con un tipo diverso da quello che la scheda dice NON cambia tipo
   (la ricetta: «decided when the unit is CREATED») — si dice.
5. **Gli id li conia chi crea** (identity.uid.policy). Questo servizio li conia
   deterministici, così lo stesso salvataggio mandato due volte è la stessa
   operazione e si fonde (SPEC §1.2 lo permette: «un singolo strumento può
   derivare i propri id per ritrovare i propri nodi»): l'unità `US<n>` come da
   sempre (`tools.unit_id_for`); una proprietà `<unità>::<campo>[::<riga>]`; un
   documento `doc::path::<percorso>` come `pyarchinit_importer._add_path_document`,
   così un file importato e lo stesso file citato da una scheda sono un nodo;
   un nodo di contesto `stable_id(tipo, campo, nome)`.
6. **Un arco simmetrico** (`equals`, `bonded_to`) **ordina i capi**: «3014
   uguale a 3021» scritto dalla scheda della 3014 e da quella della 3021 è un
   arco, non due. È la regola che `relate_su` seguiva già.
7. **Il segno del generatore sui nodi che conia**: `data.scheda =
   {template, field, of, …}`. Non è un valore di campo — è la provenienza che
   permette il RITORNO (`values_from_graph`): cinque campi della US ICCD
   (`localita`, `area`, `saggio`, `settore`, `quadrato`) producono tutti
   `is_in_location` verso un `LocationNodeGroup`, e dal grafo soltanto non si
   saprebbe più quale casella era quale. Stessa cosa per le righe di una lista
   (`label`, perché «spessore max» e «spessore min» sono entrambe `thickness`).

8. **Quando più caselle producono LO STESSO arco verso LO STESSO tipo**, l'unità
   porta un puntatore per casella: `data.scheda_links.<campo> = [id…]`. Misurato
   sulla US ICCD: `responsabile_scientifico`, `responsabile_compilazione` e
   `responsabile_rielaborazione` diventano tutti `has_author → author`; la stessa
   persona in due ruoli è UN nodo (e deve esserlo: un ORCID è una persona), e
   dal grafo soltanto non si saprebbe più chi aveva quale ruolo. La ricetta
   perde il ruolo per costruzione (proposta nel referto); il puntatore lo
   tiene, con l'orologio per campo del CRDT come `data.authorship.<campo>`.
   Non è un valore: il valore è il nodo.
9. **Le rimozioni vanno in fondo alla lista**, e non si toglie ciò che la
   stessa lista aggiunge. Un `remove_edge` e un `add_edge` dello stesso arco con
   lo stesso `ts` lasciano l'arco RIMOSSO (la resurrezione vuole un orologio
   più recente, `crdt.apply_op_to_section`): se la persona sposta «E.
   Demetrescu» da compilazione a rielaborazione, l'arco verso di lui deve
   restare.

════════════════════════════════════════════════════════════════════════════════
## CHE COSA RIFIUTA, CAMPO PER CAMPO

Un valore della forma sbagliata **non si scrive e si nomina**, e gli altri
campi della stessa scheda passano: una stringa dove serve una lista
(`"3018, 3020"` per `copre`), un testo dove serve una riga di misura. Il
modulo oggi manda stringhe per quei tipi (audit B3); i widget strutturati sono
un pacchetto a sé, e fino ad allora la risposta dice quali caselle non sono
entrate e perché, invece di spezzare una stringa indovinando il separatore.

## CHE COSA NON FA

* **Non parla con nessuno.** Legge la sezione che gli si passa (lo stato
  attuale: stanza o container) e restituisce una lista. Nessun `if` per
  trasporto: la stessa lista va al socket, alla porta REST, al container.
* **Non timbra l'autore.** Il `ts` sì — uno per tutto l'atto, come
  `RoomWriter.update` —, l'autore lo mette il token alla consegna.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .scheda import Scheda, SchedaError

#: Il tipo dell'unità quando la scheda non lo decide (decisione 4).
DEFAULT_UNIT_TYPE = "US"
#: I tipi che contano come «unità» quando se ne cerca una per numero.
_UNIT_PREFIXES = ("US", "USV", "USD", "SF", "VSF", "RSF", "TSU", "UL", "USN",
                  "BR", "SE")
#: I tipi di campo che vogliono una LISTA. Una stringa qui è rifiutata.
LIST_TYPES = frozenset({"unit_ref_list", "resource_ref_list",
                        "record_ref_list", "quantity_list"})
#: Il tipo dello stub per ogni `kind` bersaglio di un arco (decisione 1).
STUB_TYPES = {"stratigraphic_unit": "US", "special_find_record": "SF"}
#: Dove il generatore mette il suo segno, dentro `data` (decisione 7).
MARK = "scheda"
#: I PUNTATORI PER RUOLO sull'unità (decisione 8): `data.scheda_links.<campo>`.
LINKS = "scheda_links"


class OperazioniError(SchedaError):
    """Una scheda che non si traduce in operazioni, con la frase che dice perché."""


@dataclass
class Plan:
    """Che cosa mandare, e che cosa dire a chi ha salvato."""

    unit_id: str
    number: str
    ops: List[Dict[str, Any]] = dc_field(default_factory=list)
    #: per ogni operazione, il campo che l'ha prodotta ("" = l'unità stessa,
    #: "~authorship" = il marcatore di chi l'ha composta)
    op_fields: List[str] = dc_field(default_factory=list)
    created: bool = False
    promoted: bool = False
    node_type: str = ""
    #: i campi che hanno prodotto operazioni (valori scritti o svuotati)
    written: List[str] = dc_field(default_factory=list)
    #: campo → perché NON è stato scritto (forma sbagliata, aggancio mancante)
    refused: Dict[str, str] = dc_field(default_factory=dict)
    #: campo → perché non produce operazioni PER DEFINIZIONE (none, open, …)
    silent: Dict[str, str] = dc_field(default_factory=dict)
    #: gli indici delle operazioni che, contro lo stato letto, NON cambiano
    #: niente (lo stesso valore, lo stesso arco): si mandano lo stesso — sono
    #: idempotenti e tengono convergente una copia che il piano non ha visto —
    #: ma non si contano come «aggiornato»
    noop: Set[int] = dc_field(default_factory=set)
    #: le unità (o i reperti) creati minimi perché un rapporto li nominava
    stubs: List[Dict[str, Any]] = dc_field(default_factory=list)
    notes: List[str] = dc_field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for op in self.ops:
            out[op["op"]] = out.get(op["op"], 0) + 1
        return out


# ── lo stato su cui la ricetta si risolve ───────────────────────────────────

class _Context:
    """La sezione, in sola lettura, con gli indici che la ricetta interroga.

    Si aggiorna con ciò che il piano stesso aggiunge, così un secondo campo che
    cerca «Saggio III» trova il nodo che il primo ha appena coniato invece di
    coniarne un altro.
    """

    def __init__(self, section: Optional[Dict[str, Any]]) -> None:
        from s3dgraphy.crdt import live_edges, live_nodes

        section = section or {}
        self.nodes: Dict[str, Dict[str, Any]] = {
            str(n.get("id")): n for n in live_nodes(section)}
        self.edges: List[Dict[str, Any]] = list(live_edges(section))
        #: lo stato COME LETTO, prima che il piano ci aggiunga qualcosa: è
        #: contro questo che si decide se un'operazione non cambia niente
        self.before_nodes = {k: v for k, v in self.nodes.items()}
        self.before_edges = {(e.get("source"), e.get("edge_type"), e.get("target"))
                             for e in self.edges}

    def add_node(self, node: Dict[str, Any]) -> None:
        self.nodes.setdefault(str(node["id"]), node)

    def links_of(self, unit_id: str) -> Dict[str, List[str]]:
        """I puntatori per ruolo che l'unità porta (`data.scheda_links.<campo>`)."""
        data = (self.nodes.get(unit_id) or {}).get("data") or {}
        out: Dict[str, List[str]] = {}
        for key, value in data.items():
            if key.startswith(LINKS + ".") and isinstance(value, list):
                out[key[len(LINKS) + 1:]] = [str(v) for v in value]
        return out

    def edges_touching(self, node_id: str) -> List[Dict[str, Any]]:
        return [e for e in self.edges
                if node_id in (e.get("source"), e.get("target"))]


def _mark(node: Dict[str, Any]) -> Dict[str, Any]:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    mark = data.get(MARK)
    return mark if isinstance(mark, dict) else {}


def _is_unit(node: Dict[str, Any]) -> bool:
    return str(node.get("node_type") or "").startswith(_UNIT_PREFIXES)


def _find_unit(ctx: _Context, number: str) -> Optional[Dict[str, Any]]:
    """Un'unità per NUMERO, nel contesto: l'id che questo servizio conia prima,
    poi qualunque unità il cui numero risalga dall'id o dal nome."""
    from .tools import number_from_unit_id, unit_id_for

    found = ctx.nodes.get(unit_id_for(number))
    if found is not None:
        return found
    for node in ctx.nodes.values():
        if _is_unit(node) and number_from_unit_id(
                node.get("id"), str(node.get("name") or "").split(" — ")[0]) == number:
            return node
    return None


# ── i valori, nella forma che la ricetta si aspetta ─────────────────────────

_EMPTY = object()


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _text(value: Any) -> str:
    """Un valore come testo: `name` e `description` sono stringhe (SPEC §9.3)."""
    if isinstance(value, dict):
        for key in ("name", "label", "value", "concept", "ref"):
            if value.get(key) not in (None, ""):
                return str(value[key]).strip()
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _normalise(ftype: str, value: Any) -> Any:
    """La forma di un valore, o `OperazioniError` con la frase per quel campo.

    Accetta i valori STRUTTURATI (SPEC §1.5) e le poche forme scalari che sono
    la stessa cosa detta più corta (un nome di persona come stringa); rifiuta
    una stringa dove serve una lista, senza indovinare un separatore.
    """
    if ftype in LIST_TYPES:
        if not isinstance(value, list):
            raise OperazioniError(
                f"vuole una lista ({ftype}) ed è arrivato un "
                f"{type(value).__name__}: {str(value)[:60]!r}. Non la spezzo "
                f"indovinando il separatore")
        items = []
        for item in value:
            if _is_empty(item):
                continue
            if ftype == "quantity_list":
                if not isinstance(item, dict) or _is_empty(item.get("value")):
                    raise OperazioniError(
                        f"ogni riga di una misura è {{qualia, label, value, "
                        f"unit}} con un valore; è arrivato {item!r}")
                items.append({k: item[k] for k in ("qualia", "label", "value",
                                                  "unit") if not _is_empty(item.get(k))})
            elif isinstance(item, dict):
                said = _text({k: item.get(k) for k in
                              ("number", "us", "ref", "path", "url", "name",
                               "value") if item.get(k) not in (None, "")})
                if not said:
                    raise OperazioniError(f"un elemento senza riferimento: {item!r}")
                items.append(said)
            elif isinstance(item, (str, int, float)):
                items.append(str(item).strip())
            else:
                raise OperazioniError(f"elemento illeggibile: {item!r}")
        return items
    if ftype == "term":
        if isinstance(value, dict):
            concept = str(value.get("concept") or "").strip()
            label = str(value.get("label") or "").strip()
            if not concept and not label:
                raise OperazioniError(f"un termine senza concetto né etichetta: {value!r}")
            return {"concept": concept, "label": label}
        if isinstance(value, (str, int, float)):
            # una parola senza concetto: SPEC §3 la chiama `uncontrolled_string`
            return {"concept": "", "label": str(value).strip()}
        raise OperazioniError(f"un termine è {{concept, label}}: è arrivato {value!r}")
    if ftype in ("person_ref", "actor_ref", "epoch_ref", "activity_ref"):
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("label") or "").strip()
            ref = str(value.get("ref") or "").strip()
            if not name and not ref:
                raise OperazioniError(f"un riferimento senza nome: {value!r}")
            return {"name": name, "ref": ref}
        if isinstance(value, (str, int)):
            return {"name": str(value).strip(), "ref": ""}
        raise OperazioniError(f"un riferimento è {{name, ref}}: è arrivato {value!r}")
    if isinstance(value, (dict, list)):
        raise OperazioniError(
            f"vuole un valore semplice ({ftype or 'testo'}) ed è arrivato "
            f"{type(value).__name__}")
    return value


# ── i riferimenti della ricetta ─────────────────────────────────────────────

class _Missing(Exception):
    """Un riferimento che non si risolve. Chi lo raccoglie decide."""


def _lookup(root: Any, path: List[str]) -> Any:
    here = root
    for key in path:
        if isinstance(here, dict) and not _is_empty(here.get(key)):
            here = here[key]
        else:
            raise _Missing(".".join(path))
    return here


def _resolve(template: Any, env: Dict[str, Any]) -> Any:
    """Sostituisce i `$riferimenti` di un passo (SPEC §9.3), ricorsivamente.

    Un riferimento che non si risolve DENTRO `data` fa cadere la chiave (una
    riga senza unità di misura non ha `units`); altrove solleva `_Missing`.
    """
    if isinstance(template, str) and template.startswith("$"):
        head, *rest = template[1:].split(".")
        if head == "field":
            # `$field.<id>.prop`
            fid = rest[0] if rest else ""
            props = env.get("field_props") or {}
            if fid in props:
                return props[fid]
            raise _Missing(template)
        if head == "anchor":
            return env["unit"]
        if head not in env:
            raise _Missing(template)
        value = env[head]
        if rest:
            return _lookup(value, rest)
        return value
    if isinstance(template, dict):
        out: Dict[str, Any] = {}
        for key, sub in template.items():
            if key == "data" and isinstance(sub, dict):
                data: Dict[str, Any] = {}
                for dkey, dsub in sub.items():
                    try:
                        data[dkey] = _resolve(dsub, env)
                    except _Missing:
                        continue
                out[key] = data
                continue
            out[key] = _resolve(sub, env)
        for key in ("name", "description"):
            if key in out and not isinstance(out[key], str):
                out[key] = _text(out[key])
        return out
    if isinstance(template, list):
        return [_resolve(sub, env) for sub in template]
    return template


# ── i nodi che una voce trova o crea ────────────────────────────────────────

def _find_node(ctx: _Context, spec: Dict[str, Any], fid: str,
               template_id: str, *, by_field: bool = True) -> Optional[Dict[str, Any]]:
    """Trova prima di creare (SPEC §9.3): per id/ref, per percorso, per nome.

    Per NOME un nodo segnato da un ALTRO campo non si riusa: «3B» come settore
    e «3B» come quadrato sono due posti. Tranne (`by_field=False`) per ciò che
    la ricetta cerca anche per `id`/ref — persone, epoche, attività: quelli
    hanno un'identità, e lo stesso nome in due caselle è la stessa entità.
    """
    node_type = spec.get("node_type")
    wanted_id = spec.get("id")
    if wanted_id:
        found = ctx.nodes.get(str(wanted_id))
        if found is not None and (not node_type
                                  or found.get("node_type") == node_type):
            return found
    url = spec.get("url")
    if url:
        for node in ctx.nodes.values():
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            if node.get("node_type") == node_type and data.get("url") == url:
                return node
        return None
    name = spec.get("name")
    if name:
        for node in ctx.nodes.values():
            if node.get("node_type") != node_type:
                continue
            if str(node.get("name") or "").strip() != str(name).strip():
                continue
            other = _mark(node).get("field")
            if (by_field and other and other != fid
                    and _mark(node).get("template") == template_id):
                continue
            return node
    return None


def _mint_found_id(spec: Dict[str, Any], fid: str) -> str:
    from .contract import stable_id

    node_type = str(spec.get("node_type") or "")
    if spec.get("url"):
        return f"doc::path::{spec['url']}"
    if spec.get("id"):
        return str(spec["id"])
    return stable_id(node_type, fid, str(spec.get("name") or ""))


# ── il nome dell'unità ──────────────────────────────────────────────────────

def unit_name(scheda: Scheda, values: Dict[str, Any], number: str) -> str:
    """Il nome dal `pattern` della definizione (SPEC §1.2), tagliato al primo
    segnaposto che non ha un valore: «US 3014» invece di «US 3014 — {area}».
    """
    pattern = str(((scheda.raw.get("identity") or {}).get("human_key") or {})
                  .get("pattern") or "")
    unit_field = scheda.unit_field or (scheda.human_key[-1]
                                       if len(scheda.human_key) == 1 else "")
    filled = {k: _text(v) for k, v in values.items() if not _is_empty(v)}
    if unit_field:
        filled[unit_field] = number
    if not pattern:
        return number
    out = ""
    for piece in re.split(r"(\{[^}]+\})", pattern):
        match = re.fullmatch(r"\{([^}]+)\}", piece)
        if not match:
            out += piece
            continue
        key = match.group(1)
        if not filled.get(key):
            break
        out += filled[key]
    return out.rstrip(" —-·(,;:").strip() or number


# ── IL GENERATORE ───────────────────────────────────────────────────────────

def _ordered_fields(recipe: Dict[str, Any], scheda: Scheda,
                    values: Dict[str, Any]) -> List[str]:
    """L'ordine della definizione, e chi ha `after` dopo ciò che aspetta."""
    order = [str(f.get("id")) for f in scheda.fields if str(f.get("id")) in values]
    entries = recipe.get("fields") or {}
    later = [fid for fid in order if (entries.get(fid) or {}).get("after")]
    return [fid for fid in order if fid not in later] + later


def plan(scheda: Scheda, values: Dict[str, Any], *, number: str,
         section: Optional[Dict[str, Any]], ts: str, create: bool = False,
         authored_by: Optional[Dict[str, str]] = None,
         model: Optional[str] = None, additive: bool = False,
         relations: Optional[List[Tuple[str, str, str]]] = None) -> Plan:
    """Valori + identità + ricetta → la lista di operazioni, in ordine.

    `relations` = `[(edge_type, direzione, altra unità)]`: i rapporti detti a
    voce che la scheda NON ha come casella ma il datamodel dichiara fra unità
    stratigrafiche («contemporaneo a» → `has_same_time`). Passano per la
    stessa via di una casella di rapporto (stub, simmetrici ordinati, id,
    `noop`), sempre additivi, e non portano un marcatore di autorialità:
    non c'è una casella di cui essere l'autore — l'autore è quello
    dell'operazione.

    `section` è lo stato attuale (la sezione attiva della stanza o del
    container), letto e mai scritto. `values` sono SOLO i campi che si
    vogliono toccare: un campo assente non si tocca, un campo presente e vuoto
    si svuota (le sue operazioni di rimozione).

    `additive=True` non toglie niente: è la voce che dice UN rapporto («la 12
    copre la 14») e non sta riscrivendo l'intera casella COPRE.
    """
    from . import authorship
    from .tools import unit_id_for

    number = str(number or "").strip()
    if not number:
        raise OperazioniError("una scheda è di un'unità: manca il numero")
    recipe = scheda.recipe
    if recipe is None:
        raise OperazioniError(
            f"«{scheda.id}» è servita da una definizione YAML (la "
            f"sovrascrittura di sviluppo) e non dalla forma compilata: non ha "
            f"una ricetta, quindi nessuno sa che cosa le sue caselle siano nel "
            f"grafo. Si disegna e non si salva — `stratigraph-templates build` "
            f"e `./sync-schede.sh`.")
    unknown = sorted(k for k in values if k not in scheda._by_id)
    if unknown:
        raise OperazioniError(
            f"«{scheda.id}» non ha i campi {unknown}: una scheda compila le "
            f"caselle che lo standard dichiara, non altre.")

    ctx = _Context(section)
    entries = recipe.get("fields") or {}
    template_id = scheda.id

    # ── 1 · l'unità ─────────────────────────────────────────────────────────
    existing = _find_unit(ctx, number)
    unit_id = str(existing["id"]) if existing else unit_id_for(number)
    out = Plan(unit_id=unit_id, number=number)
    current = {"field": ""}
    #: le rimozioni si RACCOLGONO e si mandano in fondo (decisione 9)
    removals: List[Tuple[str, str, Dict[str, Any]]] = []

    def drop(kind: str, **fields: Any) -> None:
        removals.append((current["field"], kind, fields))

    def op(kind: str, **fields: Any) -> Dict[str, Any]:
        from s3dgraphy import api
        made = api.make_op(kind, ts=ts, **fields)
        out.ops.append(made)
        out.op_fields.append(current["field"])
        return made

    unit_recipe = recipe.get("unit") or {}
    decided = (unit_recipe.get("node_type") or {})
    decided_by = decided.get("decided_by")
    table = decided.get("table") or {}
    wanted_type = ""
    if decided_by and not _is_empty(values.get(decided_by)):
        row = table.get(str(values.get(decided_by)))
        if row is None:
            out.refused[decided_by] = (
                f"«{values.get(decided_by)}» non è un valore che decide il "
                f"tipo ({sorted(table)})")
        else:
            wanted_type = str(row.get("node_type") or "")

    is_stub = bool(existing and _mark(existing).get("stub"))
    if existing is None:
        if not create:
            raise OperazioniError(
                f"L'unità «{unit_id}» non è in questo grafo: non posso "
                f"aggiornare una scheda che non esiste. Creala prima.")
        out.node_type = wanted_type or DEFAULT_UNIT_TYPE
        if not wanted_type:
            out.notes.append(
                f"il tipo dell'unità non lo decide la scheda "
                f"({decided_by or 'nessun campo node_type'} vuoto): "
                f"{DEFAULT_UNIT_TYPE}, come a voce")
        node = {"id": unit_id, "node_type": out.node_type,
                "name": unit_name(scheda, values, number)}
        op("add_node", id=unit_id, node=node)
        ctx.add_node(node)
        out.created = True
    elif is_stub:
        # PROMOSSO: la sua scheda arriva adesso, e un `add_node` più recente
        # fonde e decide il tipo (decisione 1).
        out.node_type = wanted_type or str(existing.get("node_type") or DEFAULT_UNIT_TYPE)
        node = {"id": unit_id, "node_type": out.node_type,
                "name": unit_name(scheda, values, number)}
        op("add_node", id=unit_id, node=node)
        out.promoted = True
        out.notes.append(f"{unit_id} era segnata da un rapporto: ora ha la sua scheda")
    else:
        out.node_type = str(existing.get("node_type") or "")
        if wanted_type and wanted_type != out.node_type:
            out.notes.append(
                f"la scheda dice {wanted_type} ma {unit_id} è registrata come "
                f"{out.node_type}: il tipo si decide alla creazione e "
                f"un'operazione non lo cambia")

    # quale definizione e quale versione l'ha compilata (audit B5b)
    op("update_field", node_id=unit_id, field=f"data.{MARK}", value=scheda.ref)

    # ── 2 · i campi ─────────────────────────────────────────────────────────
    field_props: Dict[str, str] = {}
    # le proprietà già nel grafo, per `$field.<id>.prop` di un campo non toccato
    for node in ctx.nodes.values():
        mark = _mark(node)
        if mark.get("of") == unit_id and mark.get("field") and "index" not in mark:
            field_props.setdefault(str(mark["field"]), str(node["id"]))

    for fid in _ordered_fields(recipe, scheda, values):
        entry = entries.get(fid) or {}
        verdict = entry.get("verdict")
        ftype = str(scheda.field(fid).get("type") or "")
        raw = values.get(fid)
        if verdict == "identity":
            out.silent[fid] = "compone il nome dell'unità (identity)"
            continue
        if verdict == "none":
            blocked = entry.get("blocked_on") or {}
            out.silent[fid] = ("non entra nel grafo per la definizione"
                               + (f": {blocked.get('needs')}" if blocked.get("needs")
                                  else f" ({entry.get('reason')})" if entry.get("reason")
                                  else ""))
            continue
        if verdict == "node_type":
            out.silent[fid] = "decide il tipo dell'unità, alla creazione"
            continue
        if not entry.get("steps"):
            out.silent[fid] = ("la definizione non dice ancora che cosa sia nel "
                               "grafo: " + str(entry.get("open") or "open"))
            continue
        try:
            value = _EMPTY if _is_empty(raw) else _normalise(ftype, raw)
        except OperazioniError as wrong:
            out.refused[fid] = str(wrong)
            continue
        if value is not _EMPTY and isinstance(value, list) and not value:
            value = _EMPTY
        before = len(out.ops)
        current["field"] = fid
        try:
            mine = len(removals)
            _expand(out, ctx, op, drop, scheda, fid, entry, value, values,
                    field_props, template_id, additive=additive)
        except OperazioniError as wrong:
            del out.ops[before:]
            del out.op_fields[before:]
            del removals[mine:]
            out.refused[fid] = str(wrong)
            continue
        out.written.append(fid)

    # ── 2ter · i rapporti senza casella, dal datamodel ─────────────────────
    said_relations: List[str] = []
    for edge_type, direction, other in relations or []:
        fid = f"{RELATION_PREFIX}{edge_type}"
        before = len(out.ops)
        current["field"] = fid
        try:
            _expand(out, ctx, op, drop, scheda, fid,
                    _relation_entry(scheda, edge_type, direction), [str(other)], values,
                    field_props, template_id, additive=True)
        except OperazioniError as wrong:
            del out.ops[before:]
            del out.op_fields[before:]
            out.refused[fid] = str(wrong)
            continue
        out.written.append(fid)
        said_relations.append(fid)

    # ── 2bis · le rimozioni, in fondo, tolto ciò che la lista stessa vuole ──
    added_edges = {(o["source"], o["edge_type"], o["target"])
                   for o in out.ops if o["op"] == "add_edge"}
    added_nodes = {o["id"] for o in out.ops if o["op"] == "add_node"}
    links = ctx.links_of(unit_id)
    for fid, kind, fields in removals:
        current["field"] = fid
        if kind == "remove_edge":
            triple = (fields["source"], fields["edge_type"], fields["target"])
            if triple in added_edges:
                continue
            other = fields["target"] if fields["source"] == unit_id else fields["source"]
            if any(other in ids for f, ids in links.items() if f != fid):
                continue          # un'altra casella ci punta ancora
        if kind == "remove_node" and fields.get("id") in added_nodes:
            continue
        op(kind, **fields)

    out.noop = {i for i, o in enumerate(out.ops) if _is_noop(ctx, o)}

    # ── 3 · chi ha composto ogni valore, accanto al valore ─────────────────
    current["field"] = "~authorship"
    marks = authorship.marks_for([f for f in out.written if f not in said_relations],
                                 authored_by, model=model)
    for key, mark in marks.items():
        op("update_field", node_id=unit_id, field=f"data.{key}", value=mark)
    return out


def _expand(out: Plan, ctx: _Context, op, drop, scheda: Scheda, fid: str,
            entry: Dict[str, Any], value: Any, values: Dict[str, Any],
            field_props: Dict[str, str], template_id: str, *,
            additive: bool = False) -> None:
    """Le operazioni di UN campo: ciò che deve esserci, e la rimozione di ciò
    che c'era e non c'è più."""
    unit_id = out.unit_id
    verdict = entry.get("verdict")
    each = bool(entry.get("each"))
    steps = entry.get("steps") or []
    resolve = entry.get("resolve") or {}
    items: List[Any] = [] if value is _EMPTY else (value if each else [value])

    # ── un arco verso un'altra unità (o un reperto) ─────────────────────────
    if verdict == "edge":
        spec = (resolve.get("$item") or {}).get("find") or {}
        kind = str(spec.get("kind") or "stratigraphic_unit")
        emit = steps[0]["emit"]
        symmetric = bool((entry.get("edge") or {}).get("symmetric"))
        wanted: Set[Tuple[str, str, str]] = set()
        for item in items:
            target_id = _resolve_item(out, ctx, op, scheda, fid, kind, str(item),
                                      values)
            env = {"unit": unit_id, "item": target_id}
            source, target = _resolve(emit["source"], env), _resolve(emit["target"], env)
            if source == target:
                raise OperazioniError(f"l'unità {out.number} non può essere in "
                                      f"rapporto con se stessa")
            if symmetric:
                source, target = min(source, target), max(source, target)
            triple = (source, emit["edge_type"], target)
            if triple not in wanted:
                wanted.add(triple)
                _add_edge(op, ctx, *triple)
        for edge in ([] if additive else
                     _edge_footprint(ctx, unit_id, emit, symmetric, kind)):
            triple = (edge["source"], edge["edge_type"], edge["target"])
            if triple not in wanted:
                drop("remove_edge", id=edge.get("id"), source=triple[0],
                     edge_type=triple[1], target=triple[2])
        return

    # ── un campo del nodo: `description`, o un ELEMENTO del nodo ───────────
    # (`definition` → `data.definition`, dichiarato dal datamodel dei nodi e
    # letto dalla ricetta: `entry.element`). `description` è una stringa;
    # l'elemento tiene il valore INTERO — un termine resta {concept, label},
    # senza le chiavi vuote (una parola detta a voce è {label}: nessun concetto
    # inventato).
    native = [s for s in steps if s["emit"]["op"] == "update_field"]
    if native and len(steps) == 1:
        emit = native[0]["emit"]
        if value is _EMPTY:
            op("update_field", node_id=unit_id, field=emit["field"], remove=True)
        else:
            said = _resolve(emit["value"], {"unit": unit_id, "value": value})
            if entry.get("element"):
                said = ({k: v for k, v in said.items() if not _is_empty(v)}
                        if isinstance(said, dict) else said)
            else:
                said = _text(said)
            op("update_field", node_id=unit_id, field=emit["field"], value=said)
        return

    minted_key = "$prop" if "$prop" in resolve else (
        "$node" if (resolve.get("$node") or {}).get("mint") else None)

    # ── una PropertyNode (o un nodo di contenuto) coniata per il campo ─────
    if minted_key:
        wanted_ids: Set[str] = set()
        prop_info = entry.get("property") or {}
        for index, item in enumerate(items):
            minted = f"{unit_id}::{fid}" + (f"::{index}" if each else "")
            wanted_ids.add(minted)
            mark: Dict[str, Any] = {"template": template_id, "field": fid,
                                    "of": unit_id}
            if each:
                mark["index"] = index
            env: Dict[str, Any] = {"unit": unit_id, "value": item, "item": item,
                                   "field_props": field_props,
                                   minted_key[1:]: minted}
            if isinstance(item, dict) and ftype_is_term(scheda, fid):
                if not item.get("concept"):
                    # una parola senza concetto (SPEC §3 `uncontrolled_string`)
                    env["value"] = {**item, "concept": item.get("label")}
                    mark["uncontrolled"] = True
                if item.get("label"):
                    mark["label"] = item["label"]
            if each and isinstance(item, dict):
                if item.get("label"):
                    mark["label"] = item["label"]
                if _is_empty(item.get("qualia")):
                    default = (entry.get("defaults") or {}).get("$item.qualia")
                    fallback = default or prop_info.get("box") or fid
                    env["item"] = {**item, "qualia": fallback}
                    mark["qualia_missing"] = True
            anchored = [s for s in steps if "$anchor." in str(s["emit"].get("source"))]
            if anchored:
                mark["anchor"] = str(anchored[0]["emit"]["source"]).split(".", 1)[1]
            try:
                resolved = [(s, _resolve(s["emit"], env)) for s in steps]
            except _Missing as missing:
                raise OperazioniError(
                    f"la ricetta aggancia questo campo a {missing}, che non c'è "
                    f"(compila prima quel campo)") from None
            for step, emitted in resolved:
                if emitted["op"] == "add_node":
                    node = dict(emitted["node"])
                    node["data"] = {**(node.get("data") or {}), MARK: mark}
                    op("add_node", id=minted, node=node)
                    ctx.add_node(node)
                elif emitted["op"] == "add_edge":
                    _add_edge(op, ctx, emitted["source"], emitted["edge_type"],
                              emitted["target"])
        if not each and wanted_ids:
            field_props[fid] = next(iter(wanted_ids))
        # ciò che questo campo aveva coniato e non conia più
        for node in list(ctx.nodes.values()):
            mark = _mark(node)
            if (mark.get("of") == unit_id and mark.get("field") == fid
                    and str(node["id"]) not in wanted_ids):
                for edge in ctx.edges_touching(str(node["id"])):
                    drop("remove_edge", id=edge.get("id"), source=edge["source"],
                         edge_type=edge["edge_type"], target=edge["target"])
                drop("remove_node", id=str(node["id"]))
        return

    # ── un nodo di contesto, trovato o creato, e l'arco verso di lui ───────
    spec_tmpl = (resolve.get("$node") or {}).get("find") or {}
    node_step = next((s for s in steps if s["emit"]["op"] == "add_node"), None)
    edge_step = next((s for s in steps if s["emit"]["op"] == "add_edge"), None)
    wanted_targets: Set[str] = set()
    for item in items:
        env = {"unit": unit_id, "value": item, "item": item}
        spec: Dict[str, Any] = {}
        for key, sub in spec_tmpl.items():
            try:
                resolved = _resolve(sub, env)
            except _Missing:
                continue
            spec[key] = _text(resolved) if key in ("name", "url", "id") else resolved
        spec = {k: v for k, v in spec.items() if not _is_empty(v)}
        found = _find_node(ctx, spec, fid, template_id,
                           by_field="id" not in spec_tmpl)
        if found is not None:
            node_id = str(found["id"])
        else:
            node_id = _mint_found_id(spec, fid)
            if node_step is not None:
                env["node"] = node_id
                node = dict(_resolve(node_step["emit"]["node"], env))
                mark = {"template": template_id, "field": fid}
                if isinstance(item, dict) and item.get("ref"):
                    mark["ref"] = item["ref"]
                node["data"] = {**(node.get("data") or {}), MARK: mark}
                op("add_node", id=node_id, node=node)
                ctx.add_node(node)
        wanted_targets.add(node_id)
        if edge_step is not None:
            env["node"] = node_id
            emitted = _resolve(edge_step["emit"], env)
            _add_edge(op, ctx, emitted["source"], emitted["edge_type"],
                      emitted["target"])
    if edge_step is not None:
        emit = edge_step["emit"]
        outgoing = emit["source"] == "$unit"
        node_type = spec_tmpl.get("node_type")
        shared = _rivals(scheda, emit["edge_type"], node_type) > 1
        before_links = ctx.links_of(unit_id).get(fid)
        if shared:
            # decisione 8: il ruolo, tenuto dall'unità
            if wanted_targets:
                op("update_field", node_id=unit_id, field=f"data.{LINKS}.{fid}",
                   value=sorted(wanted_targets))
            elif before_links is not None:
                op("update_field", node_id=unit_id, field=f"data.{LINKS}.{fid}",
                   remove=True)
        for edge in list(ctx.edges):
            if edge.get("edge_type") != emit["edge_type"]:
                continue
            if (edge.get("source") if outgoing else edge.get("target")) != unit_id:
                continue
            other_id = edge.get("target") if outgoing else edge.get("source")
            other = ctx.nodes.get(str(other_id))
            if other is None or other.get("node_type") != node_type:
                continue
            if other_id in wanted_targets:
                continue
            if before_links is not None:
                if other_id not in before_links:
                    continue
            elif not _belongs_to(other, fid, template_id, scheda, emit, node_type):
                continue
            drop("remove_edge", id=edge.get("id"), source=edge["source"],
                 edge_type=edge["edge_type"], target=edge["target"])


def _is_noop(ctx: _Context, op: Dict[str, Any]) -> bool:
    """Questa operazione, applicata allo stato LETTO, lo lascerebbe com'è?"""
    from s3dgraphy.crdt import canonical, field_tombstone, get_field

    kind = op["op"]
    if kind == "add_edge":
        return (op["source"], op["edge_type"], op["target"]) in ctx.before_edges
    if kind == "update_field":
        node = ctx.before_nodes.get(str(op["node_id"]))
        if node is None:
            return False
        gone = field_tombstone(node, op["field"]) is not None
        if op.get("remove"):
            return gone or get_field(node, op["field"]) in (None, "")
        return (not gone and canonical(get_field(node, op["field"]))
                == canonical(op.get("value")))
    if kind == "add_node":
        node = ctx.before_nodes.get(str(op["id"]))
        if node is None:
            return False
        payload = op.get("node") or {}
        if payload.get("node_type") and payload["node_type"] != node.get("node_type"):
            return False
        for key in ("name", "description"):
            if key in payload and canonical(payload[key]) != canonical(node.get(key)):
                return False
        mine = node.get("data") or {}
        return all(canonical(v) == canonical(mine.get(k))
                   for k, v in (payload.get("data") or {}).items())
    return False


def ftype_is_term(scheda: Scheda, fid: str) -> bool:
    return str(scheda.field(fid).get("type") or "") == "term"


def _belongs_to(node: Dict[str, Any], fid: str, template_id: str,
                scheda: Scheda, emit: Dict[str, Any], node_type: str) -> bool:
    """Un nodo di contesto raggiunto dall'unità: è di QUESTO campo?

    Dal segno, se c'è. Senza segno (creato da un'altra porta), solo se questo
    è l'unico campo della definizione che produce quell'arco verso quel tipo:
    altrimenti non si sa, e un arco che non si sa di chi sia non si toglie.
    """
    mark = _mark(node)
    if mark.get("field"):
        return mark.get("field") == fid and mark.get("template") == template_id
    return _rivals(scheda, emit["edge_type"], node_type) <= 1


def _rivals(scheda: Scheda, edge_type: str, node_type: Any) -> int:
    """Quante caselle della definizione producono `edge_type` verso `node_type`."""
    rivals = 0
    for other in (scheda.recipe.get("fields") or {}).values():
        if (other.get("node") or {}).get("node_type") != node_type:
            continue
        if any((s.get("emit") or {}).get("op") == "add_edge"
               and (s.get("emit") or {}).get("edge_type") == edge_type
               for s in other.get("steps") or []):
            rivals += 1
    return rivals


def _edge_footprint(ctx: _Context, unit_id: str, emit: Dict[str, Any],
                    symmetric: bool, kind: str) -> List[Dict[str, Any]]:
    """Gli archi di questo campo che ci sono già: stesso tipo, l'unità allo
    stesso capo, e dall'altro capo qualcosa del tipo giusto."""
    out = []
    unit_is_source = emit["source"] == "$unit"
    # UN LETTORE riconosce ogni grafia che il datamodel accetta (`spellings`):
    # un `is_bonded_to` di un grafo vecchio È la casella SI LEGA A. Chi
    # scrive, scrive la canonica — e riscrivendo la casella la grafia vecchia
    # esce e la canonica entra.
    names = spellings(emit["edge_type"])
    for edge in ctx.edges:
        if edge.get("edge_type") not in names:
            continue
        ends = (edge.get("source"), edge.get("target"))
        if symmetric:
            if unit_id not in ends:
                continue
            other = ends[1] if ends[0] == unit_id else ends[0]
        else:
            if (ends[0] if unit_is_source else ends[1]) != unit_id:
                continue
            other = ends[1] if unit_is_source else ends[0]
        node = ctx.nodes.get(str(other))
        if node is None:
            continue
        if kind == "stratigraphic_unit" and not _is_unit(node):
            continue
        out.append(edge)
    return out


def _add_edge(op, ctx: _Context, source: str, edge_type: str, target: str) -> None:
    from .tools import edge_id_for

    edge = {"id": edge_id_for(source, edge_type, target), "source": source,
            "edge_type": edge_type, "target": target}
    op("add_edge", **edge)
    if not any((e.get("source"), e.get("edge_type"), e.get("target"))
               == (source, edge_type, target) for e in ctx.edges):
        ctx.edges.append(edge)


def _resolve_item(out: Plan, ctx: _Context, op, scheda: Scheda, fid: str,
                  kind: str, item: str, values: Dict[str, Any]) -> str:
    """L'altra unità di un rapporto, per chiave umana nel contesto; o uno stub."""
    from .contract import stable_id
    from .tools import unit_id_for

    if kind == "stratigraphic_unit":
        found = _find_unit(ctx, item)
        if found is not None:
            return str(found["id"])
        stub_id = unit_id_for(item)
        name = unit_name(scheda, values, item)
    else:
        for node in ctx.nodes.values():
            if str(node.get("name") or "").strip() == item:
                return str(node["id"])
        stub_id = stable_id(kind, item)
        name = item
    stub = {"id": stub_id, "node_type": STUB_TYPES.get(kind, DEFAULT_UNIT_TYPE),
            "name": name,
            "data": {MARK: {"stub": True, "kind": kind, "declared_by": out.unit_id,
                            "field": fid, "template": scheda.id}}}
    op("add_node", id=stub_id, node=stub)
    ctx.add_node(stub)
    out.stubs.append({"id": stub_id, "kind": kind, "name": name, "field": fid})
    return stub_id


# ── IL RITORNO: dal nodo dell'unità, attraverso la stessa ricetta, ai valori ─

def values_from_graph(scheda: Scheda, section: Optional[Dict[str, Any]],
                      unit_id: str) -> Dict[str, Any]:
    """La lettura inversa (audit B4): ciò che la scheda mostra riaprendo l'unità.

    Attraversa i verdetti al contrario, con la STESSA ricetta che li ha scritti:
    il campo nativo dal campo del nodo, le proprietà dai nodi coniati col segno
    del campo, i nodi di contesto dagli archi, i rapporti dagli archi con
    l'unità al capo giusto. Ciò che la definizione tiene fuori dal grafo
    (`none`, `open`) NON torna, e si dice in `silent`.
    """
    from . import authorship
    from .tools import number_from_unit_id
    from s3dgraphy.crdt import get_field

    if scheda.recipe is None:
        raise OperazioniError(f"«{scheda.id}» non è compilata: non ha una ricetta "
                              f"con cui rileggere")
    ctx = _Context(section)
    unit = ctx.nodes.get(unit_id)
    if unit is None:
        raise OperazioniError(f"L'unità «{unit_id}» non è in questo grafo.")
    entries = scheda.recipe.get("fields") or {}
    values: Dict[str, Any] = {}
    silent: Dict[str, str] = {}

    def number_of(node: Dict[str, Any]) -> str:
        return (number_from_unit_id(node.get("id"),
                                    str(node.get("name") or "").split(" — ")[0])
                or str(node.get("name") or node.get("id")))

    # le proprietà coniate per questa unità, raggruppate per campo
    minted: Dict[str, List[Dict[str, Any]]] = {}
    for node in ctx.nodes.values():
        mark = _mark(node)
        if mark.get("of") == unit_id and mark.get("field"):
            minted.setdefault(str(mark["field"]), []).append(node)
    for rows in minted.values():
        rows.sort(key=lambda n: int(_mark(n).get("index") or 0))

    for f in scheda.fields:
        fid = str(f.get("id"))
        ftype = str(f.get("type") or "")
        entry = entries.get(fid) or {}
        verdict = entry.get("verdict")
        steps = entry.get("steps") or []
        resolve = entry.get("resolve") or {}
        if verdict == "identity":
            if fid == scheda.unit_field or len(scheda.human_key) == 1:
                values[fid] = number_of(unit)
            continue
        if verdict == "node_type":
            for option, row in (entry.get("table") or {}).items():
                if row.get("node_type") == unit.get("node_type"):
                    values[fid] = option
            continue
        if verdict == "none" or not steps:
            silent[fid] = "non è nel grafo per la definizione"
            continue
        if verdict == "edge":
            emit = steps[0]["emit"]
            kind = str(((resolve.get("$item") or {}).get("find") or {}).get("kind")
                       or "stratigraphic_unit")
            symmetric = bool((entry.get("edge") or {}).get("symmetric"))
            items = []
            for edge in _edge_footprint(ctx, unit_id, emit, symmetric, kind):
                other = (edge["target"] if edge["source"] == unit_id
                         else edge["source"])
                node = ctx.nodes[str(other)]
                items.append(number_of(node) if kind == "stratigraphic_unit"
                             else str(node.get("name") or other))
            if items:
                values[fid] = items
            continue
        native = [s for s in steps if s["emit"]["op"] == "update_field"]
        if native and len(steps) == 1:
            # `description` in cima al nodo, un elemento in `data.<nome>`: lo
            # stesso indirizzo del CRDT, letto come lo legge il CRDT
            said = get_field(unit, native[0]["emit"]["field"])
            if said not in (None, ""):
                values[fid] = _typed(ftype, said)
            continue
        if fid in minted:
            rows = []
            for node in minted[fid]:
                mark = _mark(node)
                data = node.get("data") or {}
                said = node.get("description")
                if bool(entry.get("each")):
                    row: Dict[str, Any] = {}
                    if not mark.get("qualia_missing"):
                        row["qualia"] = data.get("property_type") or node.get("name")
                    if mark.get("label"):
                        row["label"] = mark["label"]
                    row["value"] = said
                    if data.get("units"):
                        row["unit"] = data["units"]
                    rows.append(row)
                elif ftype == "term":
                    rows.append({"label": mark.get("label") or said}
                                if mark.get("uncontrolled")
                                else {"concept": said,
                                      **({"label": mark["label"]} if mark.get("label") else {})})
                else:
                    rows.append(_typed(ftype, said))
            values[fid] = rows if entry.get("each") else rows[0]
            continue
        # un nodo di contesto: dall'arco
        edge_step = next((s for s in steps if s["emit"]["op"] == "add_edge"), None)
        node_type = ((resolve.get("$node") or {}).get("find") or {}).get("node_type")
        if edge_step is None:
            continue
        emit = edge_step["emit"]
        outgoing = emit["source"] == "$unit"
        pointed = ctx.links_of(unit_id).get(fid)
        found = []
        for edge in ctx.edges:
            if edge.get("edge_type") != emit["edge_type"]:
                continue
            if (edge.get("source") if outgoing else edge.get("target")) != unit_id:
                continue
            other = ctx.nodes.get(str(edge.get("target") if outgoing else edge.get("source")))
            if other is None or other.get("node_type") != node_type:
                continue
            if pointed is not None:
                if str(other["id"]) not in pointed:
                    continue
            elif not _belongs_to(other, fid, scheda.id, scheda, emit, node_type):
                continue
            found.append(other)
        if not found:
            continue
        if ftype == "resource_ref_list":
            values[fid] = [str((n.get("data") or {}).get("url") or n.get("name"))
                           for n in found]
        elif ftype in ("person_ref", "actor_ref"):
            node = found[0]
            ref = _mark(node).get("ref")
            values[fid] = {"name": node.get("name"), **({"ref": ref} if ref else {})}
        else:
            values[fid] = str(found[0].get("name") or "")

    authored = {}
    validated = []
    for fid in values:
        said = authorship.read(unit, fid)
        if said["declared"]:
            authored[fid] = said["by"] if not said["validated"] else "human"
            if said["validated"]:
                validated.append(fid)
            elif said["by"] == authorship.AI:
                authored[fid] = authorship.AI
    return {"unit_id": unit_id, "values": values, "authored_by": authored,
            "validated": validated, "silent": silent,
            "declared": _mark(unit) or None}


def _typed(ftype: str, said: Any) -> Any:
    """Il testo di un nodo, nel tipo del campo: `description` è una stringa."""
    if ftype == "integer":
        try:
            return int(str(said).strip())
        except ValueError:
            return said
    if ftype == "checkbox":
        return str(said).strip().lower() in ("true", "1", "sì", "si", "yes")
    return said


# ── la voce: ciò che si dice, nella forma che la ricetta vuole ──────────────

def spoken_value(scheda: Scheda, fid: str, text: str) -> Any:
    """UNA cosa detta, nella forma del campo.

    La voce è una superficie che sa di aver sentito UN valore: «la quota è
    145,30» è una riga di misura, «il colore è bruno» una parola senza
    concetto. Il generatore rifiuta una stringa dove serve una lista; è qui,
    e non là, che una frase diventa una riga — perché qui si sa che era una.
    """
    ftype = str(scheda.field(fid).get("type") or "")
    said = str(text or "").strip()
    if ftype == "quantity_list":
        return [{"label": said, "value": said}]
    if ftype in ("unit_ref_list", "resource_ref_list", "record_ref_list"):
        return [said]
    if ftype == "term":
        return {"label": said}
    return said


def relation_phrases(scheda: Scheda, lang: str) -> Dict[str, Tuple[str, str, str]]:
    """Le frasi dei rapporti, DERIVATE dalla ricetta (audit B2).

    `frase → (edge_type, direzione, campo)`: la frase è l'etichetta della
    casella nella lingua dei comandi, più la forma al femminile per i
    participi («coperta da», che è come si parla di una US). La direzione è
    quella del passo: `$unit → $item` è `forward`, `$item → $unit` è `swap`,
    un arco simmetrico è `symmetric`.
    """
    out: Dict[str, Tuple[str, str, str]] = {}
    if scheda.recipe is None:
        return out
    for fid, entry in (scheda.recipe.get("fields") or {}).items():
        if entry.get("verdict") != "edge":
            continue
        kind = ((entry.get("resolve") or {}).get("$item") or {}).get("find", {}).get("kind")
        if kind != "stratigraphic_unit":
            continue
        emit = entry["steps"][0]["emit"]
        direction = ("symmetric" if (entry.get("edge") or {}).get("symmetric")
                     else "forward" if emit["source"] == "$unit" else "swap")
        label = str(((scheda.field(fid).get("labels") or {}).get(lang)) or "").strip().lower()
        if not label:
            continue
        # il nome passa per il datamodel: una ricetta compilata prima del
        # 2026-10-21 può ancora dire una grafia vecchia, e la voce scrive la
        # canonica
        edge_type, direction = canonical_relation(emit["edge_type"], direction)
        for phrase in _variants(label):
            out[phrase] = (edge_type, direction, fid)
    return out


# ── le relazioni stratigrafiche che il DATAMODEL dichiara ────────────────────
#
# Decisione di E.D. (2026-10-21): la voce accetta i rapporti della ricetta PIÙ
# le relazioni che s3Dgraphy dichiara fra unità stratigrafiche, anche senza
# casella. L'elenco si LEGGE dal datamodel delle connessioni (chi le dichiara,
# fra quali classi, simmetriche o no, quale inverso, quale grafia vecchia): qui
# non c'è nessun elenco di relazioni. Le parole con cui si dicono sono del
# frasario del nodo (`tools.RELATION_WORDS`), perché il datamodel non ne ha in
# nessuna lingua di comando.

#: il segno dei campi sintetici dei rapporti senza casella nel `Plan`
RELATION_PREFIX = "~relazione:"

#: la classe da cui discendono le unità stratigrafiche, nel datamodel
STRATIGRAPHIC_CLASS = "StratigraphicNode"


def _connections():
    from s3dgraphy.edges.connections_loader import get_connections_datamodel
    return get_connections_datamodel()


def spellings(edge_type: str) -> frozenset:
    """Ogni nome che il datamodel accetta per questa relazione (lettura)."""
    return _connections().spellings(edge_type)


def canonical_relation(edge_type: str, direction: str = "forward") -> Tuple[str, str]:
    """`(nome canonico, direzione)` per un nome che il datamodel accetta.

    `normalize_edge_name` porta una grafia vecchia alla canonica (stessa
    direzione) e un inverso al canonico: allora i capi si scambiano. Un arco
    simmetrico è `symmetric` qualunque cosa si sia detto. Un nome che il
    datamodel non ha è un errore, non un arco.
    """
    dm = _connections()
    canonical = dm.normalize_edge_name(edge_type, prefer_canonical=True)
    if canonical is None:
        raise OperazioniError(f"«{edge_type}» non è un arco del datamodel "
                              f"delle connessioni {dm.get_version()}")
    if dm.is_symmetric(canonical):
        return canonical, "symmetric"
    same_way = edge_type == canonical or edge_type in dm.spellings(canonical)
    flipped = {"forward": "swap", "swap": "forward"}.get(direction, direction)
    return canonical, (direction if same_way else flipped)


def datamodel_relations() -> Dict[str, Dict[str, Any]]:
    """Le relazioni canoniche che il datamodel dichiara FRA UNITÀ STRATIGRAFICHE.

    `nome → {symmetric, reverse, physical, label}`. `physical` è ciò che il
    datamodel stesso distingue: la famiglia AP11 (`AP11_has_physical_relation_to`:
    il contatto — copre, taglia, si lega…) o no (`is_after`, `has_same_time`,
    `changed_from`, ciascuna con la sua mappatura). Non si inventa una terza
    etichetta: COPRE è `overlies` (fisica) e POSTERIORE A è `is_after` (no),
    due righe, mai una.
    """
    dm = _connections()
    out: Dict[str, Dict[str, Any]] = {}
    for name in sorted(dm.get_all_edge_names()):
        if not dm.is_canonical(name):
            continue                      # un inverso o una grafia vecchia
        definition = dm.get_edge_definition(name) or {}
        if definition.get("deprecated") or definition.get("spelling_of"):
            continue
        if not (STRATIGRAPHIC_CLASS in (dm.get_allowed_sources(name) or [])
                and STRATIGRAPHIC_CLASS in (dm.get_allowed_targets(name) or [])):
            continue
        mapping = definition.get("mapping") or {}
        physical = str(mapping.get("extension_mapping") or "").startswith("AP11")
        out[name] = {"symmetric": dm.is_symmetric(name),
                     "reverse": dm.get_reverse_name(name) if not dm.is_symmetric(name) else None,
                     "physical": physical,
                     "label": definition.get("label")}
    return out


def datamodel_relation_phrases(words: Dict[str, str]) -> Dict[str, Tuple[str, str, str]]:
    """`frase → (edge_type, direzione, "")` per le parole del frasario che
    nominano una relazione del datamodel fra unità stratigrafiche (o il suo
    inverso). Una parola legata a un nome che il datamodel non dichiara
    così non entra: la sua assenza la dice `unsayable_words`."""
    declared = datamodel_relations()
    out: Dict[str, Tuple[str, str, str]] = {}
    for phrase, name in words.items():
        try:
            edge_type, direction = canonical_relation(name)
        except OperazioniError:
            continue
        if edge_type not in declared:
            continue
        for variant in _variants(phrase.strip().lower()):
            out[variant] = (edge_type, direction, "")
    return out


def unsayable_words(words: Dict[str, str]) -> Dict[str, str]:
    """Le parole del frasario che NON nominano una relazione stratigrafica
    del datamodel — e perché."""
    declared = datamodel_relations()
    out: Dict[str, str] = {}
    for phrase, name in words.items():
        try:
            edge_type, _ = canonical_relation(name)
        except OperazioniError as wrong:
            out[phrase] = str(wrong)
            continue
        if edge_type not in declared:
            out[phrase] = (f"«{edge_type}» non è dichiarato fra "
                           f"{STRATIGRAPHIC_CLASS} e {STRATIGRAPHIC_CLASS}")
    return out


def _relation_entry(scheda: Scheda, edge_type: str, direction: str) -> Dict[str, Any]:
    """La voce di ricetta di un rapporto senza casella: una casella di rapporto
    VERA della stessa ricetta (fra unità stratigrafiche), con il nome e i capi
    cambiati. La forma resta quella che il compilatore scrive (SPEC §9.3), e
    il rapporto passa per lo stesso ramo di `_expand`: nessuna seconda via e
    nessun passo scritto qui."""
    import copy

    for entry in ((scheda.recipe or {}).get("fields") or {}).values():
        find = ((entry.get("resolve") or {}).get("$item") or {}).get("find") or {}
        if entry.get("verdict") == "edge" and find.get("kind") == "stratigraphic_unit":
            made = copy.deepcopy(entry)
            emit = made["steps"][0]["emit"]
            emit["edge_type"] = edge_type
            emit["source"], emit["target"] = (("$item", "$unit") if direction == "swap"
                                              else ("$unit", "$item"))
            made["edge"] = {"symmetric": direction == "symmetric"}
            return made
    raise OperazioniError(
        f"«{scheda.id}» non ha nessuna casella di rapporto fra unità: non so in "
        f"che forma la sua ricetta scriva un rapporto")


def _variants(label: str) -> Iterable[str]:
    yield label
    # «coperto da» → «coperta da»: una US è femminile
    match = re.fullmatch(r"(.*\w)o (da|a)", label)
    if match:
        yield f"{match.group(1)}a {match.group(2)}"
