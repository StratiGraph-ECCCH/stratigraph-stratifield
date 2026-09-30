"""La scheda dice su quale datamodel è stata costruita, e il nodo lo confronta.

Una scheda compilata porta in `header.datamodel` le versioni dei datamodel e,
dallo snapshot formato 4 di stratigraph-templates, `digest`: l'IMPRONTA del
datamodel di s3Dgraphy (`api.datamodel_fingerprint`). Fino al 2026-10-01
nessuno la leggeva (audit della catena, D3). Adesso:

* al caricamento il nodo la confronta con la s3dgraphy che porta con sé;
* una differenza NON blocca, ma si vede: un avviso nel log, e sulla scheda
  (`for_browser` → `datamodel_check`, disegnato da `web/scheda.js`);
* una scheda senza impronta — le vecchie — dà un avviso più morbido;
* una scheda uguale non dice niente.
"""

from __future__ import annotations

import copy
import json
import logging
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import scheda as S                                   # noqa: E402
from tests import sorgenti                                    # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

HERE = {
    "digest": "sha256:" + "a" * 64,
    "versions": {"nodes": "1.6.17", "node_registry": "1.6.17", "connections": "1.6.31",
                 "visual_rules": "1.6.27", "qualia": "1.6.2", "translations": "1.6"},
}

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node non è installato")


