"""L'adattatore del formato: UN modulo che legge una definizione, e nient'altro.

Le due prove che contano stanno in fondo:

* **le etichette vengono dalla definizione** — dimostrato togliendone una e
  guardando che la scheda RIFIUTI, invece di pescare una parola dal dizionario
  dell'interfaccia. È il difetto misurato in pyarchinit-mini, dove `pdf_export`
  risolveva le etichette contro un i18n generico e stampava «Notifica» dove la
  scheda dice FLOTTAZIONE;
* **il default di `recorded_in` non promette niente** — una definizione senza
  marcatori non dà nessun campo da trincea, e chi monta la scheda telefono su
  quel silenzio non ottiene tutto: ottiene nulla.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import scheda as schede                              # noqa: E402

#: Le definizioni vere, quando questa macchina ha il repository accanto. I test
#: che ne hanno bisogno si SALTANO quando non c'è: un checkout di questo solo
#: repository deve avere una suite verde.
TEMPLATES = (pathlib.Path(__file__).resolve().parents[2]
             / "stratigraph-templates" / "templates")
SPEC = TEMPLATES.parent / "SPEC.md"
have_templates = pytest.mark.skipif(
    not TEMPLATES.is_dir(),
    reason="stratigraph-templates non è accanto a questo checkout")


# ── 0 · una definizione minima, scritta qui ─────────────────────────────────

def minimal(**over):
    doc = {"template": {
        "id": "prova", "source_language": "it", "languages": ["it"],
        "standard": {"authority": "TEST", "code": "P", "version": "1",
                     "title": {"it": "Prova"}},
        "paragraphs": [{"id": "tutto", "labels": {"it": "Tutto"},
                        "fields": ["numero", "nota"]}],
        "fields": [
            {"id": "numero", "labels": {"it": "NUMERO"}, "type": "identifier",
             "required": True},
            {"id": "nota", "labels": {"it": "NOTA"}, "type": "longtext"},
        ]}}
    doc["template"].update(over)
    return doc


def write(tmp_path, doc, name="prova.yaml"):
    where = tmp_path / name
    where.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return where


# ── 1 · IL DEFAULT CHE NON PROMETTE NIENTE ──────────────────────────────────

def test_a_definition_with_no_markers_yields_no_trench_fields(tmp_path):
    """LA GUARDIA, verificata sull'EFFETTO.

    Prima si controlla che la definizione TACCIA davvero — altrimenti questa
    prova misurerebbe un file che qualcuno ha marcato — poi che il consumatore
    non ne ricavi nulla.
    """
    s = schede.load(write(tmp_path, minimal()))

    for f in s.fields:
        assert "recorded_in" not in f, "la definizione non tace più"
        assert s.recorded_in(f["id"]) == schede.UNKNOWN

    assert s.trench_fields() == []
    assert s.counts() == {"unknown": 2, "trench": 0, "lab": 0}


def test_that_the_check_above_can_fire(tmp_path):
    """Una guardia che non morde dà lo stesso verde di una che funziona.

    La STESSA definizione con UN campo marcato: se il selettore tornasse vuoto
    anche così, la prova sopra passerebbe per un bug invece che per il default.
    """
    doc = minimal()
    doc["template"]["fields"][1]["recorded_in"] = "trench"
    s = schede.load(write(tmp_path, doc))
    assert s.trench_fields() == ["nota"]
    assert s.counts()["unknown"] == 1


def test_a_value_that_is_not_one_of_the_three_is_refused(tmp_path):
    """Non un ripiego silenzioso su `unknown`: una definizione che intendeva
    `trench` e ha scritto `Trench` sparirebbe dal modulo senza che niente lo
    dica."""
    doc = minimal()
    doc["template"]["fields"][0]["recorded_in"] = "Trench"
    s = schede.load(write(tmp_path, doc))
    with pytest.raises(schede.SchedaError) as refusal:
        s.trench_fields()
    assert "Trench" in str(refusal.value)
    assert "unknown" in str(refusal.value)


# ── 2 · LE ETICHETTE VENGONO DALLA DEFINIZIONE ──────────────────────────────

def test_a_field_without_a_label_is_refused_not_substituted(tmp_path):
    """END-OF §8, dimostrato ROMPENDO.

    Si toglie l'etichetta e si guarda l'effetto: la scheda si rifiuta di
    servire quel campo, e la frase nomina il campo e la lingua. Nessuna parola
    generica prende il suo posto.
    """
    doc = minimal()
    del doc["template"]["fields"][0]["labels"]["it"]
    s = schede.load(write(tmp_path, doc))

    with pytest.raises(schede.SchedaError) as refusal:
        s.for_browser("it")
    said = str(refusal.value)
    assert "numero" in said
    assert "it" in said
    assert "dizionario dell'interfaccia" in said


def test_the_same_definition_with_the_label_serves_fine(tmp_path):
    """Il controllo che rende la prova sopra una misura e non una coincidenza:
    la definizione INTATTA passa."""
    s = schede.load(write(tmp_path, minimal()))
    doc = s.for_browser("it")
    assert [f["label"] for f in doc["fields"]] == ["NUMERO", "NOTA"]


def test_a_language_the_definition_does_not_declare_is_an_error(tmp_path):
    s = schede.load(write(tmp_path, minimal()))
    with pytest.raises(schede.SchedaError) as refusal:
        s.for_browser("pl")
    assert "['it']" in str(refusal.value)
    assert "non è una modalità degradata" in str(refusal.value) or \
           "non una modalità degradata" in str(refusal.value)


def test_an_options_label_is_held_to_the_same_rule(tmp_path):
    """Una `choice` con un'opzione senza etichetta è una casella da barrare che
    non si sa cosa dice."""
    doc = minimal()
    doc["template"]["fields"].append(
        {"id": "natura", "labels": {"it": "NATURA"}, "type": "choice",
         "options": [{"value": "naturale", "labels": {}}]})
    doc["template"]["paragraphs"][0]["fields"].append("natura")
    s = schede.load(write(tmp_path, doc))
    with pytest.raises(schede.SchedaError) as refusal:
        s.for_browser("it")
    assert "naturale" in str(refusal.value)


def test_help_is_optional_and_its_absence_is_not_an_error(tmp_path):
    """A differenza di un'etichetta: un aiuto che manca in una lingua è una
    definizione incompleta, non una rotta."""
    doc = minimal()
    doc["template"]["fields"][1]["help"] = {"en": "only in English"}
    s = schede.load(write(tmp_path, doc))
    served = s.for_browser("it")
    assert "help" not in next(f for f in served["fields"] if f["id"] == "nota")


# ── 3 · quello che NON attraversa il filo ───────────────────────────────────

def test_the_browser_never_receives_the_graph_binding(tmp_path):
    """Il modulo non decide che cosa un campo SIGNIFICA per il grafo: quello è
    dei verdetti, e sta nella definizione per l'autore, non nel telefono."""
    doc = minimal()
    doc["template"]["fields"][0]["graph"] = {"verdict": "identity"}
    doc["template"]["fields"][1]["graph"] = {"verdict": "property",
                                             "property_name": "note"}
    s = schede.load(write(tmp_path, doc))
    served = s.for_browser("it")
    for f in served["fields"]:
        assert "graph" not in f
        assert "verdict" not in f


