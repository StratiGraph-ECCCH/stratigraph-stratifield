"""La lingua dei dati (E.D., 28 settembre 2026) — chi scrive `data.lang`.

StratiField sa in che lingua si sta compilando: quella in cui il modulo è
disegnato (`GET /v1/schede/{id}?lang=`), o per la voce la lingua dei comandi
del nodo. Alla CREAZIONE di un nodo la scrive come `data.lang`; le modifiche
successive non la toccano. Non è `source_language` della scheda, che è la
lingua della NORMA: una ICCD compilata in inglese resta `source_language: it`,
e la sua US nasce `data.lang: en`.

`data.lang` è un campo come gli altri: nessuna dipendenza nuova da s3Dgraphy.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s3dgraphy.crdt import apply_op_to_section                  # noqa: E402

from app import operazioni as O                                  # noqa: E402
from app import scheda as S                                      # noqa: E402
from app.writer import LocalWriter                               # noqa: E402

pytest.importorskip("yaml")

ORCID = "0000-0002-1825-0097"
TS = "2026-10-27T09:00:00Z"
LATER = "2026-10-27T10:00:00Z"


def iccd():
    return S.find("iccd-us-2021", {})


def _apply(section, plan):
    for op in plan.ops:
        apply_op_to_section(section, op)
    return section


def _node(section, node_id):
    return next(n for n in section["nodes"] if n["id"] == node_id)


# ── il generatore ───────────────────────────────────────────────────────────

def test_a_us_created_in_a_scheda_compiled_in_hebrew_is_born_he():
    section = _apply({"nodes": [], "edges": []},
                     O.plan(iccd(), {"descrizione": "שכבת הרס"}, number="12",
                            section={"nodes": [], "edges": []}, ts=TS,
                            create=True, lang="he"))
    unit = _node(section, "US12")
    assert unit["data"]["lang"] == "he"
    assert unit["description"] == "שכבת הרס"


def test_a_later_update_does_not_touch_the_language():
    section = _apply({"nodes": [], "edges": []},
                     O.plan(iccd(), {"descrizione": "שכבת הרס"}, number="12",
                            section={"nodes": [], "edges": []}, ts=TS,
                            create=True, lang="he"))
    later = O.plan(iccd(), {"descrizione": "strato di crollo"}, number="12",
                   section=section, ts=LATER, lang="it")
    assert not any(op.get("field") == "data.lang" for op in later.ops)
    assert not any(op["op"] == "add_node" and op["id"] == "US12" for op in later.ops)
    _apply(section, later)
    unit = _node(section, "US12")
    assert unit["data"]["lang"] == "he", "la lingua si decide alla nascita"
    assert unit["description"] == "strato di crollo"
    # …e il caso si CONTA, non si corregge
    assert later.lang_differs == ["US12"]
    assert any("«he»" in n and "«it»" in n for n in later.notes)


def test_the_same_language_is_not_a_case():
    section = _apply({"nodes": [], "edges": []},
                     O.plan(iccd(), {"descrizione": "x"}, number="12",
                            section={"nodes": [], "edges": []}, ts=TS,
                            create=True, lang="it"))
    later = O.plan(iccd(), {"descrizione": "y"}, number="12", section=section,
                   ts=LATER, lang="it")
    assert later.lang_differs == []


def test_every_node_the_plan_creates_is_born_in_it_and_no_other():
    """L'unità, le proprietà coniate e lo stub di un rapporto nascono tutti
    nella lingua in cui si compila; un nodo che c'era (lo stub promosso in
    un'altra lingua) tiene la sua."""
    section = {"nodes": [], "edges": []}
    first = O.plan(iccd(), {"tagliato_da": ["3005"], "colore": "bruno"},
                   number="3014", section=section, ts=TS, create=True, lang="en")
    created = [op["node"] for op in first.ops if op["op"] == "add_node"]
    assert len(created) >= 3, created
    assert all(n["data"]["lang"] == "en" for n in created)
    _apply(section, first)
    assert _node(section, "US3005")["data"]["lang"] == "en"

    later = O.plan(iccd(), {"formazione_segno": "negativa"}, number="3005",
                   section=section, ts=LATER, lang="it")
    assert later.promoted
    _apply(section, later)
    assert _node(section, "US3005")["data"]["lang"] == "en"
    assert later.lang_differs == ["US3005"]


def test_no_language_declared_writes_none():
    """Un adattatore (PyArchInit, ATRIUM) non sa in che lingua sono i dati che
    porta: niente `data.lang`, e la lingua non si indovina."""
    plan = O.plan(iccd(), {"descrizione": "x"}, number="12",
                  section={"nodes": [], "edges": []}, ts=TS, create=True)
    assert all("lang" not in (op["node"].get("data") or {})
               for op in plan.ops if op["op"] == "add_node")


# ── la porta del modulo e la voce ───────────────────────────────────────────

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


def test_the_form_s_language_and_not_the_norm_s(client):
    """ICCD (`source_language: it`) compilata in inglese: la US nasce `en`."""
    c, writer = client
    assert iccd().source_language == "it"
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "40", "create": True, "lang": "en",
        "values": {"descrizione": "collapse layer"}})
    assert answer.json()["ok"], answer.json()
    assert writer.node("US40")["data"]["lang"] == "en"

    again = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "40", "lang": "it", "values": {"descrizione": "strato di crollo"}})
    assert again.json()["ok"], again.json()
    assert writer.node("US40")["data"]["lang"] == "en"
    assert writer.node("US40")["description"] == "strato di crollo"


def test_a_language_the_scheda_does_not_declare_is_refused(client):
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "41", "create": True, "lang": "he",
        "values": {"descrizione": "x"}})
    assert answer.status_code == 400
    assert "non «he»" in answer.json()["detail"]
    assert writer.node("US41") is None


def test_a_form_that_says_no_language_writes_none(client):
    """Una pagina vecchia, o un salvataggio rimasto in coda da prima."""
    c, writer = client
    answer = c.post("/v1/scheda/iccd-us-2021", json={
        "us": "42", "create": True, "values": {"descrizione": "x"}})
    assert answer.json()["ok"], answer.json()
    assert "lang" not in (writer.node("US42").get("data") or {})


def test_the_page_sends_the_language_it_is_drawn_in():
    js = (ROOT / "web" / "scheda.js").read_text(encoding="utf-8")
    body = js[js.index("export function payloadFor"):js.index("export async function save")]
    assert 'lang: def.lang || ""' in body


def test_the_voice_creates_in_the_command_language(client, monkeypatch):
    import app.main as M
    from app.intent import COMMAND_LANGUAGE

    c, writer = client
    seen = {}
    real = M.invoke

    def spy(descriptor, slots, author, **kw):
        seen.update(slots)
        return real(descriptor, slots, author, **kw)

    monkeypatch.setattr(M, "invoke", spy)
    answer = c.post("/v1/say", json={"transcript": "crea una nuova scheda, US 77"})
    assert answer.status_code == 200, answer.text
    assert seen.get("lang") == COMMAND_LANGUAGE
    assert answer.json()["tool"] == "create_su", answer.json()
    assert writer.node("US77")["data"]["lang"] == COMMAND_LANGUAGE
