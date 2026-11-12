"""AGGIUNGERE IL NUMERO A UN'UNITÀ CHE NON LO HA — l'app propone, chi scava
sceglie (decisione di E.D., 12 novembre 2026; MICRO dev104 e il numero
proposto, 15 novembre 2026).

Una US che si chiama «capitello» non ha numero. In EM il numero sta nel NOME
(l'identificatore, P1 is identified by): niente `data.us`. Quando chi scava
aggiunge il numero, il nome cambia, e l'app propone come:

* ``sposta`` (preselezionata): il nome diventa «US 12» e «capitello» passa
  nella descrizione — in testa, se una descrizione c'è già;
* ``accoda``: il nome diventa «US 12 capitello»;
* ``solo``: il nome diventa «US 12» e la parola non si sposta (si perde dal
  nome; resta nella cronologia della stanza e nel verbale dell'atto);
* ``libero``: il nome che chi scava scrive — purché porti il numero, perché è
  dal nome che il numero si legge.

Il PREFISSO («US», «USM», «USN», «USVs»…) viene dal TIPO dell'unità: il
`node_type`, e per una US di genere muratura o rivestimento il suo codice
(s3Dgraphy `unit_code`: USM, USR, o quello con cui è entrata). Così il nome
nuovo si rilegge con la stessa regola (`tools.number_of_node`).

Un numero già usato NELLA STESSA AREA (la chiave tipo + numero + area,
`tools.unit_key`) è un conflitto: si dice, e non si salva niente. Un'unità che
un numero lo ha già non lo cambia (`NumberNotChanged`, la regola di E.D.).

Questo modulo è PURO: legge la sezione e restituisce le operazioni. Le manda
`tools.number_unit`, firmate da chi scrive, con il verbale D7 che dice il nome
di prima.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: le quattro scelte, nell'ordine in cui il pannello le mostra
CHOICES = ("sposta", "accoda", "solo", "libero")
#: quella preselezionata
DEFAULT_CHOICE = "sposta"


class NumeroError(ValueError):
    """Un numero che non si aggiunge: la frase è il messaggio."""


class NumberTaken(NumeroError):
    """Il numero, con quel tipo, è già di un'altra unità nella stessa area."""

    def __init__(self, label: str, others: List[Dict[str, Any]]) -> None:
        self.others = others
        names = ", ".join(f"«{o.get('name') or o.get('id')}»" for o in others)
        super().__init__(
            f"{label} c'è già in questa area ({names}): due unità con lo stesso "
            f"numero sarebbero un conflitto. Non salvo: scegli un altro numero.")


@dataclass
class NumberPlan:
    unit_id: str
    number: str
    code: str
    choice: str
    before: str
    name: str
    description_before: str
    description: str
    ops: List[Dict[str, Any]] = field(default_factory=list)


def unit_code_of(node: Dict[str, Any]) -> str:
    """Il PREFISSO del nome dal tipo dell'unità: `node_type`; per una US di un
    genere (muratura, rivestimento) il codice del genere (USM, USR, o il codice
    con cui è entrata, `data.source_code`)."""
    from s3dgraphy.nodes.stratigraphic_node import (KIND_DEFAULT_CODE,
                                                     KIND_OF_CODE, SOURCE_CODE,
                                                     STRATIGRAPHIC_KIND)
    node = node or {}
    ntype = str(node.get("node_type") or "").strip() or "US"
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if ntype == "US":
        kind = data.get(STRATIGRAPHIC_KIND)
        if kind in KIND_DEFAULT_CODE:
            code = data.get(SOURCE_CODE)
            return code if code and KIND_OF_CODE.get(code) == kind else KIND_DEFAULT_CODE[kind]
    return ntype


def clean_number(said: Any) -> str:
    """Il numero com'è stato scritto, ridotto: «12», «12a»; il prefisso del
    tipo davanti («US 12») si toglie. `""` se non è un numero d'unità."""
    from .tools import _UNIT_NUMBER
    text = str(said if said is not None else "").strip()
    m = re.match(r"^[^\W\d_]*[\s_-]*(?P<n>\d.*)$", text, re.UNICODE)
    text = m.group("n").strip() if m else text
    return text if _UNIT_NUMBER.fullmatch(text) else ""


def _description_with(word: str, before: str) -> str:
    """La parola IN TESTA alla descrizione; la descrizione se non c'era."""
    word, before = word.strip(), (before or "").strip()
    if not before:
        return word
    if before.lower().startswith(word.lower()):
        return before                                  # c'è già, in testa
    sep = " " if word[-1:] in ".!?;:" else ". "
    return f"{word}{sep}{before}"


def choices(node: Dict[str, Any], number: str) -> List[Dict[str, str]]:
    """Le proposte per `node` con `number`: nome e descrizione dopo, per
    ciascuna delle tre scelte a un clic (la quarta, il nome libero, la scrive
    chi scava)."""
    number = clean_number(number)
    code = unit_code_of(node)
    word = str((node or {}).get("name") or "").strip()
    before = str((node or {}).get("description") or "").strip()
    base = f"{code} {number}"
    out = [{"choice": "sposta", "name": base,
            "description": _description_with(word, before) if word else before},
           {"choice": "accoda", "name": f"{base} {word}".strip(), "description": before},
           {"choice": "solo", "name": base, "description": before}]
    return out