def a_sheet():
    """Un foglio con le tre specie di cella (campo, blocco ruotato, spazio) e
    una chiave che nessuno dovrebbe mai vedere arrivare al browser."""
    return {
        "page": "A4",
        "margins_mm": {"top": 10, "right": 12, "bottom": 10, "left": 12},
        "sides": [{
            "id": "recto", "labels": {"it": "fronte"},
            "rows": [
                {"h": 9, "cells": [{"field": "numero", "w": 30},
                                   {"w": 70}]},
                {"h": 20, "cells": [{
                    "block": "seq", "block_labels": {"it": "SEQUENZA"},
                    "rotated": True, "w": 100,
                    "graph": {"verdict": "edge"},
                    "rows": [{"h": 20, "cells": [
                        {"field": "nota", "w": 100, "label": "none",
                         "graph": {"verdict": "property"}}]}]}]},
            ]}],
    }


def test_the_sheet_travels_as_geometry_since_2026_10_16(tmp_path):
    """LA REGOLA È CAMBIATA, e questo test lo dice invece di sparire.

    Fino al 16 ottobre 2026 si chiamava `test_the_print_sheet_does_not_travel
    _either` e affermava `"sheet" not in for_browser(...)`, con la ragione:
    «l'A4 è un atto da laboratorio e lo disegna il Python di
    `stratigraph-templates`; mandarlo al telefono sarebbe mandare la seconda
    implementazione insieme alla prima».

    Il 27 settembre E.D. ha deciso che alla scrivania la scheda si compila
    SUL FOGLIO: il modulo disegna l'A4. La griglia viaggia, quindi — ma solo
    come GEOMETRIA letta dalla definizione, non come una seconda definizione:
    pagina, margini, facciate con l'etichetta nella lingua chiesta, righe in
    mm, celle in %, blocchi, `rotated`, `label: none`. Il Python continua a
    stampare, e le due strade leggono le stesse righe."""
    doc = minimal()
    doc["template"]["sheet"] = a_sheet()
    served = schede.load(write(tmp_path, doc)).for_browser("it")

    sheet = served["sheet"]
    assert sheet["page"] == "A4"
    assert sheet["margins_mm"] == {"top": 10, "right": 12, "bottom": 10,
                                   "left": 12}
    recto = sheet["sides"][0]
    assert recto["id"] == "recto" and recto["label"] == "fronte"
    first, second = recto["rows"]
    assert first == {"h": 9, "cells": [{"w": 30, "field": "numero"},
                                        {"w": 70}]}
    block = second["cells"][0]
    assert block["label"] == "SEQUENZA" and block["rotated"] is True
    assert block["rows"][0]["cells"][0] == {"w": 100, "field": "nota",
                                            "label": "none"}


