"""«TRADUCI» — la traduzione AI dalla stanza, accanto all'originale e mai sopra.

E.D., 1 ottobre 2026 (brain: *La lingua dei dati*, «Le traduzioni»): l'originale
resta una stringa nel suo campo, nella lingua in cui è stato scritto; ogni
traduzione è un nodo, `TranslationNode` (crm:E33), raggiunto con
`has_translation` (crm:P73), firmato (`has_author`), con `data.method`. Una
traduzione fatta da un modello porta `data.ai_assisted` e **aspetta una
persona** (`s3dgraphy.api.to_review`, ragione `ai`) finché qualcuno non la firma
(`api.verify`).

## CHE COSA FA QUESTO MODULO, E CHE COSA NO

* Non decide niente sulla traduzione: chiama `s3dgraphy.api.add_translation`
  su una copia del grafo della stanza, e legge che cosa è nato — il nodo, i
  suoi archi, e se mancavano l'autore e il modello — per farne le stesse
  operazioni CRDT che un `add_node` / `add_edge` sono. Così l'id (uuid5 di ciò
  che la traduzione È), `source_digest`, `from_lang`, `ai_assisted` e il timbro
  sono quelli di s3Dgraphy e di nessun altro.
* Non scrive: costruisce la lista. La manda `tools.translate_text` con
  `graph_writer.send`, la sola via al grafo (`tests/test_one_write_path.py`).
* Non apre niente verso fuori: il modello lo chiama `tools.py` attraverso il
  traduttore che `main.py` gli passa (`intent.py`, che è già dichiarato).

## IL TESTO DI UNA CASELLA

Una casella di scheda non è un campo del grafo: `descrizione` è la
`description` dell'unità, `osservazioni` è la `description` di una
`PropertyNode` coniata dal generatore (segnata `data.scheda = {field, of}`).
`address_of_box` legge la ricetta per sapere quale dei due, e trova il nodo
coniato col segno — lo stesso ritorno di `operazioni.values_from_graph`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Tuple

#: il metodo di ogni traduzione che nasce da qui: la fa il modello del nodo
METHOD = "ai"


class TraduzioneError(ValueError):
    """Una traduzione che non si può fare, detta con una frase."""


# ── il grafo della stanza, letto da s3Dgraphy ───────────────────────────────

def _graph(section: Dict[str, Any]):
    """Una copia del grafo della stanza, solo ciò che è vivo (le lapidi le vede
    il merge, non una lettura)."""
    from s3dgraphy import api
    from s3dgraphy.crdt import live_edges, live_nodes

    live = {"nodes": copy.deepcopy(live_nodes(section)),
            "edges": copy.deepcopy(live_edges(section))}
    graph, _warnings = api.load_emjson({"graphs": {"stanza": live}})
    return graph


def source_of(section: Dict[str, Any], node_id: str, field: str) -> Dict[str, Any]:
    """Il testo da tradurre e la sua lingua: `{text, from_lang, field}`.

    La lingua viene da `data.lang` del nodo, poi da quella di lavoro dello
    studio — la cascata di s3Dgraphy — e se nessuno la dichiara è `""`: non si
    indovina, e `add_translation` lo rifiuterà con la sua frase."""
    from s3dgraphy.language import node_language, working_language
    from s3dgraphy.translation import TranslationError, field_text, normalize_field

    try:
        f = normalize_field(field)
    except TranslationError as wrong:
        raise TraduzioneError(str(wrong)) from None
    graph = _graph(section)
    node = graph.find_node_by_id(node_id)
    if node is None:
        raise TraduzioneError(f"«{node_id}» non è in questo grafo.")
    text = field_text(node, f)
    if not text or not text.strip():
        raise TraduzioneError(
            f"«{node_id}» non ha testo in {f}: non c'è niente da tradurre.")
    return {"text": text, "field": f,
            "from_lang": node_language(node) or working_language(graph) or ""}


def address_of_box(scheda, section: Dict[str, Any], unit_id: str,
                   box: str) -> Tuple[str, str]:
    """Dove sta nel grafo il testo di una casella: `(node_id, field)`."""
    from .operazioni import MARK

    entry = ((scheda.recipe or {}).get("fields") or {}).get(box)
    if not entry:
        raise TraduzioneError(
            f"«{scheda.id}» non ha una casella «{box}» con una ricetta.")
    for step in entry.get("steps") or []:
        emit = step.get("emit") or {}
        if (emit.get("op") == "update_field" and emit.get("node_id") == "$unit"
                and emit.get("value") == "$value"):
            return unit_id, str(emit.get("field"))
        node = emit.get("node") or {}
        if emit.get("op") == "add_node" and node.get("description") == "$value":
            for candidate in section.get("nodes") or []:
                mark = (candidate.get("data") or {}).get(MARK)
                if (isinstance(mark, dict) and mark.get("of") == unit_id
                        and mark.get("field") == box and "index" not in mark):
                    return str(candidate.get("id")), "description"
            raise TraduzioneError(
                f"la casella «{box}» dell'unità «{unit_id}» è vuota: non c'è "
                f"niente da tradurre.")
    raise TraduzioneError(
        f"la casella «{box}» non è un testo (è {entry.get('verdict')}): si "
        f"traduce un testo, non un valore di vocabolario o un rapporto.")


# ── chi firma: la persona, e il modello che l'ha aiutata ────────────────────

def _orcid(value: Optional[str]) -> str:
    from s3dgraphy.editorial import normalize_orcid
    return normalize_orcid(value) or ""


def find_author(section: Dict[str, Any], orcid: str) -> Optional[str]:
    """L'`AuthorNode` della stanza con questo ORCID iD, se c'è: una persona è
    UN nodo, e la seconda copia sarebbe una seconda persona."""
    wanted = _orcid(orcid)
    if not wanted:
        return None
    for node in section.get("nodes") or []:
        if (node.get("node_type") == "author"
                and _orcid((node.get("data") or {}).get("orcid")) == wanted):
            return str(node.get("id"))
    return None


def find_ai(section: Dict[str, Any], model: str) -> Optional[str]:
    """L'`AuthorAINode` di questo modello, se la stanza ce l'ha già."""
    for node in section.get("nodes") or []:
        if (node.get("node_type") == "author_ai"
                and str((node.get("data") or {}).get("model") or "") == model):
            return str(node.get("id"))
    return None


# ── il piano ────────────────────────────────────────────────────────────────

@dataclass
class Piano:
    """Le operazioni di una traduzione, e che cosa dicono."""

    translation_id: str
    of: str
    field: str
    lang: str
    from_lang: str
    #: True quando la stanza ha già questa stessa traduzione (stesso testo
    #: d'origine, lingua, persona, metodo): l'id è lo stesso e non nasce niente
    already: bool = False
    #: i nodi che mancavano e nascono con lei (la persona, il modello)
    minted: List[str] = dc_field(default_factory=list)
    ops: List[Dict[str, Any]] = dc_field(default_factory=list)


def plan_translation(section: Dict[str, Any], node_id: str, field: str,
                     lang: str, text: str, *, orcid: str, model: str,
                     ts: str) -> Piano:
    """La traduzione AI di `field` di `node_id` in `lang`, come operazioni.

    `orcid` è chi l'ha chiesta e la consegna (`has_author`: «for an AI
    translation it is the person who accepted it», `add_translation`), `model`
    il modello del nodo che l'ha composta (`ai_assisted.by` → `AuthorAINode`).
    L'originale non compare nella lista: nessuna operazione lo tocca.
    """
    from s3dgraphy import api
    from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
    from s3dgraphy.translation import TranslationError

    from .contract import stable_id

    person = _orcid(orcid)
    if not person:
        raise TraduzioneError(
            "una traduzione è firmata da chi la chiede, con il suo ORCID iD: "
            "questo nodo non sa chi sei.")
    if not model:
        raise TraduzioneError("una traduzione AI nomina il modello che l'ha fatta.")

    graph = _graph(section)
    before_nodes = {n.node_id for n in graph.nodes}
    before_edges = {e.edge_id for e in graph.edges}
    minted: List[str] = []

    by = find_author(section, person)
    if by is None:
        by = stable_id("author", person)
        graph.add_node(AuthorNode(by, name=person, orcid=person))
        minted.append(by)
    ai = find_ai(section, model)
    if ai is None:
        ai = stable_id("author_ai", model)
        graph.add_node(AuthorAINode(ai, name=model, model=model))
        minted.append(ai)

    try:
        made = api.add_translation(graph, node_id, field, lang, text, by=by,
                                   method=METHOD, ai=ai, model=model, at=ts)
    except TranslationError as wrong:
        raise TraduzioneError(str(wrong)) from None

    already = made.node_id in before_nodes
    data = made.data or {}
    out = Piano(translation_id=made.node_id, of=node_id,
                field=str(data.get("field") or field), lang=str(data.get("lang") or lang),
                from_lang=str(data.get("from_lang") or ""), already=already)
    if already:
        return out

    born = api.graph_to_emjson(graph)["graph"]
    out.minted = [m for m in minted]
    for node in born.get("nodes") or []:
        if node.get("id") in before_nodes:
            continue
        out.ops.append(api.make_op("add_node", id=node["id"], node=node, ts=ts))
    for edge in born.get("edges") or []:
        if edge.get("id") in before_edges:
            continue
        out.ops.append(api.make_op(
            "add_edge", id=edge["id"], source=edge["source"],
            target=edge["target"], edge_type=edge["edge_type"], ts=ts))
    return out
