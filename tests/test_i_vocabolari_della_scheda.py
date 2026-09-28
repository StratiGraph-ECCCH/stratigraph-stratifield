"""I vocabolari della scheda US: concetti con un URI, al posto delle parole
(notte del 23 ottobre; decisione di E.D. del 27 settembre).

I cinque campi a vocabolario della US ICCD 2021 citano schemi `declared`, e
fino a ieri il widget scriveva una parola senza concetto: la DEFINIZIONE non
entrava nel triple store (`definition.rdf.label_only` = null, e il caso si
conta). Da stanotte per quegli schemi risponde un modulo originato `em-us-*`
(stratigraph-templates SPEC §3.2): questo file misura, dalla porta vera, che il
nodo lo offre, che il widget scrive `{concept, label}`, e che l'esportatore RDF
di s3Dgraphy ne ricava le due triple. La parola libera resta possibile, e resta
senza tripla.
"""

from __future__ import annotations

import json

import pytest

from app import scheda as S

from test_i_widget_strutturati import BASE, client, post  # noqa: F401  (la fixture)

CROLLO = "https://w3id.org/extendedmatrix/vocab/us-definizione/strato-di-crollo"
CRM = "http://www.cidoc-crm.org/cidoc-crm/"
BOXES = {"definizione": "em-us-definizione", "consistenza": "em-us-consistenza",
         "colore": "em-us-colore", "stato_conservazione": "em-us-stato-conservazione",
         "affidabilita": "em-us-affidabilita"}


def test_the_five_boxes_are_offered_the_concepts_of_the_stand_in(client):
    c, _ = client
    served = {f["id"]: f for f in S.find("iccd-us-2021").for_browser("it")["fields"]}
    for fid, scheme in BOXES.items():
        assert served[fid]["vocabulary"] == scheme, fid
        assert served[fid]["vocabulary_norm"] == "iccd-" + scheme[3:], "la norma resta citata"
        voc = c.get(f"/v1/vocabolario/{scheme}?lang=it").json()
        assert voc["status"] == "resolvable" and voc["concepts"], fid
        assert voc["provisional_for"] == "iccd-" + scheme[3:]
        assert all(x["label"] for x in voc["concepts"]), "ogni concetto ha la sua parola in it"
        assert voc["unverified"] is False, "l'italiano viene dalle fonti"
    en = c.get("/v1/vocabolario/em-us-definizione?lang=en").json()
    assert en["unverified"] is True, "l'inglese è una bozza, e il nodo lo dice"
    crollo = {x["concept"]: x["label"] for x in en["concepts"]}[CROLLO]
    assert crollo == "collapse layer"


def _triples(path):
    """Il documento della stanza, letto da s3Dgraphy e proiettato in RDF.

    L'esportatore RDF di s3Dgraphy vuole `rdflib`, che è un extra di s3Dgraphy
    e non una dipendenza del nodo: senza, questi test si saltano e lo dicono."""
    pytest.importorskip("rdflib", reason="rdflib (extra RDF di s3Dgraphy) non è installato")
    from rdflib import ConjunctiveGraph
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.emjson_importer import parse_emjson

    graph, _ = parse_emjson(json.loads(path.read_text(encoding="utf-8")))
    out = path.with_suffix(".ttl")
    exporter = RDFExporter(str(out), format="turtle")
    exporter.export_single_graph(graph)
    store = ConjunctiveGraph()
    store.parse(str(out), format="turtle")
    return store, exporter.stats


def _definition_triples(store):
    from rdflib import URIRef
    has_type = URIRef(CRM + "P2_has_type")
    return {(s, o) for s, o in store.subject_objects(has_type)
            if str(o).startswith("https://w3id.org/extendedmatrix/vocab/us-definizione/")}


def test_US_3014_strato_di_crollo_round_trip_before_and_after(client, tmp_path):
    """PRIMA: la parola sola → nessuna tripla, un caso contato. DOPO: il
    concetto → `<US3014> crm:P2_has_type <…/strato-di-crollo>` e
    `<…/strato-di-crollo> a crm:E55_Type`."""
    c, writer = client
    pytest.importorskip("rdflib", reason="rdflib (extra RDF di s3Dgraphy) non è installato")
    from rdflib import URIRef
    from rdflib.namespace import RDF
    word = {"label": "strato di crollo"}
    assert post(c, "3014", {**BASE, "definizione": word})["ok"]
    store, stats = _triples(tmp_path / "scavo.em.json")
    assert _definition_triples(store) == set()
    before, label_only_before = len(store), stats["definitions_label_only"]
    assert label_only_before == 1

    term = {"concept": CROLLO, "label": "strato di crollo"}
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"us": "3014", "values": {**BASE, "definizione": term}})
    assert answer.json()["ok"], answer.json()["message"]
    unit = next(n for n in writer.section()["nodes"] if n["id"] == "US3014")
    assert unit["data"]["definition"] == term, "nel grafo va il CONCETTO, con la parola"
    back = c.get("/v1/scheda/iccd-us-2021/unita?us=3014").json()["values"]
    assert back["definizione"] == term

    store, stats = _triples(tmp_path / "scavo.em.json")
    (pair,) = _definition_triples(store)
    assert pair[1] == URIRef(CROLLO)
    assert (URIRef(CROLLO), RDF.type, URIRef(CRM + "E55_Type")) in store
    assert stats["definitions_label_only"] == 0
    assert len(store) - before == 2, (before, len(store))
    print(f"\n  US 3014 · triple: parola {before} (label_only {label_only_before}) → "
          f"concetto {len(store)} (label_only {stats['definitions_label_only']})")


def test_a_word_outside_the_list_is_still_accepted_and_still_has_no_triple(client, tmp_path):
    c, writer = client
    assert post(c, "3005", {**BASE, "definizione": {"label": "piano pavimentale"}})["ok"]
    unit = next(n for n in writer.section()["nodes"] if n["id"] == "US3005")
    assert unit["data"]["definition"] == {"label": "piano pavimentale"}
    store, stats = _triples(tmp_path / "scavo.em.json")
    assert _definition_triples(store) == set() and stats["definitions_label_only"] == 1


@pytest.mark.parametrize("fid,concept,qualia", [
    ("consistenza", "https://w3id.org/extendedmatrix/vocab/us-consistenza/friabile", "texture"),
    ("colore", "https://w3id.org/extendedmatrix/vocab/us-colore/marrone-scuro", "color"),
])
def test_a_qualia_box_lands_its_concept_as_the_property_value(client, fid, concept, qualia):
    c, writer = client
    assert post(c, "3014", {**BASE, fid: {"concept": concept, "label": "x"}})["ok"]
    section = writer.section()
    nodes = {n["id"]: n for n in section["nodes"]}
    props = [nodes[e["target"]] for e in section["edges"]
             if e["source"] == "US3014" and e["edge_type"] == "has_property"]
    (prop,) = [p for p in props if p["name"] == qualia]
    assert prop["description"] == concept, "il valore della PropertyNode è l'URI, non la parola"
