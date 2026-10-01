"""«VERIFICA» — una persona firma, nella stanza, ciò che aspettava lei.

E.D., 1 ottobre 2026 (decisione 15 del referto dev27): la verifica si fa anche
nella stanza di StratiField, `POST /v1/verify` → `s3dgraphy.api.verify`, con
l'identità della stanza. Prima si faceva solo in EMStudio.

## CHE COSA FA QUESTO MODULO, E CHE COSA NO

* Non decide niente sulla verifica: chiama `api.verify` su una copia del grafo
  della stanza e trasforma in operazioni CRDT ciò che è cambiato —
  `data.validated_by` e `data.validated_at` sul nodo, e la persona
  (`AuthorNode`) se la stanza non l'aveva. Le regole sono di s3Dgraphy: un nodo
  che non aspetta nessuno è rifiutato, chi firma è una persona con un ORCID iD.
* **Il modo d'accesso non lo scrive StratiField**: lo timbra il relay del
  server dal token (s3Dgraphy `crdt.stamp_auth`, dev28). L'operazione su
  `data.validated_auth` parte senza valore, e il relay ci scrive quello vero;
  StratiField non dichiara come una persona era entrata.
* **Ciò che è da riallineare non si chiude con una firma** (regola della dev26,
  `ai_validation.needs_review`): una traduzione il cui originale è cambiato
  aspetta un testo nuovo, non un nome. StratiField non sa riallineare — la
  traduzione nuova la compone chi legge i due originali, ed è in EMStudio
  («↻ Riallinea») — quindi lo dice invece di fingere.
* Non scrive: costruisce la lista. La manda `tools.verify_node` con
  `graph_writer.send`, la sola via al grafo (`tests/test_one_write_path.py`).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional

from .traduzione import TraduzioneError, _graph, _orcid, find_author

#: the words of `needs_review`, and what a person reads beside them
REASON_AI = "ai"
REASON_REVIEW = "review_requested"
REASON_STALE = "stale"
REASON_TEXT = {REASON_AI: "AI", REASON_REVIEW: "revisione chiesta",
               REASON_STALE: "da riallineare"}

#: what StratiField says for a stale text: it does not realign
REALIGN_ELSEWHERE = "si riallinea in EMStudio"


class VerificaError(ValueError):
    """Una verifica che non si può fare, detta con una frase."""


def to_review(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ciò che nella stanza aspetta una persona, e perché (`api.to_review`),
    con le parole della scheda e il gesto che ciascuno ammette: «Verifica», o
    per un testo da riallineare `realign: "si riallinea in EMStudio"`."""
    from s3dgraphy import api
    rows = []
    for row in api.to_review(_graph(section)):
        reasons = list(row.get("reasons") or [])
        out = dict(row)
        out["reasons_text"] = [REASON_TEXT.get(r, r) for r in reasons]
        out["can_verify"] = REASON_STALE not in reasons
        if REASON_STALE in reasons:
            out["realign"] = REALIGN_ELSEWHERE
        rows.append(out)
    return rows


@dataclass
class Firma:
    """Le operazioni di una verifica, e che cosa dicono."""

    node_id: str
    by: str
    at: str
    reasons: List[str]
    minted: List[str] = dc_field(default_factory=list)
    ops: List[Dict[str, Any]] = dc_field(default_factory=list)


def plan_verify(section: Dict[str, Any], node_id: str, *, orcid: str, ts: str) -> Firma:
    """La firma di `orcid` su `node_id`, come operazioni.

    Rifiutata, con la frase: senza un iD (la stanza non sa chi sei); un nodo che
    non c'è; un nodo che non aspetta nessuno (s3Dgraphy); un testo da
    riallineare (si riallinea in EMStudio)."""
    from s3dgraphy import api
    from s3dgraphy.ai_validation import AIValidationError, needs_review
    from s3dgraphy.nodes.author_node import AuthorNode

    from .contract import stable_id

    person = _orcid(orcid)
    if not person:
        raise VerificaError("una verifica è una firma, con il tuo ORCID iD: "
                            "questa stanza non sa chi sei.")
    graph = _graph(section)
    node = graph.find_node_by_id(node_id)
    if node is None:
        raise VerificaError(f"«{node_id}» non è in questa stanza.")
    reasons = list(needs_review(node, graph) or [])
    if REASON_STALE in reasons:
        raise VerificaError(
            f"«{node_id}» è da riallineare: il suo originale è cambiato, e una "
            f"firma non lo chiude — {REALIGN_ELSEWHERE}.")
    before = copy.deepcopy(getattr(node, "data", {}) or {})
    before_nodes = {n.node_id for n in graph.nodes}
    minted: List[str] = []
    by = find_author(section, person)
    if by is None:
        by = stable_id("author", person)
        graph.add_node(AuthorNode(by, name=person, orcid=person))
        minted.append(by)
    try:
        signed = api.verify(graph, node_id, by, at=ts)
    except AIValidationError as wrong:
        raise VerificaError(str(wrong)) from None

    out = Firma(node_id=node_id, by=by, at=str(signed.get("validated_at") or ts),
                reasons=reasons, minted=minted)
    born = api.graph_to_emjson(graph)["graph"]
    from s3dgraphy.language import working_language
    study = working_language(graph) or "und"
    for n in born.get("nodes") or []:
        if n.get("id") in before_nodes:
            continue
        n = {**n, "data": {**(n.get("data") or {}), "lang": (n.get("data") or {}).get("lang") or study}}
        out.ops.append(api.make_op("add_node", id=n["id"], node=n, ts=ts))
    after = getattr(graph.find_node_by_id(node_id), "data", {}) or {}
    for key in ("validated_by", "validated_at"):
        if after.get(key) != before.get(key):
            out.ops.append(api.make_op("update_field", node_id=node_id,
                                       field=f"data.{key}", value=after.get(key), ts=ts))
    # the way in is the relay's to write, from the token: an empty value here
    out.ops.append(api.make_op("update_field", node_id=node_id,
                               field="data.validated_auth", value=None, ts=ts))
    return out


__all__ = ["Firma", "REALIGN_ELSEWHERE", "REASON_TEXT", "VerificaError",
           "plan_verify", "to_review", "TraduzioneError"]
