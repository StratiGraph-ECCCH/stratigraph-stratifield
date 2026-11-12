"""«In campo» rifinito (MICRO 15 novembre 2026, mockup v7.2).

Cowork ha misurato cinque distanze dal mockup sugli affiancamenti della NIGHT:

1. sul telefono Detta nell'ordine del mockup: la voce in cima, Foto e Dove
   sono, gli esempi e le foto in attesa, la casella con «Manda» in fondo;
   «Cosa ci siamo detti» un collegamento discreto;
2. sul tablet e sullo schermo largo in campo niente ispettore della
   Scrivania; lingua della scheda e vista in «Altro»; niente «Unità (US)» e
   «Mappa» sotto la striscia;
3. l'elenco breve: le unità con un numero, per numero; quelle senza contate in
   una riga grigia;
4. l'avviso del datamodel in campo: una riga piccola sotto il menu «Scheda»;
5. la testata del telefono su una riga, la lingua nel foglio delle iniziali.

Le prove nel browser: `.claude/wip/reports/2026-11-15-img/rifinito.py` →
`rifinito-misurate.json`.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT / "tests"))

from sorgenti import HA_NODE, dentro, esegui                      # noqa: E402

needs_node = pytest.mark.skipif(not HA_NODE, reason="node non c'è")

PAGE = (WEB / "index.html").read_text(encoding="utf-8")
SHELL = (WEB / "shell.js").read_text(encoding="utf-8")
DESK = (WEB / "scrivania.js").read_text(encoding="utf-8")
FOGLIO = (WEB / "foglio.js").read_text(encoding="utf-8")
SCHEDA = (WEB / "scheda.js").read_text(encoding="utf-8")
CSS = (WEB / "campo.css").read_text(encoding="utf-8")


def _fn(src: str, head: str) -> str:
    body = src[src.index(head):]
    return body[:body.index("\n}\n")]


# ── 1 · Detta sul telefono ───────────────────────────────────────────────────

def test_cosa_ci_siamo_detti_e_un_collegamento_non_un_terzo_bottone():
    work = dentro(PAGE, '<section id="work"')
    row = work[work.index('<div class="row">'):]
    row = row[:row.index("</div>")]
    assert 'id="shoot"' in row and 'id="where"' in row
    assert 'id="chat-open"' not in row
    assert 'id="chat-open" class="linkish"' in work


def test_gli_esempi_sono_frasi_del_nodo():
    assert 'id="examples"' in dentro(PAGE, '<section id="work"')
    load = _fn(PAGE, "async function loadNodeCommands")
    assert 'intents[phrase] === "attach_photo_to_su"' in load
    paint = _fn(PAGE, "function paintCommandLanguage")
    assert "NODE_COMMANDS.examples" in paint
    # mai tradotte: nessun t(...) sulle frasi
    assert 't("examples' not in paint


def test_firmato_come_si_vede_in_detta_sul_telefono():
    assert '#surface[data-sg-mode="phone"]:has(#work:not([hidden])) #signature:not([hidden])' in CSS
    # «Esci» resta uno solo, nel foglio delle iniziali
    assert '#surface[data-sg-mode="phone"] #signature #signout { display: none; }' in CSS


# ── 5 · la testata del telefono ─────────────────────────────────────────────

def test_la_testata_del_telefono_e_una_riga_col_marchio():
    assert '<span class="mark-field" aria-hidden="true">StratiField</span>' in PAGE
    assert 'grid-template-areas: "logo name state me" "logo room state me";' in CSS
    assert "#me-controls #lang { order: -1; }" in CSS


@needs_node
@pytest.mark.parametrize("online, short, expected", [
    (True, True, "3 to deliver"),
    (True, False, "REST · 3 to deliver"),
    (False, True, "offline · 3 to deliver"),
])
def test_sul_telefono_lo_stato_e_il_numero(online, short, expected):
    got = esegui(
        "import { fieldStateLine } from './web/campo.js';"
        "const tr = (k, v) => ({ 'f.queue': `${v && v.n} to deliver`, 'node.offline': 'offline' })[k];"
        f"console.log(JSON.stringify(fieldStateLine({{ online: {json.dumps(online)}, pending: 3, tr,"
        f" short: {json.dumps(short)} }})));")
    assert got == expected


# ── 2 · in campo niente ispettore, «Altro», niente collegamenti ──────────────

def test_in_campo_l_ispettore_compare_solo_con_una_casella_scelta():
    assert ('#surface:not([data-sg-mode="desktop"]) .fo-body:not(:has(.fo-sel)) > .fo-insp'
            ' { display: none; }') in CSS
    assert '#surface:not([data-sg-mode="desktop"]) .fo-insp .refine { display: none; }' in CSS


def test_lingua_e_vista_in_altro_e_niente_unita_e_mappa():
    strip = _fn(SHELL, "function paintStrip")
    assert "moreMenu(make, t)" in strip
    assert '(l) => { if (l !== def.lang) void openScheda(def.id, null, l); }, inside);' in strip
    assert '(v) => { state.view = v; draw(); }, inside);' in strip
    assert "fieldLinks" not in SHELL and "fld-link" not in CSS
    assert '"f.more"' in PAGE


# ── 4 · l'avviso del datamodel ──────────────────────────────────────────────

def test_l_avviso_in_campo_e_una_riga_sotto_il_menu_scheda():
    assert 'if (notice && mode === "desktop") sheet.append(notice);' in SCHEDA
    assert 'if (notice && state.mode === "desktop") root.append(notice);' in FOGLIO
    strip = _fn(SHELL, "function paintStrip")
    assert 'const notice = field ? datamodelNotice(def) : null;' in strip
    assert 'notice.classList.add("dm-line");' in strip


# ── 3 · l'elenco breve ──────────────────────────────────────────────────────

@needs_node
def test_l_elenco_breve_tiene_fuori_le_unita_senza_numero():
    units = [{"number": "3014"}, {"name": "1.US2", "id": "a"}, {"number": "3009"},
             {"name": "1.Combinar900", "id": "b"}, {"name": "1.1.US1", "id": "c"}]
    got = esegui(
        "import { shortList } from './web/scrivania.js';"
        f"const u = {json.dumps(units)};"
        "const f = shortList(u, true), d = shortList(u, false);"
        "const n = (x) => x.number || x.name;"
        "console.log(JSON.stringify([f.listed.map(n), f.apart.map(n), d.listed.map(n), d.apart.length]));")
    assert got == [["3009", "3014"], ["1.1.US1", "1.Combinar900", "1.US2"],
                   ["3009", "3014", "1.1.US1", "1.Combinar900", "1.US2"], 0]
    paint = DESK[DESK.index("function paintInRoom"):]
    assert "shortList(units, !isDesk())" in paint
    assert re.search(r'"nav\.unnumbered": "Altre \{n\} senza numero', PAGE)


@pytest.mark.parametrize("locale", ["en", "it"])
def test_le_parole_nuove_ci_sono(locale):
    start = PAGE.index(f"  {locale}: {{")
    block = PAGE[start:PAGE.index("\n  },", start)]
    assert [k for k in ("f.more", "nav.unnumbered") if f'"{k}":' not in block] == []