def test_the_graph_binding_does_not_cross_inside_the_sheet_either(tmp_path):
    """Il gemello di `test_the_browser_never_receives_the_graph_binding`,
    dentro `sheet`: una cella nomina il SUO campo per id, e che cosa quel
    campo significhi per il grafo resta sul server. Una chiave che un autore
    aggiunge a una cella domani non arriva al telefono per sbaglio, perché le
    chiavi si copiano per nome."""
    doc = minimal()
    doc["template"]["fields"][0]["graph"] = {"verdict": "identity"}
    doc["template"]["sheet"] = a_sheet()
    served = schede.load(write(tmp_path, doc)).for_browser("it")

    import json
    wire = json.dumps(served["sheet"])
    assert "graph" not in wire
    assert "verdict" not in wire
    assert "block_labels" not in wire   # appiattite a UNA lingua, come le altre


def test_a_sheet_label_missing_in_the_language_is_refused(tmp_path):
    """Stesso rifiuto delle etichette dei campi: una facciata senza nome in
    quella lingua non si battezza col dizionario dell'interfaccia."""
    doc = minimal(languages=["it", "en"])
    for f in doc["template"]["fields"]:
        f["labels"]["en"] = f["labels"]["it"]
    doc["template"]["standard"]["title"]["en"] = "Test"
    doc["template"]["paragraphs"][0]["labels"]["en"] = "All"
    doc["template"]["sheet"] = a_sheet()        # facciata e blocco solo in it
    s = schede.load(write(tmp_path, doc))
    with pytest.raises(schede.SchedaError) as refusal:
        s.for_browser("en")
    assert "recto" in str(refusal.value)


def test_a_cell_naming_a_field_that_does_not_exist_is_refused(tmp_path):
    doc = minimal()
    doc["template"]["sheet"] = a_sheet()
    doc["template"]["sheet"]["sides"][0]["rows"][0]["cells"][0]["field"] = "x"
    with pytest.raises(schede.SchedaError):
        schede.load(write(tmp_path, doc)).for_browser("it")


def test_a_definition_without_a_sheet_sends_no_sheet_key(tmp_path):
    """Né `None` né un foglio vuoto: la CHIAVE manca, e il browser ripiega
    sulla vista «Campi» dicendolo. Un foglio senza caselle sembrerebbe uno
    standard senza campi."""
    assert "sheet" not in schede.load(
        write(tmp_path, minimal())).for_browser("it")
    doc = minimal()
    doc["template"]["sheet"] = {"page": "A4", "sides": []}
    assert "sheet" not in schede.load(write(tmp_path, doc)).for_browser("it")


