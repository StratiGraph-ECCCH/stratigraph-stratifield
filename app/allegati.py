"""R2/I1 (E.D., 4 Oct 2026) · gli allegati di una scheda e il loro STATO.

Un allegato è una risorsa che l'unità raggiunge (`has_linked_resource`,
`has_documentation`). Dov'è lo dice il risolutore UNICO di s3Dgraphy
(`api.resolve_file`): lo stesso di EMStudio ed EMtools, quindi gli stessi file
danno lo stesso stato nei tre strumenti. Il «nodo» qui è lo store condiviso
di questo servizio (`ASSET_STORE`, con la sua dispensa): ha i byte se il suo
`head` risponde per lo sha256.

Le cartelle in cui un file locale si cerca: `EM_PROJECT_ROOT` (l'albero
standard di un progetto EM, C1) e `STRATIFIELD_FILE_ROOTS` (separate da
`os.pathsep`). Senza, un file che non è nello store risulta «mancante» o «solo
riferimento» — è vero: questo nodo non lo vede.

Il segno e il significato vengono dall'elenco comune
(`datamodel.state_symbols()`); il disegno è di StratiField (`STILE`), e ogni
stato dell'elenco ha il suo (`tests/test_allegati.py`).
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

LINKS = ("has_linked_resource", "has_documentation")

#: stato → come StratiField lo disegna (una classe CSS: il tono è nostro)
STILE: Dict[str, str] = {
    "file.on_disk": "ok", "file.on_node": "info", "file.both": "ok",
    "file.reference_only": "muted", "file.missing": "bad", "file.empty_copy": "warn",
    "node.reachable": "ok", "node.unreachable": "bad", "node.global": "info",
    "node.local_only": "muted", "room.inside": "info", "room.outside": "muted",
    "room.read_only": "warn", "sync.aligned": "ok", "sync.pending": "warn",
    "sync.conflict": "bad", "role.owner": "info", "role.editor": "info",
    "role.viewer": "muted", "scene.only_here": "muted",
}


def roots() -> Dict[str, Any]:
    """Dove si cercano i file su questo computer (dall'ambiente)."""
    extra = [p for p in (os.environ.get("STRATIFIELD_FILE_ROOTS") or "").split(os.pathsep) if p]
    return {"project_root": os.environ.get("EM_PROJECT_ROOT") or None, "base_dirs": extra}


def attachments_of(section: Dict[str, Any], unit_id: str) -> List[Dict[str, Any]]:
    """Le risorse vive che l'unità raggiunge: ``{id, name, locator, checksum}``."""
    nodes = {str(n.get("id")): n for n in section.get("nodes") or []}
    out, seen = [], set()
    for e in section.get("edges") or []:
        if e.get("edge_type") not in LINKS or str(e.get("source")) != unit_id:
            continue
        if ((e.get("attributes") or {}).get("removed")):
            continue
        n = nodes.get(str(e.get("target")))
        if not n or n.get("node_type") not in ("resource", "resource_file"):
            continue
        d = n.get("data") if isinstance(n.get("data"), dict) else {}
        if d.get("removed") or n["id"] in seen:
            continue
        seen.add(n["id"])
        out.append({"id": str(n["id"]), "name": str(n.get("name") or n["id"]),
                    "locator": str(d.get("url") or ""), "checksum": d.get("checksum") or ""})
    return out


def state_of(entries: List[Dict[str, Any]], *, store_has: Optional[Callable[[str], bool]],
             lang: str = "it") -> List[Dict[str, Any]]:
    """Lo stato di ogni allegato, col segno e la frase dell'elenco comune."""
    from s3dgraphy import api
    from s3dgraphy.datamodel import state_symbols
    states = state_symbols()["states"]
    where = roots()
    out = []
    for e in entries:
        r = api.resolve_file(e, project_root=where["project_root"],
                             base_dirs=where["base_dirs"], on_node=store_has,
                             hasher=_sha256_of)
        key = f"file.{r['state']}"
        sym = states[key]
        out.append({**r, "name": e["name"], "glyph": sym["glyph"],
                    "label": sym["label"].get(lang) or sym["label"]["en"],
                    "meaning": sym["meaning"].get(lang) or sym["meaning"]["en"],
                    "tone": STILE[key],
                    # «Carica nella stanza»: c'è sul disco e lo store non l'ha
                    "can_upload": r["state"] == "on_disk"})
    return out


def _sha256_of(path: str) -> str:
    """Lo sha256 di un file trovato sul disco, per chiedere allo store se lo ha
    (un allegato scritto senza digest)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def store_probe(store: Any) -> Callable[[str], bool]:
    """``on_node(hex)`` sullo store condiviso di questo servizio."""
    def has(hexd: str) -> bool:
        try:
            return store.head(f"sha256:{hexd}") is not None
        except Exception:  # noqa: BLE001 — uno store che non risponde non ha niente, per ora
            return False
    return has


def upload(store: Any, path: str, media_type: str = "application/octet-stream") -> Dict[str, Any]:
    """«Carica nella stanza»: i byte del file nello store condiviso (la
    dispensa li porta su quando il nodo è raggiungibile)."""
    with open(path, "rb") as fh:
        data = fh.read()
    return store.put(data, media_type)
