"""La mappa della stanza: luoghi e tagli con la loro impronta (NIGHT impronte
di saggi e tagli, decisioni di E.D. dell'11 novembre 2026).

* le impronte si LEGGONO dal grafo (qualia `footprint`, WKT con il CRS dentro):
  il sito, le aree, i saggi e i tagli; una US positiva non arriva mai alla
  mappa, anche se nel grafo avesse un'impronta;
* il clic su un saggio filtra l'elenco: le unità dicono in quali luoghi stanno;
* la base viene da un catalogo con licenza e `offline` — lo STESSO di EMStudio,
  vendorizzato da s3Dgraphy (`sync-basi.sh`);
* il ponte dei tasselli: cache su disco, User-Agent dichiarato, intestazioni di
  cache rispettate, un tassello per richiesta (nessun prefetch), e senza rete la
  copia che c'è;
* «Apri in PyArchInit» dà il file di scambio.
"""

from __future__ import annotations

import io
import json
import pathlib
import time
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ORCID = "0000-0002-1825-0097"
EPSG = "<http://www.opengis.net/def/crs/EPSG/0/3004> "


def _sq(x, y, w):
    return f"{EPSG}POLYGON (({x} {y}, {x + w} {y}, {x + w} {y + w}, {x} {y + w}, {x} {y}))"


def _doc():
    """Un container come lo scrive l'importer di PyArchInit (s3Dgraphy 12 nov):
    un sito, un'area, un saggio, una US positiva, una USN — e, per prova, una
    impronta sulla US positiva, che la mappa NON deve mostrare."""
    nodes = [
        {"id": "site", "node_type": "LocationNodeGroup", "name": "Scavo di prova",
         "data": {"kind": "toponym", "level": "sito"}},
        {"id": "loc::area::study::1", "node_type": "LocationNodeGroup", "name": "1",
         "data": {"kind": "study", "level": "area"}},
        {"id": "loc::saggio::study::I", "node_type": "LocationNodeGroup", "name": "I",
         "data": {"kind": "study", "level": "saggio"}},
        {"id": "u1", "node_type": "US", "name": "1.US1", "description": "strato"},
        {"id": "u2", "node_type": "USN", "name": "1.USN2", "description": "taglio"},
    ]
    edges = []
    for owner, wkt in (("site", _sq(2324900, 4881900, 100)),
                       ("loc::area::study::1", _sq(2324905, 4881905, 30)),
                       ("loc::saggio::study::I", _sq(2324910, 4881910, 10)),
                       ("u1", _sq(2324911, 4881911, 1)),
                       ("u2", _sq(2324913, 4881911, 1))):
        pid = f"fp-{owner}"
        nodes.append({"id": pid, "node_type": "property", "name": "footprint",
                      "data": {"property_type": "footprint", "value": wkt}})
        edges.append({"id": f"{owner}-hp", "edge_type": "has_property",
                      "source": owner, "target": pid})
    for u in ("u1", "u2"):
        edges.append({"id": f"{u}-in", "edge_type": "is_in_location",
                      "source": u, "target": "loc::saggio::study::I"})
    return {"header": {"format": "em.json", "version": "1.0"},
            "graphs": {"scavo": {"graph_id": "scavo", "nodes": nodes, "edges": edges}}}


# ── le impronte, dal grafo ──────────────────────────────────────────────────

def test_the_map_has_places_and_cuts_and_no_positive_unit():
    from app.mappa import map_of
    m = map_of(_doc())
    places = {p["name"]: p for p in m["places"]}
    assert set(places) == {"Scavo di prova", "1", "I"}
    assert [p["level"] for p in m["places"]] == ["sito", "area", "saggio"]
    assert [c["id"] for c in m["cuts"]] == ["u2"]
    assert all(p["id"] != "u1" for p in m["places"] + m["cuts"])
    assert m["crs"] == "EPSG:3004"
    # i vertici come il grafo li dice: nessun ricalcolo
    assert places["I"]["rings"][0][0][0] == [2324910.0, 4881910.0]
    assert m["units_by_place"]["loc::saggio::study::I"] == ["u1", "u2"]


def test_the_map_is_in_lonlat_beside_its_crs_when_pyproj_is_there():
    pytest.importorskip("pyproj")
    from app.mappa import map_of
    m = map_of(_doc())
    assert m["projected"] is True
    lon, lat = m["places"][2]["lonlat"][0][0][0]
    # Monte Mario / Italy zone 2: un saggio in Italia
    assert 6 < lon < 19 and 36 < lat < 48


def test_the_units_say_their_places(tmp_path):
    from app.writer import units_of
    us = {u["id"]: u for u in units_of(_doc())}
    assert us["u2"]["places"] == ["loc::saggio::study::I"]


