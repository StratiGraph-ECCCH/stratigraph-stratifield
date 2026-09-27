"""La scheda diventa operazioni — le prove della notte del 19 ottobre.

L'audit del 17 ottobre aveva misurato la US 3014 intera salvata dal modulo:
**1 nodo `US`, 58 chiavi `data.<id_campo>`, 0 archi**, e una proiezione RDF
senza nessuno dei valori. Qui si misura la stessa US, per la stessa porta
(`POST /v1/scheda/iccd-us-2021`), dopo che la scrittura passa dalla ricetta
compilata (`app/operazioni.py`) e dalle cinque operazioni di s3Dgraphy.

1. la US 3014 intera: nodi, archi per tipo, proprietà; gli archi quelli che la
   ricetta dichiara; zero `data.<id_campo>`; i tre campi `none` assenti;
   `descrizione` in `description`; `negativa` → `USN`;
2. la proiezione RDF porta i valori (quando rdflib c'è: qui non è una
   dipendenza, e la misura del referto è fatta col venv del server);
3. andata e ritorno: ogni campo con un verdetto torna uguale;
4. seduti e da corrispondente: la stessa lista, lo stesso documento;
5. la voce: «la US 12 copre la US 14» è `overlies`, non `is_after`.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import operazioni as O                                  # noqa: E402
from app import scheda as S                                      # noqa: E402
from app.writer import (BatchTooLarge, LocalWriter, RoomWriter,  # noqa: E402
                        active_section)

yaml = pytest.importorskip("yaml")

ORCID = "0000-0002-1825-0097"
TS = "2026-10-19T22:00:00Z"
EXAMPLE = (ROOT.parent / "stratigraph-templates" / "examples"
           / "us-3014-cencelle.yaml")
DIST = ROOT.parent / "stratigraph-templates" / "dist" / "schede"

#: IL RECORD DELLA US 3014, com'è nell'esempio del formato. Copiato qui quando
#: l'esempio non è accanto, così la prova non dipende da un checkout vicino.
if EXAMPLE.is_file():
    RECORD = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))["record"]["values"]
else:                                                           # pragma: no cover
    RECORD = None
need_record = pytest.mark.skipif(RECORD is None,
                                 reason="examples/us-3014-cencelle.yaml non è accanto")

RELATION_TYPES = {"is_part_of", "equals", "bonded_to", "is_after", "abuts",
                  "overlies", "cuts", "fills"}


def iccd():
    return S.find("iccd-us-2021", {})


def values():
    return {k: v for k, v in RECORD.items() if k != "us"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """L'app vera, il writer locale su un file, un'identità fissata — la stessa
    sonda dell'audit (`/tmp/audit-norma/probe_write.py`)."""
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


def saved_3014(client):
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"us": "3014", "values": values(), "create": True})
    assert answer.status_code == 200 and answer.json()["ok"], answer.json()
    return writer.section(), answer.json()


# ── A · le schede sono VENDORATE ────────────────────────────────────────────

def test_the_vendored_copy_is_the_compiled_form_and_not_stale():
    """`schede/` è ciò che `sync-schede.sh` copia da `dist/schede/`, e un test
    lo confronta byte per byte quando `stratigraph-templates` è accanto: una
    definizione ricompilata e non rivendorata lascerebbe a questo servizio una
    copia vecchia che sembra ufficiale."""
    vendored = ROOT / "schede"
    index = json.loads((vendored / "index.json").read_text(encoding="utf-8"))
    assert index["format"] == S.INDEX_FORMAT
    for sid, entry in index["schede"].items():
        for version, item in entry["versions"].items():
            doc = json.loads((vendored / item["path"]).read_text(encoding="utf-8"))
            assert doc["format"] == S.COMPILED_FORMAT
            assert (doc["header"]["id"], doc["header"]["version"]) == (sid, version)
            assert doc["header"]["digest"] == item["digest"]
    if DIST.is_dir():
        for path in DIST.rglob("*.json"):
            mine = vendored / path.relative_to(DIST)
            assert mine.is_file(), f"{path.relative_to(DIST)} non è vendorata"
            assert mine.read_bytes() == path.read_bytes(), (
                f"{path.relative_to(DIST)} è cambiata di là: ./sync-schede.sh")


