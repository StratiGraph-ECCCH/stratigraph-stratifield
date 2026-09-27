"""Il nono tool: «la 12 copre la 18» — l'intento che mancava.

Trovato marcando la scheda ICCD in `stratigraph-templates` (22 settembre):
nessuno dei sette intenti permetteva di registrare un rapporto stratigrafico a
voce, e per questo le dieci caselle dei rapporti di quella scheda sono rimaste
`unknown` — marcarle `trench` senza un intento che le copra sarebbe stato
inventare il criterio.

**Dal 19 ottobre la mappa non è più di questo servizio:** `RELATIONS` è
DERIVATO dalla ricetta della scheda di riferimento del nodo (la US ICCD
compilata), le frasi sono le etichette delle sue caselle, e l'arco è quello
che la ricetta dichiara. E.D.: **COPRE è `overlies`, POSTERIORE A è
`is_after`, e non si mescolano.** Fino a ieri questo file pinnava `copre →
is_after` per allinearsi a pyarchinit-mini; l'audit del 17 ottobre ha misurato
che la stessa frase, detta a voce o scritta sulla scheda, faceva due archi.

**La cosa che questo file difende sopra tutte:** gli inversi NON esistono come
tipi di arco. Misurato in `s3Dgraphy_connections_datamodel.json` 1.6.13:
`is_after` c'è, `is_before` no; `cuts` c'è, `is_cut_by` no. Esistono solo come
etichetta `reverse` per LEGGERE un arco al contrario. Quindi «la 12 è coperta
dalla 18» si registra **scambiando i capi**, e una freccia messa al rovescio è
l'unico errore in stratigrafia che cambia la sequenza.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.assets import InMemoryAssetStore                        # noqa: E402
from app.contract import invoke                                  # noqa: E402
from app.intent import extract_relation, understand              # noqa: E402
from app.tools import (RELATIONS, build_registry, edge_id_for,    # noqa: E402
                       make_create_su, make_relate_su, unit_id_for)
from app.writer import LocalWriter                               # noqa: E402

ORCID = "0000-0002-1825-0097"


@pytest.fixture
def writer(tmp_path):
    return LocalWriter(str(tmp_path / "scavo.em.json"), study="Saggio B")


@pytest.fixture
def registry(writer):
    return build_registry(writer, InMemoryAssetStore())


def units(writer, *numbers):
    for n in numbers:
        assert make_create_su(writer).handler({"us": str(n)}, ORCID).ok


def graph_of(writer):
    doc = json.loads(writer.path.read_text(encoding="utf-8"))
    return next(iter(doc["graphs"].values()))


def edges_of(writer):
    return graph_of(writer).get("edges") or []


# ── 1 · IL DATAMODEL, misurato — la ragione per cui esiste lo scambio ───────

def test_the_inverse_edge_types_do_not_exist():
    """Se un giorno `is_before` comparisse nel datamodel, lo scambio dei capi
    diventerebbe una scelta invece che una necessità — e questo test è il posto
    dove la cosa va ridiscussa, non scoperta."""
    import pathlib

    import s3dgraphy

    base = pathlib.Path(s3dgraphy.__file__).parent
    model = json.loads(
        (base / "JSON_config" / "s3Dgraphy_connections_datamodel.json")
        .read_text(encoding="utf-8"))
    declared = model["edge_types"]

    # LA VERSIONE NON È PIÙ UN NUMERO SCRITTO QUI (19 ottobre): è quella che la
    # scheda compilata e vendorata dichiara di aver verificato
    # (`header.datamodel.connections`). Il test era rosso da quando s3Dgraphy
    # è passato da 1.6.13 a 1.6.19 senza che niente qui fosse sbagliato.
    from app.tools import reference_scheda
    compiled = reference_scheda().datamodel["connections"]
    assert model["s3Dgraphy_connections_model_version"] == compiled, (
        f"s3Dgraphy dichiara le connessioni "
        f"{model['s3Dgraphy_connections_model_version']}, la scheda compilata "
        f"è stata verificata contro {compiled}: ricompila e rivendora")
    for present in ("is_after", "overlies", "cuts", "fills", "abuts",
                    "bonded_to", "equals", "has_same_time"):
        assert present in declared, present
    for absent in ("is_before", "is_overlain_by", "is_cut_by"):
        assert absent not in declared, (
            f"{absent} è comparso: gli inversi ora esistono, e la mappa di "
            f"`RELATIONS` va ridiscussa invece che scambiare i capi")


def test_every_verb_maps_to_a_type_the_datamodel_declares():
    """Nessun tipo inventato. Un arco con un `edge_type` che il datamodel non
    conosce è la cosa che il recinto di questo repository vieta."""
    import pathlib

    import s3dgraphy

    base = pathlib.Path(s3dgraphy.__file__).parent
    declared = json.loads(
        (base / "JSON_config" / "s3Dgraphy_connections_datamodel.json")
        .read_text(encoding="utf-8"))["edge_types"]
    for verb, (edge_type, _direction) in RELATIONS.items():
        assert edge_type in declared, f"{verb} → {edge_type} non esiste"


def test_the_map_IS_the_recipe_of_the_reference_scheda():
    """Lo stesso rapporto, detto a voce o scritto sulla scheda, deve diventare
    LO STESSO arco: altrimenti la porta da cui è entrato si vede nel grafo.

    La mappa di riferimento NON è più `pyarchinit-mini/…/us_ops.py`: è la
    ricetta. Frase per frase, l'arco e la direzione sono il passo della casella
    che porta quell'etichetta."""
    from app.tools import RELATION_FIELDS, reference_scheda

    recipe = reference_scheda().recipe["fields"]
    assert RELATIONS["copre"] == ("overlies", "forward")
    assert RELATIONS["coperto da"] == ("overlies", "swap")
    assert RELATIONS["posteriore a"] == ("is_after", "forward")
    assert RELATIONS["anteriore a"] == ("is_after", "swap")
    assert RELATIONS["taglia"][0] == "cuts"
    assert RELATIONS["riempie"][0] == "fills"
    assert RELATIONS["si appoggia a"][0] == "abuts"
    assert RELATIONS["si lega a"] == ("bonded_to", "symmetric")
    assert RELATIONS["uguale a"] == ("equals", "symmetric")
    from app.operazioni import datamodel_relations

    declared = datamodel_relations()
    for phrase, (edge_type, _direction) in RELATIONS.items():
        box = RELATION_FIELDS[phrase]
        if box:
            # una casella: l'arco è il suo passo
            step = recipe[box]["steps"][0]["emit"]
            assert step["edge_type"] == edge_type, phrase
        else:
            # nessuna casella: una relazione che il DATAMODEL dichiara fra
            # unità stratigrafiche, e nient'altro (21 ottobre)
            assert edge_type in declared, phrase