def test_the_room_map_route_reads_the_container(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as M
    from app.writer import LocalWriter
    path = tmp_path / "scavo.em.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    writer = LocalWriter(str(path), study="Prova")
    monkeypatch.setattr(M, "WRITER", writer)
    monkeypatch.setattr(M, "_author", lambda request: ORCID)
    c = TestClient(M.app)
    body = c.get("/v1/room/map").json()
    assert [p["name"] for p in body["places"]] == ["Scavo di prova", "1", "I"]
    assert [b["id"] for b in body["bases"]] == ["s2cloudless-2016", "osm"]
    ex = c.get("/v1/room/map/pyarchinit/loc::saggio::study::I")
    assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"]
    said = ex.json()
    assert said["pyarchinit"] == {"table": "us_table", "filter": {"saggio": "I"}}
    assert said["footprint"]["crs"] == "EPSG:3004"
    assert c.get("/v1/room/map/pyarchinit/nessuno").status_code == 404


# ── la base: un catalogo, quello di EMStudio ────────────────────────────────

def test_the_catalogue_is_the_one_vendored_from_s3dgraphy():
    mine = json.loads((ROOT / "app" / "basi.json").read_text(encoding="utf-8"))
    src = ROOT.parent / "s3Dgraphy" / "src" / "s3dgraphy" / "JSON_config" / "em_basemap_sources.json"
    if not src.exists():
        pytest.skip("s3Dgraphy is not beside this checkout")
    assert mine == json.loads(src.read_text(encoding="utf-8")), "run ./sync-basi.sh"
    osm = next(s for s in mine["sources"] if s["id"] == "osm")
    assert osm["offline"] is False


def test_the_bases_route_is_public_and_says_the_licences(tmp_path):
    from fastapi.testclient import TestClient

    import app.main as M
    body = TestClient(M.app).get("/v1/bases").json()
    by = {s["id"]: s for s in body["sources"]}
    assert by["osm"]["offline"] is False and by["s2cloudless-2016"]["offline"] is True
    assert body["default"] == "s2cloudless-2016"
    assert all(s["attribution"] and s["licence"] for s in body["sources"])


# ── il ponte dei tasselli ───────────────────────────────────────────────────

class _Answer(io.BytesIO):
    def __init__(self, body, headers):
        super().__init__(body)
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_bridge_caches_one_tile_and_says_who_it_is(tmp_path, monkeypatch):
    from app import mappa
    monkeypatch.setenv("EM_TILE_CACHE", str(tmp_path))
    asked = []

    def net(req, timeout=10):
        asked.append((req.full_url, req.get_header("User-agent")))
        return _Answer(b"PNG1", {"Content-Type": "image/png", "Cache-Control": "max-age=600"})
    body, h = mappa.tile("osm", 16, 34000, 23000, version="t", opener=net)
    assert body == b"PNG1" and h["X-Tile-Cache"] == "miss"
    assert asked == [("https://tile.openstreetmap.org/16/34000/23000.png", asked[0][1])]
    assert "StratiField" in asked[0][1]
    # fresco: dalla cache, nessuna richiesta
    body, h = mappa.tile("osm", 16, 34000, 23000, opener=net)
    assert h["X-Tile-Cache"] == "hit" and len(asked) == 1
    # UN tassello per richiesta: nessun vicino chiesto (nessun prefetch)
    assert len(list((tmp_path / "osm").rglob("*.png"))) == 1


def test_without_network_the_copy_is_served_and_said(tmp_path, monkeypatch):
    from app import mappa
    monkeypatch.setenv("EM_TILE_CACHE", str(tmp_path))
    ok = lambda req, timeout=10: _Answer(b"JPG", {"Cache-Control": "max-age=1"})  # noqa: E731
    mappa.tile("s2cloudless-2016", 12, 2150, 1500, opener=ok)
    time.sleep(1.1)

    def down(req, timeout=10):
        raise urllib.error.URLError("no network")
    body, h = mappa.tile("s2cloudless-2016", 12, 2150, 1500, opener=down)
    assert body == b"JPG" and h["X-Tile-Cache"] == "stale"
    with pytest.raises(mappa.TileRefused) as no:
        mappa.tile("s2cloudless-2016", 12, 2151, 1500, opener=down)
    assert no.value.status == 504


def test_a_tile_outside_the_catalogue_is_refused(tmp_path, monkeypatch):
    from app import mappa
    monkeypatch.setenv("EM_TILE_CACHE", str(tmp_path))
    for src, z, x, y in (("google", 1, 0, 0), ("osm", 25, 0, 0), ("osm", 2, 9, 0),
                         ("mapterhorn", 1, 0, 0)):      # una fonte di quote non è una base
        with pytest.raises(mappa.TileRefused):
            mappa.tile(src, z, x, y, opener=lambda *a, **k: 1 / 0)


def test_no_store_is_not_kept(tmp_path, monkeypatch):
    from app import mappa
    monkeypatch.setenv("EM_TILE_CACHE", str(tmp_path))
    net = lambda req, timeout=10: _Answer(b"X", {"Cache-Control": "no-store"})  # noqa: E731
    mappa.tile("osm", 3, 1, 1, opener=net)
    assert not list(tmp_path.rglob("*.png"))


# ── la pagina ───────────────────────────────────────────────────────────────

def test_the_page_has_the_map_and_its_words():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="nav-map"' in page and 'id="map-host"' in page
    js = (ROOT / "web" / "mappa.js").read_text(encoding="utf-8")
    # i tagli spenti all'inizio, i luoghi accesi
    assert "export const layers = { places: true, cuts: false, base: true, me: true };" in js
    sw = (ROOT / "web" / "sw.js").read_text(encoding="utf-8")
    # il dispositivo tiene solo i tasselli delle fonti che lo permettono
    assert 'url.searchParams.get("k") === "1"' in sw
