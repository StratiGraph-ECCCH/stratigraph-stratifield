"""LA MAPPA DI UNA STANZA — i luoghi e i tagli con la loro impronta, e la base.

NIGHT «impronte di saggi e tagli» (decisioni di E.D., 11 novembre 2026). Sulla
mappa di StratiField **niente US positive**: si vedono i LUOGHI (sito, aree,
saggi), i TAGLI (le US negative, livello facoltativo spento all'inizio), la
posizione di chi guarda e una base di contesto. Il rilievo, le piante e le
ortofoto restano a PyArchInit ed EMStudio, che StratiField apre con «Apri in…».

**Le impronte si LEGGONO dal grafo e non si ricalcolano.** Un'impronta è una
`PropertyNode` di qualia `footprint` (s3Dgraphy, qualia 1.6.11) raggiunta con
`has_property`, il cui valore è un WKT con il CRS DENTRO
(`<…/EPSG/0/3004> POLYGON ((…))`). Qui il WKT si legge e basta; chi può averla
lo dice il datamodel (`s3dgraphy.gis.footprint`), e un'impronta su una US
positiva — che il datamodel rifiuta — non arriva alla mappa.

**Le coordinate.** La pagina oggi parla WGS 84 (lat/lon: «Dove sono» le dice
così). Il nodo dà quindi i vertici in due forme: nel loro CRS (quello che il
WKT dichiara, verbatim, per chi le vuole come sono) e in lon/lat, per la vista,
riproiettati con pyproj quando c'è. Il browser porta lon/lat in Web Mercator,
il piano dei tasselli: un cambio di piano, non un ricalcolo dell'impronta.
Senza pyproj (o con un CRS che PROJ non conosce) la mappa si disegna nel CRS
dell'impronta, senza base e senza posizione, e la didascalia lo dice.

**La base** viene da un catalogo con licenza e flag `offline`, LO STESSO di
EMStudio (`basi.json`, copiato da s3Dgraphy con `sync-basi.sh`). Il nodo fa da
ponte: `GET /v1/tiles/{fonte}/{z}/{x}/{y}` con cache su disco, User-Agent
dichiarato, intestazioni di cache rispettate e **nessun prefetch** — per OSM
(`offline: false`) la policy lo vieta, e il ponte serve solo ciò che una
persona sta guardando.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

HERE = pathlib.Path(__file__).resolve().parent
BASI = HERE / "basi.json"

QUALIA = "footprint"


# ── chi ha un'impronta: lo dice il datamodel ───────────────────────────────

def _verdict(node: Dict[str, Any]) -> Dict[str, Any]:
    """`{ok, owner}` dal datamodel (s3Dgraphy ≥ dev103, `gis.footprint`).

    Una s3Dgraphy più vecchia non ha la regola: allora vale quella che la
    regola dichiara (qualia 1.6.11), scritta qui UNA volta e da togliere
    quando la libreria pubblicata la porta — i luoghi (LocationNodeGroup) e
    le US negative (USN); mai una US positiva né una USNt."""
    try:
        from s3dgraphy.gis.footprint import footprint_verdict
        v = footprint_verdict(node)
        return {"ok": bool(v.get("ok")), "owner": v.get("owner")}
    except ImportError:
        kind = str(node.get("node_type") or "")
        if kind == "USN":
            return {"ok": True, "owner": "cut"}
        if kind in ("LocationNodeGroup", "UT", "UT0", "district"):
            return {"ok": True, "owner": "place"}
        return {"ok": False, "owner": None}


def _data(node: Dict[str, Any]) -> Dict[str, Any]:
    return node.get("data") if isinstance(node.get("data"), dict) else {}


def _attr(node: Dict[str, Any], key: str) -> Any:
    for src in (_data(node), node.get("attributes") or {}, node):
        if isinstance(src, dict) and src.get(key) not in (None, ""):
            return src[key]
    return None


def _value(prop: Dict[str, Any]) -> Optional[str]:
    try:
        from s3dgraphy.crdt import get_field
        v = get_field(prop, "data.value")
    except Exception:  # noqa: BLE001
        v = None
    return v if isinstance(v, str) else (_data(prop).get("value") or prop.get("value"))


# ── la proiezione per la vista ─────────────────────────────────────────────

_TRANSFORMERS: Dict[str, Any] = {}


def to_lonlat(crs: Optional[str]):
    """La funzione `(x, y) → (lon, lat)` per `crs`, o None (niente pyproj, o un
    CRS che PROJ non conosce, o il frame locale della scena)."""
    if not crs or not str(crs).upper().startswith("EPSG:"):
        return None
    if crs.upper() == "EPSG:4326":
        return lambda x, y: (x, y)
    if crs in _TRANSFORMERS:
        return _TRANSFORMERS[crs]
    try:
        from pyproj import Transformer
        t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        fn = (lambda x, y, _t=t: _t.transform(x, y))
    except Exception:  # noqa: BLE001 — pyproj assente, o un codice ignoto
        fn = None
    _TRANSFORMERS[crs] = fn
    return fn


def from_lonlat(crs: Optional[str]):
    """L'inverso, per dire la posizione di chi guarda nel CRS del sito."""
    if not crs or not str(crs).upper().startswith("EPSG:"):
        return None
    try:
        from pyproj import Transformer
        t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        return lambda lon, lat, _t=t: _t.transform(lon, lat)
    except Exception:  # noqa: BLE001
        return None