def test_the_image_carries_the_schede():
    """B5a: l'immagine su GHCR partiva senza schede."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY schede ./schede" in dockerfile
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "schede/" not in ignored and "schede" not in ignored


# ── B · il generatore: le regole, una per una ───────────────────────────────

def test_the_generator_is_pure_and_speaks_the_five_operations():
    section = {"nodes": [], "edges": []}
    plan = O.plan(iccd(), {"colore": "bruno"}, number="12", section=section,
                  ts=TS, create=True)
    assert section == {"nodes": [], "edges": []}, "ha scritto la sezione"
    assert {op["op"] for op in plan.ops} <= set(iccd().recipe["operations"])
    assert all(op["ts"] == TS and "author" not in op for op in plan.ops)


def test_verdict_none_produces_NO_operation():
    """B6: `ente_responsabile` «si compila e si stampa ma NON entra nel grafo»."""
    plan = O.plan(iccd(), {"ente_responsabile": "Univ. Tuscia",
                           "campionature": "CE26/M/14"},
                  number="12", section={}, ts=TS, create=True)
    assert plan.written == []
    assert set(plan.silent) == {"ente_responsabile", "campionature"}
    assert "Univ. Tuscia" not in json.dumps(plan.ops)


def test_the_unit_type_comes_from_the_node_type_verdict():
    """B7: una US negativa non è un volume positivo."""
    neg = O.plan(iccd(), {"formazione_segno": "negativa"}, number="3005",
                 section={}, ts=TS, create=True)
    pos = O.plan(iccd(), {"formazione_segno": "positiva"}, number="3006",
                 section={}, ts=TS, create=True)
    none = O.plan(iccd(), {"colore": "x"}, number="3007", section={}, ts=TS,
                  create=True)
    assert neg.ops[0]["node"]["node_type"] == "USN"
    assert pos.ops[0]["node"]["node_type"] == "US"
    assert none.ops[0]["node"]["node_type"] == "US" and none.notes, (
        "quando la scheda non decide il tipo, lo si DICE")


def test_the_unit_records_which_definition_and_which_version_compiled_it():
    """B5b — «un'unità non registra con quale scheda è stata compilata»,
    diceva `writer.units_of`. Adesso sì, con il digest."""
    plan = O.plan(iccd(), {"colore": "x"}, number="12", section={}, ts=TS,
                  create=True)
    stamp = next(op for op in plan.ops if op.get("field") == "data.scheda")
    assert stamp["value"] == {"template": "iccd-us-2021", "version": "1.0.0",
                              "digest": iccd().digest}


def test_COPRE_is_overlies_and_POSTERIORE_A_is_is_after_and_they_do_not_mix():
    """E.D.: le relazioni fisiche giustificano quelle cronologiche, ma sono due
    cose diverse."""
    plan = O.plan(iccd(), {"copre": ["18"], "posteriore_a": ["19"]},
                  number="12", section={}, ts=TS, create=True)
    edges = {(o["source"], o["edge_type"], o["target"])
             for o in plan.ops if o["op"] == "add_edge"}
    assert ("US12", "overlies", "US18") in edges
    assert ("US12", "is_after", "US19") in edges
    assert ("US12", "is_after", "US18") not in edges
    assert ("US12", "overlies", "US19") not in edges


def test_a_string_where_a_list_is_needed_is_refused_BY_NAME_and_the_rest_lands():
    """B3 resta fuori da stanotte (i widget), ma il generatore non spezza
    «3018, 3020» indovinando il separatore: lo rifiuta e lo dice."""
    plan = O.plan(iccd(), {"copre": "3018, 3020", "colore": "bruno",
                           "misure": "4,80 x 3,15"},
                  number="12", section={}, ts=TS, create=True)
    assert set(plan.refused) == {"copre", "misure"}
    assert "lista" in plan.refused["copre"]
    assert plan.written == ["colore"]
    assert not any(o["op"] == "add_edge" and o["edge_type"] == "overlies"
                   for o in plan.ops)


def test_a_missing_other_unit_is_created_minimal_and_MARKED_then_promoted():
    """La decisione sulle unità bersaglio (operazioni.py, decisione 1), e la
    sua seconda metà: quando la 3005 riceve la sua scheda, lo stub diventa
    un'unità vera, del tipo che la SUA scheda decide."""
    section = {"nodes": [], "edges": []}
    first = O.plan(iccd(), {"tagliato_da": ["3005"], "area": "Area 3000"},
                   number="3014", section=section, ts=TS, create=True)
    from s3dgraphy.crdt import apply_op_to_section
    for op in first.ops:
        apply_op_to_section(section, op)
    stub = next(n for n in section["nodes"] if n["id"] == "US3005")
    assert stub["data"]["scheda"]["stub"] is True
    assert stub["data"]["scheda"]["declared_by"] == "US3014"
    assert stub["name"].startswith("US 3005 — Area 3000"), (
        "lo stub porta la chiave umana nello STESSO contesto")
    assert [s["id"] for s in first.stubs] == ["US3005"]

    later = O.plan(iccd(), {"formazione_segno": "negativa"}, number="3005",
                   section=section, ts="2026-10-19T23:00:00Z", create=False)
    assert later.promoted and not later.created
    for op in later.ops:
        apply_op_to_section(section, op)
    unit = next(n for n in section["nodes"] if n["id"] == "US3005")
    assert unit["node_type"] == "USN", "la fossa è una US negativa"
    assert unit["data"]["scheda"]["template"] == "iccd-us-2021"
    assert not unit["data"]["scheda"].get("stub")


