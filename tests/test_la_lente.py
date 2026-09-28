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
    "formazione_natura": "artificiale",
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

    # e i buchi, che la lente deve far vedere invece di riempire
    holes = set(lens["holes"])
    assert "isNatural" in holes, ("l'ICCD scrive `formation_mode`, il DAI legge `origin_type`: "
                                  "divergenza vera, segnalata nel referto")
    assert {"soilType", "period", "dating", "shortDescription"} <= holes
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
