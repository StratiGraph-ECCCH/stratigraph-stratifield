"""Il numero si legge dal nome — MICRO del 15 novembre 2026 (decisione di E.D.
del 12 novembre).

In EM l'identificatore di un'unità è il suo NOME (P1 is identified by). Il
numero non si copia in un'altra chiave: niente `data.us`, né scritto né letto.
Il nome che l'importer PyArchInit costruisce (`{area}.{settore}.{unita_tipo}{us}`
→ `1.US2`, `1.1.US1`) dice già tipo e numero; l'area lo rende unico. Qui:

1. `tools.number_of_node` legge il numero dall'id coniato, dal nome «US n» e
   dal nome composto dell'importer (la regola di s3Dgraphy `number_of_name`,
   e la sua copia uguale); `data.us` no;
2. l'area: il luogo `is_in_location` di livello area, altrimenti il prefisso
   del nome; l'unità importata si dice «US 2 · area 1» e si apre dal suo id;
3. un conflitto è lo stesso tipo + numero NELLA STESSA AREA: `1.US2` e `2.US2`
   non lo sono (ma il numero da solo non sceglie fra loro);
4. il servizio trova per numero l'unità importata e scrive SU DI LEI;
5. «Vai alla US…» (`widgets.unitFor`) trova per nome e per «US 2 · area 1».
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
from app import tools as T                                       # noqa: E402
from app.tools import number_of_node                             # noqa: E402
from app.writer import units_of                                  # noqa: E402
from sorgenti import HA_NODE, esegui                             # noqa: E402

needs_node = pytest.mark.skipif(not HA_NODE, reason="node non c'è")
TS = "2026-11-15T10:00:00Z"
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def imported(nid, name, **data):
    """Un'unità come la scrive l'importer PyArchInit: il nome del template,
    un uuid; nessun numero in un'altra chiave."""
    return {"id": nid, "node_type": "US", "name": name,
            "data": {"label": "US (or SU)", **data}}


AREA1 = {"id": "loc-a1", "node_type": "LocationNodeGroup", "name": "1",
         "data": {"level": "area"}}
SAGGIO = {"id": "loc-s2", "node_type": "LocationNodeGroup", "name": "II",
          "data": {"level": "saggio"}}


def _in(unit, place):
    return {"id": f"e-{unit}-{place}", "source": unit, "target": place,
            "edge_type": "is_in_location"}


ROOM = {"graphs": {"scavo": {"nodes": [
    {"id": "US3014", "node_type": "US", "name": "US 3014 — Area 3000 (Leopoli-Cencelle)"},
    AREA1, SAGGIO,
    imported("019f-a", "1.1.US1"),
    imported("019f-b", "1.US2"),
    imported("019f-c", "1.USM12"),
    imported("019f-d", "1.SF300"),
    imported("019f-e", "1.Combinar900"),                # non è un'unità
    imported("019f-f", "Strato di crollo"),             # un'unità senza numero nel nome
    # una stanza importata con s3Dgraphy dev103 porta ancora `data.us`: si ignora
    imported("019f-g", "1.US5", us="99", unita_tipo="US"),
], "edges": [_in("019f-a", "loc-a1"), _in("019f-a", "loc-s2"),
             _in("019f-b", "loc-a1"), _in("019f-c", "loc-a1")]}}}


# ── 1 · il numero dal nome ──────────────────────────────────────────────────

@pytest.mark.parametrize("node,number", [
    ({"id": "US3014", "name": "US 3014 — Area"}, "3014"),     # id coniato
    ({"id": "x", "name": "US 3030"}, "3030"),                 # nome di create_su
    (imported("u", "1.US2"), "2"),
    (imported("u", "1.1.US1"), "1"),
    (imported("u", "1.USM12"), "12"),
    (imported("u", "1.USVs102"), "102"),
    (imported("u", "1.Combinar900"), ""),                     # non è un'unità
    (imported("u", "1.Pippo4"), ""),                          # codice ignoto: non si indovina
    (imported("u", "Strato di crollo"), ""),
    (imported("u", "1.US5", us="99"), "5"),                   # `data.us` non si legge
    ({"id": "u", "name": "Strato", "data": {"us": "7"}}, ""),
])
def test_the_number_is_read_from_the_name(node, number):
    assert number_of_node(node) == number


@pytest.mark.parametrize("name", ["1.US2", "1.1.US1", "1.USM12", "1.usm3", "1.USVs102",
                                  "1.USVn104", "A.USM-10", "1.SF300", "1.Combinar900",
                                  "1.DOC4001", "1.CON500", "1.property800", "1.Pippo4",
                                  "1.", "D.01.03"])
def test_the_pinned_copy_is_the_s3dgraphy_rule(name):
    try:
        from s3dgraphy.importer.unit_numbers import number_of_name
    except Exception:                                      # noqa: BLE001
        pytest.skip("s3Dgraphy senza importer/unit_numbers")
    want, got = number_of_name(name), T._number_of_name_pinned(name)
    assert got["status"] == want["status"]
    if want["status"] == "numbered":
        assert (got["number"], got["code"]) == (want["number"], want["code"])


# ── 2 · l'area e come si dice ───────────────────────────────────────────────