def test_a_symmetric_relation_is_one_edge_from_either_scheda():
    a = O.plan(iccd(), {"uguale_a": ["3021"]}, number="3014", section={},
               ts=TS, create=True)
    b = O.plan(iccd(), {"uguale_a": ["3014"]}, number="3021", section={},
               ts=TS, create=True)
    edge = lambda p: next((o["source"], o["target"]) for o in p.ops  # noqa: E731
                          if o["op"] == "add_edge" and o["edge_type"] == "equals")
    assert edge(a) == edge(b) == ("US3014", "US3021")


@need_record
def test_the_same_scheda_saved_twice_changes_nothing(tmp_path):
    """Ogni operazione si rimanda (è idempotente e tiene convergente una copia
    che il piano non ha visto), ma nessuna si conta come «aggiornata»: contro
    lo stato letto, la seconda volta sono tutte `noop` — tranne i marcatori di
    chi ha composto, che portano l'istante dell'atto."""
    writer = LocalWriter(str(tmp_path / "x.em.json"))
    first = O.plan(iccd(), values(), number="3014", section=writer.section(),
                   ts=TS, create=True)
    writer.send(first.ops, author=ORCID)
    again = O.plan(iccd(), values(), number="3014", section=writer.section(),
                   ts="2026-10-19T22:30:00Z")
    moving = [(o["op"], o.get("id") or o.get("field"))
              for i, o in enumerate(again.ops)
              if i not in again.noop and again.op_fields[i] != "~authorship"]
    assert moving == [], moving[:5]
    assert not again.created and not again.stubs


@need_record
def test_an_edit_removes_what_is_no_longer_there_and_keeps_what_another_box_wants(tmp_path):
    """Le rimozioni vanno in FONDO (decisione 9): la stessa persona spostata da
    un ruolo resta, perché un altro ruolo la vuole."""
    writer = LocalWriter(str(tmp_path / "x.em.json"))
    writer.send(O.plan(iccd(), values(), number="3014", section=writer.section(),
                       ts=TS, create=True).ops, author=ORCID)
    edited = values()
    edited["copre"] = ["3018"]
    edited["misure"] = edited["misure"][:4]
    edited["responsabile_compilazione"] = {"name": "Mario Rossi"}
    edited["descrizione"] = None
    plan = O.plan(iccd(), edited, number="3014", section=writer.section(),
                  ts="2026-10-19T22:10:00Z")
    kinds = [o["op"] for o in plan.ops]
    first_removal = next(i for i, k in enumerate(kinds) if k.startswith("remove"))
    assert all(not k.startswith("remove") or i >= first_removal
               for i, k in enumerate(kinds))
    assert not any(k.startswith("add") for k in kinds[first_removal:]
                   if k != "update_field")
    writer.send(plan.ops, author=ORCID)
    back = O.values_from_graph(iccd(), writer.section(), "US3014")["values"]
    assert back["copre"] == ["3018"]
    assert len(back["misure"]) == 4
    assert back["responsabile_compilazione"] == {"name": "Mario Rossi"}
    assert back["responsabile_rielaborazione"] == {"name": "E. Demetrescu"}
    assert "descrizione" not in back


# ── E.1 · la US 3014 intera, dalla porta del modulo ─────────────────────────