def test_the_relations_of_the_datamodel_are_READ_and_contemporaneo_is_back():
    """ERA «ciò che la derivazione ha perso» (19 ottobre): «contemporaneo a»
    non è una casella della US ICCD. Decisione di E.D. (21 ottobre): la voce
    accetta ANCHE le relazioni che il datamodel dichiara fra unità
    stratigrafiche — lette dal datamodel, non da un elenco qui."""
    from s3dgraphy.edges.connections_loader import get_connections_datamodel

    from app.operazioni import datamodel_relations
    from app.tools import RELATION_FIELDS, RELATIONS_REFUSED, RELATIONS_UNSAID

    dm = get_connections_datamodel()
    declared = datamodel_relations()
    # ciò che il datamodel dichiara, misurato con il datamodel stesso
    for name in declared:
        assert dm.is_canonical(name) and "StratigraphicNode" in dm.get_allowed_sources(name)
    assert {"overlies", "cuts", "fills", "abuts", "bonded_to", "equals",
            "is_after", "has_same_time"} <= set(declared)
    assert "is_bonded_to" not in declared          # una grafia, non una relazione
    assert "is_overlain_by" not in declared        # un inverso, non una relazione
    # fisiche e no restano DUE cose
    assert declared["overlies"]["physical"] is True
    assert declared["is_after"]["physical"] is False
    assert declared["has_same_time"]["physical"] is False

    assert RELATIONS["contemporaneo a"] == ("has_same_time", "symmetric")
    assert RELATIONS["contemporanea a"] == ("has_same_time", "symmetric")
    assert RELATION_FIELDS["contemporaneo a"] == ""       # nessuna casella
    # ciò che resta indicibile è DETTO, non nascosto
    assert "appoggia a" not in RELATIONS
    assert RELATIONS_UNSAID == ["changed_from"]
    assert RELATIONS_REFUSED == {}


def test_a_word_for_something_the_datamodel_does_not_declare_between_units_is_refused():
    from app.operazioni import datamodel_relation_phrases, unsayable_words

    words = {"ha documento": "has_documentation", "inventato a": "made_up"}
    assert datamodel_relation_phrases(words) == {}
    refused = unsayable_words(words)
    assert set(refused) == set(words)
    assert "StratigraphicNode" in refused["ha documento"]
    assert "non è un arco" in refused["inventato a"]


