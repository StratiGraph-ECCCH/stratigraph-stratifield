"""Apache-2.0 (iDAI.field, DAI) nell'immagine: la licenza e un NOTICE ACCANTO.

Deciso il 28 settembre 2026 (Cowork per E.D.): le etichette DAI possono stare
nell'immagine pubblicata di StratiField, con ciò che Apache-2.0 §4 chiede a chi
ridistribuisce — copia della licenza e l'attribuzione — accanto a ogni directory
vendorata che le contiene. `sync-schede.sh` le scrive; qui si controlla che ci
siano e che dicano il vero.
"""

from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _apache_dirs():
    dirs = {}
    for path in sorted((ROOT / "schede").rglob("*.json")):
        if path.name == "index.json":
            continue
        std = json.loads(path.read_text(encoding="utf-8"))["header"].get("standard") or {}
        if std.get("license") == "Apache-2.0":
            dirs.setdefault(path.parent, []).append(path.name)
    for path in sorted((ROOT / "vocabolari").glob("*.json")):
        if json.loads(path.read_text(encoding="utf-8")).get("license") == "Apache-2.0":
            dirs.setdefault(path.parent, []).append(path.name)
    return dirs


def test_c_e_materiale_apache_vendorato():
    names = {d.name for d in _apache_dirs()}
    assert {"dai-idaifield-layer-2026", "vocabolari"} <= names


@pytest.mark.parametrize("where", sorted(_apache_dirs()), ids=lambda p: p.name)
def test_accanto_ci_sono_la_licenza_e_il_notice(where):
    licence = (where / "LICENSE-Apache-2.0.txt").read_text(encoding="utf-8")
    assert "Apache License" in licence and "Version 2.0, January 2004" in licence
    notice = (where / "NOTICE").read_text(encoding="utf-8")
    assert "Deutsches" in notice and "Archäologisches Institut" in notice
    assert "4b5c1e2c3c499d4bd125d0eda61cc6f5c94ffcd4" in notice
    for name in _apache_dirs()[where]:
        assert name in notice, f"{name} non è nominato nel NOTICE di {where.name}"


def test_il_dockerfile_copia_le_directory_intere():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY schede ./schede" in docker and "COPY vocabolari ./vocabolari" in docker