def _context(section: Optional[Dict[str, Any]]):
    from .operazioni import _Context
    return _Context(section)


def _unit(ctx, node_id: str) -> Dict[str, Any]:
    from .operazioni import _is_unit
    unit = ctx.nodes.get(node_id)
    data = (unit or {}).get("data") if isinstance((unit or {}).get("data"), dict) else {}
    if unit is None or not _is_unit(unit) or data.get("removed"):
        raise NumeroError(f"L'unità «{node_id}» non è in questo grafo.")
    return unit


def taken_by(ctx, unit: Dict[str, Any], new_name: str) -> List[Dict[str, Any]]:
    """Le ALTRE unità con la chiave che `unit` avrebbe col nome nuovo (tipo,
    numero, area — l'area dal suo luogo, o dal prefisso del nome)."""
    from .operazioni import _is_unit
    from .tools import area_of_unit, unit_key

    after = {**unit, "name": new_name}
    key = unit_key(after, area_of_unit(after, ctx.nodes, ctx.edges)[0])
    if not key[1]:
        return []
    out = []
    for node in ctx.nodes.values():
        if node is unit or str(node.get("id")) == str(unit.get("id")) or not _is_unit(node):
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        if data.get("removed"):
            continue
        if unit_key(node, area_of_unit(node, ctx.nodes, ctx.edges)[0]) == key:
            out.append(node)
    return out


def proposal(section: Optional[Dict[str, Any]], node_id: str,
             number: str) -> Dict[str, Any]:
    """Quello che il pannello mostra: il prefisso, le scelte, e se il numero è
    già preso nella stessa area (allora non si salva)."""
    from .tools import number_of_node
    ctx = _context(section)
    unit = _unit(ctx, node_id)
    clean = clean_number(number)
    out: Dict[str, Any] = {"node": node_id, "name": str(unit.get("name") or ""),
                           "description": str(unit.get("description") or ""),
                           "code": unit_code_of(unit), "number": clean,
                           "own": number_of_node(unit), "default": DEFAULT_CHOICE,
                           "choices": [], "taken": []}
    if clean:
        out["choices"] = choices(unit, clean)
        out["taken"] = [{"id": str(n.get("id")), "name": str(n.get("name") or "")}
                        for n in taken_by(ctx, unit, out["choices"][0]["name"])]
    return out


def plan_number(section: Optional[Dict[str, Any]], node_id: str, number: str,
                choice: str, *, ts: str, name: str = "") -> NumberPlan:
    """Le operazioni che danno il numero a `node_id` con la scelta `choice`:
    `update_field name` (e `description` se cambia). Rifiuta: un'unità che un
    numero lo ha già, un numero che non è un numero, un nome libero che non
    porta il numero, un numero già preso nella stessa area."""
    from s3dgraphy import api

    from .operazioni import NumberNotChanged
    from .tools import number_of_node, unit_key

    ctx = _context(section)
    unit = _unit(ctx, node_id)
    before = str(unit.get("name") or "")
    own = number_of_node(unit)
    if own:
        raise NumberNotChanged(
            f"«{before or node_id}» ha già il numero {own}: un numero non si "
            f"cambia.")
    choice = (choice or DEFAULT_CHOICE).strip()
    if choice not in CHOICES:
        raise NumeroError(f"«{choice}» non è una delle scelte ({', '.join(CHOICES)}).")
    desc_before = str(unit.get("description") or "")
    code = unit_code_of(unit)
    if choice == "libero":
        new_name = re.sub(r"\s+", " ", str(name or "")).strip()
        read = number_of_node({"id": node_id, "name": new_name})
        if not new_name or not read:
            raise NumeroError(
                f"«{new_name}» non porta un numero che si legga: il numero di "
                f"un'unità sta nel suo nome — per esempio «{code} 12 …».")
        asked = clean_number(number)
        if asked and asked != read:
            raise NumeroError(
                f"Il nome «{new_name}» dice il numero {read}, non {asked}.")
        number, new_desc = read, desc_before
        code = unit_key({"id": node_id, "name": new_name})[0] or code
    else:
        number = clean_number(number)
        if not number:
            raise NumeroError("Scrivi il numero: «12», «12a», «1001.2».")
        picked = next(c for c in choices(unit, number) if c["choice"] == choice)
        new_name, new_desc = picked["name"], picked["description"]
    others = taken_by(ctx, unit, new_name)
    if others:
        raise NumberTaken(f"{code} {number}", others)
    made = NumberPlan(unit_id=node_id, number=number, code=code, choice=choice,
                      before=before, name=new_name, description_before=desc_before,
                      description=new_desc)
    made.ops.append(api.make_op("update_field", node_id=node_id, field="name",
                                value=new_name, ts=ts))
    if new_desc != desc_before:
        made.ops.append(api.make_op("update_field", node_id=node_id,
                                    field="description", value=new_desc, ts=ts))
    return made