def test_an_older_spelling_or_an_inverse_goes_through_normalize_edge_name():
    from app.operazioni import canonical_relation

    assert canonical_relation("is_bonded_to") == ("bonded_to", "symmetric")
    assert canonical_relation("is_physically_equal_to") == ("equals", "symmetric")
    assert canonical_relation("is_overlain_by") == ("overlies", "swap")
    assert canonical_relation("is_before") == ("is_after", "swap")
    assert canonical_relation("overlies") == ("overlies", "forward")


# ── 2 · LE REGOLE, senza modello — che sul campo è un martedì ──────────────

@pytest.mark.parametrize("sentence, expected", [
    ("la 12 copre la 18", {"us": "12", "relation": "copre", "other": "18"}),
    ("US 12 copre US 18", {"us": "12", "relation": "copre", "other": "18"}),
    ("la 12 è coperta dalla 18",
     {"us": "12", "relation": "coperta da", "other": "18"}),
    ("la 3 è tagliata dalla 7",
     {"us": "3", "relation": "tagliata da", "other": "7"}),
    ("la 5 riempie la 9", {"us": "5", "relation": "riempie", "other": "9"}),
    ("la 5 è riempita dalla 9",
     {"us": "5", "relation": "riempita da", "other": "9"}),
    ("la 12 si appoggia alla 11",
     {"us": "12", "relation": "si appoggia a", "other": "11"}),
    ("la 12 si lega alla 18",
     {"us": "12", "relation": "si lega a", "other": "18"}),
    ("la 12 è uguale alla 21",
     {"us": "12", "relation": "uguale a", "other": "21"}),
    ("la 12 è posteriore alla 18",
     {"us": "12", "relation": "posteriore a", "other": "18"}),
    ("la 12 è anteriore alla 18",
     {"us": "12", "relation": "anteriore a", "other": "18"}),
])
def test_the_field_phrase_routes_and_fills_all_three_slots(registry, sentence,
                                                           expected):
    understood = understand(sentence, registry)          # NO model passed
    assert understood.tool == "relate_su", understood.as_dict()
    assert understood.via == "rules", (
        "riconosciuto dal modello: sul campo il modello può non esserci")
    assert understood.slots == expected


def test_the_feminine_forms_are_the_ones_people_actually_say(registry):
    """Un'unità stratigrafica è femminile: «la 12 è copertA dalla 18».

    Le forme al femminile erano nella mappa e NON nella lista degli intenti,
    perché le due liste erano scritte a mano, e quelle frasi non venivano
    riconosciute affatto. Ora la lista È la mappa. Questo test è ciò che
    impedisce alle due di divergere di nuovo.
    """
    descriptor = registry.get("relate_su")
    for feminine in ("coperta da", "tagliata da", "riempita da"):
        assert feminine in RELATIONS
        assert feminine in descriptor.intents, (
            f"«{feminine}» è nella mappa e non fra gli intenti: la frase non "
            f"verrebbe riconosciuta")


def test_a_sentence_with_one_number_fills_nothing_rather_than_guessing():
    assert extract_relation("la 4 gli si appoggia") is None
    assert extract_relation("crea la us 12") is None


def test_a_verb_nobody_declared_is_not_invented():
    assert extract_relation("la 12 somiglia alla 18") is None


def test_the_longest_verb_wins():
    """«si appoggia a» deve battere «appoggia a», altrimenti il verbo cambia."""
    found = extract_relation("la 12 si appoggia alla 11")
    assert found["relation"] == "si appoggia a"


# ── 3 · L'ARCO che ne esce ─────────────────────────────────────────────────

def test_copre_lands_one_edge_in_the_canonical_direction(writer):
    units(writer, 12, 18)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "copre"}, ORCID)
    assert result.ok, result.message

    edges = edges_of(writer)
    assert len(edges) == 1
    assert edges[0]["source"] == "US12"
    assert edges[0]["target"] == "US18"
    assert edges[0]["edge_type"] == "overlies"


def test_the_inverse_swaps_the_ends_and_does_not_invent_a_type(writer):
    """IL CUORE DEL TOOL. «La 12 è coperta dalla 18» vuol dire che la 18 è
    posteriore alla 12, quindi l'arco parte da 18."""
    units(writer, 12, 18)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "coperta da"}, ORCID)
    assert result.ok, result.message

    edge = edges_of(writer)[0]
    assert edge["edge_type"] == "overlies", "non si inventa un tipo inverso"
    assert edge["source"] == "US18", "i capi non sono stati scambiati"
    assert edge["target"] == "US12"
    assert result.data["direction"] == "swap"
    assert result.data["said"] == "coperta da"


