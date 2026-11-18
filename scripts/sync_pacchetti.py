#!/usr/bin/env python3
"""THE COMMUNITY PACKAGES THIS NODE SERVES: their schede and their vocabularies.

MICRO-PL13 (row W10 of the extensions plan, E.D. 18 Nov 2026). A community
package (EM Profile, em-profiles SPEC) can carry a scheda — a definition
compiled by `stratigraph-templates package-build`, with its digest in the
manifest — and the vocabularies its boxes offer. StratiField takes them THE WAY
IT TAKES THE OTHER SCHEDE (SPEC-pacchetto §11.2): at sync, vendored, committed.
Nothing is read at runtime and no 3D pose comes to the field (D-10).

Called by `sync-schede.sh` after the schede of `stratigraph-templates`, with the
python of that checkout (it needs `stratigraph_templates.packages`, which reads
the package with `s3dgraphy.profiles`, the one reader of every EM tool):

    sync_pacchetti.py <chatbot root> <previous schede/index.json or ''> [--from DIR]...

WHICH packages: those `pacchetti.json` DECLARES (id + version), never «whatever
is in the folder». The folder is only WHERE to look: `--from DIR` (repeatable),
`STRATIGRAPH_PACKAGES_PATH` (colon-separated), then `../em-profiles/profiles`.
A package is a folder (`em-extension.toml` or `profile.json`) or a zip, as its
curator distributes it.

WHAT is checked before anything is written (one declared package that fails
stops the sync, with the sentence, and nothing changes):

* the package validates with s3Dgraphy (`open_community_package`);
* each compiled scheda is VERIFIED (`packages.verify_compiled`): the file's
  digest against `forms[].digest`, a compiled definition, `header.digest` =
  the content, id and version — a scheda changed after compiling is refused,
  as EMStudio's bridge refuses it (PL11);
* a scheda id that `stratigraph-templates` also serves, or that two packages
  carry, is refused: one id, one owner;
* the vocabularies: only tiers A and B travel (D-16); a tier less prudent than
  the licence is refused (`s3dgraphy.vocabularies.check_tier`); a C one is
  never vendored, only named.

WHAT is written:

* `schede/<scheda id>/<version>.json`, the bytes of the package's file, plus
  `LICENSE*` of the package and a `NOTICE` beside them;
* `vocabolari/<prefix>/<slug>.json`, the scheme in the shape the other
  vocabularies have (`packages.scheme_file`), with `package`, `fascia`,
  `attribution`; the package's `LICENSE*` and a `NOTICE` in the same folder.
  A subfolder per prefix: a package scheme is called `<prefix>:<slug>` and a
  colon is not a file name;
* in `schede/index.json`, one entry per scheda with `package` on each version.

ONLY THE DATA. A mixed package (`[data]` + `[code]`) gives its data; its code
is never copied (PIANO §6.1 W10: «un pacchetto misto installato sul nodo serve
solo i dati»).

A version NO LONGER DECLARED is NOT deleted: a unit compiled with it is read
back with it (`app/scheda.py`), exactly as `stratigraph-templates` keeps every
published version. It stays in the index with `declared: false` and the sync
names it; whoever really wants it gone removes it with git, where the diff
shows it.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

DECLARATION = "pacchetti.json"
DECLARATION_FORMAT = "stratigraph-chatbot/pacchetti"
PATH_VARIABLE = "STRATIGRAPH_PACKAGES_PATH"


class SyncError(RuntimeError):
    """A declared package this node cannot serve, in a sentence."""


# ── the declaration ─────────────────────────────────────────────────────────

def read_declaration(root: pathlib.Path) -> List[Dict[str, str]]:
    path = root / DECLARATION
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("format") != DECLARATION_FORMAT:
        raise SyncError(f"{path}: format must be «{DECLARATION_FORMAT}»")
    out, seen = [], set()
    for i, entry in enumerate(doc.get("packages") or []):
        pid, ver = str((entry or {}).get("id") or ""), str((entry or {}).get("version") or "")
        if not pid or not ver:
            raise SyncError(f"{path}: packages[{i}] needs «id» and «version»")
        if (pid, ver) in seen:
            raise SyncError(f"{path}: {pid} {ver} is declared twice")
        seen.add((pid, ver))
        out.append({"id": pid, "version": ver})
    return out


def search_path(root: pathlib.Path, given: Sequence[str],
                environ: Optional[Dict[str, str]] = None) -> List[pathlib.Path]:
    env = (environ if environ is not None else os.environ).get(PATH_VARIABLE) or ""
    dirs = [pathlib.Path(d).expanduser() for d in list(given) + [p for p in env.split(os.pathsep) if p]]
    dirs.append(root.parent / "em-profiles" / "profiles")
    return [d for d in dirs if d.is_dir()]


# ── finding a package ──────────────────────────────────────────────────────

def _identity(folder: pathlib.Path) -> Optional[Tuple[str, str, str]]:
    """(envelope id, profile name, data version) of a package folder, or None."""
    from stratigraph_templates.packages import _profiles
    P = _profiles()
    try:
        pkg = P.open_package(folder)
    except Exception:  # noqa: BLE001 — not a package: not a candidate
        return None
    if not pkg.has_data or pkg.profile is None:
        return None
    return str(pkg.id or ""), str(pkg.profile.get("name") or ""), str(pkg.data_version or "")


def _candidates(where: pathlib.Path) -> List[pathlib.Path]:
    out = []
    for p in sorted(where.iterdir()):
        if p.suffix == ".zip" and p.is_file():
            out.append(p)
        elif p.is_dir():
            out.append(p)
            out.extend(q for q in sorted(p.iterdir()) if q.is_dir())  # <id>/<version>/
    return out


def find_package(want: Dict[str, str], dirs: Sequence[pathlib.Path],
                 scratch: pathlib.Path) -> pathlib.Path:
    """The folder of the declared package (a zip is unpacked into ``scratch``)."""
    for d in dirs:
        for cand in _candidates(d):
            folder = cand
            if cand.suffix == ".zip":
                folder = scratch / f"{cand.stem}-{abs(hash(str(cand)))}"
                if not folder.exists():
                    with zipfile.ZipFile(cand) as z:
                        z.extractall(folder)
                inner = [p for p in folder.iterdir() if p.is_dir()]
                if not any((folder / n).is_file() for n in ("em-extension.toml", "profile.json")) \
                        and len(inner) == 1:
                    folder = inner[0]
            ident = _identity(folder)
            if ident and want["id"] in ident[:2] and ident[2] == want["version"]:
                return folder
    looked = ", ".join(str(d) for d in dirs) or "nowhere (no folder exists)"
    raise SyncError(f"declared package {want['id']} {want['version']} not found in {looked}: "
                    f"pass --from <folder>")


# ── reading one package, checking everything ───────────────────────────────

def _git_commit(folder: pathlib.Path) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(folder), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return None
    return out.stdout.strip() or None


def _licences(pkg_root: pathlib.Path, data_dir: pathlib.Path) -> List[pathlib.Path]:
    found = {}
    for where in (pkg_root, data_dir):
        for p in sorted(where.glob("LICENSE*")) + sorted(where.glob("COPYING*")):
            if p.is_file():
                found.setdefault(p.name, p)
    return list(found.values())


def read_package(want: Dict[str, str], folder: pathlib.Path) -> Dict[str, Any]:
    """Everything that will be written for one package, checked; nothing written."""
    from stratigraph_templates import packages as SP
    from stratigraph_templates.vocab import Vocabularies

    try:
        from s3dgraphy.vocabularies import check_tier, tier_for_license
    except ImportError as exc:  # pragma: no cover — s3dgraphy before dev110
        raise SyncError(f"s3dgraphy.vocabularies is needed for the tiers ({exc})") from None

    try:
        pkg = SP.open_community_package(folder)
    except SP.PackageError as exc:
        raise SyncError(f"{want['id']} {want['version']}: {exc}") from None
    raw_pkg = SP._profiles().open_package(folder)
    env = raw_pkg.envelope or {}
    has_code = raw_pkg.has_code
    entry = pkg.header_entry()

    # the schede
    forms, notes = [], []
    langs: set = set()
    for f in pkg.forms():
        if not f.get("compiled"):
            notes.append(f"scheda {f.get('id')}: no compiled file in the manifest, not served")
            continue
        path = pkg.data_dir / str(f["compiled"])
        raw = path.read_bytes()
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = None
        problems = SP.verify_compiled(doc, f, raw, path.name)
        if problems:
            said = "; ".join(p["en"] for p in problems)
            raise SyncError(f"{pkg.label()}: scheda {f.get('id')} not verified — {said}")
        head = doc["header"]
        langs.update(head.get("languages") or [])
        forms.append({"id": head["id"], "version": str(head["version"]), "raw": raw, "header": head})

    # the vocabularies it carries: A and B travel, C never
    vocab = SP.vocabularies_with(Vocabularies.load(), [pkg])
    carried = {str(v.get("scheme")): v for v in SP._carried(raw_pkg, pkg.manifest)}
    schemes, local_only = [], []
    for sid, scheme in sorted(pkg.schemes.items()):
        v = carried.get(str(scheme.uri)) or {}
        lic = v.get("license") or scheme.license or pkg.manifest.get("license")
        tier = v.get("fascia") or tier_for_license(lic)
        why = check_tier(tier, lic)
        if why:
            raise SyncError(f"{pkg.label()}: vocabulary {scheme.uri}: {why}")
        if tier == "C":
            local_only.append(sid)
            continue
        doc = SP.scheme_file(vocab, sid, sorted(langs) or ["en", "it"])
        doc["fascia"] = tier
        doc["package"] = entry
        if not doc.get("attribution"):
            who = env.get("maintainer") or pkg.manifest.get("maintainer") or pkg.name
            doc["attribution"] = f"{who} — community package {pkg.label()}"
        schemes.append({"id": sid, "slug": sid.split(":", 1)[1], "doc": doc})
    for v in raw_pkg.carried_vocabularies():   # C entries carry no file: named, not served
        if v.get("fascia") == "C":
            local_only.append(str(v.get("scheme")))

    return {"want": want, "package": entry, "label": pkg.label(), "prefix": pkg.prefix,
            "folder": folder, "data_dir": pkg.data_dir, "has_code": has_code,
            "forms": forms, "schemes": schemes, "local_only": local_only, "notes": notes,
            "licences": _licences(folder, pkg.data_dir), "commit": _git_commit(folder),
            "title": pkg.manifest.get("title"), "license": pkg.manifest.get("license")}


# ── writing ─────────────────────────────────────────────────────────────────

def _semver(v: str) -> tuple:
    return tuple(int("".join(c for c in x if c.isdigit()) or 0) for x in str(v).split("."))


def _notice(r: Dict[str, Any]) -> str:
    p = r["package"]
    return (f"This directory contains material from the community package {p['name']} {p['version']}\n"
            f"({p['iri']}, prefix «{p['prefix']}»), licence {r['license'] or 'see LICENSE'}.\n"
            f"Read from {r['folder'].name}{' at commit ' + r['commit'] if r['commit'] else ''}.\n"
            f"Copied as the package carries it (the scheda byte for byte, the vocabularies\n"
            f"resolved into StratiField's shape); only its data: a package's code never\n"
            f"comes to a node. Written by stratigraph-chatbot/sync-schede.sh\n"
            f"(scripts/sync_pacchetti.py), never by hand.\n")


def _copy_licences(r: Dict[str, Any], where: pathlib.Path) -> None:
    for lic in r["licences"]:
        shutil.copyfile(lic, where / lic.name)
    (where / "NOTICE").write_text(_notice(r), encoding="utf-8")


def write(root: pathlib.Path, read: List[Dict[str, Any]], prev_index: Dict[str, Any],
          templates_ids: Sequence[str]) -> List[str]:
    """Write the checked packages; returns what to print."""
    schede, voc = root / "schede", root / "vocabolari"
    index_path = schede / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {
        "format": "stratigraph-templates/compiled-definition/index", "format_version": "1", "schede": {}}
    lines: List[str] = []

    declared: Dict[str, Dict[str, Any]] = {}  # scheda id -> {version: (record, form)}
    for r in read:
        for f in r["forms"]:
            declared.setdefault(f["id"], {})[f["version"]] = (r, f)
    for sid in declared:
        if sid in templates_ids:
            raise SyncError(f"scheda {sid} is served by stratigraph-templates AND by a package: one id, one owner")
        owners = {r["package"]["name"] for r, _ in declared[sid].values()}
        if len(owners) > 1:
            raise SyncError(f"scheda {sid} is carried by {', '.join(sorted(owners))}: one id, one owner")

    # the schede of the declared packages
    for sid, versions in sorted(declared.items()):
        where = schede / sid
        where.mkdir(parents=True, exist_ok=True)
        old = ((prev_index.get("schede") or {}).get(sid) or {}).get("versions") or {}
        entry_versions: Dict[str, Any] = {}
        for ver, info in old.items():          # kept: no longer declared, never deleted
            if info.get("package") and ver not in versions and (where / f"{ver}.json").is_file():
                entry_versions[ver] = {**info, "declared": False}
                lines.append(f"  package scheda {sid} {ver} no longer declared — kept "
                             f"(units compiled with it read it back); remove it with git if meant")
        for ver, (r, f) in versions.items():
            (where / f"{ver}.json").write_bytes(f["raw"])
            head = f["header"]
            dm = head.get("datamodel") or {}
            entry_versions[ver] = {
                "path": f"{sid}/{ver}.json", "digest": head.get("digest"),
                "standard": {k: (head.get("standard") or {}).get(k)
                             for k in ("authority", "code", "version", "invented")},
                "datamodel": {k: dm[k] for k in ("nodes", "connections", "qualia", "em_ttl", "digest") if k in dm},
                "package": r["package"], "declared": True}
            _copy_licences(r, where)
            lines.append(f"  package scheda  {sid:<26} {ver:<8} from {r['label']} · verified "
                         f"({str(head.get('digest'))[7:19]})")
        ordered = sorted(entry_versions, key=_semver)
        live = [v for v in ordered if entry_versions[v].get("declared")]
        index["schede"][sid] = {"versions": {v: entry_versions[v] for v in ordered},
                                "latest": (live or ordered)[-1],
                                "package": next(iter(versions.values()))[0]["package"]["name"]}

    # package schede of the previous index that nothing declares any more: kept
    for sid, entry in sorted((prev_index.get("schede") or {}).items()):
        if sid in declared or not entry.get("package") or sid in templates_ids:
            continue
        kept = {v: {**i, "declared": False} for v, i in (entry.get("versions") or {}).items()
                if (schede / sid / f"{v}.json").is_file()}
        if kept:
            ordered = sorted(kept, key=_semver)
            index["schede"][sid] = {"versions": {v: kept[v] for v in ordered}, "latest": ordered[-1],
                                    "package": entry["package"]}
            lines.append(f"  package scheda {sid} ({', '.join(ordered)}) no longer declared — kept; "
                         f"remove it with git if meant")
    index["schede"] = dict(sorted(index["schede"].items()))
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # the vocabularies
    for r in read:
        if not r["schemes"]:
            continue
        where = voc / r["prefix"]
        where.mkdir(parents=True, exist_ok=True)
        for s in r["schemes"]:
            (where / f"{s['slug']}.json").write_text(
                json.dumps(s["doc"], ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            lines.append(f"  package vocabulary {s['id']:<24} tier {s['doc']['fascia']}  "
                         f"{len(s['doc']['concepts'])} concepts")
        _copy_licences(r, where)
    for r in read:
        if r["has_code"]:
            lines.append(f"  {r['label']}: mixed package — its data only; its code is never copied to a node")
        for c in r["local_only"]:
            lines.append(f"  {r['label']}: vocabulary {c} is tier C — not served by a node (local copy only)")
        lines.extend(f"  {r['label']}: {n}" for n in r["notes"])
    return lines


def package_schemes(header: Dict[str, Any]) -> List[str]:
    """The scheme ids of a scheda header that a PACKAGE carries (`<prefix>:…` of
    one of its `header.packages`): the central vocabulary step skips them."""
    prefixes = {str(p.get("prefix")) for p in header.get("packages") or [] if p.get("prefix")}
    return [str(v.get("id")) for v in header.get("vocabularies") or []
            if str(v.get("id", "")).split(":", 1)[0] in prefixes and ":" in str(v.get("id", ""))]


def sync(root: pathlib.Path, prev_index: Dict[str, Any], given: Sequence[str] = (),
         environ: Optional[Dict[str, str]] = None) -> List[str]:
    wanted = read_declaration(root)
    index_path = root / "schede" / "index.json"
    templates_ids = [sid for sid, e in (json.loads(index_path.read_text(encoding="utf-8"))
                                        if index_path.is_file() else {"schede": {}})["schede"].items()
                     if not e.get("package") and not e.get("only_here")]
    if not wanted and not any(e.get("package") for e in (prev_index.get("schede") or {}).values()):
        return ["  community packages: none declared (pacchetti.json)"]
    dirs = search_path(root, given, environ)
    with tempfile.TemporaryDirectory() as scratch:
        read = [read_package(w, find_package(w, dirs, pathlib.Path(scratch))) for w in wanted]
        return write(root, read, prev_index, templates_ids)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root")
    ap.add_argument("prev_index", nargs="?", default="")
    ap.add_argument("--from", dest="dirs", action="append", default=[])
    a = ap.parse_args(argv)
    prev = {}
    if a.prev_index and pathlib.Path(a.prev_index).is_file():
        prev = json.loads(pathlib.Path(a.prev_index).read_text(encoding="utf-8"))
    try:
        for line in sync(pathlib.Path(a.root), prev, a.dirs):
            print(line)
    except SyncError as exc:
        print(f"  community packages: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
