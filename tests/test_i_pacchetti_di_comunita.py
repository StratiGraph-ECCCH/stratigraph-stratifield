"""I PACCHETTI DI COMUNITÀ sul nodo: la scheda e i vocabolari, alla sync.

MICRO-PL13 (riga W10 del piano delle estensioni, E.D. 18 nov 2026). Un pacchetto
di comunità (EM Profile) può portare una scheda compilata, con il suo digest, e
i vocabolari che le sue caselle offrono. StratiField li prende come prende le
altre schede: alla sync (`scripts/sync_pacchetti.py`, chiamato da
`sync-schede.sh`), vendorati e committati; mai a runtime, mai la posa 3D (D-10).

Qui il pacchetto d'esempio di em-profiles (inventato, D-5), copiato in una
cartella temporanea: la sync vera scrive in una radice temporanea, mai in
`schede/` del repository.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES_SRC = ROOT.parent / "stratigraph-templates" / "src"
EXAMPLES = ROOT.parent / "em-profiles" / "examples"

if not (TEMPLATES_SRC / "stratigraph_templates" / "packages.py").is_file() \
        or not (EXAMPLES / "esempio-statuaria").is_dir():
    pytest.skip("servono stratigraph-templates (con packages.py, PL11) ed em-profiles accanto",
                allow_module_level=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
if str(TEMPLATES_SRC) not in sys.path:
    sys.path.append(str(TEMPLATES_SRC))
pytest.importorskip("yaml")

import sync_pacchetti as SP                                       # noqa: E402
from app import operazioni as O                                   # noqa: E402
from app import scheda as S                                       # noqa: E402

PKG = "esempio-statuaria"
FORM = "stat-scheda-superficie"
TS = "2026-11-18T22:00:00Z"


def _declare(root: pathlib.Path, *pairs):
    (root / SP.DECLARATION).write_text(json.dumps({
        "format": SP.DECLARATION_FORMAT, "format_version": "1",
        "packages": [{"id": i, "version": v} for i, v in pairs]}), encoding="utf-8")


@pytest.fixture
def node(tmp_path):
    """Una radice di nodo: l'indice delle schede vendorate (copiato) e una
    cartella di pacchetti con le due forme dell'esempio."""
    root = tmp_path / "node"
    (root / "schede").mkdir(parents=True)
    (root / "vocabolari").mkdir()
    shutil.copyfile(ROOT / "schede" / "index.json", root / "schede" / "index.json")
    shutil.copytree(ROOT / "schede" / "iccd-us-2021", root / "schede" / "iccd-us-2021")
    for v in (ROOT / "vocabolari").glob("*.json"):
        shutil.copyfile(v, root / "vocabolari" / v.name)
    shelf = tmp_path / "pacchetti"
    shelf.mkdir()
    shutil.copytree(EXAMPLES / "esempio-statuaria", shelf / "esempio-statuaria")
    return root, shelf


def _sync(root, shelf, prev=None):
    return SP.sync(root, prev or {}, [str(shelf)], environ={})


def test_nothing_declared_nothing_changes(node):
    root, shelf = node
    before = (root / "schede" / "index.json").read_bytes()
    lines = _sync(root, shelf)
    assert lines == ["  community packages: none declared (pacchetti.json)"]
    assert (root / "schede" / "index.json").read_bytes() == before


def test_the_declared_package_brings_its_scheda_verified_and_its_vocabularies(node):
    root, shelf = node
    _declare(root, (PKG, "0.1.0"))
    lines = "\n".join(_sync(root, shelf))
    scheda = root / "schede" / FORM / "0.1.0.json"
    shipped = shelf / PKG / "forms" / FORM / "0.1.0.json"
    assert scheda.read_bytes() == shipped.read_bytes(), "la scheda si copia byte per byte"
    assert "verified" in lines
    entry = json.loads((root / "schede" / "index.json").read_text())["schede"][FORM]
    v = entry["versions"]["0.1.0"]
    assert v["package"]["name"] == PKG and v["package"]["prefix"] == "stat" and v["declared"]
    assert entry["latest"] == "0.1.0" and entry["package"] == PKG
    voc = root / "vocabolari" / "stat"
    assert sorted(p.name for p in voc.glob("*.json")) == [
        "fase-superficie.json", "lavorazione.json", "punti-volto.json"]
    fase = json.loads((voc / "fase-superficie.json").read_text())
    assert fase["scheme"] == "stat:fase-superficie" and fase["fascia"] == "A"
    assert fase["package"]["name"] == PKG and fase["attribution"]
    assert {c["labels"]["it"] for c in fase["concepts"]} >= {"integrazione di restauro"}
    # la licenza viaggia accanto, con chi e da dove
    for where in (voc, root / "schede" / FORM):
        assert (where / "LICENSE").is_file()
        assert PKG in (where / "NOTICE").read_text()