@need_record
def test_E1_the_whole_US_3014_lands_as_the_recipe_declares(client):
    section, answer = saved_3014(client)
    nodes = {n["id"]: n for n in section["nodes"]}
    by_type = collections.Counter(e["edge_type"] for e in section["edges"])
    unit = nodes["US3014"]

    # gli archi dei rapporti: quanti la ricetta ne dichiara sul record (15)
    recipe = iccd().recipe["fields"]
    expected = collections.Counter()
    for fid, entry in recipe.items():
        if entry["verdict"] == "edge":
            expected[entry["steps"][0]["emit"]["edge_type"]] += len(RECORD.get(fid) or [])
    assert sum(expected.values()) == 15
    assert {k: by_type[k] for k in expected} == dict(expected)

    # zero `data.<id_campo>` per i campi con un verdetto, su QUALUNQUE nodo
    ids = set(iccd()._by_id)
    assert not [(n["id"], k) for n in section["nodes"]
                for k in (n.get("data") or {}) if k in ids]
    # i tre `none` assenti dal documento intero
    text = json.dumps(section, ensure_ascii=False)
    for fid in ("ente_responsabile", "ufficio_mic", "campionature"):
        assert str(RECORD[fid])[:30] not in text, fid
    # `descrizione` è il campo del nodo (crm:P3_has_note)
    assert unit["description"] == RECORD["descrizione"]
    assert unit["node_type"] == "US"
    # le proprietà: una per campo `property`/`vocabulary` con passi, una per
    # riga delle liste di misure
    props = [n for n in section["nodes"] if n["node_type"] == "property"]
    assert len(props) == 31
    assert "definizione" in answer["data"]["silent"]


def test_E1_negativa_is_USN(client):
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "3005", "create": True,
        "values": {"formazione_segno": "negativa",
                   "ente_responsabile": "Univ. Tuscia"}})
    assert answer.json()["ok"], answer.json()
    assert writer.node("US3005")["node_type"] == "USN"
    assert "Univ. Tuscia" not in json.dumps(writer.section())


# ── E.2 · la proiezione RDF porta i valori ──────────────────────────────────

@need_record
def test_E2_the_RDF_projection_carries_every_field_that_has_operations():
    """Senza la rotta, di proposito: rdflib non è una dipendenza di questo
    servizio, e l'interprete che ce l'ha (quello di stratigraph-server) non ha
    le dipendenze della rotta. La lista è la stessa che la rotta manda (E.1 ed
    E.4 lo provano), applicata con lo stesso CRDT.

        ../stratigraph-server/.venv/bin/python -m pytest -k E2 tests/test_la_scheda_diventa_operazioni.py
    """
    rdflib = pytest.importorskip("rdflib", reason="rdflib non è una dipendenza "
                                 "di questo servizio: misurato nel referto col "
                                 "venv di stratigraph-server")
    from s3dgraphy import api
    from s3dgraphy.crdt import apply_op_to_section

    plan = O.plan(iccd(), values(), number="3014", section={}, ts=TS, create=True)
    section = {"graph_id": "scavo", "name": "Cencelle", "nodes": [], "edges": []}
    for op in plan.ops:
        apply_op_to_section(section, {**op, "author": ORCID})
    doc = {"graphs": {"scavo": section}, "active_graph_id": "scavo"}
    graph = rdflib.Graph()
    graph.parse(data=api.emjson_to_ttl(doc), format="turtle")
    base = "https://w3id.org/em/id/graph/scavo/node/"
    for fid in plan.written:
        mine = {o["id"] for o, f in zip(plan.ops, plan.op_fields)
                if f == fid and o["op"] == "add_node"}
        pairs = {(o["source"], o["target"]) for o, f in zip(plan.ops, plan.op_fields)
                 if f == fid and o["op"] == "add_edge"}
        if fid == "descrizione":
            count = len(list(graph.triples((rdflib.URIRef(base + "US3014"), None,
                                            rdflib.Literal(RECORD[fid])))))
        else:
            count = sum(1 for s, _p, o in graph
                        if any(str(s) == base + i or str(s).startswith(base + i + "/")
                               for i in mine)
                        or any({str(s), str(o)} == {base + a, base + b}
                               for a, b in pairs))
        if RECORD.get(fid) not in ([], None):
            assert count > 0, f"{fid}: nessuna tripla"


# ── E.3 · andata e ritorno ──────────────────────────────────────────────────

@need_record
def test_E3_save_reopen_and_every_field_with_a_verdict_comes_back(client):
    c, _ = client
    saved_3014(client)
    read = c.get("/v1/scheda/iccd-us-2021/unita", params={"us": "3014"}).json()
    assert read["read_with"]["version"] == "1.0.0" and read["note"] == ""
    recipe = iccd().recipe["fields"]
    compared = 0
    for fid, want in RECORD.items():
        entry = recipe[fid]
        if entry["verdict"] == "none" or (not entry["steps"] and entry["verdict"]
                                          not in ("identity", "node_type")):
            assert fid not in read["values"], f"{fid} non doveva tornare"
            continue
        got = read["values"].get(fid)
        if want == []:
            assert got is None, fid
        else:
            assert got == want, fid
        compared += 1
    assert compared == 55
    assert set(read["silent"]) == {"ente_responsabile", "ufficio_mic",
                                   "definizione", "campionature"}