def test_the_two_ways_of_saying_it_produce_the_SAME_edge(writer):
    """«12 copre 18» e «18 è coperta dalla 12» sono lo stesso fatto.

    Un grafo che li registra come due archi conta due rapporti dove ce n'è uno,
    e la matrice li disegna entrambi.
    """
    units(writer, 12, 18)
    tool = make_relate_su(writer)
    assert tool.handler({"us": "12", "other": "18", "relation": "copre"},
                        ORCID).ok
    assert tool.handler({"us": "18", "other": "12", "relation": "coperta da"},
                        ORCID).ok
    assert len(edges_of(writer)) == 1, edges_of(writer)


@pytest.mark.parametrize("verb", ["uguale a", "si lega a"])
def test_a_symmetric_relation_is_one_edge_whichever_end_you_name(writer, verb):
    """I capi si ORDINANO. Senza, i simmetrici sarebbero il solo posto che
    raddoppia ancora — che è precisamente il difetto che `us_ops._oriented`
    documenta di aver evitato dall'altra parte."""
    units(writer, 12, 18)
    tool = make_relate_su(writer)
    assert tool.handler({"us": "12", "other": "18", "relation": verb}, ORCID).ok
    assert tool.handler({"us": "18", "other": "12", "relation": verb}, ORCID).ok
    assert len(edges_of(writer)) == 1, edges_of(writer)


def test_the_edge_id_follows_the_convention_the_ecosystem_composes(writer):
    """`source__type__target` — così un arco detto a voce e lo stesso arco
    disegnato a mano in EMStudio SONO un arco."""
    units(writer, 12, 18)
    make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "copre"}, ORCID)
    assert edges_of(writer)[0]["id"] == "US12__overlies__US18"
    assert edge_id_for("US12", "overlies", "US18") == "US12__overlies__US18"


def test_saying_it_twice_does_not_double_the_arrow(writer):
    units(writer, 12, 18)
    tool = make_relate_su(writer)
    tool.handler({"us": "12", "other": "18", "relation": "copre"}, ORCID)
    tool.handler({"us": "12", "other": "18", "relation": "copre"}, ORCID)
    assert len(edges_of(writer)) == 1


# ── 4 · quello che rifiuta ─────────────────────────────────────────────────

def test_the_OTHER_unit_that_does_not_exist_is_marked_not_refused(writer):
    """UNA DECISIONE CAMBIATA (19 ottobre), la stessa della scheda.

    Era: «un arco verso un'unità che non c'è è una freccia nel vuoto, rifiuta».
    La freccia nel vuoto resta vietata — e non c'è: la 18 viene creata MINIMA
    e SEGNATA (`data.scheda.stub`), perché chi dice «la 12 copre la 18» sta
    dicendo che la 18 esiste, e rimandare l'arco vorrebbe dire tenerlo in un
    posto che non c'è. Quando la 18 avrà la sua scheda, la scheda la promuove
    (`app/operazioni.py`, decisione 1)."""
    units(writer, 12)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "copre"}, ORCID)
    assert result.ok, result.message
    assert "segnata da compilare" in result.message
    stub = next(n for n in graph_of(writer)["nodes"] if n["id"] == "US18")
    assert stub["data"]["scheda"]["stub"] is True
    assert stub["data"]["scheda"]["declared_by"] == "US12"
    assert [(e["source"], e["edge_type"], e["target"])
            for e in edges_of(writer)] == [("US12", "overlies", "US18")]


def test_the_unit_that_ACTS_must_exist(writer):
    """Chi fa l'azione no: è un aggiornamento, e un numero sbagliato non
    diventa un'unità nuova — la stessa regola di `update_su`."""
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "copre"}, ORCID)
    assert not result.ok
    assert "non è in questo grafo" in result.message
    assert result.data["missing"] == ["12"]
    assert edges_of(writer) == []


def test_a_unit_cannot_be_in_a_relation_with_itself(writer):
    units(writer, 12)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "12", "relation": "copre"}, ORCID)
    assert not result.ok
    assert "se stessa" in result.message
    assert edges_of(writer) == []


def test_an_unknown_verb_is_refused_and_says_what_it_knows(writer):
    units(writer, 12, 18)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "somiglia a"}, ORCID)
    assert not result.ok
    assert "somiglia a" in result.message
    assert "copre" in result.message and "uguale a" in result.message


def test_one_unit_alone_is_a_question_not_a_guess(writer):
    units(writer, 12)
    result = make_relate_su(writer).handler(
        {"us": "12", "relation": "copre"}, ORCID)
    assert not result.ok
    assert "due unità" in result.message