@have_templates
def test_every_real_sheet_crosses_the_wire_in_every_language():
    """Sulle definizioni vere: ogni facciata e ogni blocco ha l'etichetta in
    ogni lingua dichiarata, e ogni campo ha una casella sola."""
    for path in sorted(TEMPLATES.glob("*/template.yaml")):
        s = schede.load(path)
        if not s.raw.get("sheet"):
            continue
        for lang in s.languages:
            served = s.for_browser(lang)
            seen = []

            def walk(rows):
                for row in rows:
                    for cell in row["cells"]:
                        if "rows" in cell:
                            walk(cell["rows"])
                        elif "field" in cell:
                            seen.append(cell["field"])
            for side in served["sheet"]["sides"]:
                walk(side["rows"])
            assert len(seen) == len(set(seen)), (s.id, lang)


# ── 4 · niente dipendenza dal Python del formato ────────────────────────────

def test_this_module_does_not_import_stratigraph_templates():
    """§3bis: il modulo funziona offline nel browser, il renderer Python gira
    sul server. Le due cose non si incontrano, e questa è la riga che tiene
    separati i due percorsi.

    Letto sul SORGENTE e non con un `try: import`, perché un ambiente che non
    ha quel pacchetto installato darebbe un verde che non misura niente.
    """
    source = pathlib.Path(schede.__file__).read_text(encoding="utf-8")
    for forbidden in ("import stratigraph_templates",
                      "from stratigraph_templates"):
        assert forbidden not in source, forbidden


