"""Il Foglio: la scheda compilata sulle due facciate dell'A4 (16 ottobre).

Quello che si può misurare da Python, e con quale forza (`tests/sorgenti.py`):

* **il programma** — `foglio.js` è puro al caricamento, quindi la scala, le
  opzioni dalla postura, chi è attenuato e la chiave dell'intestazione si
  ESEGUONO con node, anche sulle definizioni vere;
* **la salute** — `/health` dice `seated`, e `postureOf` (room.js) ne ricava la
  postura: è la sola lettura della postura, e si esegue;
* **il sorgente** — zero colori letterali nel CSS nuovo fuori dal blocco dei
  token dichiarati, nessuno standard nominato nel JS nuovo, i due file serviti
  e in cache. Queste sono la terza forza, con la loro ragione accanto.

Quello che NON si prova qui è come si vede: le due facciate affiancate, il
glifo, la casella che cresce, il tema scuro. È nel referto della notte,
misurato con `getBoundingClientRect` nel browser.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests import sorgenti                                    # noqa: E402
from tests.test_la_scheda_surface import _literals            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
TEMPLATES = ROOT.parent / "stratigraph-templates" / "templates"
have_templates = pytest.mark.skipif(
    not TEMPLATES.is_dir(), reason="stratigraph-templates non è accanto")
needs_node = pytest.mark.skipif(
    not sorgenti.HA_NODE, reason="node non è installato: il foglio non si esegue")


# ── 1 · la postura: una lettura, dal nodo ──────────────────────────────────

def test_health_says_whether_the_node_is_seated(monkeypatch):
    """`seated` viene dalla sessione (`session.seated`), non da `writes_to`:
    un nodo con il container locale non è seduto da nessuna parte."""
    from fastapi.testclient import TestClient
    from app import main

    client = TestClient(main.app)
    assert client.get("/health").json()["seated"] is False

    class Sessione:
        seated = True

    class Seduto:
        session = Sessione()

    monkeypatch.setattr(main, "WRITER", Seduto())
    assert main._health().seated is True


@needs_node
def test_the_posture_is_read_from_seated_and_nothing_else():
    """Scrivania solo se seduti. Una stanza «degraded, writing locally» comincia
    anche lei con «room», ed è proprio il caso che una lettura di `writes_to`
    sbaglierebbe: la frase dice stanza, la sessione non c'è."""
    got = sorgenti.esegui("""
const m = await import("./web/room.js");
console.log(JSON.stringify([
  m.postureOf({seated: true, writes_to: "room r at http://x"}),
  m.postureOf({seated: false, writes_to: "room r at http://x (degraded, writing locally)"}),
  m.postureOf({writes_to: "local container (/tmp/x)"}),
  m.postureOf(null),
  m.postureOf({seated: "yes"}),
]));
""")
    assert got == ["desk", "field", "field", "field", "field"]


def test_the_page_feeds_the_posture_from_the_same_heartbeat():
    """La postura non ha un suo giro di rete: la porta `ping()`, che già
    ascolta la salute — e il nodo che non risponde passa `null`."""
    page = (WEB / "index.html").read_text(encoding="utf-8")
    ping = page[page.index("async function ping()"):]
    ping = ping[:ping.index("\n}\n")]
    assert "window.SGPosture?.(health)" in ping
    assert "window.SGPosture?.(null)" in ping


# ── 2 · il foglio, eseguito ─────────────────────────────────────────────────

@needs_node
def test_the_scale_has_a_floor_and_one_side_has_a_ceiling():
    """Fronte e retro alla scala minima invece di impilarsi; una facciata sola
    si allarga fino a 1000 px e non oltre."""
    got = sorgenti.esegui("""
const m = await import("./web/foglio.js");
console.log(JSON.stringify({
  wide: m.scaleFor(1000, 2), narrow: m.scaleFor(200, 2),
  one: m.scaleFor(691, 1), huge: m.scaleFor(5000, 1), tiny: m.scaleFor(100, 1),
}));
""")
    assert got["wide"] == pytest.approx((1000 - 22) / 2 / 210)
    assert got["narrow"] == 0.95
    assert got["one"] == pytest.approx(691 / 210)
    assert got["huge"] == pytest.approx(1000 / 210)
    assert got["tiny"] == 1.25


@needs_node
def test_one_renderer_three_options_from_the_posture():
    """Nessun `if (postura)` nel disegno: la postura diventa TRE opzioni qui, e
    il disegno legge solo quelle."""
    got = sorgenti.esegui("""
const m = await import("./web/foglio.js");
console.log(JSON.stringify([
  m.optionsFor("desk", {}),
  m.optionsFor("desk", {faces: "verso"}),
  m.optionsFor("field", {}),
  m.optionsFor("field", {side: "verso", trenchOnly: false}),
]));
""")
    assert got == [
        {"sides": "both", "corner": True, "trenchFocus": False},
        {"sides": "verso", "corner": True, "trenchFocus": False},
        {"sides": "recto", "corner": False, "trenchFocus": True},
        {"sides": "verso", "corner": False, "trenchFocus": False},
    ]


