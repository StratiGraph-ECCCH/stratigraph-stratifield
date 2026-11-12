"""«In campo» come nel mockup, e la revisione della scrivania (NIGHT 15 novembre
2026, mockup v7.2).

E.D., 12 novembre, Safari a tutto schermo: «In campo» su uno schermo largo
mostrava ancora la colonna con l'ELENCO delle definizioni (DAI, DEMO·UE, IAA,
ICCD, «n da trincea su m»), «Dove scrivo», «Tutti i campi»; al centro «Tocca e
parla» e il vuoto. Adesso:

* una sola cornice per le due posture: la lingua sempre nella barra, la stanza
  un elemento solo che apre la scelta, lo stato con il salvataggio (in campo
  «REST · n da consegnare»);
* in campo quattro voci, Detta · Scheda · Foto · Consegna; le definizioni nel
  menu «Scheda» (lo stesso della scrivania), «Tutti i campi» diventa «Solo i
  campi da trincea»; sul tablet e sullo schermo largo la cornice del tablet,
  centrata;
* la scrivania più densa, la colonna per numero, il perché dei bottoni spenti
  scritto, «n caselle vuote · apri il Foglio».

Le prove nel browser stanno nel referto:
`.claude/wip/reports/2026-11-15-img/prove.py`, `prove-misurate.json`.
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
FIELD = (WEB / "campo.js").read_text(encoding="utf-8")
CSS = (WEB / "campo.css").read_text(encoding="utf-8")


def _fn(src: str, head: str) -> str:
    body = src[src.index(head):]
    return body[:body.index("\n}\n")]


# ── A · una sola cornice ──────────────────────────────────────────────────────

def test_la_lingua_sta_nella_barra_in_ogni_modo():
    place = _fn(SHELL, "function placeControls")
    assert 'id === "lang" && $("bar-lang")' in place
    assert 'mode === "desktop"' not in place


def test_la_stanza_e_lo_stato_dicono_una_cosa_sola():
    """La pastiglia non dice più «locale» accanto a «container locale»: dove si
    scrive lo dice il nome della stanza; la pastiglia lo stato e il salvataggio."""
    ping = _fn(PAGE, "async function ping()")
    assert 'PILL_WHERE = t("pill.room");' in ping
    assert '"pill.local"' not in ping
    # la stanza apre la sua scelta in ogni modo, non più la colonna
    click = SHELL[SHELL.index('$("room-name")?.addEventListener("click"'):]
    click = click[:click.index("});")]
    assert "setNavOpen" not in click
    place = _fn(SHELL, "function placeDesk")
    assert place.index('move("nav-room", $("room-pop-host"));') < place.index("if (desk)")


@needs_node
@pytest.mark.parametrize("online, n, expected", [
    (True, 0, "REST · 0 to deliver"),
    (True, 3, "REST · 3 to deliver"),
    (False, 1, "offline · 1 to deliver"),
])
def test_in_campo_lo_stato_dice_REST_e_quanto_c_e_da_consegnare(online, n, expected):
    got = esegui(
        "import { fieldStateLine } from './web/campo.js';"
        "const tr = (k, v) => ({ 'f.queue': `${v && v.n} to deliver`, 'node.offline': 'offline' })[k];"
        f"console.log(JSON.stringify(fieldStateLine({{ online: {json.dumps(online)}, pending: {n}, tr }})));")
    assert got == expected


# ── B · in campo come nel mockup ─────────────────────────────────────────────

def test_le_quattro_voci_sono_quelle_del_mockup():
    nav = dentro(PAGE, '<nav class="fieldtabs" id="field-tabs"')
    assert re.findall(r'data-ftab="([a-z]+)"', nav) == ["voice", "sheet", "photos", "deliver"]
    assert re.findall(r'data-t="(tab\.[a-z]+)"', nav) == [
        "tab.dictate", "tab.sheet", "tab.photos", "tab.deliver"]
    assert 'id="tb-deliver-n"' in nav, "il numero da consegnare sulla Consegna"
    # la Consegna è un pannello come gli altri, e «Prendi dalla stanza» ci sta dentro
    assert '<section id="deliver"' in PAGE
    assert '"deliver"]' in SHELL and "pullRoom" in SHELL
    assert '"f.pull"' in FIELD and '"f.deliver_now"' in FIELD


@needs_node
def test_quale_voce_e_accesa():
    got = esegui(
        "import { fieldTabOf } from './web/campo.js';"
        "console.log(JSON.stringify(['voice','scheda','index','map','photos-sec','deliver','finds']"
        ".map(fieldTabOf)));")
    assert got == ["voice", "sheet", "sheet", "sheet", "photos", "deliver", None]


def test_in_campo_non_c_e_piu_un_elenco_di_definizioni():
    """La colonna: sul telefono non c'è, sul tablet resta SOLO l'elenco breve
    delle unità. Le definizioni sono il menu «Scheda», in ogni modo."""
    assert '#surface[data-sg-mode="phone"] .sidenav' in CSS
    assert '#surface[data-sg-mode="tablet"] .sidenav > :not(#nav-inroom-box) { display: none; }' in CSS
    strip = _fn(SHELL, "function paintStrip")
    assert 'if (state.mode === "desktop") {\n    const box = make("div", { className: "fo-ctl" });\n    box.dataset.ctl = "card";' not in strip
    assert 'box.dataset.ctl = "card";' in strip
    # il conteggio «n da trincea su m» è testo dell'opzione, non una lista
    assert 'tr("schede.count"' in strip
    # e la lente separata del tablet («Leggi con…») non c'è più: è lo stesso menu
    assert "unav-lens" not in _fn(SHELL, "function paintUnav")


def test_tutti_i_campi_diventa_solo_i_campi_da_trincea():
    toggle = _fn(SHELL, "function trenchToggle")
    assert "state.showAll = !state.trenchOnly;" in toggle
    strip = _fn(SHELL, "function paintStrip")
    assert "strip.append(trenchToggle());" in strip


def test_la_postura_e_l_interruttore():
    assert '|| (state.mode === "desktop" ? "desk" : "field");' in SHELL


def test_sul_tablet_le_voci_vanno_in_alto_e_la_cornice_e_centrata():
    place = _fn(SHELL, "function placeDesk")
    assert 'move("field-tabs", state.mode === "tablet" ? top : $("thumbbar"));' in place
    assert "max-width: 64rem;" in CSS and "margin-inline: auto;" in CSS


def test_la_lingua_dei_comandi_in_una_frase_sola():
    """«This node understands commands in Italiano» — due lingue in una frase."""
    paint = _fn(PAGE, "function paintCommandLanguage")
    assert "languageNameIn(language, LOCALE)" in paint
    assert "LOCALE_NAMES[language]" not in paint
    assert "Intl.DisplayNames" in _fn(PAGE, "function languageNameIn")


# ── C · la revisione della scrivania ─────────────────────────────────────────

@needs_node
def test_in_questa_stanza_per_numero():
    units = [{"number": "500"}, {"number": "25"}, {"name": "1.US5", "id": "x"},
             {"number": "13"}, {"number": "501"}, {"number": "3009"}, {"number": "42"}]
    got = esegui("import { byNumber } from './web/scrivania.js';"
                 f"console.log(JSON.stringify(byNumber({json.dumps(units)}).map(u => u.number || u.name)));")
    assert got == ["13", "25", "42", "500", "501", "3009", "1.US5"]
    assert 'nav.by_number' in DESK


def test_il_perche_dei_bottoni_spenti_si_legge():
    assert DESK.count("whyLine(") >= 3
    mappa = (WEB / "mappa.js").read_text(encoding="utf-8")
    assert mappa.count('class: "why"') == 2


def test_la_vista_unita_dice_cio_che_manca_e_porta_al_foglio():
    page = _fn(SHELL, "function drawUnitPage")
    assert 'tr("unit.left"' in page and 'state.view = "sheet"' in page


def test_l_ispettore_dice_il_nome_della_scheda_in_piccolo():
    foglio = (WEB / "foglio.js").read_text(encoding="utf-8")
    summary = _fn(foglio, "function paintSummary")
    assert 'el("p", { class: "fo-defname", text: def.title })' in summary
    assert 'el("h2", { text: def.title })' not in summary


# ── le parole ────────────────────────────────────────────────────────────────

NEW = ["tab.sheet", "tab.photos", "tab.deliver", "f.queue", "f.last", "f.pending",
       "f.need_net", "f.delivered", "f.pull", "f.pull_note", "f.pulling", "f.pulled",
       "f.nothing", "nav.by_number", "unit.left", "unit.open_sheet"]


@pytest.mark.parametrize("locale", ["en", "it"])
def test_le_parole_nuove_ci_sono_in_inglese_e_in_italiano(locale):
    start = PAGE.index(f"  {locale}: {{")
    block = PAGE[start:PAGE.index("\n  },", start)]
    missing = [k for k in NEW if f'"{k}":' not in block]
    assert missing == []
