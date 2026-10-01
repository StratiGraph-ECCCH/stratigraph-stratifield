"""THE ONE PLACE that reads a `stratigraph-templates` definition.

A scheda is not a new subsystem: it is the same act as `create_su` with another
INPUT SURFACE. Instead of filling one slot at a time by voice, many are filled
at once by looking at them. So this module does exactly one job — take a
definition written in the format `stratigraph-templates/SPEC.md` describes, and
hand it to this service in the shape it needs.

**If the format changes, it changes in here and nowhere else.** That is the
whole reason it is one module and not a helper next to whatever needs it.

════════════════════════════════════════════════════════════════════════════════
## WHAT IT READS, SINCE 2026-10-19: THE COMPILED FORM, VENDORED

`stratigraph-templates build` produces `dist/schede/<id>/<version>.json`: a
header (the definition's own version, a digest, the datamodel it was checked
against), the VISUAL half the module is drawn from, and the RECIPE — what to
send to a room, in the vocabulary of s3Dgraphy's five CRDT operations
(templates SPEC §9). `sync-schede.sh` copies that directory into `schede/`
here, and the copy is committed, exactly like `sync-brand.sh` does with the
theme. So:

* **one definition per id AND version.** A unit compiled with 1.0.0 is re-read
  with 1.0.0 even after 1.1.0 is vendored; `find(id)` alone means the latest;
* **the image carries its schede**, because they are in the repository — until
  tonight the only road was the dev-stack's bind-mount of a checkout, and the
  image on GHCR served none (audit 2026-10-17, B5a);
* **`STRATIGRAPH_SCHEDE_DIR` is a DEVELOPMENT override**, said in the log when
  it is used. It may hold compiled files or — for somebody editing a
  definition — the YAML sources. A YAML definition has NO recipe: it is drawn,
  and a save against it is refused by the generator with a sentence, because
  the only thing that knows what a box means to the graph is the compiled
  recipe, and this module does not compile.

════════════════════════════════════════════════════════════════════════════════
## WHAT THIS DELIBERATELY DOES NOT DO

**It does not import `stratigraph_templates`.** Not for tidiness — the Python
renderer over there runs on a SERVER, and the form has to work offline in a
browser on a telephone in a trench. Those two do not meet. The decision (E.D.,
5 September) is that the module is rendered in JavaScript from the definition
travelling as DATA, and the Python stays the authoring engine and the A4 print.
So this reads JSON (and YAML for the development override) and nothing else.

**It does not turn values into operations.** That is `app/operazioni.py`, which
reads `Scheda.recipe`; this module only hands the recipe over.

**It does not interpret.** Labels, `required`, `repeatable`, vocabularies and
`recorded_in` are READ. If a rule appears here that the format already
expresses, that is a second implementation of the standard in another place —
which is the defect measured in pyarchinit-mini, where the same sheet was
written twice (786 lines of form, 4,864 of PDF) and seven labels were wrong on
one side only.

**It does not translate.** The labels come from the definition, in the
languages the definition declares. The interface's own chrome is a different
dictionary and stays a different dictionary: what the STANDARD says is not
translatable by us. Asking for a language a definition does not declare is an
**error**, not a degraded mode — `SPEC.md` §1.5 states it, and
`labels_for` refuses rather than falling back.

## THE ONE THING IT ADDS: `recorded_in` DEFAULTS TO NOTHING

`SPEC.md` §1.6: three values, `trench` · `lab` · `unknown`, and the absence of
the marker means `unknown`. **A consumer must not read silence as «trench».**
So `trench_fields()` returns only what the definition SAYS is trench, and a
definition with no markers yields an empty list — which is the honest answer,
and the reason a phone form built on it shows nothing rather than everything.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

#: Where a node keeps the definitions it serves. A DIRECTORY, so that adding a
#: standard is dropping a file in — which is the format's own claim, and the
#: thing tonight's end-of has to demonstrate: a definition nobody has seen must
#: reach the telephone without rebuilding the front-end.
SCHEDE_DIR_VARIABLE = "STRATIGRAPH_SCHEDE_DIR"

#: The three values of `recorded_in`, and the default. Repeated from the format
#: rather than imported, because importing would mean a Python dependency on
#: `stratigraph-templates` — and `test_scheda.py` asserts that these agree with
#: that repository's `SPEC.md` when it is present, so the repetition cannot
#: drift silently.
TRENCH = "trench"
LAB = "lab"
UNKNOWN = "unknown"
RECORDED_IN_VALUES = (UNKNOWN, TRENCH, LAB)


class SchedaError(ValueError):
    """A definition this node cannot serve, in a sentence that says why."""


class Scheda:
    """One definition, read. Immutable as far as this service is concerned."""

    def __init__(self, doc: Dict[str, Any], *, path: Optional[str] = None):
        #: THE COMPILED FORM (templates SPEC §9) or a YAML source (SPEC §1).
        #: Both are turned into ONE `raw` with the YAML's shape, so that every
        #: reader below — the labels, the sheet, `recorded_in` — has one input
        #: and cannot drift between the two. What only the compiled form has
        #: (version, digest, datamodel, recipe) lives in its own attributes.
        self.compiled = isinstance(doc, dict) and doc.get("format") == COMPILED_FORMAT
        if self.compiled:
            template = _raw_from_compiled(doc)
            header = doc.get("header") or {}
            self.version: str = str(header.get("version") or "")
            self.digest: str = str(header.get("digest") or "")
            self.datamodel: Dict[str, Any] = dict(header.get("datamodel") or {})
            #: THE RECIPE — read by `app/operazioni.py`, never interpreted here.
            self.recipe: Optional[Dict[str, Any]] = dict(doc.get("recipe") or {})
        else:
            template = doc.get("template") if isinstance(doc, dict) else None
            if not isinstance(template, dict):
                raise SchedaError(
                    "questo file non è una definizione di scheda: né la forma "
                    "compilata (`format: " + COMPILED_FORMAT + "`) né la chiave "
                    "`template` di primo livello (SPEC.md §1)")
            self.version = str(template.get("version") or "")
            self.digest = ""
            self.datamodel = {}
            #: A YAML SOURCE HAS NO RECIPE. It can be drawn and not saved.
            self.recipe = None
        self.raw = template
        self.path = path
        self.id = str(template.get("id") or "")
        if not self.id:
            raise SchedaError("una definizione senza `id` non è servibile")
        self.languages: List[str] = list(template.get("languages") or [])
        self.source_language = str(template.get("source_language") or "")
        self.standard: Dict[str, Any] = dict(template.get("standard") or {})
        self.fields: List[Dict[str, Any]] = list(template.get("fields") or [])
        #: WHICH FIELDS SPELL THE UNIT'S NAME, from `identity.human_key`
        #: (SPEC §1.2). The module needs it so the box that says which unit the
        #: record is about is the definition's own, not a second one beside it
        #: — and it cannot be `us` hard-coded here, because the Spanish sheet
        #: calls it `contexto`.
        identity = template.get("identity") or {}
        self.human_key: List[str] = list(
            ((identity.get("human_key") or {}).get("fields")) or [])
        #: WHICH of those fields IS the unit — `identity.human_key.unit_field`,
        #: added to SPEC §1.2 on 2026-09-24. It is READ and passed on, not
        #: resolved here: this module does not interpret, and the rule for what
        #: to do when it is absent belongs to the consumer that has to draw a
        #: box (`keyField` in `web/scheda.js`).
        #:
        #: WHY IT HAD TO TRAVEL. Until tonight it did not, and the module took
        #: the LAST field of the key. Measured against this node, on the
        #: Hungarian sheet: `human_key = [retegszam, lelohely]`, declared
        #: designator `retegszam` — the FIRST — and the browser chose
        #: `lelohely`, the place name. A scheda filed under «Aquincum» instead
        #: of under the layer number, and nothing anywhere would have said so.
        #:
        #: ONE FIELD, NOTHING TO CHOOSE (SPEC §1.2, 2026-10-26). A key of a
        #: single field may omit `unit_field`, and the compiled form already
        #: writes it resolved (`unit_field_of`). The YAML path read it as "" —
        #: harmless until the first single-field key (iDAI.field `identifier`)
        #: made the two paths draw different modules. Same rule, same answer.
        declared_unit = str(((identity.get("human_key") or {}).get("unit_field")) or "")
        self.unit_field: str = declared_unit or (
            self.human_key[0] if len(self.human_key) == 1 else "")
        self.paragraphs: List[Dict[str, Any]] = list(
            template.get("paragraphs") or [])
        if not self.fields:
            raise SchedaError(f"«{self.id}» non dichiara nessun campo")
        self._by_id = {str(f.get("id")): f for f in self.fields}
        self._datamodel_check: Optional[Dict[str, Any]] = None
        if self.compiled:
            self.datamodel_check()   # said in the log AT LOAD, not at first draw

    def datamodel_check(self) -> Optional[Dict[str, Any]]:
        """The scheda's datamodel against this node's (see `check_datamodel`).
        None for a YAML source: it was never compiled against anything."""
        if not self.compiled:
            return None
        if self._datamodel_check is None:
            self._datamodel_check = check_datamodel(self.datamodel, datamodel_here())
            _say_datamodel(self, self._datamodel_check)
        return self._datamodel_check

    @property
    def ref(self) -> Dict[str, str]:
        """WHICH definition, which version — what a unit records (audit B5b)."""
        out = {"template": self.id, "version": self.version}
        if self.digest:
            out["digest"] = self.digest
        return out

    # ── what the definition says ────────────────────────────────────────────

    def title(self, lang: str) -> str:
        return labels_for(self.standard.get("title") or {}, lang,
                          f"il titolo di «{self.id}»")

    def field(self, fid: str) -> Dict[str, Any]:
        try:
            return self._by_id[fid]
        except KeyError:
            raise SchedaError(
                f"«{self.id}» non ha un campo «{fid}»") from None

    def recorded_in(self, fid: str) -> str:
        """Where a field is filled in — ABSENT MEANS `unknown`.

        Read through this rather than off the dict, so the default lives in one
        place and no caller can accidentally spell it `!= "lab"`.
        """
        value = self.field(fid).get("recorded_in")
        if value is None:
            return UNKNOWN
        if value not in RECORDED_IN_VALUES:
            raise SchedaError(
                f"«{self.id}», campo «{fid}»: recorded_in={value!r} non è uno "
                f"di {list(RECORDED_IN_VALUES)}. Una definizione con un valore "
                f"che non esiste non si serve: il modulo non saprebbe se "
                f"mostrare quella casella o no.")
        return str(value)

    def trench_fields(self) -> List[str]:
        """What a telephone form shows. Nothing more, and nothing by default."""
        return [str(f.get("id")) for f in self.fields
                if self.recorded_in(str(f.get("id"))) == TRENCH]

    def counts(self) -> Dict[str, int]:
        tally = {value: 0 for value in RECORDED_IN_VALUES}
        for f in self.fields:
            tally[self.recorded_in(str(f.get("id")))] += 1
        return tally

    # ── what the browser gets ───────────────────────────────────────────────

    def for_browser(self, lang: str) -> Dict[str, Any]:
        """The definition, as DATA, in one language.

        Flattened to one language on purpose: a phone in a trench does not need
        five, and `labels_for` has already refused a language the definition
        does not declare — so what crosses the wire cannot contain a label
        nobody wrote.

        Everything the JS renderer needs is here and nothing it does not:
        `graph` bindings and `provenance` stay behind, because the module does
        not decide what a field means to the graph.

        **The `sheet` TRAVELS since 2026-10-16**, and that is a decision
        reversed, not a detail. Until then it stayed behind with the words «the
        module does not draw an A4»: the print was the Python renderer's, and
        sending the grid to the browser would have looked like sending the
        second implementation along with the first. E.D. decided on 27
        September that at the desk the scheda is filled IN ON THE SHEET — the
        two faces of the A4, where an archaeologist already knows where every
        box is — so the browser now draws the grid the definition declares.

        What crosses is **the geometry and nothing else** (`_sheet_for_browser`
        whitelists it): page, margins, sides with their label in THIS language,
        rows in mm, cells in % of the row, blocks, `rotated`, `label: none`. A
        cell names its field by id and the field's meaning stays in `fields`,
        where the graph binding has already been left out. Still one
        implementation of the standard: the grid is READ from the definition,
        the Python print and the JS sheet both read the same rows.

        A definition with no `sheet` sends no `sheet` key — not an empty one.
        The browser then falls back to the field list and says so: an empty
        sheet would look like a standard with no boxes.
        """
        if lang not in self.languages:
            raise SchedaError(
                f"«{self.id}» dichiara {self.languages} e non «{lang}». "
                f"Chiedere una lingua che la definizione non ha è un errore, "
                f"non una modalità degradata: servirebbe una parola che "
                f"nessuno ha scritto per quello standard.")
        out = {
            "id": self.id,
            "lang": lang,
            "title": self.title(lang),
            "standard": {k: self.standard.get(k)
                         for k in ("authority", "code", "version", "invented")},
            "languages": self.languages,
            "paragraphs": [
                {"id": str(p.get("id")),
                 "label": labels_for(p.get("labels") or {}, lang,
                                     f"il paragrafo «{p.get('id')}»"),
                 "fields": list(p.get("fields") or [])}
                for p in self.paragraphs],
            "fields": [self._field_for_browser(f, lang) for f in self.fields],
            "human_key": list(self.human_key),
            "unit_field": self.unit_field,
            "counts": self.counts(),
            # WHICH version the module is drawn from, and whether it can be
            # saved at all: a YAML source served by the development override
            # has no recipe, and a form that let somebody fill 58 boxes before
            # saying so would be the cruellest place to learn it.
            "version": self.version,
            "saveable": self.recipe is not None,
        }
        # THE DATAMODEL IT WAS BUILT ON, against this node's: never blocking,
        # always visible (see `check_datamodel`). Absent for a YAML source.
        check = self.datamodel_check()
        if check is not None:
            out["datamodel_check"] = check
        # The running head of the sheet spells the unit with the definition's
        # own pattern (SPEC §1.2), so the browser does not invent «US 12».
        pattern = ((self.raw.get("identity") or {}).get("human_key")
                   or {}).get("pattern")
        if pattern:
            out["human_key_pattern"] = str(pattern)
        sheet = self.raw.get("sheet")
        if isinstance(sheet, dict) and sheet.get("sides"):
            out["sheet"] = self._sheet_for_browser(sheet, lang)
        return out

    # ── the A4, as geometry ─────────────────────────────────────────────────

    def _sheet_for_browser(self, sheet: Dict[str, Any],
                           lang: str) -> Dict[str, Any]:
        """The grid of SPEC §4, WHITELISTED key by key.

        Copied by name and not passed through, so that whatever an author adds
        to a cell tomorrow does not reach the telephone by accident — the same
        reason `graph` is left out of the fields. Labels are flattened to one
        language with `labels_for`, and refused the same way.
        """
        margins = sheet.get("margins_mm") or {}
        return {
            "page": str(sheet.get("page") or "A4"),
            "margins_mm": {k: float(margins.get(k) or 0)
                           for k in ("top", "right", "bottom", "left")},
            "sides": [
                {"id": str(side.get("id")),
                 "label": labels_for(side.get("labels") or {}, lang,
                                     f"la facciata «{side.get('id')}» di "
                                     f"«{self.id}»"),
                 "rows": self._rows_for_browser(side.get("rows") or [], lang)}
                for side in sheet.get("sides") or []],
        }

    def _rows_for_browser(self, rows: List[Dict[str, Any]],
                          lang: str) -> List[Dict[str, Any]]:
        return [{"h": float(row.get("h") or 0),
                 "cells": [self._cell_for_browser(c, lang)
                           for c in row.get("cells") or []]}
                for row in rows]

    def _cell_for_browser(self, cell: Dict[str, Any],
                          lang: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {"w": float(cell.get("w") or 0)}
        # A BLOCK is a cell with a `block` name or rows of its own. Not `rows is
        # not None`: the compiled form spells every cell completely, so a plain
        # field cell arrives with `rows: []` and `block: null`.
        if cell.get("block") or cell.get("rows"):
            # A BLOCK: a nested grid. Its label is optional (`label: none`, or
            # simply no `block_labels`); when it is declared it is a label like
            # any other, and a missing language is refused like any other.
            out["block"] = str(cell.get("block") or "")
            labels = cell.get("block_labels") or {}
            if labels and cell.get("label") != "none":
                out["label"] = labels_for(labels, lang,
                                          f"il blocco «{cell.get('block')}» "
                                          f"di «{self.id}»")
            if cell.get("rotated"):
                out["rotated"] = True
            out["rows"] = self._rows_for_browser(cell["rows"], lang)
            return out
        if cell.get("field"):
            fid = str(cell["field"])
            self.field(fid)       # a box for a field that does not exist: refuse
            out["field"] = fid
            if cell.get("label") == "none":
                out["label"] = "none"
        # …and otherwise a SPACE: `{w}` alone, an empty cell nobody writes in.
        return out

    def _field_for_browser(self, f: Dict[str, Any], lang: str) -> Dict[str, Any]:
        fid = str(f.get("id"))
        out: Dict[str, Any] = {
            "id": fid,
            # THE LABEL COMES FROM THE DEFINITION, and its absence is an error.
            # This is the line that makes end-of §8 demonstrable: remove a
            # label from a definition and the scheda refuses instead of
            # fishing a word out of the interface's dictionary.
            "label": labels_for(f.get("labels") or {}, lang,
                                f"il campo «{fid}» di «{self.id}»"),
            "type": str(f.get("type") or ""),
            "required": bool(f.get("required", False)),
            "repeatable": bool(f.get("repeatable", False)),
            "recorded_in": self.recorded_in(fid),
        }
        if f.get("max_len"):
            out["max_len"] = f["max_len"]
        help_text = f.get("help") or {}
        if help_text:
            # Help is OPTIONAL, so a definition that has it in one language and
            # not another is not broken — unlike a label. `.get`, deliberately.
            said = help_text.get(lang)
            if said:
                out["help"] = said
        options = f.get("options") or []
        if options:
            out["options"] = [
                {"value": str(o.get("value")),
                 "label": labels_for(o.get("labels") or {}, lang,
                                     f"l'opzione «{o.get('value')}» di «{fid}»")}
                for o in options]
        vocabulary = f.get("vocabulary") or {}
        if vocabulary.get("scheme"):
            # The SCHEME's name only: resolving a vocabulary is the authoring
            # engine's job and needs a server. The form says which controlled
            # list a box belongs to, and a node with the vocabulary can offer
            # it (`GET /v1/vocabolario/{scheme}`); a node without it still
            # shows the box.
            #
            # A norm's scheme that is only DECLARED may name a PROVISIONAL one
            # (stratigraph-templates SPEC §3.2, 2026-09-27): the box keeps
            # citing the norm and is OFFERED the concepts of the stand-in —
            # the one `sync-schede.sh` vendored with concepts.
            out["vocabulary"] = str(vocabulary.get("provisional") or vocabulary["scheme"])
            if vocabulary.get("provisional"):
                out["vocabulary_norm"] = str(vocabulary["scheme"])
        if out["type"] == "quantity_list":
            out["measures"] = self._measures_for_browser(fid, lang)
        return out

    def _measures_for_browser(self, fid: str, lang: str) -> Dict[str, Any]:
        """WHAT a row of a measurement box may say it measures (2026-10-22).

        A `quantity_list` value is rows of `{qualia, label, value, unit}` (SPEC
        §1.5): the QUALIA is part of the value, so the row widget has to offer
        the qualia by name. They are read from the datamodel
        (`em_qualia_types.json`, the ones that measure: a number with units),
        not written here — and not from the verdict either, which stays behind.

        The one thing the recipe adds is the box's DEFAULT (`defaults
        .$item.qualia`: QUOTE is `elevation` when a row says nothing), and it
        is offered first.

        THE NAMES IN THE CARD'S LANGUAGE (2026-10-24). The datamodel now has
        them in every language (`datamodel_translations.json`, s3Dgraphy), and
        they are read through ONE road, the library's `qualia_label`, in the
        language of THE CARD — not of the interface: an ICCD card says
        «Spessore» even with the interface in Hebrew. Falling back to English is
        the library's; `label_lang` says when that happened, so the widget can
        show the word for what it is. They travel inside the definition, so
        the definition's offline cache (`scheda.js::definitionFor`) carries
        them too. The row's own `label` («spessore max») still wins.
        """
        entry = ((self.recipe or {}).get("fields") or {}).get(fid) or {}
        default = str((entry.get("defaults") or {}).get("$item.qualia") or "")
        if not default and self.recipe is None:
            # un sorgente YAML (la sovrascrittura di sviluppo) non ha ricetta:
            # il default è dove la ricetta lo compila, `graph.qualia`. Le due
            # forme devono disegnare lo stesso modulo (test_scheda).
            source = self._by_id.get(fid) or {}
            default = str(((source.get("graph") or {}).get("qualia")) or "")
        qualia = measuring_qualia(lang)
        if default:
            qualia = ([q for q in qualia if q["id"] == default]
                      + [q for q in qualia if q["id"] != default])
        return {"qualia": qualia, "default": default or None}


def labels_for(labels: Dict[str, Any], lang: str, what: str) -> str:
    """A label in one language, or a refusal naming what is missing.

    NO FALLBACK, and this is the measured reason: `pdf_export` in
    pyarchinit-mini resolved sheet labels against a generic i18n dictionary and
    printed «Notifica» where the sheet says FLOTTAZIONE, «Struttura Valida»
    where it says AREA — seven labels wrong, and wrong only in print. A missing
    label is a hole in the definition and has to read as one.
    """
    said = (labels or {}).get(lang)
    if said in (None, ""):
        raise SchedaError(
            f"{what}: manca l'etichetta in «{lang}». Le etichette di una "
            f"scheda vengono dalla definizione dello standard, non dal "
            f"dizionario dell'interfaccia — quindi questa non si sostituisce "
            f"con una parola generica, si segnala.")
    return str(said)


# ── loading ──────────────────────────────────────────────────────────────────

#: What `stratigraph-templates build` writes (templates SPEC §9). Read by name:
#: a JSON file that is not this is not a definition.
COMPILED_FORMAT = "stratigraph-templates/compiled-definition"
INDEX_FORMAT = COMPILED_FORMAT + "/index"

#: WHERE THE VENDORED COPY LIVES — `schede/` beside `app/`, filled by
#: `sync-schede.sh` and committed. The Dockerfile copies it into the image.
VENDORED_DIR = pathlib.Path(__file__).resolve().parent.parent / "schede"
#: The concepts of the schemes the vendored schede name (`sync-schede.sh`).
#: Beside `schede/` and not inside: every `*.json` there is read as a scheda.
VOCABULARY_DIR = pathlib.Path(__file__).resolve().parent.parent / "vocabolari"

_log = logging.getLogger("stratigraph-chatbot.scheda")
_said_override: set = set()


# ── THE DATAMODEL A SCHEDA WAS BUILT ON, AGAINST THE ONE HERE (2026-10-01) ──
#
# A compiled scheda says, in `header.datamodel`, which s3Dgraphy datamodel it
# was checked against: one version per datamodel and, since stratigraph-
# templates snapshot format 4, `digest` — s3Dgraphy's datamodel FINGERPRINT
# (`api.datamodel_fingerprint`). Until tonight nobody read it (the audit of the
# chain, D3): a scheda compiled against nodes 1.6.12 was served by a node
# carrying 1.6.17 and nothing said so.
#
# It does NOT block. The recipe is five CRDT operations and the room applies
# them with its own s3Dgraphy; a scheda one version behind usually still says
# the right thing, and refusing it in a trench would cost the record. What it
# does is make the difference VISIBLE: once in the log, and on the scheda
# itself (`for_browser` → `datamodel_check`, drawn by `web/scheda.js`).
#
# Three answers, and a fourth when the question cannot be asked:
#   aligned    — same digest;
#   differs    — another digest: each datamodel that moved is named;
#   no_digest  — a scheda compiled before the fingerprint: the versions it has
#                are compared, and the softer warning says it cannot be checked
#                in full;
#   unchecked  — this node's s3dgraphy cannot compute the fingerprint (older
#                than the one that introduced it).
#
# WHICH FILES (2026-10-26, s3Dgraphy dev25): a scheda compiled since then also
# carries `header.datamodel.files`, the digest and version of each datamodel
# file stratigraph-templates READ to build it (nodes, node_registry,
# connections, qualia). When it is there, those files are compared and nothing
# else: a node whose visual rules or translations moved serves the same scheda,
# and saying «another datamodel» about it would be a warning about nothing. The
# one `digest` is still carried and shown; without `files` (an older scheda) it
# is what is compared, as before.

#: how the log names each datamodel; the interface has its own keys (`dm.*`)
DATAMODEL_NAMES_IT = {
    "nodes": "nodi", "node_registry": "registro dei nodi",
    "connections": "connessioni", "visual_rules": "regole visive",
    "qualia": "qualia", "translations": "traduzioni",
}
_said_datamodel: set = set()
_here_cache: Dict[str, Any] = {}


def datamodel_here() -> Optional[Dict[str, Any]]:
    """The fingerprint of the s3dgraphy this node carries, or None when that
    s3dgraphy cannot compute one. Read once: the package does not change under a
    running process."""
    if "fp" not in _here_cache:
        try:
            from s3dgraphy.datamodel import datamodel_fingerprint
            _here_cache["fp"] = datamodel_fingerprint()
        except Exception as exc:          # ImportError on an older s3dgraphy
            _log.info("[scheda] questa s3dgraphy non calcola l'impronta del "
                      "datamodel (%s): le schede non si controllano", exc)
            _here_cache["fp"] = None
    return _here_cache["fp"]


def check_datamodel(declared: Dict[str, Any],
                    here: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """`header.datamodel` of a scheda against the fingerprint `here`.

    Returns `{state, differences: [{name, scheda, here}], digest, here_digest}`.
    A difference with `name: None` means «same versions, different content».
    Pure: no log, no cache — `Scheda.datamodel_check` does those.
    """
    out: Dict[str, Any] = {"state": "unchecked", "differences": [],
                           "digest": declared.get("digest"),
                           "here_digest": (here or {}).get("digest")}
    if here is None:
        return out
    versions = here.get("versions") or {}
    files = declared.get("files")
    if isinstance(files, dict) and files:
        # the files the scheda was built from, each on its own digest
        digests = here.get("digests") or {}
        out["compared"] = sorted(files)
        diffs = [{"name": name, "scheda": (entry or {}).get("version"),
                  "here": versions.get(name)}
                 for name, entry in sorted(files.items())
                 if (entry or {}).get("version") != versions.get(name)]
        moved = [name for name, entry in sorted(files.items())
                 if (entry or {}).get("digest") != digests.get(name)]
        out["differences"] = diffs
        if not moved and not diffs:
            out["state"] = "aligned"
        else:
            out["state"] = "differs"
            if not diffs:
                out["differences"] = [{"name": None, "scheda": None, "here": None}]
        return out
    diffs = [{"name": name, "scheda": declared.get(name), "here": version}
             for name, version in versions.items()
             if name in declared and declared.get(name) != version]
    out["differences"] = diffs
    if not declared.get("digest"):
        out["state"] = "no_digest"
    elif declared["digest"] == here.get("digest"):
        out["state"] = "aligned"
    else:
        out["state"] = "differs"
        if not diffs:
            out["differences"] = [{"name": None, "scheda": None, "here": None}]
    return out


def _say_datamodel(scheda: "Scheda", check: Dict[str, Any]) -> None:
    """Once per scheda version and datamodel: the directory is re-read on every
    request, and a warning repeated at every listing is a warning nobody reads."""
    key = (scheda.id, scheda.version, check.get("digest"), check["state"])
    if check["state"] == "aligned" or key in _said_datamodel:
        return
    _said_datamodel.add(key)
    what = "; ".join(
        f"{DATAMODEL_NAMES_IT.get(d['name'], d['name'])} {d['scheda']}, qui {d['here']}"
        if d["name"] else "stesse versioni, contenuto diverso"
        for d in check["differences"])
    if check["state"] == "differs":
        _log.warning("[scheda] %s %s costruita su un altro datamodel: %s",
                     scheda.id, scheda.version, what)
    elif check["state"] == "no_digest":
        _log.info("[scheda] %s %s compilata prima dell'impronta del datamodel: "
                  "non si controlla per intero%s", scheda.id, scheda.version,
                  f" ({what})" if what else "")


def _raw_from_compiled(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The compiled form, in the YAML's shape (`template: {…}`).

    Read, not interpreted: the VISUAL half (SPEC §9.2) already holds the
    identity, the paragraphs, the fields with labels in every declared
    language, and the sheet. The only reshaping is `identity.human_key`, which
    the compiled form spells as a flat list plus `pattern` and `unit_field`
    beside it, and the YAML as `{fields, pattern, unit_field}`.
    """
    header = doc.get("header") or {}
    visual = doc.get("visual") or {}
    identity = dict(visual.get("identity") or {})
    human_key = identity.get("human_key")
    if isinstance(human_key, list):
        identity["human_key"] = {"fields": list(human_key),
                                 "pattern": identity.get("pattern"),
                                 "unit_field": identity.get("unit_field")}
    return {
        "id": header.get("id"),
        "version": header.get("version"),
        "standard": header.get("standard") or {},
        "source_language": header.get("source_language"),
        "languages": header.get("languages") or [],
        "identity": identity,
        "provenance": visual.get("provenance") or {},
        "paragraphs": visual.get("paragraphs") or [],
        "fields": visual.get("fields") or [],
        "sheet": visual.get("sheet"),
        "notes": visual.get("notes") or {},
    }


def load(path: Any) -> Scheda:
    """One definition from a file: compiled JSON, or a YAML source."""
    where = pathlib.Path(path)
    try:
        text = where.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SchedaError(f"nessuna definizione in {where}") from None
    if where.suffix == ".json":
        try:
            doc = json.loads(text)
        except ValueError as exc:
            raise SchedaError(f"{where} non è JSON leggibile: {exc}") from exc
        return Scheda(doc, path=str(where))
    import yaml
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SchedaError(f"{where} non è YAML leggibile: {exc}") from exc
    return Scheda(doc, path=str(where))


def schede_dir(environ: Optional[Dict[str, str]] = None) -> Optional[pathlib.Path]:
    """The directory a scheda is looked for FIRST, or None.

    **The development override when it is set, the vendored copy otherwise.**
    Until 2026-10-19 absence of the variable meant NO schede; now the
    repository carries them, so absence means «the ones this build was
    released with».

    None only when neither exists (a checkout that never ran `sync-schede.sh`):
    then the node takes dictation, which is what it always was.
    """
    override = _override_dir(environ)
    if override is not None:
        return override
    return VENDORED_DIR if VENDORED_DIR.is_dir() else None


def _override_dir(environ: Optional[Dict[str, str]] = None) -> Optional[pathlib.Path]:
    source = environ if environ is not None else os.environ
    raw = (source.get(SCHEDE_DIR_VARIABLE) or "").strip()
    if not raw:
        return None
    where = pathlib.Path(raw).expanduser()
    if not where.is_dir():
        _log.warning("[scheda] %s=%s non è una directory: uso la copia "
                     "vendorata", SCHEDE_DIR_VARIABLE, where)
        return None
    if str(where) not in _said_override:
        _said_override.add(str(where))
        _log.warning("[scheda] %s=%s: sovrascrittura di SVILUPPO, letta prima "
                     "della copia vendorata (%s). Una definizione YAML qui si "
                     "disegna ma non si salva; se la stessa id è vendorata "
                     "compilata, vince quella compilata.", SCHEDE_DIR_VARIABLE,
                     where, VENDORED_DIR)
    return where


def _semver(version: str) -> tuple:
    parts = []
    for piece in str(version or "0").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _read_dir(where: pathlib.Path) -> List[Scheda]:
    found: List[Scheda] = []
    candidates = (sorted(where.rglob("*.json")) + sorted(where.rglob("*.yaml"))
                  + sorted(where.rglob("*.yml")))
    for candidate in candidates:
        if candidate.name == "index.json":
            continue          # the index names the files; it is not one
        try:
            found.append(load(candidate))
        except SchedaError as problem:
            _log.warning("[scheda] %s non servibile: %s", candidate, problem)
    return found


def _all(environ: Optional[Dict[str, str]] = None) -> List[Scheda]:
    """EVERY definition this node can see, every version, override FIRST.

    **The override is ADDED to the vendored copy, not a replacement.** Measured
    the night it was written: the dev-stack points `STRATIGRAPH_SCHEDE_DIR` at
    the YAML sources of `stratigraph-templates/templates`, and a replacement
    would have left that node with definitions that have no recipe — the voice
    and the module would have stopped saving. So the vendored compiled form is
    always there underneath, and a YAML source only wins where nothing
    compiled has its id.
    """
    found: List[Scheda] = []
    override = _override_dir(environ)
    if override is not None:
        found.extend(_read_dir(override))
    if VENDORED_DIR.is_dir() and (override is None
                                  or override.resolve() != VENDORED_DIR.resolve()):
        found.extend(_read_dir(VENDORED_DIR))
    return found


def available(environ: Optional[Dict[str, str]] = None) -> List[Scheda]:
    """Every definition this node can serve — THE LATEST version of each —
    in id order.

    A DIRECTORY LISTING, and that is the point: dropping the Spanish sheet in
    makes it appear, with no code change and no release. A file that does not
    parse is SKIPPED and named in the log rather than taking the others down —
    one bad definition must not cost a person their whole scheda list.

    For one id: a COMPILED form beats a YAML source (it is the one that can be
    saved), a higher version beats a lower one, and at equal version the
    override beats the vendored copy (it is listed first).
    """
    best: Dict[str, Scheda] = {}
    for scheda in _all(environ):
        held = best.get(scheda.id)
        if held is None or (scheda.compiled, _semver(scheda.version)) > (
                held.compiled, _semver(held.version)):
            best[scheda.id] = scheda
    return sorted(best.values(), key=lambda s: s.id)


def find(scheda_id: str, environ: Optional[Dict[str, str]] = None, *,
         version: Optional[str] = None) -> Optional[Scheda]:
    """One definition: the latest, or exactly `version`.

    A version asked for and not present is None, not the latest: a unit
    compiled with 1.0.0 read back with 1.1.0 would be read with rules that are
    not the ones it was written with, and the caller has to be able to SAY so.
    """
    if not version:
        return next((s for s in available(environ) if s.id == scheda_id), None)
    matches = [s for s in _all(environ)
               if s.id == scheda_id and s.version == str(version)]
    # the YAML source of a version declares the same number as its compiled
    # form: the compiled one is the one with a recipe, so it wins
    matches.sort(key=lambda s: not s.compiled)
    return matches[0] if matches else None


# ── i vocabolari e le qualia, per i widget (2026-10-22) ────────────────────────

#: I tipi di dato del datamodel che MISURANO: un numero con un'unità.
_MEASURING = ("float", "integer", "percentage")


def measuring_qualia(lang: str = "en") -> List[Dict[str, Any]]:
    """Le qualia che una riga di misura può dichiarare, DAL DATAMODEL.

    `em_qualia_types.json` di s3Dgraphy, nell'ordine in cui le dichiara: id,
    nome, unità, e il gruppo (la sottocategoria: dimensional, spatial…) perché
    trenta voci in fila non si leggono. Solo quelle con un tipo numerico e delle
    unità: «colore» è una qualia, ma non si misura in metri.

    `name` resta il nome inglese del datamodel; `label` e `group_label` sono in
    `lang` (la lingua della SCHEDA), letti da `qualia_label` di s3Dgraphy e da
    nessun'altra parte. `label_lang` compare quando la lingua non è fra quelle
    del datamodel e la parola è quindi l'inglese (una ficha ungherese: «hu»).
    """
    from s3dgraphy.nodes.base_node import load_json_mapping

    labels = _qualia_labels()
    base = (lang or "en").split("-")[0].split("_")[0].lower()
    fallen = labels is not None and base not in labels.LANGUAGES

    out: List[Dict[str, Any]] = []
    for category in load_json_mapping("em_qualia_types.json").get("qualia_categories") or []:
        for group, sub in (category.get("subcategories") or {}).items():
            for q in sub.get("qualia") or []:
                if q.get("data_type") in _MEASURING and q.get("units"):
                    name = str(q.get("name") or q["id"])
                    item: Dict[str, Any] = {
                        "id": str(q["id"]), "name": name,
                        "units": [str(u) for u in q["units"]],
                        "group": str(group)}
                    if labels is not None:
                        item["label"] = labels.qualia_label(item["id"], lang) or name
                        item["group_label"] = (
                            labels.qualia_subcategory_label(str(group), lang)
                            or str(group))
                        if fallen:
                            item["label_lang"] = "en"
                    out.append(item)
    return out


def _qualia_labels() -> Any:
    """Il lettore di s3Dgraphy (`tools.datamodel_i18n`), o None se la versione
    installata è di prima che esistesse: allora il widget mostra `name`, come
    prima, e non si inventa una parola."""
    try:
        from s3dgraphy.tools import datamodel_i18n
    except ImportError:                     # s3dgraphy precedente al 2026-09-27
        return None
    return datamodel_i18n


def vocabulary(scheme_id: str, lang: str) -> Optional[Dict[str, Any]]:
    """I concetti di uno schema, con l'etichetta in UNA lingua — o None.

    Da `vocabolari/<schema>.json`, che `sync-schede.sh` risolve col risolutore
    di `stratigraph-templates` (schema proprio → allineamento). Un concetto
    senza parola in quella lingua torna con `label: null` e la lingua in cui
    una parola c'è (`label_lang`): il widget lo mostra per quello che è,
    invece di inventare una traduzione.

    Uno schema `declared` torna con zero concetti e lo dice (`status`): la norma
    prescrive un vocabolario che non esiste in SKOS, e il widget scrive allora
    una parola senza concetto — che è ciò che SPEC §3 chiama `uncontrolled`.
    """
    safe = "".join(ch for ch in str(scheme_id or "") if ch.isalnum() or ch in "-_.")
    if not safe or safe != scheme_id:
        return None
    path = VOCABULARY_DIR / f"{safe}.json"
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    concepts = []
    for c in doc.get("concepts") or []:
        labels = c.get("labels") or {}
        here = labels.get(lang)
        other = next(((k, v) for k, v in sorted(labels.items()) if v), (None, None))
        concepts.append({"concept": c["concept"], "label": here or None,
                         **({} if here else {"label_lang": other[0],
                                             "label_there": other[1]})})
    return {"scheme": doc.get("scheme"), "status": doc.get("status"),
            "authority": doc.get("authority"), "fixture": bool(doc.get("fixture")),
            **({"provisional_for": doc["provisional_for"]} if doc.get("provisional_for") else {}),
            "unverified": lang in (doc.get("unverified_languages") or []),
            "label": (doc.get("labels") or {}).get(lang), "lang": lang,
            "concepts": concepts}