def test_E3_a_unit_compiled_with_another_definition_is_read_with_THAT_one(client):
    c, writer = client
    hu = S.find("hu-rl-demo-2026", {})
    unit_field = hu.unit_field
    plan = O.plan(hu, {f: "x" for f in hu._by_id
                       if f != unit_field and hu.recipe["fields"][f]["steps"]
                       and hu.field(f)["type"] in ("text", "longtext")},
                  number="7", section=writer.section(), ts=TS, create=True)
    writer.send(plan.ops, author=ORCID)
    read = c.get("/v1/scheda/iccd-us-2021/unita", params={"us": "7"}).json()
    assert read["read_with"]["template"] == "hu-rl-demo-2026"
    assert "hu-rl-demo-2026" in read["note"] and "iccd-us-2021" in read["note"]


# ── E.4 · seduti e da corrispondente: la stessa lista, lo stesso documento ──

class _Relay:
    """Ciò che il relay fa di un'operazione, senza il relay: `author` tolto e
    rimesso dal token, `ts` onorato, `em.apply_op` sulla sezione. È la riga di
    `stratigraph-server/app/ws.py::apply_from_connector` e di `rooms.apply`."""

    def __init__(self):
        self.section = {"nodes": [], "edges": []}
        self.heard = []

    def apply(self, op):
        from s3dgraphy.crdt import apply_op_to_section
        entry = {k: v for k, v in op.items() if k != "author"}
        entry["author"] = ORCID
        self.heard.append(dict(op))
        result = apply_op_to_section(self.section, entry)
        return {"applied": result.applied, "reason": result.reason}


class _Session:
    """Una sessione tenuta: il socket di `RoomWriter` quando è seduto."""

    def __init__(self, relay):
        self.relay, self.seated, self._last = relay, True, None

    def send(self, kind, payload):
        if kind == "op":
            self._last = {"type": "op_result",
                          "payload": {**self.relay.apply(payload), "op": payload}}

    def await_answer(self, wanted="op_result", matches=None):
        return self._last


def _room_writer(tmp_path, name):
    from app.bridge import bridge_for
    local = LocalWriter(str(tmp_path / f"{name}.em.json"))
    return RoomWriter("http://127.0.0.1:9", name, "tok", fallback=local,
                      bridge=bridge_for(local.path, name))


@need_record
def test_E4_seated_and_correspondent_produce_the_same_room_document(tmp_path):
    from s3dgraphy import api

    plan = O.plan(iccd(), values(), number="3014", section={}, ts=TS, create=True)

    # seduti: il socket
    desk_room = _Relay()
    desk = _room_writer(tmp_path, "desk")
    desk.session = _Session(desk_room)
    desk._seated = lambda: None
    assert desk.posture == "desk"
    desk.send(plan.ops, author=ORCID)

    # corrispondente: la sessione non si apre, la coda parte dalla porta REST
    field_room = _Relay()
    field = _room_writer(tmp_path, "field")
    posted = []

    def no_seat():
        raise ConnectionError("in campo")

    def post(batch):
        if len(batch) > 40:
            field.ops_batch = 40          # la porta dichiara il suo limite
            raise BatchTooLarge(40)
        posted.append(len(batch))
        refused = []
        applied = 0
        for op in batch:
            out = field_room.apply(op)
            if out["applied"]:
                applied += 1
            else:
                refused.append({"op": op["op"], "reason": out["reason"]})
        return {"applied": applied, "refused": refused}

    field._seated = no_seat
    field._post_ops = post
    assert field.posture == "field"
    outcomes = field.send(plan.ops, author=ORCID)
    assert all(o.get("queued") for o in outcomes)
    assert len(field.bridge) == 0, "la coda è partita tutta"
    assert posted and max(posted) <= 40, "il limite della porta è stato rispettato"

    # la STESSA lista, e lo STESSO documento
    assert desk_room.heard == field_room.heard == plan.ops
    digest = lambda sec: api.content_digest(                     # noqa: E731
        {"graphs": {"g": {"nodes": sec["nodes"], "edges": sec["edges"]}},
         "active_graph_id": "g"})
    assert digest(desk_room.section) == digest(field_room.section)
    # …e il container locale del corrispondente è la stessa cosa: converge
    assert digest(field.fallback.section()) == digest(field_room.section)


