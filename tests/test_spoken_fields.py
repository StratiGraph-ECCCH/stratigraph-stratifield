"""Le parole che mancavano — un campo detto a voce.

Il 21 settembre si è visto che nessuno dei sette intenti permetteva di dire un
rapporto stratigrafico. **La scoperta era più larga**: non c'era un modo di dire
nemmeno `definizione` — che è obbligatoria — né le quote, né le misure. Sulla US
ICCD i campi da trincea erano **8 su 59**: non una scheda semplificata, una
scheda quasi vuota.

**Il collo di bottiglia non era il formato, erano le parole.**

E non è servito un tool nuovo: `update_su` scrive già qualunque campo. Mancava
il VOCABOLARIO che porta una frase a un campo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.assets import InMemoryAssetStore                        # noqa: E402
from app.intent import extract_spoken_field, understand          # noqa: E402
from app.tools import (SPOKEN_FIELDS, build_registry,             # noqa: E402
                       make_create_su, make_update_su)
from app.writer import LocalWriter                               # noqa: E402

ORCID = "0000-0002-1825-0097"


@pytest.fixture
def writer(tmp_path):
    w = LocalWriter(str(tmp_path / "scavo.em.json"), study="Saggio B")
    assert make_create_su(w).handler({"us": "12"}, ORCID).ok
    return w


@pytest.fixture
def registry(writer):
    return build_registry(writer, InMemoryAssetStore())


# ── 1 · LE FRASI, riconosciute DALLE REGOLE e senza modello ────────────────

def _row(v):
    return [{"label": v, "value": v}]


# NELLA FORMA DEL CAMPO (19 ottobre): la ricetta vuole righe per le quote e le
# misure, un termine per colore e consistenza. La voce sa di aver sentito UNA
# cosa, e la dà in quella forma (`operazioni.spoken_value`); il generatore
# rifiuterebbe una stringa dove serve una lista.
@pytest.mark.parametrize("said, field, value", [
    ("la us 12 è uno strato di crollo", "definizione", {"label": "strato di crollo"}),
    ("la definizione della us 12 è muro", "definizione", {"label": "muro"}),
    ("us 12 quota 145,30", "quote", _row("145,30")),
    ("la quota della us 7 è -1,25", "quote", _row("-1,25")),
    ("la us 12 misura 2 per 1,5 metri", "misure", _row("2 per 1,5 metri")),
    ("il colore della us 12 è bruno scuro", "colore", {"label": "bruno scuro"}),
    ("la consistenza della us 12 è friabile", "consistenza", {"label": "friabile"}),
])
def test_a_field_said_out_loud_reaches_update_su(registry, said, field, value):
    understood = understand(said, registry)              # NESSUN modello
    assert understood.tool == "update_su", understood.as_dict()
    assert understood.via == "rules", (
        "riconosciuto dal modello: sul campo il modello può non esserci, ed è "
        "un martedì")
    assert understood.slots["fields"] == {field: value}


def test_the_unit_number_comes_out_of_the_same_sentence(registry):
    assert understand("la us 12 è uno strato", registry).slots["us"] == "12"
    assert understand("la quota della us 7 è -1,25",
                      registry).slots["us"] == "7"


# ── 2 · LA VIRGOLA È IL DATO, e la prima versione la buttava ───────────────

def test_the_value_keeps_its_punctuation():
    """`_normalise` toglie la punteggiatura per far combaciare le frasi, e su un
    valore la distrugge. La prima versione prendeva la coda dal testo
    normalizzato: «quota 145,30» diventava «145 30».

    Su una quota e su una misura **la virgola è il dato**, e sono precisamente
    i due campi che questa serata aggiunge.
    """
    assert extract_spoken_field("us 12 quota 145,30")["value"] == "145,30"
    assert extract_spoken_field("la us 12 misura 2 per 1,5 metri")["value"] \
        == "2 per 1,5 metri"
    assert extract_spoken_field("la quota è -1,25")["value"] == "-1,25"


def test_that_the_punctuation_check_would_catch_the_old_bug():
    """Una guardia che non morde dà lo stesso verde di una che funziona.

    Si applica al valore la stessa normalizzazione che la prima versione
    applicava, e si pretende che il risultato sia DIVERSO — altrimenti il test
    sopra passerebbe anche col difetto.
    """
    from app.intent import _normalise

    value = extract_spoken_field("us 12 quota 145,30")["value"]
    assert _normalise(value) != value, (
        "la normalizzazione non cambia più questo valore: il test sopra non "
        "sta più misurando il difetto che ha trovato")
    assert _normalise(value) == "145 30"


# ── 3 · quello che NON riconosce ───────────────────────────────────────────

def test_a_phrase_with_nothing_after_it_is_a_question_not_a_write():
    """«definizione» detto da solo è una domanda."""
    assert extract_spoken_field("definizione") is None
    assert extract_spoken_field("la quota è") is None


def test_a_word_nobody_declared_is_not_invented():
    assert extract_spoken_field("la us 12 pesa 4 chili") is None


def test_the_longest_phrase_wins():
    """«la definizione è» deve battere «definizione», altrimenti il valore
    comincerebbe con « è »."""
    assert extract_spoken_field("la definizione è muro")["value"] == "muro"


def test_the_phrases_and_the_map_are_ONE_list(registry):
    """Due elenchi scritti a mano divergono — l'ho già pagato con le forme al
    femminile di `relate_su`, che la mappa conosceva e gli intenti no."""
    declared = registry.get("update_su").intents
    for phrases in SPOKEN_FIELDS.values():
        for phrase in phrases:
            assert phrase in declared, phrase


# ── 4 · e la frase ATTERRA nel grafo ───────────────────────────────────────

def _back(writer):
    from app.operazioni import values_from_graph
    from app.tools import reference_scheda
    return values_from_graph(reference_scheda(), writer.section(), "US12")["values"]


def test_the_sentence_becomes_a_field_in_the_graph(writer, registry):
    from app.contract import invoke

    understood = understand("il colore della us 12 è bruno", registry)
    result = invoke(registry.get(understood.tool), understood.slots, ORCID,
                    registry=registry)
    assert result.ok, result.message
    assert result.data["updated"] == ["colore"]
    # una PropertyNode `color` appesa all'unità, come dice la ricetta ICCD
    assert _back(writer)["colore"] == {"label": "bruno"}
    assert "colore" not in writer.node("US12")["data"]


@pytest.mark.parametrize("said", ["la us 12 è uno strato di crollo",
                                  "definizione della us 12 strato di crollo"])
def test_DEFINIZIONE_is_heard_AND_lands_on_the_unit_since_2026_10_21(
        writer, registry, said):
    """ERA «capita e non scrive» (19 ottobre): la ricetta ICCD 1.0.0 teneva
    `definizione` in `recipe.open`, e ogni posto sarebbe stato inventato.

    Decisione di E.D. (21 ottobre): la definizione è un ELEMENTO DEL NODO US,
    dichiarato da s3Dgraphy (`StratigraphicNode.properties.definition`, nodi
    1.6.9), e la ricetta 1.0.1 scrive `update_field data.definition`. La parola
    detta è un termine senza concetto: `{label}`, nessun URI inventato. Niente
    PropertyNode e niente `data.definizione` (il difetto dell'audit)."""
    from app.contract import invoke
    from app.operazioni import values_from_graph
    from app.scheda import find

    understood = understand(said, registry)
    assert understood.slots["fields"] == {"definizione": {"label": "strato di crollo"}}
    result = invoke(registry.get(understood.tool), understood.slots, ORCID,
                    registry=registry)
    assert result.ok, result.message
    assert result.data["updated"] == ["definizione"]
    assert "definizione" not in result.data["silent"]
    unit = writer.node("US12")
    assert unit["data"]["definition"] == {"label": "strato di crollo"}
    assert "definizione" not in unit["data"]
    assert not [n for n in writer.section()["nodes"]
                if n.get("node_type") == "property" and n.get("name") == "definition"]
    back = values_from_graph(find("iccd-us-2021", {}), writer.section(), "US12")
    assert back["values"]["definizione"] == {"label": "strato di crollo"}


def test_a_spoken_field_is_authored_by_the_person_not_by_a_model(writer,
                                                                 registry):
    """Le regole non compongono: riconoscono. Una frase capita da una regola è
    verbatim, e il campo resta di chi l'ha detto."""
    from app.authorship import read
    from app.contract import invoke

    understood = understand("il colore della us 12 è bruno", registry)
    assert understood.via == "rules"
    invoke(registry.get("update_su"), understood.slots, ORCID, registry=registry)

    said = read(writer.node("US12"), "colore")
    assert said["by"] == "human"
    assert said["validated"] is False


def test_two_things_said_in_two_sentences_are_two_fields(writer, registry):
    from app.contract import invoke

    for phrase in ("il colore della us 12 è bruno",
                   "la us 12 misura 2 per 1,5 metri"):
        understood = understand(phrase, registry)
        assert invoke(registry.get("update_su"), understood.slots, ORCID,
                      registry=registry).ok

    values = _back(writer)
    assert values["colore"] == {"label": "bruno"}
    # una riga senza qualia: la ricetta non ne dà una di difetto per `misure`,
    # e la riga porta il nome della casella (`measurements`) e lo DICE
    assert values["misure"] == [{"label": "2 per 1,5 metri",
                                 "value": "2 per 1,5 metri"}]