def test_a_mixed_package_gives_its_data_and_never_its_code(node, tmp_path):
    root, _ = node
    shelf = tmp_path / "misti"
    shelf.mkdir()
    shutil.copytree(EXAMPLES / "esempio-statuaria-misto", shelf / "esempio-statuaria-misto")
    _declare(root, (PKG, "0.1.0"))
    lines = "\n".join(_sync(root, shelf))
    assert (root / "schede" / FORM / "0.1.0.json").is_file()
    assert "its data only" in lines
    assert not [p for p in root.rglob("*") if p.suffix in (".py", ".pyc", ".so", ".whl")], (
        "un byte di codice del pacchetto è arrivato sul nodo")


def test_a_scheda_changed_after_compiling_is_refused_and_nothing_is_written(node):
    root, shelf = node
    shipped = shelf / PKG / "forms" / FORM / "0.1.0.json"
    doc = json.loads(shipped.read_text())
    doc["visual"]["fields"][1]["labels"]["it"] = "DESCRIZIONE CAMBIATA"
    shipped.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    _declare(root, (PKG, "0.1.0"))
    before = (root / "schede" / "index.json").read_bytes()
    with pytest.raises(SP.SyncError) as why:
        _sync(root, shelf)
    assert "not verified" in str(why.value) or "does not validate" in str(why.value)
    assert (root / "schede" / "index.json").read_bytes() == before
    assert not (root / "schede" / FORM).exists() and not (root / "vocabolari" / "stat").exists()


def test_a_declared_package_that_is_not_there_is_said_with_where_it_was_looked_for(node):
    root, shelf = node
    _declare(root, (PKG, "9.9.9"))
    with pytest.raises(SP.SyncError) as why:
        _sync(root, shelf)
    assert "9.9.9 not found" in str(why.value) and "--from" in str(why.value)


def test_a_zip_is_read_as_its_curator_distributes_it(node, tmp_path):
    root, shelf = node
    zips = tmp_path / "zips"
    zips.mkdir()
    shutil.make_archive(str(zips / "esempio-statuaria-0.1.0"), "zip", shelf / PKG)
    _declare(root, (PKG, "0.1.0"))
    _sync(root, zips)
    assert (root / "schede" / FORM / "0.1.0.json").is_file()


def test_a_tier_less_prudent_than_the_licence_is_refused(node):
    root, shelf = node
    env = shelf / PKG / "em-extension.toml"
    text = env.read_text()
    first = text.index('license = "SPDX:CC-BY-4.0"', text.index("[[data.vocabularies]]"))
    env.write_text(text[:first] + 'license = "SPDX:CC-BY-SA-4.0"'
                   + text[first + len('license = "SPDX:CC-BY-4.0"'):])
    _declare(root, (PKG, "0.1.0"))
    with pytest.raises(SP.SyncError) as why:
        _sync(root, shelf)
    assert "tier" in str(why.value).lower() or "fascia" in str(why.value).lower()


def test_one_scheda_id_one_owner(node):
    root, shelf = node
    folder = SP.find_package({"id": PKG, "version": "0.1.0"}, [shelf], shelf)
    read = [SP.read_package({"id": PKG, "version": "0.1.0"}, folder)]
    with pytest.raises(SP.SyncError) as why:
        SP.write(root, read, {}, templates_ids=[FORM])
    assert "one id, one owner" in str(why.value)