def test_the_list_says_number_area_and_opens_by_id():
    units = {u["id"]: u for u in units_of(ROOM)}
    a, b, g = units["019f-a"], units["019f-b"], units["019f-g"]
    assert (a["number"], a["label"], a["area_from"]) == ("1", "US 1 · area 1", "luogo")
    assert b["label"] == "US 2 · area 1" and b["by_id"] is True
    assert units["019f-c"]["label"] == "USM 12 · area 1"
    # senza luogo: l'area dal prefisso del nome
    assert (g["number"], g["label"], g["area_from"]) == ("5", "US 5 · area 1", "nome")
    assert units["019f-d"]["key"] == ["SF", "300", "1"]
    # una coniata qui si dice come prima, e si apre per numero
    assert units["US3014"]["label"] == "" and units["US3014"]["by_id"] is False
    assert units["019f-f"]["number"] == "" and "019f-e" not in units
    assert all(u["conflict"] == 0 for u in units.values())


# ── 3 · il conflitto è nella stessa area ────────────────────────────────────

def _with(*nodes, edges=()):
    room = json.loads(json.dumps(ROOM))
    room["graphs"]["scavo"]["nodes"] += list(nodes)
    room["graphs"]["scavo"]["edges"] += list(edges)
    return room


def test_the_same_number_in_another_area_is_not_a_conflict():
    units = {u["id"]: u for u in units_of(_with(imported("019f-z", "2.US2")))}
    assert units["019f-b"]["conflict"] == 0 and units["019f-z"]["conflict"] == 0
    assert units["019f-z"]["label"] == "US 2 · area 2"


def test_the_same_type_and_number_in_the_same_area_is_a_conflict():
    units = {u["id"]: u for u in units_of(
        _with(imported("019f-z", "1.1.US2"), edges=[_in("019f-z", "loc-a1")]))}
    assert units["019f-b"]["conflict"] == 2 and units["019f-z"]["conflict"] == 2
    assert units["019f-a"]["conflict"] == 0
    # un altro tipo con lo stesso numero, nella stessa area: non lo è
    units = {u["id"]: u for u in units_of(_with(imported("019f-y", "1.USM2")))}
    assert units["019f-b"]["conflict"] == 0


def test_the_service_finds_the_imported_unit_and_never_chooses():
    section = ROOM["graphs"]["scavo"]
    assert O._find_unit(O._Context(section), "12")["id"] == "019f-c"
    # stessa area: il conflitto
    room = _with(imported("019f-z", "1.1.US2"), edges=[_in("019f-z", "loc-a1")])
    with pytest.raises(O.UnitConflict) as doppio:
        O._find_unit(O._Context(room["graphs"]["scavo"]), "2")
    assert "conflitto" in str(doppio.value)
    # aree diverse: non un conflitto, ma il numero da solo non sceglie
    room = _with(imported("019f-z", "2.US2"))
    with pytest.raises(O.NumberInManyAreas) as tanti:
        O._find_unit(O._Context(room["graphs"]["scavo"]), "2")
    assert "aree diverse" in str(tanti.value) and "conflitto" not in str(tanti.value)


# ── 4 · scrivere ────────────────────────────────────────────────────────────

def _scheda():
    scheda = S.find("iccd-us-2021", {})
    if scheda is None or scheda.recipe is None:
        pytest.skip("la scheda ICCD compilata non è qui")
    return scheda


def test_a_sheet_saved_by_number_writes_on_the_imported_unit_and_no_data_us():
    section = json.loads(json.dumps(ROOM["graphs"]["scavo"]))
    plan = O.plan(_scheda(), {"colore": "bruno"}, number="2", section=section, ts=TS)
    assert plan.unit_id == "019f-b"                    # non un `US2` nuovo
    assert not any(op.get("op") == "add_node" and (op.get("node") or {}).get("id") == "US2"
                   for op in plan.ops)
    assert not any(str(op.get("field") or "").startswith("data.us") for op in plan.ops)
    # dal suo id, col numero del suo nome: lo stesso
    plan = O.plan(_scheda(), {"colore": "bruno"}, number="2", node_id="019f-b",
                  section=section, ts=TS)
    assert plan.unit_id == "019f-b" and plan.number == "2"


# ── 5 · nell'interfaccia ────────────────────────────────────────────────────

@needs_node
def test_go_to_unit_finds_by_name_and_label_and_opens_by_id():
    units = units_of(_with(imported("019f-z", "2.US2")))
    got = esegui(
        "import { orderedUnits, unitFor, unitLabel } from './web/widgets.js';"
        "import { addressOf } from './web/indice.js';"
        f"const u = {json.dumps(units)};"
        "const id = (x) => x && (x.conflict && x.conflict.map ? x.conflict.map((y) => y.id) : x.id);"
        "console.log(JSON.stringify(["
        " id(unitFor('12', '12', u)),"
        " id(unitFor('1.USM12', '1.USM12', u)),"
        " id(unitFor('US 2 · area 2', 'US 2 · area 2', u)),"
        " unitFor('2', '2', u),"
        " id(unitFor('1.US2', '1.US2', u)),"
        " unitLabel(u.find((x) => x.id === '019f-b'), 'US '),"
        " unitLabel(u.find((x) => x.id === 'US3014'), 'US '),"
        " addressOf(u.find((x) => x.id === '019f-b')),"
        " addressOf(u.find((x) => x.id === 'US3014')),"
        " orderedUnits(u).filter((x) => x.number === '2').map((x) => x.id)]));")
    assert got == ["019f-c", "019f-c", "019f-z", None, "019f-b",
                   "US 2 · area 1", "US 3014",
                   {"node": "019f-b"}, {"us": "3014"}, ["019f-b", "019f-z"]]


def test_the_conflict_is_said_in_the_interface_languages_of_the_page():
    assert '"nav.conflict": "Il numero {n} è di {count} unità' in PAGE
    assert '"nav.conflict": "The number {n} belongs to {count} units' in PAGE