def test_the_drawing_does_not_branch_on_the_posture():
    """La terza forza, con la sua ragione: `drawSheet` non si può eseguire
    senza un DOM, quindi si guarda che la parola non ci sia. `optionsFor` è
    l'unica funzione del file che la nomina."""
    code = sorgenti.senza_prosa((WEB / "foglio.js").read_text(encoding="utf-8"))
    draw = code[code.index("export function drawSheet"):]
    for word in ("posture", "postura", '"desk"', '"field"', "postureForced"):
        assert word not in draw, word


@have_templates
@needs_node
def test_the_dimmed_boxes_are_the_non_trench_fields_of_that_side():
    """Sulle definizioni vere: con il fuoco sulla trincea le caselle attenuate
    di una facciata sono ESATTAMENTE i suoi campi con `recorded_in` diverso da
    `trench`; spento, nessuna. È la misura del browser, rifatta sul dato."""
    from app import scheda as S

    for sid in ("iccd-us-2021", "es-ue-demo-2026"):
        found = S.load(TEMPLATES / sid / "template.yaml")
        payload = found.for_browser(found.source_language)
        got = sorgenti.esegui(f"""
const m = await import("./web/foglio.js");
const def = {json.dumps(payload)};
const by = new Map(def.fields.map((f) => [f.id, f]));
const out = {{}};
for (const side of def.sheet.sides) {{
  const ids = m.fieldsOn(side);
  const on = m.optionsFor("field", {{side: side.id}});
  const off = m.optionsFor("field", {{side: side.id, trenchOnly: false}});
  out[side.id] = {{
    dimmed: ids.filter((id) => m.isDimmed(by.get(id), on)).length,
    nonTrench: ids.filter((id) => by.get(id).recorded_in !== "trench").length,
    off: ids.filter((id) => m.isDimmed(by.get(id), off)).length,
    shown: m.sidesShown(def.sheet, on.sides).map((s) => s.id),
  }};
}}
console.log(JSON.stringify(out));
""")
        for side, r in got.items():
            assert r["dimmed"] == r["nonTrench"], (sid, side, r)
            assert r["off"] == 0, (sid, side, r)
            assert r["shown"] == [side], (sid, side, r)


@needs_node
def test_the_running_head_spells_the_unit_with_the_definitions_pattern():
    got = sorgenti.esegui("""
const m = await import("./web/foglio.js");
console.log(JSON.stringify([
  m.headKey("X {a} · {b}", {a: "12", b: "Aquincum"}),
  m.headKey("X {a} · {b}", {a: "12"}),
  m.headKey("", {a: "12"}),
]));
""")
    assert got == ["X 12 · Aquincum", "X 12 · …", ""]


# ── 3 · una via sola verso i valori ─────────────────────────────────────────

@needs_node
def test_both_views_write_through_one_function():
    """`writeValue` è l'unico atto: il valore, il numero dell'unità se è la
    casella-identità, l'autorialità che torna alla persona."""
    got = sorgenti.esegui("""
const m = await import("./web/scheda.js");
let changed = 0;
const state = {values: {}, authored: {nota: "ai"}, keyField: "numero",
               us: "", onChange: () => { changed += 1; }};
m.writeValue(state, "numero", " 12 ");
m.writeValue(state, "nota", "mia");
console.log(JSON.stringify({values: state.values, us: state.us,
                            authored: state.authored, changed}));
""")
    assert got == {"values": {"numero": " 12 ", "nota": "mia"}, "us": "12",
                   "authored": {}, "changed": 2}


def test_the_sheet_has_no_road_of_its_own_to_the_service():
    """Nessun `fetch`, nessun `SG().send` nel foglio: si salva con lo stesso
    `state.onSave` della vista «Campi», che è `save()` → `SG.send` → coda."""
    code = sorgenti.senza_prosa((WEB / "foglio.js").read_text(encoding="utf-8"))
    assert "fetch(" not in code
    assert ".send(" not in code
    assert "WebSocket" not in code
    assert "state.onSave()" in code
    assert "writeValue(state" in code
    assert not re.search(r"state\.values\[[^\]]+\]\s*=(?!=)", code), (
        "una seconda via ai valori")


# ── 4 · nessuno standard nominato ───────────────────────────────────────────

def _standard_words():
    """Le parole che nominerebbero uno standard: i nomi dei campi e delle
    definizioni vere quando il repository è accanto, più quelle che si
    ripetono in ogni scheda italiana e che un renderer sarebbe tentato di
    scrivere."""
    words = {"us", "iccd", "copre", "contexto", "yacimiento", "retegszam"}
    if TEMPLATES.is_dir():
        import yaml
        for path in TEMPLATES.glob("*/template.yaml"):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))["template"]
            words.add(str(doc["id"]))
            words |= {str(f["id"]) for f in doc.get("fields") or []}
    return words


