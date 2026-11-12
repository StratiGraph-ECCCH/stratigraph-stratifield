"""La scrivania come nel mockup (NIGHT 14 novembre 2026) — le prove del nodo.

A.5 · l'elenco delle unità tiene SOLO le unità stratigrafiche, con i tipi del
datamodel di s3Dgraphy: documenti, estrattori, proprietà, continuità importati
come US (il DB demo di PyArchInit, misurato) restano fuori, e si contano.
Un'unità senza numero si apre dal suo id.

C.1 · dove è stata scritta la descrizione (trincea, scrivania, entrambe) e
quante parole ha; «da rifinire» = solo trincea e sotto la soglia.

C.2 · l'ora del salvataggio è quella della conferma del nodo, e c'è solo su
una scrittura vera.

Scavo · l'albero dei luoghi.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app import unita as U                                       # noqa: E402
from app.writer import LocalWriter, units_of                     # noqa: E402

ORCID = "0000-0002-1825-0097"


# ── A.5 · che cosa è un'unità ───────────────────────────────────────────────

def test_the_unit_types_come_from_the_datamodel_and_leave_out_continuity_and_events():
    kinds = U.unit_types()["units"]
    for k in ("US", "USVs", "USVn", "SF", "VSF", "RSF", "USD", "TSU", "UL", "USN", "USNt",
              "serSU"):
        assert k in kinds, k
    # nello stesso blocco del datamodel, ma sono NODI che parlano di unità
    assert "BR" not in kinds and "SE" not in kinds
    assert all(not c.endswith("Node") for c in kinds.values())


@pytest.mark.parametrize("name, unit, why", [
    ("1.CON500", False, "ContinuityNode"),
    ("1.DOC4001", False, "DocumentNode"),
    ("1.Extractor400", False, "ExtractorNode"),
    ("1.property800", False, "PropertyNode"),
    ("1.US5", True, ""),
    ("1.USM6", True, ""),          # un genere di s3Dgraphy (muratura)
    ("1.SF300", True, ""),
    ("1.USVs102", True, ""),
    ("US 3014", True, ""),
    ("Strato 3", True, ""),        # una classe astratta non ruba i nomi
])
def test_a_unit_whose_name_says_another_kind_is_not_a_unit(name, unit, why):
    assert U.unit_verdict({"node_type": "US", "name": name}) == (unit, why)


def test_the_list_holds_units_only_and_counts_what_it_left_out():
    doc = {"graphs": {"g": {"nodes": [
        {"id": "a", "node_type": "US", "name": "1.US5"},
        {"id": "b", "node_type": "US", "name": "1.DOC4001"},
        {"id": "c", "node_type": "US", "name": "1.Extractor400"},
        {"id": "d", "node_type": "BR", "name": "fine di US 5"},
        {"id": "e", "node_type": "document", "name": "D.1"},
        {"id": "f", "node_type": "USN", "name": "1.USN7"},
    ], "edges": []}}}
    elenco = units_of(doc)
    assert sorted(u["id"] for u in elenco) == ["a", "f"]
    assert elenco.left_out == {"DocumentNode": 1, "ExtractorNode": 1}


# ── C.1 · trincea e scrivania, e le parole ──────────────────────────────────

def test_words_and_the_one_threshold():
    assert U.words("Strato di terra, l'argilla sub-orizzontale; US 3014.") == 7
    assert U.REFINE_UNDER_WORDS == 30
    assert U.to_refine("trench", 29) and not U.to_refine("trench", 30)
    assert not U.to_refine("both", 3) and not U.to_refine(None, 3)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as M
    from app.assets import InMemoryAssetStore
    from app.tools import build_registry

    monkeypatch.delenv("STRATIGRAPH_SCHEDE_DIR", raising=False)
    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Cencelle")
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "STORE", InMemoryAssetStore())
    monkeypatch.setattr(M, "REGISTRY", build_registry(writer, M.STORE))
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    return TestClient(M.app), writer


def _save(c, us, values, posture, create=False):
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"us": us, "values": values, "create": create, "lang": "it"},
                    headers={U.HEADER: posture} if posture else {})
    assert answer.status_code == 200 and answer.json()["ok"], answer.json()
    return answer.json()


def _unit(c, us):
    listed = c.get("/v1/room/units").json()
    return next(u for u in listed["units"] if u["number"] == us), listed


def test_dictated_in_the_trench_then_refined_at_the_desk(client):
    c, writer = client
    first = _save(c, "3021", {"localita": "Leopoli-Cencelle",
                              "descrizione": "strato di crollo, laterizi"}, "trench",
                  create=True)
    # C.2: una scrittura accettata porta l'ora del nodo
    assert first["saved_at"] and first["saved_at"].endswith("+00:00")
    u, listed = _unit(c, "3021")
    assert (u["written_in"], u["words"], u["to_refine"]) == ("trench", 4, True)
    assert listed["refine_under_words"] == U.REFINE_UNDER_WORDS
    # il segno sta sul nodo, accanto alla descrizione, e non è un «campo»
    node = writer.node(u["id"])
    assert node["data"][U.WRITTEN_IN] == ["trench"]
    assert "written_in" not in " ".join(u["field_names"])
    # rifinita alla scrivania: entrambe, ed esce dal filtro
    long = ("Strato di crollo a matrice sabbiosa con laterizi frammentari abbondanti, "
            "coppi e tegole in giacitura caotica, malta disgregata; copre il piano "
            "US 3018 ed è tagliato dalla fossa US 3005 nell'angolo sud-est del vano.")
    _save(c, "3021", {"descrizione": long}, "desk")
    u, _ = _unit(c, "3021")
    assert u["written_in"] == "both" and u["words"] >= 30 and not u["to_refine"]
    # la rilettura della scheda dice la stessa cosa, e quale casella è la descrizione
    read = c.get("/v1/scheda/iccd-us-2021/unita?us=3021").json()
    assert read["description_field"] == "descrizione"
    assert read["written_in"] == "both"


def test_a_save_that_does_not_change_the_description_does_not_mark_it(client):
    c, writer = client
    _save(c, "3022", {"localita": "X", "descrizione": "breve"}, "trench", create=True)
    _save(c, "3022", {"localita": "Y", "descrizione": "breve"}, "desk")
    u, _ = _unit(c, "3022")
    assert u["written_in"] == "trench"


def test_without_a_declared_posture_the_transport_decides(client):
    """Il container locale non è seduto in nessuna stanza: in campo, come dice
    `room.js::postureOf`."""
    c, _ = client
    _save(c, "3023", {"descrizione": "terra"}, "", create=True)
    u, _ = _unit(c, "3023")
    assert u["written_in"] == "trench"


def test_a_description_from_before_tonight_has_no_known_origin():
    doc = {"graphs": {"g": {"nodes": [
        {"id": "US7", "node_type": "US", "name": "US 7", "description": "due parole"}],
        "edges": []}}}
    (u,) = units_of(doc)
    assert u["written_in"] is None and u["words"] == 2 and u["to_refine"] is False


# ── C.2 · l'ora solo dopo una scrittura vera ───────────────────────────────

def test_a_question_is_not_a_save(client):
    c, _ = client
    answer = c.post("/v1/say", json={"transcript": "quante unità ci sono?"}).json()
    assert answer["saved_at"] is None


# ── A.5 · un'unità senza numero si apre dal suo id ──────────────────────────

def test_an_unnumbered_unit_opens_from_its_id(client):
    """Un'unità importata (uuid, nome `1.US5`): niente numero, si apre lo
    stesso — per leggerla."""
    c, writer = client
    _save(c, "1", {"descrizione": "x"}, "desk", create=True)
    doc = writer._read()
    sec = next(iter(doc["graphs"].values()))
    sec["nodes"].append({"id": "019f-uuid", "node_type": "US", "name": "1.US5",
                         "description": "Struttura in muratura"})
    writer._write(doc)
    read = c.get("/v1/scheda/iccd-us-2021/unita?node=019f-uuid").json()
    assert read["by_id"] is True and read["name"] == "1.US5"
    assert read["node_id"] == "019f-uuid"
    assert c.get("/v1/scheda/iccd-us-2021/unita?node=nessuno").status_code == 404


# ── Scavo · l'albero dei luoghi ─────────────────────────────────────────────

def test_the_places_come_as_a_tree():
    sec = {"nodes": [
        {"id": "s", "node_type": "LocationNodeGroup", "name": "Sito", "data": {"level": "sito"}},
        {"id": "a", "node_type": "LocationNodeGroup", "name": "1", "data": {"level": "area"}},
        {"id": "t", "node_type": "LocationNodeGroup", "name": "II", "data": {"level": "saggio"}},
        {"id": "u", "node_type": "US", "name": "US 3"},
        {"id": "d", "node_type": "US", "name": "1.DOC4001"},
    ], "edges": [
        {"source": "a", "target": "s", "edge_type": "is_in_location"},
        {"source": "t", "target": "s", "edge_type": "is_in_location"},
        {"source": "u", "target": "t", "edge_type": "is_in_location"},
        {"source": "d", "target": "t", "edge_type": "is_in_location"},
    ]}
    tree = {p["id"]: p for p in U.places_tree(sec)}
    assert tree["a"]["parent"] == "s" and tree["t"]["parent"] == "s"
    assert tree["s"]["parent"] is None
    # il documento importato come US non conta fra le unità del saggio
    assert tree["t"]["units"] == 1


def test_the_description_field_is_read_from_the_recipe():
    from app import scheda as S
    assert S.description_field(S.find("iccd-us-2021", {})) == "descrizione"
    assert S.description_field(S.find("dai-idaifield-layer-2026", {})) == "description"


# ── C.3 · le parole sul telefono, con la stessa regola ──────────────────────

def test_the_phone_counts_words_as_the_node_does():
    from sorgenti import HA_NODE, esegui
    if not HA_NODE:
        pytest.skip("node non c'è")
    text = "Strato di terra, l'argilla sub-orizzontale; US 3014."
    got = esegui(
        "import { wordCount, appendSaid } from './web/scheda.js';"
        f"console.log(JSON.stringify([wordCount({text!r}), appendSaid('a b  ', 'c'),"
        " appendSaid('', ' x '), appendSaid('a', '')]));")
    assert got == [U.words(text), "a b c", "x", "a"]
