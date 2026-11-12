"""La scrivania si apre sulla Scheda, non su «Detta» (MICRO, 14 novembre 2026).

Misurato da Cowork il 12 novembre: `shell.js` partiva con il pannello della voce
in ogni modo, e alla scrivania l'app si apriva su «Detta» con la striscia e
l'ispettore nascosti. Adesso:

* alla scrivania, all'avvio e passando da «In campo»: Scheda se c'è una scheda
  aperta o un'unità toccata per ultima, altrimenti Unità (`openingSection`);
* la sezione scelta si ricorda sul dispositivo (`sg.section.v1`) e un
  ricaricamento ci torna; «Detta» si ricorda come «voice»;
* in campo non cambia niente;
* la lingua: la scelta salvata vince, al primo avvio decide `navigator.language`.

Le prove nel browser (1440 px e telefono) stanno nel referto:
`.claude/wip/reports/2026-11-14-img/prove-apertura.py`.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from sorgenti import HA_NODE, esegui                              # noqa: E402

needs_node = pytest.mark.skipif(not HA_NODE, reason="node non c'è")


# ── 1 · la sezione con cui si apre (pura, eseguita) ──────────────────────────

@needs_node
@pytest.mark.parametrize("asked, expected", [
    ({}, "units"),                                         # primo avvio, stanza vuota
    ({"hasRecent": True}, "sheet"),                        # l'unità toccata per ultima
    ({"hasDef": True}, "sheet"),                           # una scheda aperta
    ({"saved": "voice", "hasDef": True}, "voice"),         # «Detta» scelta e ricaricata
    ({"saved": "finds"}, "finds"),
    ({"saved": "map", "hasRecent": True}, "map"),
    ({"saved": "sheet"}, "units"),                         # Scheda ricordata, niente da aprire
    ({"saved": "sheet", "hasRecent": True}, "sheet"),
    ({"saved": "nonsense", "hasRecent": True}, "sheet"),   # un valore estraneo non vale
])
def test_the_desk_opens_on_the_sheet_or_on_the_units(asked, expected):
    got = esegui("import { openingSection } from './web/scrivania.js';"
                 f"console.log(JSON.stringify(openingSection({json.dumps(asked)})));")
    assert got == expected


@needs_node
def test_what_is_kept_is_the_section_of_the_panel_in_front():
    got = esegui(
        "import { sectionToKeep, SECTION_KEY } from './web/scrivania.js';"
        "console.log(JSON.stringify([SECTION_KEY, ...['voice', 'work', 'scheda', 'index',"
        " 'finds', 'photos-sec', 'excavation', 'map', 'boh'].map(sectionToKeep)]));")
    assert got == ["sg.section.v1", "voice", "voice", "sheet", "units", "finds", "photos",
                   "excavation", "map", None]


# ── 2 · dove la conchiglia la usa (terza forza: shell.js tocca `document` al
#        primo livello e non si importa) ─────────────────────────────────────

SHELL = (ROOT / "web" / "shell.js").read_text(encoding="utf-8")


def test_the_boot_opens_the_desk_only_when_nothing_else_chose_a_panel():
    chain = SHELL[SHELL.index("void land().then("):]
    chain = chain[:chain.index(";\n")]
    assert "followHash()" in chain and "openDesk(true)" in chain
    assert 'state.panel === "voice"' in chain and "location.hash" in chain
    # e solo alla scrivania: in campo `openDesk` non fa niente
    body = SHELL[SHELL.index("async function openDesk("):]
    assert body.index('if (state.mode !== "desktop") return;') < body.index("loadRoom()")


def test_from_the_field_to_the_desk_opens_the_desk_without_the_kept_choice():
    body = SHELL[SHELL.index("function setMode(mode) {"):]
    body = body[:body.index("\n}\n")]
    assert re.search(r'was !== "desktop" && mode === "desktop" && state\.panel === "voice"', body)
    assert "openDesk(false)" in body


def test_the_choice_is_kept_only_at_the_desk_and_after_the_boot():
    body = SHELL[SHELL.index("function keepSection() {"):]
    body = body[:body.index("\n}\n")]
    assert 'if (!opened || state.mode !== "desktop") return;' in body
    assert "try { localStorage.setItem(SECTION_KEY" in body


def test_the_signature_does_not_put_dictate_beside_the_sheet():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    line = next(x for x in page.splitlines() if x.strip().startswith('$("work").hidden ='))
    assert "!voiceInFront" in line


# ── 3 · la lingua: la scelta salvata vince, poi `navigator.language` ─────────

def _pick_locale_source() -> str:
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    locales = re.search(r"^const LOCALES = \[.*?\];$", page, re.M).group(0)
    key = re.search(r'^const LOCALE_KEY = ".*?";$', page, re.M).group(0)
    start = page.index("function pickLocale() {")
    body = page[start:page.index("\n}\n", start) + 2]
    return "\n".join([locales, key, body])


def _pick(saved, language, storage_breaks=False):
    storage = ("{ getItem() { throw new Error('no storage'); } }" if storage_breaks
               else "{ getItem: (k) => (k === LOCALE_KEY ? " + json.dumps(saved) + " : null) }")
    js = (_pick_locale_source()
          + "\nObject.defineProperty(globalThis, 'navigator', { value: { language: "
          + json.dumps(language) + " }, configurable: true });"
          + "\nglobalThis.localStorage = " + storage + ";"
          + "\nconsole.log(JSON.stringify(pickLocale()));")
    done = subprocess.run(["node", "--input-type=module", "-e", js],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
@pytest.mark.parametrize("saved, language, expected", [
    ("it", "de-DE", "it"),       # la scelta salvata vince
    (None, "de-DE", "de"),       # primo avvio: decide il browser
    (None, "he", "he"),
    (None, "ja-JP", "en"),       # una lingua che l'interfaccia non ha → inglese
    ("xx", "es-ES", "es"),       # una scelta salvata estranea non vale
])
def test_the_saved_language_wins_and_the_first_boot_follows_the_browser(saved, language,
                                                                        expected):
    assert _pick(saved, language) == expected


@needs_node
def test_a_browser_without_storage_follows_the_browser_language():
    assert _pick(None, "pl-PL", storage_breaks=True) == "pl"
