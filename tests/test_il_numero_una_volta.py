"""Il numero di un'unità, una volta sola (prova 4 del tavolo, 12 ottobre).

Misurato contro la stanza con s3Dgraphy dev47: `POST /v1/scheda/iccd-us-2021`
con `copre: ["US1"]` faceva nascere il nodo `USUS1` — «US US1», «segnata da
compilare» — e l'arco `overlies US8 → USUS1`. Con `["1"]` l'arco andava alla
US 1. Il widget del browser toglieva il prefisso (`bareNumber`); il servizio
no, e la voce o un client esterno passano dal servizio.

Da stanotte la regola è UNA (`tools.unit_number`): la usano la scheda
(`operazioni._resolve_item`), la voce (`relate_su`) e il widget, che la chiede
al servizio (`GET /v1/schede/{id}/numero`) invece di averne una copia.
"""

from __future__ import annotations

import json
import re

import pytest

import sorgenti
from app import scheda as S
from app.tools import NotAUnitNumber, make_create_su, make_relate_su, unit_number
from app.writer import LocalWriter

ORCID = "0000-0002-1825-0097"
BASE = {"localita": "Tavolo di prova", "definizione": "strato"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as M
    from app.assets import InMemoryAssetStore
    from app.tools import build_registry

    monkeypatch.delenv("STRATIGRAPH_SCHEDE_DIR", raising=False)
    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Tavolo")
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "STORE", InMemoryAssetStore())
    monkeypatch.setattr(M, "REGISTRY", build_registry(writer, M.STORE))
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    return TestClient(M.app), writer


def graph_of(writer):
    doc = json.loads(writer.path.read_text(encoding="utf-8"))
    return next(iter(doc["graphs"].values()))


def overlies_from(writer, unit_id):
    return sorted((e["source"], e["edge_type"], e["target"])
                  for e in graph_of(writer).get("edges") or []
                  if e["source"] == unit_id and e["edge_type"] == "overlies")


def ghosts(writer):
    return sorted(n["id"] for n in graph_of(writer)["nodes"]
                  if str(n["id"]).startswith("USUS"))


# ── 1 · la regola ───────────────────────────────────────────────────────────

def test_the_rule_reads_the_prefix_of_the_definition():
    iccd = S.find("iccd-us-2021")
    es = S.find("es-ue-demo-2026")
    for said in ("US1", "us 1", "US 1", "1", " Us1 "):
        assert unit_number(said, iccd) == "1", said
    assert unit_number("Contexto 14", es) == "14"
    assert unit_number("contexto14", es) == "14"
    for said in ("12a", "1001.2", "3014-bis"):
        assert unit_number(f"US {said}", iccd) == said


@pytest.mark.parametrize("said", ["USUS 3 · da B …", "US US1", "tre", "US", ""])
def test_what_is_not_a_number_is_refused_with_the_sentence(said):
    with pytest.raises(NotAUnitNumber) as wrong:
        unit_number(said, S.find("iccd-us-2021"))
    assert "unità" in str(wrong.value)


def test_a_definition_without_a_prefix_keeps_its_free_identifiers():
    """iDAI.field: `{identifier}`. Un identificativo libero non è un numero da
    controllare; si toglie solo l'id coniato davanti a un numero."""
    idai = S.find("dai-idaifield-layer-2026")
    assert unit_number("Befund 12", idai) == "Befund 12"
    assert unit_number("US1", idai) == "1"


# ── 2 · la scheda: tre grafie, un arco, nessun fantasma ─────────────────────

def test_three_spellings_are_the_same_unit_and_no_ghost_is_born(client):
    c, writer = client
    for us, said in (("40", "US1"), ("41", "us 1"), ("42", "1")):
        answer = c.post("/v1/scheda/iccd-us-2021",
                        json={"us": us, "create": True,
                              "values": {**BASE, "copre": [said]}})
        assert answer.status_code == 200, answer.text
        assert answer.json()["ok"], answer.json()
        assert overlies_from(writer, f"US{us}") == [(f"US{us}", "overlies", "US1")], said
    assert ghosts(writer) == []
    ones = [n for n in graph_of(writer)["nodes"] if n["id"] == "US1"]
    assert len(ones) == 1, "una US 1, segnata una volta"


def test_a_value_that_is_not_a_number_is_refused_not_minted(client):
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"us": "43", "create": True,
                          "values": {**BASE, "copre": ["USUS 3 · da B …"]}}).json()
    assert "non è il numero di un'unità" in answer["message"], answer["message"]
    assert overlies_from(writer, "US43") == []
    assert ghosts(writer) == []
    assert {n["id"] for n in graph_of(writer)["nodes"]
            if str(n["id"]).startswith("US")} == {"US43"}, "nessuno stub nuovo"


# ── 3 · la voce ─────────────────────────────────────────────────────────────

def test_the_voice_uses_the_same_number(tmp_path):
    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Tavolo")
    for n in ("12", "18"):
        assert make_create_su(writer).handler({"us": n}, ORCID).ok
    result = make_relate_su(writer).handler(
        {"us": "US 12", "other": "us18", "relation": "copre"}, ORCID)
    assert result.ok, result.message
    assert overlies_from(writer, "US12") == [("US12", "overlies", "US18")]
    assert result.message == "Registrato: US 12 copre US 18."
    assert ghosts(writer) == []
    refused = make_relate_su(writer).handler(
        {"us": "12", "other": "la diciotto", "relation": "copre"}, ORCID)
    assert not refused.ok and "non è il numero di un'unità" in refused.message


# ── 4 · il widget chiede al servizio, e non ha una copia ────────────────────

def test_the_service_answers_the_widget(client):
    c, _ = client
    for said in ("US1", "us 1", "1"):
        answer = c.get("/v1/schede/iccd-us-2021/numero", params={"detto": said})
        assert answer.status_code == 200 and answer.json() == {"number": "1"}
    refused = c.get("/v1/schede/iccd-us-2021/numero",
                    params={"detto": "USUS 3 · da B …"})
    assert refused.status_code == 400
    assert "non è il numero di un'unità" in refused.json()["detail"]


def test_the_widget_has_no_second_copy_of_the_rule():
    code = sorgenti.senza_prosa(
        (sorgenti.ROOT / "web" / "widgets.js").read_text(encoding="utf-8"))
    assert "bareNumber" not in code
    assert "/numero?detto=" in code
    assert not re.search(r"startsWith\(\s*prefix", code), "il prefisso si toglie di nuovo qui"
