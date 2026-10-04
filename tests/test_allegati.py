"""R2/I1 (4 ottobre 2026) · gli allegati della scheda dicono dove sono, col
risolutore unico e i segni dell'elenco comune; nessun segno fuori elenco."""
from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import allegati as A                                    # noqa: E402

datamodel = pytest.importorskip("s3dgraphy.datamodel")
if not hasattr(datamodel, "state_symbols"):                      # pragma: no cover
    pytest.skip("s3dgraphy senza l'elenco degli stati (prima della I1)", allow_module_level=True)


def test_every_state_has_its_sign_and_none_is_invented():
    assert set(A.STILE) == set(datamodel.state_symbols()["states"])


def test_the_attachments_say_where_they_are(tmp_path, monkeypatch):
    from s3dgraphy import api
    root = pathlib.Path(api.create_em_project(str(tmp_path), "Scavo")["root"])
    photo = root / "EM" / "DosCo" / "D.01.jpg"
    photo.write_bytes(b"\xff\xd8 foto")
    hexd = hashlib.sha256(photo.read_bytes()).hexdigest()
    monkeypatch.setenv("EM_PROJECT_ROOT", str(root))
    section = {"nodes": [
        {"id": "US1", "node_type": "US", "name": "US 1", "data": {}},
        {"id": "r1", "node_type": "resource", "name": "D.01", "data": {"url": "/DosCo/D.01.jpg"}},
        {"id": "r2", "node_type": "resource", "name": "persa", "data": {"url": "/DosCo/via.jpg"}},
        {"id": "r3", "node_type": "resource", "name": "nello store",
         "data": {"url": "sha256:" + "ab" * 32, "checksum": "sha256:" + "ab" * 32}},
        {"id": "r4", "node_type": "resource", "name": "di un'altra", "data": {"url": "/DosCo/D.01.jpg"}},
    ], "edges": [
        {"id": "e1", "source": "US1", "target": "r1", "edge_type": "has_linked_resource"},
        {"id": "e2", "source": "US1", "target": "r2", "edge_type": "has_linked_resource"},
        {"id": "e3", "source": "US1", "target": "r3", "edge_type": "has_documentation"},
    ]}
    entries = A.attachments_of(section, "US1")
    assert [e["id"] for e in entries] == ["r1", "r2", "r3"]
    rows = {r["id"]: r for r in A.state_of(entries, store_has=lambda h: h == "ab" * 32)}
    assert rows["r1"]["state"] == "on_disk" and rows["r1"]["can_upload"]
    assert rows["r1"]["glyph"] == "●" and rows["r1"]["label"] == "sul disco"
    assert rows["r2"]["state"] == "missing" and not rows["r2"]["can_upload"]
    assert rows["r3"]["state"] == "on_node"
    rows = {r["id"]: r for r in A.state_of(entries[:1], store_has=lambda h: h == hexd)}
    assert rows["r1"]["state"] == "both"


def test_upload_puts_the_bytes_in_the_store(tmp_path):
    from app.assets import InMemoryAssetStore
    store = InMemoryAssetStore()
    f = tmp_path / "a.jpg"
    f.write_bytes(b"jpg")
    out = A.upload(store, str(f), "image/jpeg")
    assert store.head(out["ref"]) is not None
