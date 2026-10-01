"""«Traduci» dalla stanza (VLONG dev27, parte F, 2026-10-31).

Il modello del nodo traduce un testo e nasce un `TranslationNode` — `method:
ai`, `ai_assisted` — accanto all'originale, raggiunto con `has_translation`.
L'originale resta com'era, e la traduzione è in `api.to_review` (ragione `ai`)
finché una persona non la firma (`api.verify`, oggi in EMStudio).

Il modello è FINTO: nessun endpoint, nessuna chiave. Lo stesso gesto dei test
del modello d'intento (`test_intent_model_gate.py`), che per la rotta HTTP usa
un server su loopback — qui c'è anche quello, per `translate`.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s3dgraphy import api                                        # noqa: E402

from app.writer import LocalWriter                               # noqa: E402

pytest.importorskip("yaml")

ORCID = "0000-0002-1825-0097"


class FakeTranslator:
    """Un traduttore che non chiama nessuno."""

    model = "finto-7b"

    def __init__(self, answer="collapse layer"):
        self.answer = answer
        self.asked = []

    def translate(self, text, *, source, target):
        self.asked.append((text, source, target))
        return self.answer


def _graph(writer):
    graph, _ = api.load_emjson({"graphs": {"g": writer.section()}})
    return graph


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as M
    from app.assets import InMemoryAssetStore
    from app.tools import build_registry

    monkeypatch.delenv("STRATIGRAPH_SCHEDE_DIR", raising=False)
    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Cencelle")
    translator = FakeTranslator()
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "STORE", InMemoryAssetStore())
    monkeypatch.setattr(M, "REGISTRY",
                        build_registry(writer, M.STORE, translator=translator))
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    return TestClient(M.app), writer, translator


def _a_unit(c, values, us="12"):
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": us, "create": True, "lang": "it", "values": values})
    assert answer.json()["ok"], answer.json()


def test_an_ai_translation_from_the_room_waits_and_the_original_stays(client):
    c, writer, translator = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    before = json.loads(json.dumps(writer.node("US12")))

    answer = c.post("/v1/translate", json={"us": "12", "field": "descrizione",
                                           "lang": "en"})
    body = answer.json()
    assert body["ok"], body
    assert translator.asked == [("strato di crollo", "it", "en")]

    # l'originale: lo stesso nodo, byte per byte
    assert writer.node("US12") == before
    assert writer.node("US12")["description"] == "strato di crollo"

    # la traduzione: un nodo suo, ai, in to_review
    tid = body["data"]["translation_id"]
    node = writer.node(tid)
    assert node["node_type"] == "translation"
    assert node["data"]["method"] == "ai"
    assert node["data"]["lang"] == "en" and node["data"]["from_lang"] == "it"
    assert node["data"]["text"] == "collapse layer"
    assert node["data"]["ai_assisted"]["model"] == "finto-7b"
    assert not node["data"].get("validated_by")

    graph = _graph(writer)
    rows = [r for r in api.to_review(graph) if r["node"] == tid]
    assert rows and rows[0]["reasons"] == ["ai"], api.to_review(graph)
    assert rows[0]["of"] == "US12" and rows[0]["field"] == "description"
    shown = api.text(graph, "US12", "description", "en")
    assert shown["text"] == "collapse layer" and shown["reasons"] == ["ai"]


def test_the_person_signs_it_and_the_model_is_named(client):
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    tid = c.post("/v1/translate", json={"us": "12", "field": "descrizione",
                                        "lang": "en"}).json()["data"]["translation_id"]
    section = writer.section()
    edges = {(e["source"], e["edge_type"], e["target"]) for e in section["edges"]}
    assert ("US12", "has_translation", tid) in edges
    authors = [n for n in section["nodes"] if n["node_type"] == "author"
               and (n.get("data") or {}).get("orcid") == ORCID]
    assert len(authors) == 1
    assert (tid, "has_author", authors[0]["id"]) in edges
    ai = [n for n in section["nodes"] if n["node_type"] == "author_ai"]
    assert [n["data"]["model"] for n in ai] == ["finto-7b"]
    assert writer.node(tid)["data"]["ai_assisted"]["by"] == ai[0]["id"]

    # …e una persona che la verifica la toglie dall'elenco (in EMStudio, oggi)
    graph = _graph(writer)
    api.verify(graph, tid, authors[0]["id"])
    assert not [r for r in api.to_review(graph) if r["node"] == tid]


def test_a_property_box_translates_the_property_not_the_unit(client):
    c, writer, translator = client
    _a_unit(c, {"descrizione": "strato", "osservazioni": "molti frammenti"})
    body = c.post("/v1/translate", json={"us": "12", "field": "osservazioni",
                                         "lang": "en"}).json()
    assert body["ok"], body
    assert translator.asked[-1][0] == "molti frammenti"
    of = body["data"]["of"]
    assert of != "US12"
    assert writer.node(of)["description"] == "molti frammenti"
    assert writer.node(body["data"]["translation_id"])["data"]["field"] == "description"


def test_the_same_translation_twice_is_one_node(client):
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    ask = {"us": "12", "field": "descrizione", "lang": "en"}
    first = c.post("/v1/translate", json=ask).json()
    again = c.post("/v1/translate", json=ask).json()
    assert again["ok"] and again["data"]["already"]
    assert again["data"]["translation_id"] == first["data"]["translation_id"]
    assert sum(1 for n in writer.section()["nodes"]
               if n["node_type"] == "translation") == 1


def test_no_model_on_the_node_writes_nothing_and_says_so(tmp_path, monkeypatch):
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
    _a_unit(c, {"descrizione": "strato di crollo"})
    count = len(writer.section()["nodes"])
    body = c.post("/v1/translate", json={"us": "12", "field": "descrizione",
                                         "lang": "en"}).json()
    assert not body["ok"] and body["data"]["reason"] == "no-model"
    assert len(writer.section()["nodes"]) == count


def test_a_unit_with_no_language_is_not_guessed(client):
    """Una US nata senza lingua (un adattatore, una pagina vecchia) in uno
    studio che non dichiara la sua: `add_translation` rifiuta, niente scritto."""
    c, writer, _ = client
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "13", "create": True, "values": {"descrizione": "x"}})
    assert answer.json()["ok"]
    count = len(writer.section()["nodes"])
    body = c.post("/v1/translate", json={"us": "13", "field": "descrizione",
                                         "lang": "en"}).json()
    assert not body["ok"]
    assert "never guessed" in body["message"]
    assert len(writer.section()["nodes"]) == count


def test_no_text_is_accepted_from_outside():
    """La rotta non ha una casella per il testo: lo compone il modello."""
    import app.main as M
    assert "text" not in M.TranslateIn.model_fields


# ── il modello vero, su loopback ────────────────────────────────────────────

class _Model(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):                                        # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        _Model.seen.append(json.loads(self.rfile.read(length) or b"{}"))
        payload = json.dumps({"choices": [{"message": {"content": "collapse layer\n"}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload.encode())

    def log_message(self, *args):                             # noqa: A003
        pass


def test_the_node_model_translates_over_the_same_endpoint():
    from app.intent import (INTENT_ENDPOINT_VAR, INTENT_MODEL_VAR,
                            intent_model_from_env)

    _Model.seen = []
    server = HTTPServer(("127.0.0.1", 0), _Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    try:
        model = intent_model_from_env({INTENT_MODEL_VAR: "llama3.2",
                                       INTENT_ENDPOINT_VAR: f"http://{host}:{port}/v1"})
        assert model.translate("strato di crollo", source="it",
                               target="en") == "collapse layer"
    finally:
        server.shutdown()
    sent = _Model.seen[0]
    assert sent["model"] == "llama3.2"
    assert "from the language tagged it into the language tagged en" in \
        sent["messages"][0]["content"]
    assert sent["messages"][1]["content"] == "strato di crollo"
