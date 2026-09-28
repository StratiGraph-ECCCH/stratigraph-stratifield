"""Eight languages, and no locale with a hole.

English is the source language of every StratiGraph surface; beside it, the
languages of the project's case studies (T2.3) — `it` `ro` `el` `es` `pl` —
because those are the languages somebody will actually excavate in.

`en` and `it` are complete. The other four exist with **the same keys and empty
values**, which fall back to English. That is deliberate and it is not laziness:
**translating is the partners' work**, each for their own language and their own
dig. A string invented by us in a language none of us re-reads is worse than the
English it replaced.

What this file defends is the SLOT, not the translation:

* every locale carries every key — a locale with a hole is a missing sentence in
  a trench, and it would go unnoticed because the fallback hides it;
* nothing that is a domain TERM has been translated (US, DTC, ORCID, `crmdig:D7`):
  a translated term is a term lost;
* the coverage is printable, because that number is what goes to the partners.

Read from the page's SOURCE: the dictionaries live inline, by design — one HTML
file, no build step, nothing to fetch on a device three metres underground.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests.test_field_signature import LOCALES, PAGE   # noqa: E402

EXPECTED = ("en", "it", "ro", "el", "es", "pl", "he", "de")
#: complete today; the rest are the partners' to fill
COMPLETE = ("en", "it")
#: GENERATED from the partners' xlsx by `scripts/ui_strings.py` (24 October):
#: drafts, and only the keys the page shares with the file
GENERATED = ("he", "de")


def test_the_eight_locales_are_declared():
    # the ARRAY is the picker's order; the dictionaries may sit in another
    # order (the generated block comes before the empty slots)
    declared = re.search(r"const LOCALES = \[([^\]]*)\]", PAGE).group(1)
    assert tuple(re.findall(r'"(\w+)"', declared)) == EXPECTED, declared
    assert set(LOCALES) == set(EXPECTED), tuple(LOCALES)
    names = re.search(r"const LOCALE_NAMES = \{(.*?)\};", PAGE, re.S).group(1)
    assert 'he: "עברית"' in names and 'de: "Deutsch"' in names


def test_every_locale_carries_every_key_of_en():
    """A hole is invisible: the fallback shows English and nobody knows a string
    was never translated. So the KEYS are the contract, and they are filled in at
    load time by the page itself (`for (const code of LOCALES) …`)."""
    keys = set(LOCALES["en"])
    assert len(keys) > 25, f"only {len(keys)} keys — did the parser find them?"
    # the page normalises the empty locales at load; the SOURCE declares them
    # empty, so what is asserted here is that the normalisation exists
    assert "if (!(key in STRINGS[code])) STRINGS[code][key] = \"\";" in PAGE
    for code in COMPLETE:
        missing = keys - set(LOCALES[code])
        assert not missing, f"{code} is missing {sorted(missing)}"


def test_the_complete_locales_have_no_empty_value():
    for code in COMPLETE:
        empty = [key for key, value in LOCALES[code].items() if not value.strip()]
        assert not empty, f"{code} has empty values: {empty}"


def test_the_placeholders_survive_translation():
    """A `{n}` lost in translation is a sentence that says "note by" and stops."""
    for key, source in LOCALES["en"].items():
        wanted = set(re.findall(r"\{(\w+)\}", source))
        for code in COMPLETE + GENERATED:
            value = LOCALES[code].get(key, "")
            if not value:
                continue
            assert set(re.findall(r"\{(\w+)\}", value)) == wanted, f"{code}/{key}"


def test_no_domain_term_was_translated():
    """Terms, not text. An archaeologist writing in Polish leaves them alone, and
    so must we — see `stratigraph-brand/GLOSSARY.md`."""
    terms = ("US", "DTC", "ORCID", "HDT", "em.json", "crmdig")
    for code in COMPLETE + GENERATED:
        for key, value in LOCALES[code].items():
            for term in terms:
                if term in LOCALES["en"].get(key, ""):
                    assert term in value, f"{code}/{key} lost the term {term}"


def test_the_language_may_live_on_disk_and_the_token_may_not():
    """Reasoned twice, and worth a test because it is the kind of line somebody
    'tidies up': the locale is not a credential and it belongs to the DEVICE, not
    to the person — like the queue, unlike the token. A borrowed tablet must
    change author, not language."""
    assert 'localStorage.setItem(LOCALE_KEY' in PAGE
    stored = re.findall(r"localStorage\.setItem\(([^,]+),", PAGE)
    assert all("TOKEN" not in name for name in stored), stored


def test_the_html_lang_follows_the_active_locale():
    assert "document.documentElement.lang = code" in PAGE
    assert "document.documentElement.lang = LOCALE" in PAGE


def test_coverage_report():
    """Not an assertion — the number that goes to the partners."""
    keys = len(LOCALES["en"])
    print(f"\n  locale coverage ({keys} keys)")
    for code in EXPECTED:
        filled = sum(1 for value in LOCALES[code].values() if value.strip())
        print(f"    {code}  {filled:3}/{keys}"
              + ("  complete" if filled == keys else "  ← partners"))


# ── he · de, from the partners' xlsx (24 October) ───────────────────────────

def test_the_generated_locales_are_generated_and_not_written_by_hand():
    """Between the two marks, and nowhere else: a hand edit there is lost at the
    next run, and a hand-written `he` elsewhere would be a second source."""
    assert PAGE.count("// >>> ui_strings.py") == 1
    assert PAGE.count("// <<< ui_strings.py") == 1
    block = PAGE.split("// >>> ui_strings.py")[1].split("// <<< ui_strings.py")[0]
    for code in GENERATED:
        assert f"\n  {code}: {{" in block, code
        assert PAGE.count(f"\n  {code}: {{") == 1, code


def test_the_generated_locales_carry_real_text_and_no_invented_key():
    for code in GENERATED:
        filled = {k: v for k, v in LOCALES[code].items() if v.strip()}
        assert len(filled) > 40, (code, len(filled))
        assert set(filled) <= set(LOCALES["en"]), set(filled) - set(LOCALES["en"])
    assert LOCALES["he"]["view.sheet"] == "נייר"
    assert LOCALES["de"]["view.fields"] == "Felder"


def test_the_generated_block_matches_the_xlsx_when_the_file_is_here():
    """The file lives on the partners' OneDrive, not in this repository: where it
    is reachable, the page must be what the script would write from it."""
    import subprocess

    script = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "ui_strings.py"
    sys.path.insert(0, str(script.parent))
    import ui_strings                                             # noqa: E402

    if not ui_strings.DEFAULT_XLSX.is_file():
        import pytest
        pytest.skip(f"xlsx not reachable: {ui_strings.DEFAULT_XLSX}")
    done = subprocess.run([sys.executable, str(script), "--check"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_hebrew_turns_the_document_right_to_left_and_the_sheet_keeps_its_own():
    """The DOCUMENT follows the interface; the paper follows ITS card. An ICCD
    card is Italian and left to right even with the interface in Hebrew."""
    assert 'const RTL_LOCALES = new Set(["he"' in PAGE
    assert "document.documentElement.dir = scriptDir(code)" in PAGE
    assert "document.documentElement.dir = scriptDir(LOCALE)" in PAGE
    web = pathlib.Path(__file__).resolve().parent.parent / "web"
    for module in ("foglio.js", "scheda.js"):
        source = (web / module).read_text(encoding="utf-8")
        assert "dir: SG().scriptDir ? SG().scriptDir(def.lang)" in source, module
        assert 'lang: def.lang || ""' in source, module


def test_no_physical_left_or_right_is_left_in_the_apps_css():
    """Logical properties, so the layout mirrors in RTL by itself. The brand is a
    propagated copy (`sync-brand.sh`) and is not ours to edit."""
    web = pathlib.Path(__file__).resolve().parent.parent / "web"
    physical = re.compile(r"(?:margin|padding|border)-(?:left|right)\b|"
                          r"(?<![-\w])(?:left|right)\s*:|"
                          r"text-align:\s*(?:left|right)|float:\s*(?:left|right)")
    for sheet in ("shell.css", "scheda.css", "foglio.css"):
        text = re.sub(r"/\*.*?\*/", "", (web / sheet).read_text("utf-8"), flags=re.S)
        assert not physical.findall(text), (sheet, physical.findall(text))


def test_in_rtl_values_are_isolated_and_english_fallbacks_stay_english():
    """Measured in `he` on 24 October: without it «.If there is no microphone…»
    lost its full stop to the other end, and «· 0000-0002-…» its dot."""
    assert 'const iso = rtl ? (v) => "\\u2068" + v + "\\u2069"' in PAGE
    assert 'return rtl && !own ? "\\u2066" + said + "\\u2069" : said;' in PAGE
    # a window title is not a paragraph: no isolates there
    assert 't("app.subtitle").replace(/[\\u2066-\\u2069]/g, "")' in PAGE
    shell = (pathlib.Path(__file__).resolve().parent.parent / "web" / "shell.css"
             ).read_text(encoding="utf-8")
    assert "unicode-bidi: plaintext;" in shell
    assert ':root[dir="rtl"] #tb-prev, :root[dir="rtl"] #tb-next' in shell


def test_a_card_link_waits_for_the_listing_before_choosing_the_cards_language():
    """With the interface in `he` or `de`, a `#scheda=iccd-us-2021` link on a new
    device asked for the definition in Hebrew — the ICCD card declares it · en —
    and got «no definition»: `followHash` ran before the listing (and its
    languages) had been stored."""
    shell = (pathlib.Path(__file__).resolve().parent.parent / "web" / "shell.js"
             ).read_text(encoding="utf-8")
    assert "const schedeLoaded = loadSchede();" in shell
    assert "void land().then(() => schedeLoaded).then(() => followHash());" in shell