# ── i luoghi e i tagli di un documento ─────────────────────────────────────

def _polygons(wkt: str) -> Tuple[Optional[str], List[Any]]:
    from s3dgraphy.geometry.wkt import WktError, wkt_to_polygons
    try:
        crs, _shape, polys = wkt_to_polygons(wkt)
    except WktError:
        return None, []
    return crs, polys


def map_of(document: Dict[str, Any]) -> Dict[str, Any]:
    """Che cosa disegna la mappa di una stanza, letto dal suo em.json.

    `{places, cuts, crs, crs_list, projected, units_by_place}`:

    * `places` — i luoghi CON e senza impronta (sito, aree, saggi: i
      `LocationNodeGroup`, con `level` e `kind`); `rings` (nel CRS
      dell'impronta) e `lonlat` (gli stessi anelli in WGS 84, quando si può);
    * `cuts` — le US negative con un'impronta (le altre non hanno niente da
      disegnare);
    * `units_by_place` — per ogni luogo, le unità che vi stanno
      (`is_in_location`), per aprire l'elenco filtrato con un clic.

    Le US positive non ci sono, mai: la loro geometria è il proxy."""
    from .conversazione import is_message

    places: List[Dict[str, Any]] = []
    cuts: List[Dict[str, Any]] = []
    by_place: Dict[str, List[str]] = {}
    crs_seen: Dict[str, int] = {}
    projected = True
    for section in (document.get("graphs") or {}).values():
        nodes = {str(n.get("id")): n for n in section.get("nodes") or []
                 if not is_message(n) and not _data(n).get("removed")}
        edges = [e for e in section.get("edges") or []
                 if not (e.get("data") or {}).get("removed")
                 and not (e.get("attributes") or {}).get("removed")]
        fp: Dict[str, Dict[str, Any]] = {}
        for e in edges:
            if e.get("edge_type") != "has_property":
                continue
            prop = nodes.get(str(e.get("target")))
            if not prop or (_data(prop).get("property_type") or prop.get("name")) != QUALIA:
                continue
            fp[str(e.get("source"))] = prop
        for e in edges:
            if e.get("edge_type") == "is_in_location":
                src, tgt = str(e.get("source")), str(e.get("target"))
                if src in nodes and tgt in nodes and str(
                        nodes[src].get("node_type") or "") != "LocationNodeGroup":
                    by_place.setdefault(tgt, []).append(src)
        for nid, node in nodes.items():
            kind = str(node.get("node_type") or "")
            is_place = kind == "LocationNodeGroup"
            prop = fp.get(nid)
            if not is_place and prop is None:
                continue
            v = _verdict(node)
            if prop is not None and not v["ok"]:
                continue                     # una US positiva: il proxy, non la mappa
            entry: Dict[str, Any] = {
                "id": nid, "name": str(node.get("name") or nid), "node_type": kind,
                "level": _attr(node, "level"), "kind": _attr(node, "kind"),
                "owner": v["owner"] or ("place" if is_place else None),
                "has_footprint": prop is not None,
            }
            if prop is not None:
                wkt = _value(prop) or ""
                crs, polys = _polygons(wkt)
                entry.update({"crs": crs, "wkt": wkt, "footprint_id": prop.get("id"),
                              "rings": polys})
                if crs:
                    crs_seen[crs] = crs_seen.get(crs, 0) + 1
                fn = to_lonlat(crs)
                if fn and polys:
                    entry["lonlat"] = [[[list(map(lambda c: round(c, 8), fn(p[0], p[1])))
                                         for p in ring] for ring in poly] for poly in polys]
                elif polys:
                    projected = False
            (cuts if entry["owner"] == "cut" else places).append(entry)
    order = {"sito": 0, "area": 1, "settore": 2, "saggio": 3, "quadrato": 4}
    places.sort(key=lambda p: (order.get(str(p.get("level") or ""), 9), p["name"]))
    cuts.sort(key=lambda c: c["name"])
    crs = max(crs_seen, key=crs_seen.get) if crs_seen else None
    return {"places": places, "cuts": cuts, "crs": crs,
            "crs_list": sorted(crs_seen), "projected": projected and bool(crs_seen),
            "units_by_place": {k: sorted(set(v)) for k, v in by_place.items()}}


