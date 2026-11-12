"""Aggiungere il numero a un'unità che non lo ha — MICRO dev104 e il numero
proposto (15 novembre 2026; decisione di E.D. del 12 novembre).

Una US che si chiama «capitello» non ha numero. Il numero in EM sta nel NOME:
l'app propone, chi scava sceglie (`app/numero.py`):

1. ``sposta`` (preselezionata): «US 12», e «capitello» in testa alla
   descrizione; ``accoda``: «US 12 capitello»; ``solo``: «US 12», la parola non
   si sposta; ``libero``: un nome scritto a mano, che porti il numero;
2. il prefisso dal TIPO dell'unità (US, USM per una muratura, USN…);
3. il nome nuovo si rilegge con la regola di sempre (`number_of_node`):
   «USM 12» e «US 12 capitello» compresi, «US capitello» no;
4. un numero già usato nella stessa area: niente si salva; in un'altra area sì;
5. dal servizio: un'operazione firmata, un verbale D7 col nome di prima, mai
   `data.us`; l'unità esce da «Senza numero»;
6. nella pagina: il comando accanto all'avviso, il pannello, le parole en/it.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import numero as N                                       # noqa: E402
from app.operazioni import NumberNotChanged                       # noqa: E402
from app.tools import number_of_node, unit_key                   # noqa: E402
from app.writer import LocalWriter                               # noqa: E402

TS = "2026-11-15T10:00:00.000Z"
ORCID = "0000-0002-1825-0097"
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
SHELL = (ROOT / "web" / "shell.js").read_text(encoding="utf-8")

AREA1 = {"id": "loc-a1", "node_type": "LocationNodeGroup", "name": "1",
         "data": {"level": "area"}}
AREA2 = {"id": "loc-a2", "node_type": "LocationNodeGroup", "name": "2",
         "data": {"level": "area"}}


def _in(unit, place):
    return {"id": f"e-{unit}-{place}", "source": unit, "target": place,
            "edge_type": "is_in_location"}


def _section(description=""):
    return {"nodes": [
        AREA1, AREA2,
        {"id": "cap", "node_type": "US", "name": "capitello",
         "description": description, "data": {}},
        {"id": "mur", "node_type": "US", "name": "muro est",
         "data": {"stratigraphic_kind": "masonry"}},
        {"id": "tag", "node_type": "USN", "name": "taglio", "data": {}},
        {"id": "u7", "node_type": "US", "name": "1.US7", "data": {}},
        {"id": "u8", "node_type": "US", "name": "2.US8", "data": {}},
    ], "edges": [_in("cap", "loc-a1"), _in("u7", "loc-a1"), _in("u8", "loc-a2")]}


def _ops(plan):
    return {(o["field"]): o["value"] for o in plan.ops if o["op"] == "update_field"}


# ── 1 · le scelte ───────────────────────────────────────────────────────────

def test_the_preselected_choice_moves_the_word_into_the_description():
    plan = N.plan_number(_section(), "cap", "12", "sposta", ts=TS)
    assert _ops(plan) == {"name": "US 12", "description": "capitello"}
    assert plan.before == "capitello"


def test_the_word_goes_at_the_head_of_a_description_already_there():
    plan = N.plan_number(_section("frammento in marmo"), "cap", "12", "sposta", ts=TS)
    assert _ops(plan)["description"] == "capitello. frammento in marmo"


@pytest.mark.parametrize("choice,name", [("accoda", "US 12 capitello"), ("solo", "US 12")])
def test_the_two_alternatives_leave_the_description_alone(choice, name):
    plan = N.plan_number(_section("frammento"), "cap", "12", choice, ts=TS)
    assert _ops(plan) == {"name": name}


def test_a_free_name_has_to_carry_the_number():
    plan = N.plan_number(_section(), "cap", "", "libero", ts=TS, name="US 12a capitello corinzio")
    assert _ops(plan) == {"name": "US 12a capitello corinzio"} and plan.number == "12a"
    for wrong in ("capitello corinzio", "US capitello"):
        with pytest.raises(N.NumeroError):
            N.plan_number(_section(), "cap", "", "libero", ts=TS, name=wrong)
    with pytest.raises(N.NumeroError):        # il nome dice un altro numero
        N.plan_number(_section(), "cap", "13", "libero", ts=TS, name="US 12")


def test_the_number_is_cleaned_and_must_be_one():
    assert N.plan_number(_section(), "cap", "US 12", "solo", ts=TS).name == "US 12"
    with pytest.raises(N.NumeroError):
        N.plan_number(_section(), "cap", "dodici", "solo", ts=TS)


# ── 2 · il prefisso dal tipo ────────────────────────────────────────────────

@pytest.mark.parametrize("node,name", [("cap", "US 4"), ("mur", "USM 4"), ("tag", "USN 4")])
def test_the_prefix_comes_from_the_type(node, name):
    assert N.plan_number(_section(), node, "4", "solo", ts=TS).name == name


# ── 3 · il nome nuovo si rilegge ────────────────────────────────────────────

@pytest.mark.parametrize("name,number,key", [
    ("US 12", "12", ("US", "12", "")),
    ("US 12 capitello", "12", ("US", "12", "")),
    ("USM 4", "4", ("USM", "4", "")),
    ("USN 4 taglio", "4", ("USN", "4", "")),
    ("US capitello", "", ("", "", "")),
    ("Strato 3", "", ("", "", "")),
    ("capitello", "", ("", "", "")),
])
def test_the_new_name_is_read_back(name, number, key):
    node = {"id": "u", "name": name}
    assert number_of_node(node) == number and unit_key(node) == key


def test_a_unit_with_a_number_keeps_it():
    with pytest.raises(NumberNotChanged):
        N.plan_number(_section(), "u7", "9", "solo", ts=TS)


# ── 4 · lo stesso numero nella stessa area ──────────────────────────────────

def test_the_same_number_in_the_same_area_is_refused():
    with pytest.raises(N.NumberTaken) as taken:
        N.plan_number(_section(), "cap", "7", "sposta", ts=TS)
    assert "1.US7" in str(taken.value)
    prop = N.proposal(_section(), "cap", "7")
    assert [u["name"] for u in prop["taken"]] == ["1.US7"]


def test_the_same_number_in_another_area_is_not_a_conflict():
    # US 8 c'è nell'area 2; «capitello» sta nell'area 1
    plan = N.plan_number(_section(), "cap", "8", "solo", ts=TS)
    assert plan.name == "US 8"
    assert N.proposal(_section(), "cap", "8")["taken"] == []


def test_the_proposal_says_the_three_choices():
    prop = N.proposal(_section("x"), "cap", "12")
    assert prop["code"] == "US" and prop["default"] == "sposta"
    assert [(c["choice"], c["name"], c["description"]) for c in prop["choices"]] == [
        ("sposta", "US 12", "capitello. x"), ("accoda", "US 12 capitello", "x"),
        ("solo", "US 12", "x")]


# ── 5 · dal servizio ────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as M
    from app.assets import InMemoryAssetStore
    from app.tools import build_registry

    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Cencelle")
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "STORE", InMemoryAssetStore())
    monkeypatch.setattr(M, "REGISTRY", build_registry(writer, M.STORE))
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    c = TestClient(M.app)
    first = c.post("/v1/scheda/iccd-us-2021",
                   json={"us": "3", "values": {"descrizione": "x"}, "create": True,
                         "lang": "it"})
    assert first.json()["ok"], first.json()
    doc = writer._read()
    sec = next(iter(doc["graphs"].values()))
    sec["nodes"] += [dict(n) for n in _section()["nodes"]]
    sec["edges"] = list(sec.get("edges") or []) + _section()["edges"]
    writer._write(doc)
    return c, writer


def _node(writer, nid):
    sec = next(iter(writer._read()["graphs"].values()))
    return next(n for n in sec["nodes"] if n["id"] == nid)


def _units(c):
    return {u["id"]: u for u in c.get("/v1/room/units").json()["units"]}


@pytest.mark.parametrize("choice,name,description", [
    ("sposta", "US 12", "capitello"), ("accoda", "US 12 capitello", ""),
    ("solo", "US 12", "")])
def test_the_service_names_the_unit_and_signs_it(client, choice, name, description):
    c, writer = client
    assert _units(c)["cap"]["number"] == ""
    got = c.post("/v1/numero", json={"node": "cap", "number": "12", "choice": choice}).json()
    assert got["ok"], got
    node = _node(writer, "cap")
    assert node["name"] == name and (node.get("description") or "") == description
    assert "us" not in (node.get("data") or {})                     # mai data.us
    unit = _units(c)["cap"]
    assert unit["number"] == "12" and unit["by_id"] is True
    # il verbale dell'atto dice il nome di prima
    d7 = _node(writer, got["data"]["process"])
    assert "«capitello»" in d7["description"] and d7["data"]["created_by"] == ORCID
    # la scheda riletta dal suo id ha il numero: l'avviso non c'è più
    read = c.get("/v1/scheda/iccd-us-2021/unita", params={"node": "cap"}).json()
    assert str(read.get("number")) == "12"


def test_the_service_refuses_a_number_taken_in_the_same_area(client):
    c, writer = client
    got = c.post("/v1/numero", json={"node": "cap", "number": "7", "choice": "sposta"}).json()
    assert not got["ok"] and got["data"]["conflict"][0]["name"] == "1.US7"
    assert _node(writer, "cap")["name"] == "capitello"               # niente salvato


def test_the_proposals_route(client):
    c, _ = client
    got = c.get("/v1/numero/proposte", params={"node": "mur", "number": "5"}).json()
    assert got["code"] == "USM" and got["choices"][0]["name"] == "USM 5"
    assert c.get("/v1/numero/proposte", params={"node": "nope", "number": "5"}).status_code == 404


# ── 6 · la pagina ───────────────────────────────────────────────────────────

WORDS = ("unit.add_number", "num.title", "num.choose", "num.move", "num.append",
         "num.only", "num.free", "num.history", "num.need", "num.free_need",
         "num.taken", "num.save", "num.cancel")


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_words_are_in_the_page(locale):
    start = PAGE.index(f"  {locale}: {{")
    block = PAGE[start:PAGE.index("\n  },", start)]
    assert [k for k in WORDS if f'"{k}":' not in block] == []


def test_the_panel_proposes_and_saves_through_the_room():
    panel = SHELL[SHELL.index("function openNumberPanel"):]
    panel = panel[:panel.index("\n}\n")]
    assert "/v1/numero/proposte" in panel and "/v1/numero`" in panel
    assert "radios.sposta.checked = true" in panel                    # preselezionata
    assert 'state.mode === "phone"' in panel                          # a tutto schermo
    assert "window.prompt" not in panel and "confirm(" not in panel   # non un dialogo
    assert re.search(r'<div class="nonum-note" id="scheda-nonum"', PAGE)
