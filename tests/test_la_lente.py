"""LA LENTE: la stessa unità letta con la scheda di un altro standard.

La US 3014 si compila con la scheda ICCD; poi la si chiede con la scheda del
DAI (iDAI.field `Layer`, stratigraph-templates `dai-idaifield-layer-2026`) e
con quella dell'IAA (DANA locus). Il nodo rilegge **con la scheda chiesta**
(`?lente=1`) invece che con quella dichiarata dall'unità, e dice che cosa il
grafo sa riempire e che cosa no.

Ciò che la lente legge non è una traduzione: sono gli INDIRIZZI DEL GRAFO che
le due schede hanno in comune — il campo `description`, l'elemento del nodo
`data.definition`, le stesse qualia, gli stessi archi canonici. Dove una scheda
scrive una qualia che l'altra non legge, il buco resta, e il test lo pretende.
"""

from __future__ import annotations

from app import scheda as S

from test_i_widget_strutturati import BASE, client, post  # noqa: F401  (la fixture)

CROLLO = "https://w3id.org/extendedmatrix/vocab/us-definizione/strato-di-crollo"
FRIABILE = "https://w3id.org/extendedmatrix/vocab/us-consistenza/friabile"
DAI = "dai-idaifield-layer-2026"
IAA = "iaa-dana-locus-2026"

US_3014 = {
    **BASE,
    "definizione": {"concept": CROLLO, "label": "strato di crollo"},
    "consistenza": {"concept": FRIABILE, "label": "friabile"},
    "colore": {"label": "bruno chiaro (10YR 6/3)"},
    "descrizione": "Crollo di tegole e pietrame in matrice terrosa.",
    "formazione_natura": "artificial",       # ICCD 2.0.0: la chiave di `origin_type`
    "misure": [{"qualia": "thickness", "label": "spessore max", "value": "0,42", "unit": "m"}],
    "copre": ["3018", "3020"],
    "tagliato_da": ["3009"],
    "posteriore_a": ["3021"],
}


def _written(c):
    for other in ("3018", "3020", "3009", "3021"):
        assert post(c, other, dict(BASE))["ok"]
    answer = post(c, "3014", US_3014)
    assert answer["ok"], answer.get("message")


def test_without_the_lens_the_unit_is_read_with_what_wrote_it(client):
    c, _ = client
    _written(c)
    read = c.get(f"/v1/scheda/{DAI}/unita?us=3014").json()
    assert read["read_with"]["template"] == "iccd-us-2021"
    assert "lens" not in read


def test_the_DAI_lens_on_US_3014(client):
    c, _ = client
    _written(c)
    read = c.get(f"/v1/scheda/{DAI}/unita?us=3014&lente=1").json()
    assert read["read_with"]["template"] == DAI
    lens = read["lens"]
    assert lens["written_with"]["template"] == "iccd-us-2021"
    v = read["values"]

    # ciò che il grafo sa dire alla scheda DAI
    assert v["identifier"] == "3014"
    assert v["category"] == "Layer", "US nel grafo = Erdbefund per la tabella node_type"
    assert v["description"] == US_3014["descrizione"]
    assert v["layerClassification"] == US_3014["definizione"], "lo stesso elemento del nodo"
    assert v["consistency"] == [US_3014["consistenza"]], "stessa qualia `texture`"
    assert v["color"] == [US_3014["colore"]], "stessa qualia `color`, parola libera com'era"
    assert v["dimensionThickness"][0]["value"] == "0,42", "la riga `thickness` di MISURE"
    assert sorted(v["isAbove"]) == ["3018", "3020"], "COPRE = isAbove: `overlies` uscente"
    assert v["isCutBy"] == ["3009"]
    assert v["isAfter"] == ["3021"]

    # ICCD 2.0.0 (2026-09-28): la natura scrive `origin_type`, la stessa qualia di
    # isNatural — prima era un buco (`formation_mode`, mai registrata)
    assert v["isNatural"] == "artificial"

    # e i buchi, che la lente deve far vedere invece di riempire
    holes = set(lens["holes"])
    assert "isNatural" not in holes
    assert {"soilType", "period", "dating", "shortDescription"} <= holes
    assert lens["unread"] == [], "tutto ciò che la ICCD 2.0.0 scrive e il DAI ha, il DAI lo legge"
    assert set(lens["filled"]) | holes == {str(f["id"]) for f in S.find(DAI).fields}
    print(f"\n  lente DAI su US 3014: {len(lens['filled'])} caselle dal grafo, "
          f"{len(holes)} buchi")


