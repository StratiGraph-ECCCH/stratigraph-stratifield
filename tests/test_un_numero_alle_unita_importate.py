"""Un numero alle unità importate — MICRO del 15 novembre 2026.

Nella stanza di prova 45 unità stratigrafiche vere (`1.1.US1`, `1.US2`,
`1.USM12`, `1.SF300`…) non avevano un numero: l'importer PyArchInit le nomina
col suo template e dà loro l'uuid della riga. Ora l'importer (s3Dgraphy
`importer/unit_numbers`) scrive il numero in `data.us`, accanto a
`data.unita_tipo`, e lascia il nome com'era. Qui:

1. il numero di un nodo si legge anche da `data.us` (`tools.number_of_node`);
2. l'elenco delle unità lo dà, e un numero di due unità è un CONFLITTO
   (`conflict` sull'una e sull'altra);
3. il servizio trova per numero l'unità importata (la scheda si salva SU DI
   LEI, non su un `US2` nuovo) e rifiuta di scegliere fra due (`UnitConflict`);
4. «Vai alla US…» (`widgets.unitFor`) trova anche dal nome originale, e un
   numero doppio torna come conflitto, non come la prima unità.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app import operazioni as O                                  # noqa: E402
from app import scheda as S                                      # noqa: E402
from app.tools import number_of_node                             # noqa: E402
from app.writer import units_of                                  # noqa: E402
from sorgenti import HA_NODE, esegui                             # noqa: E402

needs_node = pytest.mark.skipif(not HA_NODE, reason="node non c'è")
TS = "2026-11-15T10:00:00Z"
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def imported(nid, name, us=None, code="US"):
    """Un'unità come la scrive l'importer PyArchInit corretto."""
    node = {"id": nid, "node_type": "US", "name": name,
            "data": {"label": "US (or SU)"}}
    if us is not None:
        node["data"].update({"us": us, "unita_tipo": code})
    return node


ROOM = {"graphs": {"scavo": {"nodes": [
    {"id": "US3014", "node_type": "US", "name": "US 3014 — Area 3000 (Leopoli-Cencelle)"},
    imported("019f-a", "1.1.US1", "1"),
    imported("019f-b", "1.US2", "2"),
    imported("019f-c", "1.USM12", "12", "USM"),
    imported("019f-d", "1.SF300", "300", "SF"),
    imported("019f-e", "1.Combinar900"),                # non è un'unità: niente numero
], "edges": []}}}


def test_the_number_of_a_node_is_read_from_data_us_too():
    assert number_of_node({"id": "US3014", "name": "US 3014 — Area"}) == "3014"
    assert number_of_node({"id": "x", "name": "US 3030"}) == "3030"
    assert number_of_node(imported("u", "1.USM12", "12", "USM")) == "12"
    assert number_of_node(imported("u", "1.1.US1")) == ""          # non si indovina qui
    assert number_of_node({"id": "u", "data": {"us": "Strato"}}) == ""


def test_the_list_numbers_the_imported_units_and_keeps_their_name():
    units = {u["id"]: u for u in units_of(ROOM)}
    assert units["019f-a"]["number"] == "1" and units["019f-a"]["name"] == "1.1.US1"
    assert units["019f-c"]["number"] == "12"
    assert units["019f-d"]["number"] == "300"
    assert units["019f-e"]["number"] == ""
    assert all(u["conflict"] == 0 for u in units.values())


def _twice():
    room = json.loads(json.dumps(ROOM))
    room["graphs"]["scavo"]["nodes"].append(imported("019f-z", "2.US2", "2"))
    return room


def test_a_number_of_two_units_is_a_conflict_on_both():
    units = {u["id"]: u for u in units_of(_twice())}
    assert units["019f-b"]["conflict"] == 2 and units["019f-z"]["conflict"] == 2
    assert units["019f-a"]["conflict"] == 0


def test_the_service_finds_the_imported_unit_and_refuses_to_choose():
    section = ROOM["graphs"]["scavo"]
    assert O._find_unit(O._Context(section), "12")["id"] == "019f-c"
    with pytest.raises(O.UnitConflict) as doppio:
        O._find_unit(O._Context(_twice()["graphs"]["scavo"]), "2")
    said = str(doppio.value)
    assert "1.US2" in said and "2.US2" in said and "conflitto" in said
    # una coniata qui e una importata con lo stesso numero: conflitto anche lei
    room = json.loads(json.dumps(section))
    room["nodes"].append(imported("019f-y", "1.US3014", "3014"))
    with pytest.raises(O.UnitConflict):
        O._find_unit(O._Context(room), "3014")


def test_a_sheet_saved_by_number_writes_on_the_imported_unit():
    scheda = S.find("iccd-us-2021", {})
    if scheda is None or scheda.recipe is None:
        pytest.skip("la scheda ICCD compilata non è qui")
    section = json.loads(json.dumps(ROOM["graphs"]["scavo"]))
    plan = O.plan(scheda, {"colore": "bruno"}, number="2", section=section, ts=TS)
    assert plan.unit_id == "019f-b"                    # non un `US2` nuovo
    assert not any(op.get("op") == "add_node" and (op.get("node") or {}).get("id") == "US2"
                   for op in plan.ops)
    with pytest.raises(O.OperazioniError):             # due unità «2»: non sceglie
        O.plan(scheda, {"colore": "bruno"}, number="2",
               section=_twice()["graphs"]["scavo"], ts=TS)


@needs_node
def test_go_to_unit_finds_by_original_name_and_says_a_conflict():
    units = [u for u in units_of(_twice())]
    got = esegui(
        "import { unitFor, unitLabel } from './web/widgets.js';"
        f"const u = {json.dumps(units)};"
        "const id = (x) => x && (x.conflict && x.conflict.map ? x.conflict.map((y) => y.id) : x.id);"
        "console.log(JSON.stringify(["
        " id(unitFor('12', '12', u)),"
        " id(unitFor('1.USM12', '1.USM12', u)),"
        " id(unitFor('1.combinar900', '1.combinar900', u)),"
        " id(unitFor('2', '2', u)),"
        " id(unitFor('1.US2', '1.US2', u)),"
        " unitFor('77', '77', u),"
        " unitLabel(u.find((x) => x.id === '019f-b'), 'US '),"
        " unitLabel(u.find((x) => x.id === '019f-c'), 'US '),"
        " unitLabel(u.find((x) => x.id === '019f-e'), 'US ')]));")
    assert got == ["019f-c", "019f-c", "019f-e", ["019f-b", "019f-z"], "019f-b", None,
                   "US 2 ⚠ 1.US2", "US 12", "1.Combinar900"]


def test_the_conflict_is_said_in_the_interface_languages_of_the_page():
    assert '"nav.conflict": "Il numero {n} è di {count} unità' in PAGE
    assert '"nav.conflict": "The number {n} belongs to {count} units' in PAGE