def _compiled(datamodel: dict) -> dict:
    """Una scheda vendorata vera, con la testata del datamodel sostituita."""
    path = next(p for p in sorted((ROOT / "schede").rglob("*.json")) if p.name != "index.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc = copy.deepcopy(doc)
    doc["header"]["datamodel"] = datamodel
    doc["header"]["version"] = "9.9." + str(abs(hash(json.dumps(datamodel, sort_keys=True))) % 1000)
    return doc


@pytest.fixture
def here(monkeypatch):
    monkeypatch.setattr(S, "datamodel_here", lambda: HERE)
    return HERE


def test_the_same_fingerprint_says_nothing(here, caplog):
    same = dict(HERE["versions"], digest=HERE["digest"])
    with caplog.at_level(logging.INFO, logger="stratigraph-chatbot.scheda"):
        scheda = S.Scheda(_compiled(same))
    check = scheda.datamodel_check()
    assert check["state"] == "aligned" and check["differences"] == []
    assert not [r for r in caplog.records if "datamodel" in r.getMessage()]


def test_another_fingerprint_is_named_in_the_log_and_does_not_block(here, caplog):
    older = dict(HERE["versions"], nodes="1.6.12", digest="sha256:" + "b" * 64)
    with caplog.at_level(logging.INFO, logger="stratigraph-chatbot.scheda"):
        scheda = S.Scheda(_compiled(older))      # it LOADS: nothing refused
    check = scheda.datamodel_check()
    assert check["state"] == "differs"
    assert check["differences"] == [{"name": "nodes", "scheda": "1.6.12", "here": "1.6.17"}]
    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1 and "nodi 1.6.12, qui 1.6.17" in warned[0].getMessage()
    assert scheda.recipe is not None, "the recipe is still there: it can be saved"


def test_same_versions_different_content_is_said_too(here):
    edited = dict(HERE["versions"], digest="sha256:" + "c" * 64)
    check = S.Scheda(_compiled(edited)).datamodel_check()
    assert check["state"] == "differs"
    assert check["differences"] == [{"name": None, "scheda": None, "here": None}]


def test_a_scheda_without_a_fingerprint_gets_the_softer_warning(here, caplog):
    old = {"nodes": "1.6.9", "connections": "1.6.20", "qualia": "1.6.2", "em_ttl": "1.6.5"}
    with caplog.at_level(logging.INFO, logger="stratigraph-chatbot.scheda"):
        check = S.Scheda(_compiled(old)).datamodel_check()
    assert check["state"] == "no_digest"
    assert {d["name"] for d in check["differences"]} == {"nodes", "connections"}
    said = [r for r in caplog.records if "impronta" in r.getMessage()]
    assert said and all(r.levelno == logging.INFO for r in said), "softer: info, not warning"


def test_a_node_that_cannot_compute_the_fingerprint_says_unchecked(monkeypatch):
    monkeypatch.setattr(S, "datamodel_here", lambda: None)
    check = S.Scheda(_compiled(dict(HERE["versions"], digest=HERE["digest"]))).datamodel_check()
    assert check["state"] == "unchecked"


def test_the_check_travels_to_the_browser(here):
    older = dict(HERE["versions"], connections="1.6.27", digest="sha256:" + "d" * 64)
    scheda = S.Scheda(_compiled(older))
    drawn = scheda.for_browser(scheda.languages[0])
    assert drawn["datamodel_check"]["state"] == "differs"
    assert drawn["datamodel_check"]["differences"][0]["name"] == "connections"


def test_the_real_fingerprint_here_is_s3dgraphys():
    pytest.importorskip("s3dgraphy.datamodel")
    from s3dgraphy import api
    S._here_cache.clear()
    assert S.datamodel_here()["digest"] == api.datamodel_fingerprint()["digest"]


# ── l'interfaccia ────────────────────────────────────────────────────────────

def test_both_views_draw_the_notice_from_one_function():
    scheda_js = (WEB / "scheda.js").read_text(encoding="utf-8")
    foglio_js = (WEB / "foglio.js").read_text(encoding="utf-8")
    assert "export function datamodelNotice(def)" in scheda_js
    assert scheda_js.count("datamodelNotice(def)") == 2      # declared + used in render
    assert "datamodelNotice" in foglio_js.split("from \"./scheda.js\"")[0]
    assert "datamodelNotice(def)" in foglio_js


_DOM = """
globalThis.document = { createElement(tag) { return {
  tag, attrs: {}, kids: [], className: "", textContent: "",
  setAttribute(k, v) { this.attrs[k] = v; }, append(...k) { this.kids.push(...k); } }; } };
globalThis.window = { SG: { t: (key, values) => key + (values ? JSON.stringify(values) : "") } };
const s = await import("./web/scheda.js");
const show = (n) => n && { cls: n.className, state: n.attrs["data-state"],
                           text: n.kids.map((k) => k.textContent) };
"""


@needs_node
def test_the_notice_is_drawn_for_a_difference_and_not_for_an_equal_one():
    said = sorgenti.esegui(_DOM + """
console.log(JSON.stringify([
  show(s.datamodelNotice({ datamodel_check: { state: "aligned", differences: [] } })),
  show(s.datamodelNotice({ datamodel_check: { state: "differs",
       differences: [{ name: "nodes", scheda: "1.6.12", here: "1.6.17" }] } })),
  show(s.datamodelNotice({ datamodel_check: { state: "no_digest", differences: [] } })),
  show(s.datamodelNotice({})),
]));
""")
    aligned, differs, old, yaml = said
    assert aligned is None and yaml is None
    assert differs["cls"] == "dm-notice differs" and differs["state"] == "differs"
    assert differs["text"][0] == "sheet.dm.differs"
    assert differs["text"][1] == 'sheet.dm.line{"name":"dm.nodes","sheet":"1.6.12","here":"1.6.17"}'
    assert old["cls"] == "dm-notice" and old["text"] == ["sheet.dm.nodigest"]


def test_the_words_of_the_notice_exist_in_en_and_it():
    from tests.test_field_signature import LOCALES
    for key in ("sheet.dm.differs", "sheet.dm.line", "sheet.dm.content",
                "sheet.dm.nodigest", "sheet.dm.unchecked", "dm.nodes", "dm.node_registry",
                "dm.connections", "dm.visual_rules", "dm.qualia", "dm.translations"):
        assert LOCALES["en"].get(key), key
        assert LOCALES["it"].get(key), key
    assert LOCALES["it"]["sheet.dm.line"] == "{name} {sheet}, qui {here}"


def test_sync_prints_both_fingerprints():
    script = (ROOT / "sync-schede.sh").read_text(encoding="utf-8")
    assert "from s3dgraphy.datamodel import datamodel_fingerprint" in script
    assert '(head["header"].get("datamodel") or {}).get("digest")' in script
