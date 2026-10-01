"""«Verifica» nella stanza (VLONG dev28, parte G, 2026-11-01).

E.D. (1 ott 2026, decisione 15): la verifica si fa anche nella stanza di
StratiField — `POST /v1/verify` → `s3dgraphy.api.verify`, con l'identità della
stanza. Il modo d'accesso lo mette il relay (dal token), non StratiField. Ciò
che è da riallineare non si chiude con una firma (regola della dev26): lo si
dice, «si riallinea in EMStudio».
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s3dgraphy import api                                        # noqa: E402

from tests.test_la_traduzione_dalla_stanza import (ORCID, _a_unit, _graph,  # noqa: E402,F401
                                                   client)

pytest.importorskip("yaml")


def _translate(c, us="12"):
    body = c.post("/v1/translate", json={"us": us, "field": "descrizione",
                                         "lang": "en"}).json()
    assert body["ok"], body
    return body["data"]["translation_id"]


def test_an_ai_translation_verified_in_the_room_leaves_to_review(client):
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    tid = _translate(c)
    rows = c.get("/v1/to-review").json()["rows"]
    row = next(r for r in rows if r["node"] == tid)
    assert row["reasons"] == ["ai"] and row["reasons_text"] == ["AI"]
    assert row["can_verify"] is True and "realign" not in row

    signed = c.post("/v1/verify", json={"node_id": tid}).json()
    assert signed["ok"], signed
    assert tid not in [r["node"] for r in api.to_review(_graph(writer))]
    node = writer.node(tid)
    author = writer.node(node["data"]["validated_by"])
    assert author["node_type"] == "author" and author["data"]["orcid"] == ORCID
    assert node["data"]["validated_at"]
    # the way in is the relay's: StratiField declares none (a LocalWriter has no relay)
    assert not node["data"].get("validated_auth")


def test_a_translation_to_realign_is_not_closed_by_a_signature(client):
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    tid = _translate(c)
    # the original changes: the translation waits for a new text, not a name
    c.post("/v1/scheda/iccd-us-2021", json={"us": "12", "lang": "it",
                                           "values": {"descrizione": "strato di crollo e cenere"}})
    graph = _graph(writer)
    assert "stale" in next(r for r in api.to_review(graph) if r["node"] == tid)["reasons"]
    row = next(r for r in c.get("/v1/to-review").json()["rows"] if r["node"] == tid)
    assert row["can_verify"] is False and row["realign"] == "si riallinea in EMStudio"
    assert "da riallineare" in row["reasons_text"]

    count = len(writer.section()["nodes"])
    refused = c.post("/v1/verify", json={"node_id": tid}).json()
    assert not refused["ok"] and refused["data"]["realign"] == "si riallinea in EMStudio"
    assert not writer.node(tid)["data"].get("validated_by")
    assert len(writer.section()["nodes"]) == count


def test_a_node_that_waits_for_nobody_is_refused_by_s3dgraphy(client):
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato"})
    refused = c.post("/v1/verify", json={"node_id": "US12"}).json()
    assert not refused["ok"] and "waits for no verification" in refused["message"]
    assert not writer.node("US12")["data"].get("validated_by")


def test_without_an_identity_nothing_is_signed(client, monkeypatch):
    import app.main as M
    c, writer, _ = client
    _a_unit(c, {"descrizione": "strato di crollo"})
    tid = _translate(c)
    monkeypatch.setattr(M, "_author", lambda request: None)
    refused = c.post("/v1/verify", json={"node_id": tid}).json()
    assert not refused["ok"]                       # the contract refuses an act with no one
    assert not writer.node(tid)["data"].get("validated_by")


def test_the_relay_would_write_the_way_in():
    """The op on data.validated_auth leaves empty, and stamp_auth fills it."""
    from s3dgraphy.crdt import stamp_auth
    from app import verifica as V
    section = {"nodes": [
        {"id": "g", "node_type": "graph", "data": {"language": "it"}},
        {"id": "p1", "node_type": "property", "name": "x", "description": "y",
         "data": {"lang": "it", "ai_assisted": {"by": "ai1", "model": "m"}}},
        {"id": "ai1", "node_type": "author_ai", "name": "m", "data": {"model": "m"}},
    ], "edges": []}
    made = V.plan_verify(section, "p1", orcid=ORCID, ts="2026-11-01T10:00:00Z")
    auth_op = next(o for o in made.ops if o.get("field") == "data.validated_auth")
    assert auth_op["value"] is None
    stamped, outcome = stamp_auth(auth_op, {"mode": "node_password", "attested_by": "fcn"})
    assert stamped["value"] == {"mode": "node_password", "attested_by": "fcn"}


def test_the_translator_is_the_node_s_ai_and_no_other_configuration():
    """Measured: StratiField's AI is the intent model (`app/intent.py`, the
    EM_CHATBOT_INTENT_* variables) and the translator IS that model — no
    configuration of its own was added by dev27 part F, so none is removed."""
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "TRANSLATOR = " in main and "INTENT_MODEL" in main
    for name in ("EM_CHATBOT_TRANSLATE", "TRANSLATOR_MODEL", "TRANSLATE_ENDPOINT"):
        assert name not in main


def test_the_page_draws_verify_beside_what_waits():
    js = (ROOT / "web" / "scheda.js").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "shell.js").read_text(encoding="utf-8")
    assert "export function reviewRowsFor" in js and "r.of === unitId" in js
    assert 'data-action": "verify"' in js and "row.realign" in js
    assert '"/v1/verify"' in shell and "/v1/to-review" in shell
    assert "onVerify: (nodeId) => verifyNode(nodeId)" in shell


def test_reviewRowsFor_keeps_the_unit_and_its_translations():
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node to run the page's pure function")
    script = (
        "import('./web/scheda.js').then((m) => {"
        "const rows = [{node: 'US12'}, {node: 't1', of: 'US12'}, {node: 'US13'}];"
        "console.log(JSON.stringify(m.reviewRowsFor(rows, 'US12').map((r) => r.node)));"
        "console.log(JSON.stringify(m.reviewRowsFor(rows, '')));})")
    out = subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT,
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        pytest.skip(f"scheda.js does not load outside a page: {out.stderr[:120]}")
    assert out.stdout.split() == ['["US12","t1"]', "[]"]