def test_no_module_in_app_imports_it_either():
    app_dir = pathlib.Path(schede.__file__).parent
    for py in sorted(app_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        assert "import stratigraph_templates" not in text, py.name
        assert "from stratigraph_templates" not in text, py.name


# ── 5 · la directory è il meccanismo ────────────────────────────────────────

def test_no_directory_means_no_schede_and_that_is_not_broken():
    assert schede.schede_dir({}) is None
    assert schede.available({}) == []


def test_a_definition_appears_by_being_dropped_in(tmp_path):
    """IL VINCOLO DI §3bis: una definizione nuova arriva al telefono senza un
    rilascio. Provato: la directory è vuota, poi non lo è."""
    env = {schede.SCHEDE_DIR_VARIABLE: str(tmp_path)}
    assert schede.available(env) == []

    write(tmp_path, minimal(), "prova.yaml")
    found = schede.available(env)
    assert [s.id for s in found] == ["prova"]
    assert schede.find("prova", env) is not None


def test_one_unreadable_definition_does_not_take_the_others_down(tmp_path):
    """Una definizione rotta non deve costare a una persona l'intera lista."""
    env = {schede.SCHEDE_DIR_VARIABLE: str(tmp_path)}
    write(tmp_path, minimal(), "buona.yaml")
    (tmp_path / "rotta.yaml").write_text("questo: [non chiude",
                                         encoding="utf-8")
    assert [s.id for s in schede.available(env)] == ["prova"]


def test_a_file_without_a_template_key_is_named_as_such(tmp_path):
    where = tmp_path / "x.yaml"
    where.write_text(yaml.safe_dump({"campi": []}), encoding="utf-8")
    with pytest.raises(schede.SchedaError) as refusal:
        schede.load(where)
    assert "template" in str(refusal.value)


# ── 6 · dalla scheda compilata agli slot dei tool ───────────────────────────

def test_a_filled_scheda_becomes_the_slots_of_a_tool(tmp_path):
    """Nessuna seconda via: quello che esce da qui è quello che una voce
    avrebbe prodotto, e lo prende `update_su`."""
    s = schede.load(write(tmp_path, minimal()))
    slots = schede.slots_for(s, {"nota": "strato di crollo"}, us="12")
    assert slots == {"us": "12", "fields": {"nota": "strato di crollo"}}


def test_a_field_the_definition_does_not_declare_is_refused(tmp_path):
    """Altrimenti un modulo sarebbe un modo per mettere qualunque cosa in
    `data`: la definizione è ciò che dice che cos'è una casella."""
    s = schede.load(write(tmp_path, minimal()))
    with pytest.raises(schede.SchedaError) as refusal:
        schede.slots_for(s, {"nota": "x", "inventato": "y"}, us="12")
    assert "inventato" in str(refusal.value)


# ── 7 · LE DEFINIZIONI VERE, quando ci sono ─────────────────────────────────

@have_templates
def test_the_three_real_definitions_are_servable():
    """Erano due fino al 2026-09-23. La terza — la scheda ungherese — è tornata
    ED È PERMANENTE, perché era nata come prova del vincolo più importante del
    progetto ed era stata cancellata: *una prova che vive in un documento non è
    una prova, è un ricordo.*

    Questo test è il lato di QUESTO repository di quella regressione: se una
    scheda sparisce di là, l'adattatore di qua se ne accorge.
    """
    env = {schede.SCHEDE_DIR_VARIABLE: str(TEMPLATES)}
    found = {s.id: s for s in schede.available(env)}
    assert set(found) == {"iccd-us-2021", "es-ue-demo-2026", "hu-rl-demo-2026"}
    assert len(found["iccd-us-2021"].fields) == 59
    assert len(found["es-ue-demo-2026"].fields) == 15
    assert len(found["hu-rl-demo-2026"].fields) == 6


@have_templates
def test_the_counts_agree_with_the_repository_that_owns_them():
    """MISURA INCROCIATA. Gli stessi numeri che
    `stratigraph-templates/tests/test_recorded_in.py` pretende dalla sua parte:
    se le due parti divergono, una delle due sta leggendo male il marcatore."""
    env = {schede.SCHEDE_DIR_VARIABLE: str(TEMPLATES)}
    found = {s.id: s for s in schede.available(env)}
    # 2026-09-24: da 8 a 25 campi da trincea, perche' il field assistant ha
    # imparato le parole che mancavano (`definizione`, quote, misure, colore,
    # consistenza) e le dodici caselle dei rapporti — coperte da `relate_su`
    # dal 21 settembre — sono state finalmente marcate LA'.
    assert found["iccd-us-2021"].counts() == {"unknown": 31, "trench": 25,
                                              "lab": 3}
    assert found["es-ue-demo-2026"].counts() == {"unknown": 0, "trench": 14,
                                                 "lab": 1}


@have_templates
def test_the_sheets_give_a_phone_three_different_forms():
    """Se il sottoinsieme fosse lo stesso, il marcatore starebbe descrivendo il
    nostro pregiudizio invece che lo standard — e un modulo telefono costruito
    su di esso mostrerebbe le caselle sbagliate in uno dei tre paesi."""
    env = {schede.SCHEDE_DIR_VARIABLE: str(TEMPLATES)}
    found = {s.id: s for s in schede.available(env)}
    sizes = {i: len(s.trench_fields()) for i, s in found.items()}
    assert sizes == {"iccd-us-2021": 25, "es-ue-demo-2026": 14,
                     "hu-rl-demo-2026": 4}, sizes
    assert len(set(sizes.values())) == 3


@have_templates
def test_the_three_values_are_the_ones_the_format_declares():
    """I tre valori sono RIPETUTI qui invece che importati, perché importarli
    vorrebbe dire dipendere dal Python del formato. La ripetizione non può
    andare alla deriva in silenzio: la SPEC è la fonte, e qui la si legge."""
    spec = SPEC.read_text(encoding="utf-8")
    assert "### 1.6" in spec and "recorded_in" in spec
    for value in schede.RECORDED_IN_VALUES:
        assert f"`{value}`" in spec, (
            f"«{value}» non è più uno dei valori che SPEC.md dichiara")


@have_templates
def test_the_iccd_sheet_serves_in_both_languages_it_declares():
    env = {schede.SCHEDE_DIR_VARIABLE: str(TEMPLATES)}
    us = schede.find("iccd-us-2021", env)
    for lang in ("it", "en"):
        served = us.for_browser(lang)
        assert served["lang"] == lang
        assert len(served["fields"]) == 59
        assert all(f["label"] for f in served["fields"])