def test_E4_a_door_that_does_not_answer_keeps_the_queue(tmp_path):
    field = _room_writer(tmp_path, "trincea")

    def no_seat():
        raise ConnectionError("in campo")

    def unreachable(batch):
        raise OSError("nessuna rete")

    field._seated = no_seat
    field._post_ops = unreachable
    plan = O.plan(iccd(), {"colore": "bruno"}, number="12", section={}, ts=TS,
                  create=True)
    field.send(plan.ops, author=ORCID)
    assert len(field.bridge) == len(plan.ops), "niente perso, tutto in coda"
    assert field.last_rest["stopped"].startswith("OSError")
    assert O.values_from_graph(iccd(), field.fallback.section(), "US12")[
        "values"]["colore"] == {"label": "bruno"}, (
        "il nodo sa rispondere su ciò che ha appena scritto")


# ── E.5 · la voce ───────────────────────────────────────────────────────────

def test_E5_the_voice_says_copre_and_writes_overlies(tmp_path):
    from app.assets import InMemoryAssetStore
    from app.contract import invoke
    from app.intent import understand
    from app.tools import build_registry, make_create_su

    writer = LocalWriter(str(tmp_path / "v.em.json"))
    assert make_create_su(writer).handler({"us": "12"}, ORCID).ok
    registry = build_registry(writer, InMemoryAssetStore())
    understood = understand("la US 12 copre la US 14", registry)
    assert understood.tool == "relate_su"
    result = invoke(registry.get("relate_su"), understood.slots, ORCID,
                    registry=registry)
    assert result.ok, result.message
    edges = [(e["source"], e["edge_type"], e["target"])
             for e in writer.section()["edges"]]
    assert edges == [("US12", "overlies", "US14")], edges
    assert result.data["field"] == "copre"


def test_E5_what_the_voice_writes_the_scheda_reads_back():
    """Una porta, un arco: detto a voce, riletto nella casella COPRE."""
    section = {"nodes": [], "edges": []}
    from s3dgraphy.crdt import apply_op_to_section
    for op in O.plan(iccd(), {"copre": ["14"]}, number="12", section=section,
                     ts=TS, create=True, additive=True).ops:
        apply_op_to_section(section, op)
    back = O.values_from_graph(iccd(), section, "US12")["values"]
    assert back["copre"] == ["14"]
    back14 = O.values_from_graph(iccd(), section, "US14")["values"]
    assert back14["coperto_da"] == ["12"], "la lente: lo stesso arco dall'altro capo"


# ── l'elenco delle unità ────────────────────────────────────────────────────

@need_record
def test_the_index_lists_UNITS_says_their_scheda_and_marks_the_stubs(client):
    """Una scheda scrive 65 nodi: l'elenco ne mostra le UNITÀ, dice con quale
    definizione ognuna è stata compilata, e segna quelle che esistono solo
    perché un rapporto le nomina."""
    c, writer = client
    saved_3014(client)
    listed = {u["id"]: u for u in c.get("/v1/room/units").json()["units"]}
    assert all(u["node_type"] in ("US", "USN", "SF") for u in listed.values())
    us = listed["US3014"]
    assert us["scheda"] == {"template": "iccd-us-2021", "version": "1.0.0"}
    assert us["stub"] is False
    assert "copre" in us["field_names"] and "scheda" not in us["field_names"]
    assert listed["US3018"]["stub"] is True and listed["US3018"]["scheda"] is None


def test_the_list_of_schede_says_version_and_whether_it_saves(client):
    c, _ = client
    listed = {s["id"]: s for s in c.get("/v1/schede").json()["schede"]}
    assert listed["iccd-us-2021"]["version"] == "1.0.0"
    assert listed["iccd-us-2021"]["saveable"] is True


# ── il vecchio percorso è sparito ───────────────────────────────────────────

def test_the_old_path_is_gone_from_the_tools():
    """`update_su` non chiama più `graph_writer.update(unit, {campo: valore})`:
    quella riga è la `data.<id_campo>` dell'audit."""
    import inspect

    from app import tools
    source = inspect.getsource(tools.make_update_su)
    assert "graph_writer.update(" not in source
    assert "_through_the_recipe" in source
    assert "RELATIONS: Dict[str, Tuple[str, str]] = {" not in inspect.getsource(tools)