def test_the_IAA_lens_on_the_same_unit(client):
    """Terzo termine: la DANA ha poche caselle in comune col grafo di una US
    ICCD, e la lente lo misura."""
    c, _ = client
    _written(c)
    read = c.get(f"/v1/scheda/{IAA}/unita?us=3014&lente=1").json()
    v, lens = read["values"], read["lens"]
    assert v["d_description"] == US_3014["descrizione"]
    assert v["d_locus_no_canonical"] == "3014"
    assert "loci_above" in lens["holes"], ("la DANA dice «sopra» come `is_after` ENTRANTE: la US "
                                          "3014 è posteriore a 3021, quindi 3021 non le sta sopra")
    assert v.get("loci_cutting") == ["3009"], "`cuts` entrante: stesso arco della ICCD"


def test_the_lens_reads_and_does_not_write(client):
    c, writer = client
    _written(c)
    before = len(writer.section()["nodes"]), len(writer.section()["edges"])
    c.get(f"/v1/scheda/{DAI}/unita?us=3014&lente=1")
    assert (len(writer.section()["nodes"]), len(writer.section()["edges"])) == before


# ═══ LE US GIÀ SCRITTE CON `formation_mode` (ICCD ≤ 1.0.2) ═══════════════════

def _written_with_1_0_2(c):
    for other in ("3018", "3020", "3009", "3021"):
        assert post(c, other, dict(BASE))["ok"]
    old = {**US_3014, "formazione_natura": "artificiale"}
    answer = post(c, "3014", old, version="1.0.2")
    assert answer["ok"], answer.get("message")


def test_una_US_1_0_2_senza_lente_si_rilegge_con_la_1_0_2_e_non_perde_niente(client):
    c, _ = client
    _written_with_1_0_2(c)
    read = c.get("/v1/scheda/iccd-us-2021/unita?us=3014").json()
    assert read["read_with"]["version"] == "1.0.2"
    assert read["values"]["formazione_natura"] == "artificiale"


def test_la_lente_della_ICCD_2_0_0_su_una_US_1_0_2_dice_formation_mode_non_la_traduce(client):
    """Stesso campo, verdetto cambiato: il segno del campo c'è, la qualia no. La
    casella nuova resta vuota (niente «artificiale» in una scelta natural/artificial)
    e la proprietà vecchia torna in `unread`, con il campo che l'ha scritta."""
    c, _ = client
    _written_with_1_0_2(c)
    read = c.get("/v1/scheda/iccd-us-2021/unita?us=3014&lente=1").json()
    lens = read["lens"]
    assert read["read_with"]["version"] == "2.0.0"
    assert lens["written_with"] == {"template": "iccd-us-2021", "version": "1.0.2"}
    assert "formazione_natura" in lens["holes"]
    assert {"property": "formation_mode", "value": "artificiale",
            "field": "formazione_natura", "template": "iccd-us-2021"} in lens["unread"]


def test_la_lente_DAI_su_una_US_1_0_2_isNatural_e_un_buco_detto(client):
    c, _ = client
    _written_with_1_0_2(c)
    lens = c.get(f"/v1/scheda/{DAI}/unita?us=3014&lente=1").json()["lens"]
    assert "isNatural" in lens["holes"]
    assert [u["property"] for u in lens["unread"]] == ["formation_mode"]


def test_riscritta_con_la_2_0_0_la_stessa_proprieta_cambia_qualia_non_si_duplica(client, monkeypatch):
    """Il nodo coniato ha lo stesso id (`US3014::formazione_natura`): riscrivere la
    casella con la 2.0.0 lo aggiorna, non ne appende un secondo. (L'orologio va
    avanti: a timbro uguale, per il merge datato, resta chi c'era.)"""
    from app import tools as tools_module, writer as writer_module
    c, writer = client
    _written_with_1_0_2(c)
    for module in (tools_module, writer_module):
        monkeypatch.setattr(module, "_now", lambda: "2099-01-01T00:00:00Z")
    answer = post(c, "3014", {**BASE, "formazione_natura": "artificial"})
    assert answer["data"]["updated"] == ["formazione_natura"], answer["message"]
    props = [n for n in writer.section()["nodes"] if n["id"].endswith("::formazione_natura")]
    assert len(props) == 1
    assert (props[0]["data"]["property_type"], props[0]["description"]) == ("origin_type", "artificial")
    lens = c.get(f"/v1/scheda/{DAI}/unita?us=3014&lente=1").json()["lens"]
    assert "isNatural" in lens["filled"] and lens["unread"] == []