# ── il catalogo delle basi ─────────────────────────────────────────────────

def catalogue() -> Dict[str, Any]:
    """`basi.json` così com'è (vendorizzato da s3Dgraphy con `sync-basi.sh`)."""
    try:
        return json.loads(BASI.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"sources": [], "default_imagery": None}


def imagery() -> List[Dict[str, Any]]:
    """Le fonti di immagine (le `terrain` sono quote, non una base da guardare)."""
    keep = ("id", "label", "attribution", "licence", "licenceUrl", "offline",
            "offlineNote", "minZoom", "maxZoom", "tileSize", "format")
    return [{k: s.get(k) for k in keep}
            for s in catalogue().get("sources") or [] if s.get("kind") == "imagery"]


# ── il ponte dei tasselli ──────────────────────────────────────────────────

USER_AGENT = ("StratiField/{v} (StratiGraph field node; tile bridge with a disk cache, "
              "no prefetch; https://github.com/ExtendedMatrix)")


class TileRefused(RuntimeError):
    """Una richiesta che il ponte non serve, con la ragione."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _cache_root() -> pathlib.Path:
    root = (os.environ.get("EM_TILE_CACHE") or "").strip()
    if root:
        return pathlib.Path(root)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return pathlib.Path(base) / "stratifield" / "tiles"


_MAX_AGE = re.compile(r"max-age=(\d+)")
_locks: Dict[str, threading.Lock] = {}


def _fresh_until(headers: Dict[str, str], now: float) -> float:
    """Fino a quando un tassello è fresco, dalle SUE intestazioni: `max-age`,
    altrimenti `Expires`; senza nessuna delle due, un giorno (il minimo che la
    policy OSM chiede di tenere: 7 giorni è il loro consiglio, un giorno il
    più prudente rispetto a chi ridisegna)."""
    cc = headers.get("cache-control") or ""
    if "no-store" in cc:
        return 0.0
    m = _MAX_AGE.search(cc)
    if m:
        return now + int(m.group(1))
    exp = headers.get("expires")
    if exp:
        from email.utils import parsedate_to_datetime
        try:
            return parsedate_to_datetime(exp).timestamp()
        except (TypeError, ValueError):
            pass
    return now + 86400


def tile(source_id: str, z: int, x: int, y: int, *, version: str = "",
         offline_only: bool = False, opener=None) -> Tuple[bytes, Dict[str, str]]:
    """Il tassello `z/x/y` di `source_id`: dalla cache se fresco, altrimenti
    dalla fonte (e in cache); senza rete, quello che la cache ha anche se
    scaduto, dichiarato con `X-Tile-Cache: stale`. Uno che la cache non ha e la
    rete non dà → `TileRefused(504)`.

    Un tassello per richiesta, mai i vicini: il ponte NON precarica — è ciò
    che la policy di OSM vieta, e una fonte `offline: true` non ne ha bisogno
    per restare sul dispositivo (la cache tiene ciò che si è guardato)."""
    src = next((s for s in catalogue().get("sources") or []
                if s.get("id") == source_id and s.get("kind") == "imagery"), None)
    if src is None:
        raise TileRefused(404, f"la fonte «{source_id}» non è nel catalogo")
    lo, hi = int(src.get("minZoom") or 0), int(src.get("maxZoom") or 19)
    if not (lo <= z <= hi) or not (0 <= x < 2 ** z) or not (0 <= y < 2 ** z):
        raise TileRefused(404, f"{z}/{x}/{y} non è un tassello di «{source_id}»")
    ext = src.get("format") or "png"
    path = _cache_root() / source_id / str(z) / str(x) / f"{y}.{ext}"
    meta = path.with_suffix(path.suffix + ".json")
    now = time.time()
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    cached = None
    if path.exists():
        try:
            info = json.loads(meta.read_text()) if meta.exists() else {}
        except ValueError:
            info = {}
        cached = (path.read_bytes(), info)
        if info.get("fresh_until", 0) > now or offline_only:
            return cached[0], {"Content-Type": media, "X-Tile-Cache": "hit"
                               if info.get("fresh_until", 0) > now else "stale",
                               "Cache-Control": "private, max-age=3600"}
    url = (src["url"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)))
    key = f"{source_id}/{z}/{x}/{y}"
    lock = _locks.setdefault(key, threading.Lock())
    with lock:
        headers = {"User-Agent": USER_AGENT.format(v=version or "dev"),
                   "Accept": media}
        if cached and cached[1].get("etag"):
            headers["If-None-Match"] = cached[1]["etag"]
        if cached and cached[1].get("last_modified"):
            headers["If-Modified-Since"] = cached[1]["last_modified"]
        req = urllib.request.Request(url, headers=headers)
        open_ = opener or urllib.request.urlopen
        try:
            with open_(req, timeout=10) as answer:
                body = answer.read()
                h = {k.lower(): v for k, v in answer.headers.items()}
        except urllib.error.HTTPError as err:
            if err.code == 304 and cached:
                h = {k.lower(): v for k, v in err.headers.items()}
                info = dict(cached[1])
                info["fresh_until"] = _fresh_until(h, now)
                meta.write_text(json.dumps(info))
                return cached[0], {"Content-Type": media, "X-Tile-Cache": "revalidated",
                                   "Cache-Control": "private, max-age=3600"}
            if cached:
                return cached[0], {"Content-Type": media, "X-Tile-Cache": "stale"}
            raise TileRefused(502, f"la fonte ha risposto {err.code}") from None
        except (urllib.error.URLError, OSError, TimeoutError):
            if cached:
                return cached[0], {"Content-Type": media, "X-Tile-Cache": "stale"}
            raise TileRefused(504, "nessuna rete e nessuna copia in cache") from None
        until = _fresh_until(h, now)
        if until > now:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(body)
            os.replace(tmp, path)
            meta.write_text(json.dumps({"fresh_until": until, "etag": h.get("etag"),
                                        "last_modified": h.get("last-modified"),
                                        "url": url,
                                        "sha256": hashlib.sha256(body).hexdigest()}))
        return body, {"Content-Type": h.get("content-type") or media, "X-Tile-Cache": "miss",
                      "Cache-Control": "private, max-age=3600"}


# ── «Apri in PyArchInit»: il file di scambio ───────────────────────────────

def pyarchinit_exchange(document: Dict[str, Any], node_id: str, *, server: str = "",
                        room: str = "") -> Dict[str, Any]:
    """Ciò che serve a PyArchInit per trovare un luogo o un'unità: misurato il
    12 novembre in `pyarchinit_stratigraph` (sola lettura), PyArchInit non ha
    un modo di essere aperto dall'esterno — nessuno schema d'indirizzo, nessun
    progetto QGIS generato; la stanza la legge dalle sue impostazioni
    (`pyarchinit/stratigraph/server_url`, `room_id`). Finché il contratto
    proposto a Enzo non c'è, il pulsante dà QUESTO: gli identificativi, il
    link della stanza, e i campi della scheda di PyArchInit che li cercano."""
    m = map_of(document)
    hit = next((p for p in m["places"] + m["cuts"] if p["id"] == node_id), None)
    node = None
    for section in (document.get("graphs") or {}).values():
        for n in section.get("nodes") or []:
            if str(n.get("id")) == node_id:
                node = n
    if node is None:
        raise KeyError(node_id)
    d = _data(node)
    out = {
        "format": "stratigraph-open/0 (proposal, see the report of 12 Nov 2026)",
        "action": "open",
        "server": server, "room": room,
        "handoff": (f"stratigraph://open?server={server}&room={room}&node={node_id}"
                    if server and room else ""),
        "node": {"id": node_id, "node_type": node.get("node_type"),
                 "name": node.get("name"), "level": _attr(node, "level"),
                 "kind": _attr(node, "kind"),
                 "entity_uuid": d.get("entity_uuid") or (node.get("attributes") or {}).get("entity_uuid")},
    }
    if hit and hit.get("has_footprint"):
        out["footprint"] = {"crs": hit.get("crs"), "wkt": hit.get("wkt")}
    lvl = str(_attr(node, "level") or "")
    if node.get("node_type") == "LocationNodeGroup" and lvl in ("area", "settore", "saggio"):
        out["pyarchinit"] = {"table": "us_table", "filter": {lvl: node.get("name")}}
    elif node.get("node_type") == "LocationNodeGroup" and lvl == "sito":
        out["pyarchinit"] = {"table": "site_table", "filter": {"sito": node.get("name")}}
    return out