def _named(code: str, words):
    low = code.lower()
    return sorted(w for w in words
                  if re.search(rf"(?<![\w-]){re.escape(w.lower())}(?![\w-])", low))


@pytest.mark.parametrize("name", ["foglio.js", "foglio.css", "widgets.js"])
def test_no_standard_is_named_in_the_sheet(name):
    """Il foglio disegna QUALSIASI definizione dichiari un `sheet`: la griglia,
    le etichette e i nomi dei campi vengono dal dato. Una parola di uno
    standard nel codice sarebbe la seconda implementazione in un altro posto.

    Confine di parola (la terza forza), sul codice senza commenti: la prosa che
    racconta SEQUENZA FISICA non la usa."""
    code = sorgenti.senza_prosa((WEB / name).read_text(encoding="utf-8"))
    assert _named(code, _standard_words()) == []


def test_that_the_standard_detector_actually_detects():
    """Una guardia che non morde dà lo stesso verde di una che funziona."""
    assert _named('const k = state.values["copre"];', {"copre"}) == ["copre"]
    assert _named("if (id === 'us') {}", {"us"}) == ["us"]
    assert _named("status, focus, --fo-us-x", {"us"}) == []


# ── 5 · i colori ────────────────────────────────────────────────────────────

def _outside_the_tokens(css: pathlib.Path):
    """I letterali del file, TRANNE le dichiarazioni `--sf-*`: quelle sono il
    blocco dei token della carta, dichiarati come debito con la loro tabella di
    contrasto. Ovunque altro un colore è un ruolo."""
    found = []
    for number, kind, line in _literals(css):
        if re.match(r"--sf-[a-z-]+\s*:", line):
            continue
        found.append((number, kind, line))
    return found


def test_the_css_of_the_sheet_uses_roles_outside_its_declared_tokens():
    assert _outside_the_tokens(WEB / "foglio.css") == []


def test_the_token_exemption_does_not_swallow_a_rule(tmp_path):
    guilty = tmp_path / "g.css"
    guilty.write_text(":root {\n  --sf-paper: #FFFFFF;\n}\n"
                      ".fo-page { background: #FFFFFF; }\n", encoding="utf-8")
    assert [k for _n, k, _l in _outside_the_tokens(guilty)] == ["hex"]


def test_the_dark_rule_is_the_measured_one_in_both_dark_blocks():
    """Il filetto su carta scura misurava 2,85: scurito fino a #87807C (3,13).
    Deve esserlo nei due posti in cui il tema scuro si dichiara, o la
    preferenza di sistema e la scelta esplicita darebbero due fogli diversi."""
    css = (WEB / "foglio.css").read_text(encoding="utf-8")
    assert css.count("--sf-paper-rule: #87807C;") == 2
    assert "--sf-paper-rule:  #8E8782;" in css


def _contrast(a: str, b: str) -> float:
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
             for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_rule_holds_three_to_one_on_both_papers():
    assert _contrast("#8E8782", "#FFFFFF") >= 3
    assert _contrast("#87807C", "#ECE6DE") >= 3.1
    assert _contrast("#8E8782", "#ECE6DE") < 3, "il valore vecchio reggeva?"


# ── 6 · la conchiglia li serve e li mette in cache ──────────────────────────

def test_the_page_links_the_sheet_stylesheet_and_has_the_strip():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="./foglio.css">' in page
    assert 'id="scheda-strip"' in sorgenti.dentro(page, '<section id="scheda"')


def test_the_new_words_are_the_xlsx_keys_in_en_and_it():
    """Le chiavi del file `StratiGraph_UI_strings.xlsx` (spec §7), con quei
    nomi e nessun altro."""
    from tests.test_field_signature import LOCALES

    keys = ["view.sheet", "view.fields", "ctl.faces", "ctl.cardlang",
            "faces.both", "faces.recto", "faces.verso", "page.expand",
            "page.collapse", "insp.thiscard", "insp.all", "insp.trench",
            "insp.lab", "insp.check", "insp.required", "insp.ai_todo",
            "insp.ai_ok", "insp.empty", "insp.write", "act.confirm", "f.side",
            "f.trench_only", "f.later"]
    for key in keys:
        assert LOCALES["en"].get(key), key
        assert LOCALES["it"].get(key), key
        # Le altre sei sono le BOZZE dei partner, dall'xlsx: «bozza subito,
        # correzione postuma» (E.D.), quindi una lingua in bozza è presente.
        for other in ("ro", "el", "es", "pl", "he", "de"):
            assert LOCALES[other].get(key), (other, key)
    assert LOCALES["it"]["page.expand"] == "Ingrandisci questa facciata per scrivere"
    assert LOCALES["en"]["f.trench_only"] == "Trench fields only"
