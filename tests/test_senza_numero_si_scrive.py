"""Senza numero si scrive — MICRO del 15 novembre 2026.

La regola di E.D. (12 novembre): i numeri non si cambiano né si inventano;
quando un numero manca l'app lo dice; numerare è buona pratica, non un obbligo.

1. un'unità senza numero si SCRIVE dal suo id (`POST /v1/scheda` con `node`),
   senza numero e senza crearne una nuova;
2. il numero si AGGIUNGE (`data.us`) a un'unità che non lo aveva, e da quel
   momento si trova per numero; un numero già di un'altra unità è il conflitto
   (nessuna sovrascrittura); un numero che ne sostituirebbe un altro si rifiuta;
3. `1.Combinar900` (CombinerNode, codice pyArchInit `Combinar`) non è
   un'unità: lo dice il dato dell'importer (`data.unita_tipo`), e nelle stanze
   importate prima il codice del template nel nome, con la STESSA tabella;
4. negli elenchi le unità senza numero vanno in fondo, col segno «senza
   numero»; il filtro «Senza numero»; le parole en/it.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app import operazioni as O                                  # noqa: E402
from app import scheda as S                                      # noqa: E402
from app import unita as U                                       # noqa: E402
from app.writer import LocalWriter, units_of                     # noqa: E402
from sorgenti import HA_NODE, esegui                             # noqa: E402

needs_node = pytest.mark.skipif(not HA_NODE, reason="node non c'è")
TS = "2026-11-15T10:00:00Z"
ORCID = "0000-0002-1825-0097"
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
SHELL = (ROOT / "web" / "shell.js").read_text(encoding="utf-8")


def _scheda():
    scheda = S.find("iccd-us-2021", {})
    if scheda is None or scheda.recipe is None:
        pytest.skip("la scheda ICCD compilata non è qui")
    return scheda


def _section():
    return {"nodes": [
        {"id": "019f-b", "node_type": "US", "name": "1.US2", "data": {"label": "US (or SU)"}},
        {"id": "019f-c", "node_type": "US", "name": "1.USM12",
         "data": {"us": "12", "unita_tipo": "USM"}},
    ], "edges": []}


# ── 1-2 · il piano, dal suo id ──────────────────────────────────────────────

def test_an_unnumbered_unit_is_written_from_its_id():
    plan = O.plan(_scheda(), {"colore": "bruno"}, number="", node_id="019f-b",
                  section=_section(), ts=TS)
    assert plan.unit_id == "019f-b" and plan.number == "" and not plan.numbered
    assert not plan.created
    assert not any(op["op"] == "add_node" and op.get("id") == "019f-b" for op in plan.ops)
    assert not any(op.get("field") == "data.us" for op in plan.ops)
    assert "colore" in plan.written


def test_a_number_written_on_it_is_added_not_invented():
    plan = O.plan(_scheda(), {}, number="7", node_id="019f-b", section=_section(), ts=TS)
    assert plan.numbered and plan.number == "7"
    added = [op for op in plan.ops if op.get("field") == "data.us"]
    assert [(op["node_id"], op["value"]) for op in added] == [("019f-b", "7")]
    # il nome e l'id non cambiano
    assert not any(op.get("field") in ("name", "id") for op in plan.ops)


def test_a_number_of_another_unit_is_the_conflict_and_nothing_is_overwritten():
    with pytest.raises(O.UnitConflict) as doppio:
        O.plan(_scheda(), {}, number="12", node_id="019f-b", section=_section(), ts=TS)
    said = str(doppio.value)
    assert "1.USM12" in said and "1.US2" in said and "conflitto" in said
    assert {n["id"] for n in doppio.value.nodes} == {"019f-b", "019f-c"}


def test_a_number_is_never_changed():
    with pytest.raises(O.NumberNotChanged):
        O.plan(_scheda(), {}, number="13", node_id="019f-c", section=_section(), ts=TS)
    # lo stesso numero che ha già: niente da aggiungere, si scrive
    plan = O.plan(_scheda(), {"colore": "bruno"}, number="12", node_id="019f-c",
                  section=_section(), ts=TS)
    assert plan.unit_id == "019f-c" and not plan.numbered


def test_from_an_id_nothing_is_created():
    with pytest.raises(O.OperazioniError):
        O.plan(_scheda(), {"colore": "bruno"}, number="", node_id="nessuno",
               section=_section(), ts=TS)


# ── 1-2 · lo stesso, dal servizio ───────────────────────────────────────────

@pytest.fixture()
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
    c = TestClient(M.app)
    first = c.post("/v1/scheda/iccd-us-2021",
                   json={"us": "3", "values": {"descrizione": "x"}, "create": True,
                         "lang": "it"})
    assert first.json()["ok"], first.json()
    doc = writer._read()
    sec = next(iter(doc["graphs"].values()))
    sec["nodes"] += [
        {"id": "019f-uuid", "node_type": "US", "name": "1.US5",
         "data": {"label": "US (or SU)"}},
        {"id": "019f-comb", "node_type": "US", "name": "1.Combinar900",
         "data": {"label": "US (or SU)"}},
    ]
    writer._write(doc)
    return c, writer


def _units(c):
    return {u["id"]: u for u in c.get("/v1/room/units").json()["units"]}


def test_the_service_writes_from_the_id_then_adds_the_number(client):
    _scheda()
    c, _ = client
    read = c.get("/v1/scheda/iccd-us-2021/unita?node=019f-uuid").json()
    assert read["by_id"] is True and read["number"] == "" and read["name"] == "1.US5"

    saved = c.post("/v1/scheda/iccd-us-2021",
                   json={"node": "019f-uuid", "values": {"descrizione": "muro a secco"},
                         "lang": "it"}).json()
    assert saved["ok"], saved
    units = _units(c)
    assert units["019f-uuid"]["number"] == ""                 # salvata senza numero
    assert "US5" not in units and len([u for u in units.values() if u["name"] == "1.US5"]) == 1
    again = c.get("/v1/scheda/iccd-us-2021/unita?node=019f-uuid").json()
    assert again["values"].get("descrizione") == "muro a secco"

    # il numero aggiunto: da qui l'unità si trova per numero
    numbered = c.post("/v1/scheda/iccd-us-2021",
                      json={"node": "019f-uuid", "us": "5", "values": {},
                            "lang": "it"}).json()
    assert numbered["ok"], numbered
    assert _units(c)["019f-uuid"]["number"] == "5"
    by_number = c.get("/v1/scheda/iccd-us-2021/unita?us=5").json()
    assert by_number["node_id"] == "019f-uuid"

    # un numero che non è il suo: non lo cambia
    other = c.post("/v1/scheda/iccd-us-2021",
                   json={"node": "019f-uuid", "us": "6", "values": {}, "lang": "it"}).json()
    assert not other["ok"] and "non si cambia" in other["message"]
    assert _units(c)["019f-uuid"]["number"] == "5"


def test_the_service_refuses_a_number_already_in_the_room(client):
    _scheda()
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"node": "019f-uuid", "us": "3", "values": {"descrizione": "y"},
                          "lang": "it"}).json()
    assert not answer["ok"] and "conflitto" in answer["message"]
    assert _units(c)["019f-uuid"]["number"] == ""             # nessuna sovrascrittura
    sec = next(iter(writer._read()["graphs"].values()))
    node = next(n for n in sec["nodes"] if n["id"] == "019f-uuid")
    assert "us" not in (node.get("data") or {})


def test_neither_number_nor_id_is_still_refused(client):
    c, _ = client
    assert c.post("/v1/scheda/iccd-us-2021",
                  json={"values": {"descrizione": "x"}}).status_code == 400


# ── 3 · i nodi che non sono unità ───────────────────────────────────────────

def test_combinar_is_a_combiner_and_stays_out(client):
    c, _ = client
    units = _units(c)
    assert "019f-comb" not in units and "019f-uuid" in units
    listed = c.get("/v1/room/units").json()
    assert {x["class"]: x["count"] for x in listed["left_out"]}.get("CombinerNode") == 1


@pytest.mark.parametrize("node, verdict", [
    # il dato dell'importer decide, anche contro il nome
    ({"node_type": "US", "name": "X", "data": {"unita_tipo": "Combinar"}}, (False, "CombinerNode")),
    ({"node_type": "US", "name": "1.Combinar900", "data": {"unita_tipo": "US"}}, (True, "")),
    ({"node_type": "US", "name": "1.SF300", "data": {"us": "300", "unita_tipo": "SF"}}, (True, "")),
    ({"node_type": "US", "name": "z", "data": {"unita_tipo": "property"}}, (False, "PropertyNode")),
    # una stanza importata prima: il codice del template nel nome, la stessa tabella
    ({"node_type": "US", "name": "1.Combinar900"}, (False, "CombinerNode")),
    ({"node_type": "US", "name": "1.2.Extractor400"}, (False, "ExtractorNode")),
    ({"node_type": "US", "name": "1.1.US1"}, (True, "")),
    ({"node_type": "US", "name": "1.US2"}, (True, "")),
])
def test_the_verdict_reads_the_importer_code(node, verdict):
    assert U.unit_verdict(node) == verdict


def test_the_pinned_codes_match_s3dgraphy():
    """La copia di `NOT_UNIT_CODES_PINNED` è la tabella di s3Dgraphy: i codici
    non-unità di `_CLASSIFIED_KIND_TO_UNITA_TIPO`, letti dal SORGENTE (il modulo
    vuole SQLAlchemy), più CON. Senza il sorgente accanto si salta."""
    import s3dgraphy
    src = (pathlib.Path(s3dgraphy.__file__).parent / "sync" / "yed_import_pipeline.py")
    if not src.exists():
        pytest.skip("il sorgente di s3Dgraphy non è qui")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    table = next(n for n in ast.walk(tree)
                 if isinstance(n, (ast.Assign, ast.AnnAssign))
                 and "_CLASSIFIED_KIND_TO_UNITA_TIPO" in ast.unparse(
                     n.targets[0] if isinstance(n, ast.Assign) else n.target))
    pairs = {ast.unparse(k).split(".")[-1]: ast.literal_eval(v)
             for k, v in zip(table.value.keys, table.value.values)}
    paradata = {pairs[k] for k in ("DOCUMENT", "COMBINER", "EXTRACTOR", "PROPERTY")}
    assert paradata | {"CON"} == set(U.NOT_UNIT_CODES_PINNED)
    try:
        from s3dgraphy.importer.unit_numbers import NOT_UNIT_CODES
    except ImportError:
        return
    assert NOT_UNIT_CODES == U.NOT_UNIT_CODES_PINNED


# ── 4 · gli elenchi e le parole ─────────────────────────────────────────────

@needs_node
def test_unnumbered_units_go_last_and_the_filter_finds_them():
    units = [{"id": "a", "name": "1.US2"}, {"id": "b", "number": "10"},
             {"id": "c", "number": "9"}, {"id": "d", "name": "1.1.US1"}]
    got = esegui(
        "import { byNumber, matches } from './web/indice.js';"
        f"const u = {json.dumps(units)};"
        "const o = u.slice().sort(byNumber).map((x) => x.id);"
        "const f = u.filter((x) => matches(x, { nonum: true }, [], null)).map((x) => x.id);"
        "const all = u.filter((x) => matches(x, { nonum: false }, [], null)).length;"
        "console.log(JSON.stringify([o, f, all]));")
    assert got == [["c", "b", "d", "a"], ["a", "d"], 4]


def test_the_sheet_says_the_number_is_missing_and_writes_anyway():
    assert 'id="scheda-nonum"' in PAGE
    assert "function paintNoNumber" in SHELL
    # dal suo id si scrive: si legge soltanto un'unità in conflitto
    reading = SHELL[SHELL.index("const reading = () =>"):][:200]
    assert "state.byId && state.idNumber" in reading
    scheda = (ROOT / "web" / "scheda.js").read_text(encoding="utf-8")
    assert "node: state.nodeId" in scheda and "!body.us && !body.node" in scheda


WORDS = ("unit.no_number", "unit.no_number.tag", "unit.number_label", "flt.no_number",
         "index.unnumberedNote", "unit.conflict_read", "nav.unnumbered",
         "nav.conflict", "unit.conflict")


@pytest.mark.parametrize("locale", ["en", "it"])
def test_the_words_are_in_the_page(locale):
    start = PAGE.index(f"  {locale}: {{")
    block = PAGE[start:PAGE.index("\n  },", start)]
    assert [k for k in WORDS if f'"{k}":' not in block] == []
    unnumbered = re.search(r'"nav\.unnumbered": "([^"]*)"', block).group(1)
    assert "lettura" not in unnumbered and "reading" not in unnumbered


def test_the_positive_notice_in_italian():
    assert ('"unit.no_number": "Questa unità non ha ancora un numero: '
            'aggiungilo quando puoi."') in PAGE