def test_a_relation_with_nobody_behind_it_is_refused(writer):
    units(writer, 12, 18)
    result = invoke(make_relate_su(writer),
                    {"us": "12", "other": "18", "relation": "copre"}, None)
    assert not result.ok
    assert result.data["reason"] == "no-author"
    assert edges_of(writer) == []


# ── 5 · l'atto resta registrato ────────────────────────────────────────────

def test_the_act_records_what_was_said_and_not_only_what_was_written(writer):
    """Chi rilegge deve poter vedere che «coperta da» è diventata un `overlies`
    a capi scambiati, e non un tipo inverso che non esiste."""
    units(writer, 12, 18)
    result = make_relate_su(writer).handler(
        {"us": "12", "other": "18", "relation": "coperta da"}, ORCID)

    d7 = [n for n in graph_of(writer)["nodes"]
          if n.get("node_type") == "dtc_process"
          and n["data"].get("tool") == "relate_su"]
    assert len(d7) == 1
    assert "coperta da" in d7[0]["description"]
    assert d7[0]["data"]["created_by"] == ORCID
    assert result.delta.author == ORCID
    assert result.delta.edges[0]["edge_type"] == "overlies"


# ── 4 · LE RELAZIONI DEL DATAMODEL, dette a voce (21 ottobre) ───────────────

def _said(writer, registry, sentence):
    understood = understand(sentence, registry)
    assert understood.tool == "relate_su" and understood.via == "rules", \
        understood.as_dict()
    return invoke(registry.get("relate_su"), understood.slots, ORCID,
                  registry=registry)


def test_contemporanea_lands_has_same_time_through_the_same_generator(
        writer, registry):
    """«la US 12 è contemporanea alla US 14»: nessuna casella della US ICCD, una
    relazione che il datamodel dichiara. Un arco `has_same_time`, simmetrico
    (capi ordinati), con l'id della convenzione; nessun marcatore di
    autorialità inventato per una casella che non c'è."""
    units(writer, 12)
    result = _said(writer, registry, "la US 12 è contemporanea alla US 14")
    assert result.ok, result.message
    edges = [e for e in edges_of(writer) if e["edge_type"] == "has_same_time"]
    assert [(e["source"], e["target"]) for e in edges] == [("US12", "US14")]
    assert edges[0]["id"] == edge_id_for("US12", "has_same_time", "US14")
    assert result.data["field"] is None and result.data["physical"] is False
    assert result.data["direction"] == "symmetric"
    # l'altra unità non c'era: segnata, come per una casella
    assert [s["id"] for s in result.data["stubs"]] == ["US14"]
    unit = next(n for n in graph_of(writer)["nodes"] if n["id"] == "US12")
    assert not [k for k in (unit.get("data") or {}).get("authorship", {})
                if "relazione" in k]
    # detta dall'altra parte, è LO STESSO arco
    again = _said(writer, registry, "la US 14 è contemporanea alla US 12")
    assert again.ok
    assert len([e for e in edges_of(writer)
                if e["edge_type"] == "has_same_time"]) == 1


def test_si_lega_lands_the_canonical_bonded_to(writer, registry):
    units(writer, 12, 14)
    result = _said(writer, registry, "la US 12 si lega alla US 14")
    assert result.ok, result.message
    kinds = {e["edge_type"] for e in edges_of(writer)}
    assert "bonded_to" in kinds and "is_bonded_to" not in kinds


def test_COPRE_is_physical_and_POSTERIORE_A_is_not_and_they_stay_two(writer,
                                                                     registry):
    units(writer, 12, 14)
    assert _said(writer, registry, "la US 12 copre la US 14").data["physical"] is True
    assert {e["edge_type"] for e in edges_of(writer)} == {"overlies"}
    assert _said(writer, registry,
                 "la US 12 è posteriore alla US 14").data["physical"] is False
    assert {e["edge_type"] for e in edges_of(writer)} == {"overlies", "is_after"}


def test_an_old_spelling_in_the_graph_is_READ_as_the_box():
    """Un lettore riconosce ogni grafia (`spellings`): un `is_bonded_to` di un
    grafo vecchio è la casella SI LEGA A."""
    from app import operazioni as O
    from app.tools import reference_scheda

    section = {"nodes": [{"id": "US12", "node_type": "US", "name": "US 12"},
                         {"id": "US14", "node_type": "US", "name": "US 14"}],
               "edges": [{"id": "x", "source": "US14", "edge_type": "is_bonded_to",
                          "target": "US12"}]}
    back = O.values_from_graph(reference_scheda(), section, "US12")["values"]
    assert back["si_lega_a"] == ["14"]