def test_a_version_no_longer_declared_is_kept_and_said(node):
    root, shelf = node
    _declare(root, (PKG, "0.1.0"))
    _sync(root, shelf)
    prev = json.loads((root / "schede" / "index.json").read_text())
    shutil.copyfile(ROOT / "schede" / "index.json", root / "schede" / "index.json")  # templates' step
    _declare(root)
    lines = "\n".join(_sync(root, shelf, prev))
    assert "no longer declared" in lines
    entry = json.loads((root / "schede" / "index.json").read_text())["schede"][FORM]
    assert entry["versions"]["0.1.0"]["declared"] is False
    assert (root / "schede" / FORM / "0.1.0.json").is_file()


def test_the_central_vocabulary_step_skips_what_a_package_carries():
    head = {"packages": [{"prefix": "stat"}],
            "vocabularies": [{"id": "stat:fase-superficie"}, {"id": "iccd-us-colore"},
                             {"id": "altro:x"}]}
    assert SP.package_schemes(head) == ["stat:fase-superficie"]
    text = (ROOT / "sync-schede.sh").read_text()
    assert "sync_pacchetti.py" in text and "in own:" in text


# ── l'app legge ciò che la sync ha scritto ──────────────────────────────────

@pytest.fixture
def served(node, monkeypatch):
    root, shelf = node
    _declare(root, (PKG, "0.1.0"))
    _sync(root, shelf)
    monkeypatch.setattr(S, "VENDORED_DIR", root / "schede")
    monkeypatch.setattr(S, "VOCABULARY_DIR", root / "vocabolari")
    monkeypatch.delenv("STRATIGRAPH_SCHEDE_DIR", raising=False)
    return root


def test_the_node_serves_the_package_scheda_and_names_its_package(served):
    found = S.find(FORM, {})
    assert found is not None and found.compiled and found.recipe
    assert S.package_of(found)["name"] == PKG
    for lang in ("it", "en"):
        drawn = found.for_browser(lang)
        assert drawn["package"]["prefix"] == "stat"
    iccd = S.find("iccd-us-2021", {})
    assert S.package_of(iccd) is None and "package" not in iccd.for_browser("it")


def test_the_package_vocabulary_answers_by_its_prefixed_id(served):
    it = S.vocabulary("stat:fase-superficie", "it")
    en = S.vocabulary("stat:fase-superficie", "en")
    assert it["package"]["name"] == PKG and it["fascia"] == "A"
    assert "integrazione di restauro" in {c["label"] for c in it["concepts"]}
    assert "restoration infill" in {c["label"] for c in en["concepts"]}
    for bad in ("stat:../fase-superficie", "stat:fase:superficie", ":x", "stat:", "../stat"):
        assert S.vocabulary(bad, "it") is None, bad
    assert S.vocabulary("iccd-us-colore", "it") is not None, "i vocabolari del nucleo come prima"


def test_the_package_scheda_becomes_operations_like_any_other(served):
    plan = O.plan(S.find(FORM, {}), {"area": "0.0042"}, number="1",
                  section={"nodes": [], "edges": []}, ts=TS, create=True)
    assert plan.ops, plan.notes
    said = json.dumps(plan.ops, ensure_ascii=False)
    assert "stat:area_integrazione" in said
    stamp = next(op for op in plan.ops if op.get("field") == "data.scheda")
    assert stamp["value"]["template"] == FORM and stamp["value"]["version"] == "0.1.0"


def test_the_list_says_which_package(served, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as M

    listing = TestClient(M.app).get("/v1/schede").json()["schede"]
    mine = next(s for s in listing if s["id"] == FORM)
    assert mine["package"] == {"name": PKG, "iri": "https://w3id.org/extendedmatrix/profile/esempio-statuaria",
                               "prefix": "stat", "version": "0.1.0"}
    assert all("package" not in s for s in listing if s["id"] != FORM)
    voc = TestClient(M.app).get("/v1/vocabolario/stat:fase-superficie?lang=it")
    assert voc.status_code == 200 and voc.json()["scheme"] == "stat:fase-superficie"
