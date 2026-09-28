"""I widget strutturati, e muoversi fra le unità (notte del 22 ottobre).

Il generatore accettava i valori strutturati e rifiutava per nome il testo
dove serve una lista (referto del 19): dal modulo, COPRE e MISURE tornavano
rifiutate perché il modulo mandava soltanto testo. Da stanotte ogni tipo di
valore (SPEC §1.5) ha il suo widget (`web/widgets.js`), e questo file tiene
insieme le tre metà di quella promessa:

* il SERVIZIO dà ai widget ciò che serve senza inventarlo — i concetti di un
  vocabolario (vendorati da `sync-schede.sh`), le qualia che una riga di misura
  può dichiarare (dal datamodel), le unità della stanza con definizione, area e
  proposte AI, i periodi, le attività e le foto;
* le FORME che i widget compongono passano dal generatore e tornano uguali;
* le funzioni del front-end che si possono sbagliare in silenzio — l'ORCID che
  diventerebbe l'id di una persona, l'ordine di ‹ ›, le righe di misura a metà,
  i filtri che si combinano — si ESEGUONO con node, come `thumbbarPlan`.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil

import pytest

import sorgenti
from app import operazioni as O
from app import scheda as S
from app.writer import LocalWriter, choices_of, units_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
ORCID = "0000-0002-1825-0097"

needs_node = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node non è installato")
_run = sorgenti.esegui


@pytest.fixture
def client(tmp_path, monkeypatch):
    """L'app vera, il writer locale su un file, un'identità fissata."""
    from fastapi.testclient import TestClient

    import app.main as M
    from app.assets import InMemoryAssetStore
    from app.tools import build_registry

    monkeypatch.delenv("STRATIGRAPH_SCHEDE_DIR", raising=False)
    writer = LocalWriter(str(tmp_path / "scavo.em.json"), study="Cencelle")
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "STORE", InMemoryAssetStore())
    monkeypatch.setattr(M, "REGISTRY", build_registry(writer, M.STORE))
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    return TestClient(M.app), writer


def post(c, us, values, **extra):
    answer = c.post("/v1/scheda/iccd-us-2021",
                    json={"us": us, "values": values, "create": True, **extra})
    assert answer.status_code == 200, answer.text
    return answer.json()


BASE = {"localita": "Leopoli-Cencelle", "area": "Area 3000"}


# ═══ 1 · IL SERVIZIO DÀ AI WIDGET CIÒ CHE SERVE, SENZA INVENTARLO ═══════════

def test_the_vocabularies_the_schede_name_are_vendored_beside_them():
    """Uno per ogni schema che una scheda vendorata nomina, e fuori da
    `schede/`: là ogni `*.json` si legge come una definizione."""
    named = set()
    for path in (ROOT / "schede").rglob("*.json"):
        if path.name == "index.json":
            continue
        header = json.loads(path.read_text(encoding="utf-8"))["header"]
        named |= {v["id"] for v in header.get("vocabularies") or []}
    vendored = {p.stem for p in (ROOT / "vocabolari").glob("*.json")}
    assert named and named == vendored
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY vocabolari ./vocabolari" in dockerfile


def test_a_declared_scheme_says_so_and_invents_no_concept(client):
    """La DEFINIZIONE ICCD: la norma prescrive un vocabolario che nessuno ha
    pubblicato in SKOS. Il nodo risponde, con zero concetti e lo stato."""
    c, _ = client
    said = c.get("/v1/vocabolario/iccd-us-definizione?lang=it").json()
    assert said["status"] == "declared"
    assert said["concepts"] == []


def test_a_resolvable_scheme_labels_its_concepts_in_the_asked_language(client):
    """La fixture spagnola, in italiano: l'etichetta viene dall'ALLINEAMENTO
    (`exactMatch`), risolto da `stratigraph-templates`, non tradotta qui."""
    c, _ = client
    es = c.get("/v1/vocabolario/fx-ue-definicion-es?lang=es").json()
    it = c.get("/v1/vocabolario/fx-ue-definicion-es?lang=it").json()
    by_es = {x["concept"]: x["label"] for x in es["concepts"]}
    by_it = {x["concept"]: x["label"] for x in it["concepts"]}
    crollo = "https://example.invalid/fixture/ue-definicion-es/derrumbe"
    assert by_es[crollo] == "estrato de derrumbe"
    assert by_it[crollo] == "strato di crollo"
    # lo schema non è un concetto di sé stesso
    assert not any(k.endswith("/ue-definicion-es/") for k in by_es)


def test_a_vocabulary_the_node_does_not_have_is_a_404_and_no_path_escapes(client):
    c, _ = client
    assert c.get("/v1/vocabolario/nessuno?lang=it").status_code == 404
    assert S.vocabulary("../schede/index", "it") is None
    assert S.vocabulary("iccd-us-definizione/../x", "it") is None


def test_the_rows_of_a_measurement_offer_the_datamodels_measuring_qualia():
    """Le qualia di una riga vengono dal datamodel (quelle con un numero e
    un'unità), e il default della casella dalla ricetta: QUOTE → elevation."""
    served = {f["id"]: f for f in S.find("iccd-us-2021").for_browser("it")["fields"]}
    quote, misure = served["quote"]["measures"], served["misure"]["measures"]
    assert quote["default"] == "elevation"
    assert quote["qualia"][0]["id"] == "elevation", "il default è offerto per primo"
    assert misure["default"] is None
    ids = {q["id"] for q in misure["qualia"]}
    assert {"length", "width", "thickness", "height"} <= ids
    assert "color" not in ids, "una qualia che non si misura in metri"
    assert all(q["units"] for q in misure["qualia"])
    # e il legame al grafo resta dietro, come sempre
    assert "graph" not in served["misure"] and "verdict" not in served["misure"]


def _measures(scheda_id, lang, field):
    served = {f["id"]: f for f in S.find(scheda_id).for_browser(lang)["fields"]}
    return {q["id"]: q for q in served[field]["measures"]["qualia"]}


def test_the_measures_speak_the_cards_language_from_the_datamodel():
    """2026-10-24, §C: «Thickness» diventa la parola del DATAMODEL nella lingua
    della SCHEDA, attraverso il nodo. Una sola strada: `qualia_label` di
    s3Dgraphy. Se la parola qui fosse scritta a mano, questo test la vedrebbe
    uguale alla libreria per caso; lo confronta con la libreria apposta."""
    labels = pytest.importorskip("s3dgraphy.tools.datamodel_i18n")
    it = _measures("iccd-us-2021", "it", "misure")
    es = _measures("es-ue-demo-2026", "es", "cota")
    en = _measures("iccd-us-2021", "en", "misure")
    assert it["thickness"]["label"] == "Spessore"
    assert es["thickness"]["label"] == "Espesor"
    assert en["thickness"]["label"] == "Thickness"
    for q in it.values():
        assert q["label"] == labels.qualia_label(q["id"], "it"), q["id"]
    for q in es.values():
        assert q["label"] == labels.qualia_label(q["id"], "es"), q["id"]
    # il nome inglese resta, per le definizioni già in cache e per chi lo vuole
    assert it["thickness"]["name"] == "Thickness"
    # e il gruppo, che diventa l'optgroup del menu
    assert it["thickness"]["group_label"] == labels.qualia_subcategory_label(
        "dimensional", "it")
    assert "label_lang" not in it["thickness"]


def test_a_card_in_a_language_the_datamodel_lacks_says_its_word_is_english():
    """La ficha ungherese (hu · it): il datamodel non ha l'ungherese, quindi la
    parola è l'inglese — e lo dice, invece di passarla per ungherese."""
    pytest.importorskip("s3dgraphy.tools.datamodel_i18n")
    hu = _measures("hu-rl-demo-2026", "hu", "melyseg")
    assert hu["thickness"]["label"] == "Thickness"
    assert hu["thickness"]["label_lang"] == "en"
    it = _measures("hu-rl-demo-2026", "it", "melyseg")
    assert it["thickness"]["label"] == "Spessore" and "label_lang" not in it["thickness"]


def test_the_measures_follow_the_card_and_not_the_interface(client):
    """La lingua è quella chiesta al nodo per la DEFINIZIONE (`?lang=`), che
    `shell.js::cardLanguageFor` sceglie fra quelle della scheda: l'interfaccia in
    ebraico non la cambia. E la definizione è ciò che il telefono mette in cache
    (`scheda.js::definitionFor`), quindi le parole valgono anche offline."""
    c, _ = client
    body = c.get("/v1/schede/iccd-us-2021?lang=it").json()
    misure = {f["id"]: f for f in body["fields"]}["misure"]["measures"]
    assert {q["id"]: q["label"] for q in misure["qualia"]}["thickness"] == "Spessore"
    widgets = (WEB / "widgets.js").read_text(encoding="utf-8")
    assert "q.label || q.name" in widgets
    assert "q.group_label || q.group" in widgets
    scheda = (WEB / "scheda.js").read_text(encoding="utf-8")
    assert "cache.setItem(key, JSON.stringify(fresh))" in scheda


def test_the_units_of_a_room_carry_definition_area_and_what_ai_proposed(client):
    c, _ = client
    post(c, "3005", {**BASE, "definizione": {"label": "taglio di fossa"}})
    post(c, "3020", {**BASE, "area": "Area 1000", "definizione": {"label": "crollo"},
                     "descrizione": "tegole", "interpretazione": "tetto"},
         authored_by={"descrizione": "ai", "interpretazione": "ai"}, model="m")
    units = {u["number"]: u for u in c.get("/v1/room/units").json()["units"]}
    assert units["3005"]["definition"] == "taglio di fossa"
    assert units["3005"]["area"] == ["Area 3000"]
    assert units["3005"]["ai"] == 0
    assert units["3020"]["area"] == ["Area 1000"]
    assert units["3020"]["ai"] == 2
    # validarne una la toglie dal conto
    assert c.post("/v1/validate", json={"us": "3020", "fields": ["descrizione"]}).json()["ok"]
    units = {u["number"]: u for u in c.get("/v1/room/units").json()["units"]}
    assert units["3020"]["ai"] == 1


def test_the_choices_of_a_room_are_its_periods_activities_and_photos(client):
    c, _ = client
    post(c, "3018", {**BASE, "periodo": {"name": "Periodo IV"},
                     "fotografie": ["foto/CE26-3018-01.jpg"]})
    said = c.get("/v1/room/choices").json()
    assert [e["name"] for e in said["epochs"]] == ["Periodo IV"]
    assert said["activities"] == []
    (photo,) = said["photos"]
    assert photo["url"] == "foto/CE26-3018-01.jpg" and photo["unit"] == "US3018"


def test_the_choices_read_the_same_document_the_units_do():
    """Una sola lettura dei due scrivani, come `units_of`."""
    doc = {"graphs": {"g": {"nodes": [
        {"id": "e1", "node_type": "EpochNode", "name": "Fase IV.1"},
        {"id": "a1", "node_type": "ActivityNodeGroup", "name": "Spoliazione"},
        {"id": "r1", "node_type": "resource", "name": "x.jpg", "data": {"url": "s3://x"}},
        {"id": "r2", "node_type": "resource", "name": "y.jpg",
         "data": {"url": "s3://y", "removed": True}},
    ], "edges": []}}}
    said = choices_of(doc)
    assert [x["id"] for x in said["epochs"]] == ["e1"]
    assert [x["id"] for x in said["activities"]] == ["a1"]
    assert [x["url"] for x in said["photos"]] == ["s3://x"], "un tombstone non è una foto"
    assert units_of(doc) == []


# ═══ 2 · LE FORME DEI WIDGET PASSANO DAL GENERATORE E TORNANO UGUALI ════════

def test_a_NEW_scheda_with_the_widgets_values_is_accepted_and_reads_back(client):
    """La prova della notte, dalla porta vera: da scheda NUOVA, COPRE con due
    unità (una c'è, una no), MISURE con tre righe, DEFINIZIONE come termine.
    Il 19 COPRE e MISURE sarebbero tornate rifiutate per nome."""
    c, writer = client
    post(c, "3018", {**BASE, "definizione": {"label": "piano pavimentale"}})
    values = {**BASE,
              "copre": ["3018", "3023"],
              "misure": [{"qualia": "length", "value": "4.80", "unit": "m"},
                         {"qualia": "width", "value": "3.15", "unit": "m"},
                         {"qualia": "thickness", "label": "spessore max",
                          "value": "0.40", "unit": "m"}],
              "definizione": {"label": "strato di crollo"}}
    said = post(c, "3014", values)
    assert said["ok"], said["message"]
    assert "rifiut" not in said["message"].lower()

    section = writer.section()
    nodes = {n["id"]: n for n in section["nodes"]}
    edges = [(e["source"], e["edge_type"], e["target"]) for e in section["edges"]]
    assert ("US3014", "overlies", "US3018") in edges
    assert ("US3014", "overlies", "US3023") in edges
    assert nodes["US3023"]["data"]["scheda"]["stub"] is True, "creata minima e SEGNATA"
    props = sorted((nodes[t]["name"], nodes[t]["description"], nodes[t]["data"]["units"])
                   for s, k, t in edges if s == "US3014" and k == "has_property")
    assert props == [("length", "4.80", "m"), ("thickness", "0.40", "m"),
                     ("width", "3.15", "m")]

    back = c.get("/v1/scheda/iccd-us-2021/unita?us=3014").json()["values"]
    assert back["copre"] == ["3018", "3023"]
    assert back["misure"] == values["misure"]
    assert back["definizione"] == {"label": "strato di crollo"}


def test_a_term_from_a_vocabulary_lands_as_its_concept(client):
    """Il termine scelto dal vocabolario (la fixture spagnola): nel grafo va il
    CONCETTO, e l'etichetta lo accompagna (`data.definition`)."""
    c, writer = client
    term = {"concept": "https://example.invalid/fixture/ue-definicion-es/derrumbe",
            "label": "strato di crollo"}
    answer = c.post("/v1/scheda/es-ue-demo-2026",
                    json={"us": "13", "create": True,
                          "values": {"yacimiento": "Tarraco", "definicion": term,
                                     "cubre": ["14"]}}).json()
    assert answer["ok"], answer["message"]
    from s3dgraphy.crdt import get_field
    unit = next(n for n in writer.section()["nodes"] if n["id"] == "US13")
    assert get_field(unit, "data.definition") == term


def test_the_widgets_shapes_are_the_ones_the_generator_accepts():
    """Ogni forma che `widgets.js` compone, contro `_normalise`: una persona con
    ORCID, un periodo scelto dalla stanza (con il suo id), le foto."""
    iccd = S.find("iccd-us-2021")
    plan = O.plan(iccd, {**BASE,
                         "responsabile_compilazione": {"name": "E. D.", "ref": f"orcid:{ORCID}"},
                         "periodo": {"name": "Periodo IV", "ref": "e1"},
                         "fotografie": ["foto/a.jpg"]},
                  number="12", section={"nodes": [
                      {"id": "e1", "node_type": "EpochNode", "name": "Periodo IV"}],
                      "edges": []}, ts="2026-10-22T00:00:00Z", create=True)
    assert plan.refused == {}
    adds = [op for op in plan.ops if op["op"] == "add_edge"]
    assert any(op["edge_type"] == "has_first_epoch" and op["target"] == "e1" for op in adds), (
        "il periodo della stanza è quello, non uno nuovo con lo stesso nome")
    assert any(op["edge_type"] == "has_author" and op["target"] == f"orcid:{ORCID}"
               for op in adds)


# ═══ 3 · IL FRONT-END, ESEGUITO ═════════════════════════════════════════════

@needs_node
def test_an_orcid_passes_only_with_its_check_digit():
    """Il riferimento diventa l'id del nodo autore: un ORCID sbagliato sarebbe
    una seconda persona. Il campione è quello che orcid.org pubblica."""
    said = _run("""
const w = await import("./web/widgets.js");
console.log(JSON.stringify([
  w.orcidOk("0000-0002-1825-0097"), w.orcidOk("orcid:0000-0002-1825-0097"),
  w.orcidOk("https://orcid.org/0000-0002-1825-0097"),
  w.orcidOk("0000-0002-1825-0098"), w.orcidOk("0000-0002-1825-009"),
  w.orcidOk("0000-0001-5109-3700"), w.orcidOk("0000-0002-9079-593X")]));
""")
    assert said[:3] == [ORCID] * 3
    assert said[3] is None, "la cifra di controllo sbagliata passa"
    assert said[4] is None
    assert said[5] == "0000-0001-5109-3700"
    assert said[6] == "0000-0002-9079-593X", "la X finale è una cifra di controllo"


@needs_node
def test_the_unit_prefix_comes_from_the_definitions_pattern():
    """«US 3018», «Contexto 14»: dal pattern della chiave umana, non da qui."""
    said = _run("""
const w = await import("./web/widgets.js");
const iccd = {human_key_pattern: "US {us} — {area} ({localita})", unit_field: "us"};
const es = {human_key_pattern: "Contexto {contexto} · {yacimiento}", unit_field: "contexto"};
const hu = {human_key_pattern: "{lelohely} · {retegszam}", unit_field: "retegszam"};
console.log(JSON.stringify([w.unitPrefix(iccd), w.unitPrefix(es), w.unitPrefix(hu),
  w.bareNumber("US 3018", iccd), w.bareNumber("us3018", iccd), w.bareNumber("3018", iccd),
  w.bareNumber("Contexto 14", es)]));
""")
    assert said == ["US ", "Contexto ", "", "3018", "3018", "3018", "14"]


@needs_node
def test_the_order_of_the_arrows_is_numeric_one_per_number_and_stubs_to_fill():
    said = _run("""
const w = await import("./web/widgets.js");
// la scheda vera PRIMA dello stub: l'ultimo che arriva non deve vincere
const units = [{number: "3020"}, {number: "3005"}, {number: "3100"}, {number: "3023", stub: false},
               {number: ""}, {number: "3023", stub: true}, {number: "998"}];
console.log(JSON.stringify({order: w.orderedUnits(units).map(u => u.number),
  fill: ["3005", "3023", "4000"].map(n => w.toFill(n, units)),
  stubOnly: w.toFill("1", [{number: "1", stub: true}])}));
""")
    assert said["order"] == ["998", "3005", "3020", "3023", "3100"], (
        "ordine NUMERICO, non alfabetico (998 prima di 3005), e un numero una volta")
    assert said["fill"] == [False, False, True], "la scheda vera batte lo stub"
    assert said["stubOnly"] is True


@needs_node
def test_a_half_written_measurement_row_does_not_leave():
    """La riga aggiunta e non riempita resta a schermo e non parte: il
    generatore la rifiuterebbe («ogni riga … con un valore»)."""
    said = _run("""
const s = await import("./web/scheda.js");
const def = {id: "x", version: "1", fields: [{id: "misure", type: "quantity_list"},
             {id: "copre", type: "unit_ref_list"}]};
const state = {values: {misure: [{qualia: "length", value: "4.8", unit: "m"},
                                 {qualia: "width", value: "", unit: "m"}],
                        copre: ["3018", ""]},
               loaded: new Set(["misure"]), authored: {}, us: "3014", keyField: null};
const only = {values: {misure: [{qualia: "width", value: " ", unit: "m"}]},
              loaded: new Set(["misure"]), authored: {}, us: "3014", keyField: null};
console.log(JSON.stringify([s.payloadFor(def, state).values, s.payloadFor(def, only).values]));
""")
    assert said[0] == {"misure": [{"qualia": "length", "value": "4.8", "unit": "m"}],
                       "copre": ["3018"]}
    assert said[1] == {"misure": None}, (
        "una casella riletta che resta solo con righe a metà si SVUOTA, non manda righe vuote")


@needs_node
def test_the_filters_combine_and_the_count_is_of_what_matches():
    said = _run("""
const i = await import("./web/indice.js");
const listing = [{id: "iccd", fields: 60}];
const units = [
  {number: "3005", definition: "taglio di fossa", area: ["Area 3000"], ai: 0, fields: 40, scheda: {template: "iccd"}},
  {number: "3020", definition: "strato di crollo", area: ["Area 1000"], ai: 2, fields: 6, scheda: {template: "iccd"}},
  {number: "3021", definition: "muro", area: ["Area 1000"], ai: 0, fields: 4},
  {number: "3014", definition: "strato di crollo", area: ["Area 3000"], ai: 1, fields: 31, scheda: {template: "iccd"}}];
const n = (f) => units.filter((u) => i.matches(u, {q: "", area: null, ai: false, inc: false, ...f}, listing, null))
                      .map((u) => u.number);
console.log(JSON.stringify({area: n({area: "Area 1000"}), ai: n({ai: true}),
  both: n({area: "Area 1000", ai: true}), crollo: n({q: "crollo"}), num: n({q: "US 30"}),
  inc: n({inc: true}), all: n({}), none: n({q: "zzz"})}));
""")
    assert said["area"] == ["3020", "3021"]
    assert said["ai"] == ["3020", "3014"]
    assert said["both"] == ["3020"], "i filtri si COMBINANO"
    assert said["crollo"] == ["3020", "3014"]
    assert said["num"] == ["3005", "3020", "3021", "3014"], "«US 30» cerca il numero"
    assert said["inc"] == ["3020", "3021"], (
        "meno della metà: 6/60 e 4/60 (sulla definizione di fallback), non 40 né 31")
    assert len(said["all"]) == 4 and said["none"] == []


# ═══ 4 · I VINCOLI DEL FRONT-END, SUL SORGENTE ═════════════════════════════

def test_the_widgets_write_through_one_function_and_have_no_road_to_the_graph():
    """Le scritture passano da `writeValue` (lo stesso `save()` di sempre);
    le sole richieste sono LETTURE del servizio, mai della stanza."""
    code = sorgenti.senza_prosa((WEB / "widgets.js").read_text(encoding="utf-8"))
    assert "writeValue(state, field.id, value)" in code
    assert not re.search(r"state\.values\[[^\]]+\]\s*=(?!=)", code), "una seconda via ai valori"
    assert ".send(" not in code and "method:" not in code and "WebSocket" not in code
    for call in re.findall(r"fetch\(\s*`?([^`\"',)]+)", code):
        assert "/v1/rooms" not in call


def test_the_new_words_are_the_mockups_keys_in_en_and_it():
    """Le chiavi del mockup approvato (oggetto `UI`), in `en` e in `it`.

    Contate nella parte SCRITTA A MANO della pagina: il blocco fra
    `>>> ui_strings.py` e `<<< ui_strings.py` è generato dall'xlsx dei partner
    (`he`, `de`, 24 ottobre) e ripete le chiavi per costruzione."""
    page = (WEB / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"  // >>> ui_strings\.py.*?  // <<< ui_strings\.py", "", page,
                  flags=re.S)
    for key in ("w.add_unit", "w.to_fill", "w.remove", "w.unit_note", "w.search",
                "w.term_note", "w.what", "w.value", "w.add_row", "w.pick_photos",
                "w.orcid_note", "w.new_epoch", "nav.units", "nav.prev_unit",
                "nav.next_unit", "nav.jump", "nav.no_unit", "flt.search", "flt.ai",
                "flt.incomplete", "flt.count", "flt.none"):
        assert page.count(f'"{key}"') == 2, key


def test_the_open_unit_lives_in_the_address():
    shell = (WEB / "shell.js").read_text(encoding="utf-8")
    assert 'window.addEventListener("hashchange"' in shell
    assert "history.pushState" in shell
    assert "event.altKey" in shell and "typing(event.target)" in shell
