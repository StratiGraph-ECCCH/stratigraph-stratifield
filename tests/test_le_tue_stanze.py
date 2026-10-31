"""«Dove scrivo» è un elenco di stanze da toccare, e «+ Nuova US» sta in «Le US»
(31 ottobre, dall'iPhone vero)."""
import json
import pathlib
from unittest import mock

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"


def test_the_room_panel_lists_rooms_and_hides_the_free_text():
    room = (WEB / "room.js").read_text()
    assert 'seam.request("/v1/rooms"' in room
    assert 'createElement("details")' in room
    assert room.index("fillRooms(elenco") < room.index('campo.id = "room-target"')


def test_new_unit_starts_from_the_units_list():
    indice = (WEB / "indice.js").read_text()
    assert 'b.id = "index-new"' in indice
    assert 't("index.newWhich")' in indice
    css = (WEB / "scheda.css").read_text()
    assert '#surface[data-sg-mode="phone"] #nav-schede' in css
    html = (WEB / "index.html").read_text()
    assert '"index.new": "+ Nuova US"' in html


def test_the_node_lists_the_callers_rooms_and_drops_the_archived(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m

    class Answer:
        status = 200
        def __init__(self, body): self.body = body
        def read(self): return json.dumps(self.body).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    listed = [{"room_id": "b-scavo", "title": "Scavo B", "your_role": "editor"},
              {"room_id": "a-old", "title": "Vecchio", "your_role": "owner",
               "archived_at": "2026-01-01"},
              {"room_id": "a-scavo", "title": "Area A", "your_role": "owner"}]
    seen = {}

    def fake_open(req, timeout=0):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        return Answer(listed)

    monkeypatch.setattr(m, "_author", lambda request: "0000-0000-0000-0001")
    monkeypatch.setattr(m, "_node_server", lambda: "https://srv.test/em")
    where = mock.Mock(dial="http://inside:8000")
    monkeypatch.setattr(m.SCRIVANI, "where", lambda server, room: where)
    with mock.patch("urllib.request.urlopen", fake_open):
        r = TestClient(m.app).get("/v1/rooms", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["room"] for x in body["rooms"]] == ["a-scavo", "b-scavo"]
    assert body["rooms"][0]["role"] == "owner"
    assert seen["url"] == "http://inside:8000/v1/rooms"
    assert seen["auth"] == "Bearer tok"
