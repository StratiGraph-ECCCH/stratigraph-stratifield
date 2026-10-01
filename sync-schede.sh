#!/usr/bin/env bash
# Vendor the COMPILED schede from `stratigraph-templates/dist/schede/` — the
# single source. Same shape and same reasoning as `sync-brand.sh` and EMStudio's
# `sync-datamodels.sh`: the app does not read another repository at runtime, so
# the compiled form is COPIED in and committed.
#
#   ./sync-schede.sh                          # from the sibling checkout
#   ./sync-schede.sh ../stratigraph-templates # from an explicit path
#
# Why a copy and not the bind-mount of the checkout the dev-stack used: an image
# published to GHCR has to serve schede on a node nobody has cloned anything on
# (audit 2026-10-17, B5a: «l'immagine GHCR parte senza schede»), and a definition
# read live from a working tree is a definition that changes under a scheda
# somebody is filling in. A compiled version never changes (SPEC §9.4): what is
# copied here is what the unit will say it was compiled with.
#
# `STRATIGRAPH_SCHEDE_DIR` still overrides this directory, for development only,
# and `app/scheda.py` says so in the log.
#
# Never edit a vendored scheda by hand: the next sync overwrites it. Review the
# diff — a version that CHANGED rather than appeared is the thing to look for,
# and `stratigraph-templates build` already refuses to produce one.
#
# A scheda that `dist/` does NOT have is not touched (2026-10-26): it was added
# here, not vendored from templates — today `iaa-dana-locus-2026`, which moves
# to stratigraph-templates once its licence is cleared. The sync lists it as
# «only here», with the date and commit of its last change, and keeps it in
# `index.json`. Until that day the sync began with `rm -rf schede/`, which
# would have lost it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="$HERE/schede"
SIBLING="$(cd "$HERE/.." && pwd)/stratigraph-templates"

has_dist() { [ -f "$1/dist/schede/index.json" ]; }

SRC=""
if [ -n "${1:-}" ]; then
  for cand in "$1" "$1/stratigraph-templates"; do
    if has_dist "$cand"; then SRC="$cand"; break; fi
  done
  [ -n "$SRC" ] || { echo "no dist/schede/index.json under '$1' — run 'stratigraph-templates build' there" >&2; exit 1; }
fi
if [ -z "$SRC" ] && has_dist "$SIBLING"; then SRC="$SIBLING"; fi
[ -n "$SRC" ] || {
  echo "stratigraph-templates/dist/schede not found beside this repo — pass a path." >&2
  exit 1
}

# Each scheda `dist/` has is REPLACED whole, its directory emptied first: a
# version file left behind that the index no longer names would be served by
# nobody and believed by whoever reads the directory. A scheda `dist/` does not
# have is left as it is (see the top), and named.
mkdir -p "$DST"
ONLY_HERE=()
for dir in "$DST"/*/; do
  [ -d "$dir" ] || continue
  sid="$(basename "$dir")"
  [ -d "$SRC/dist/schede/$sid" ] || ONLY_HERE+=("$sid")
done
for dir in "$SRC/dist/schede"/*/; do
  [ -d "$dir" ] || continue
  sid="$(basename "$dir")"
  rm -rf "${DST:?}/$sid"
  mkdir -p "$DST/$sid"
  ( cd "$dir" && find . -name '*.json' -print0 ) |
    while IFS= read -r -d '' rel; do
      mkdir -p "$DST/$sid/$(dirname "$rel")"
      cp "$dir/$rel" "$DST/$sid/$rel"
    done
done
# The index: templates' own, byte for byte when nothing is only here; else
# with one entry per scheda only here, in the same shape
# (stratigraph-templates compile.write_index), marked `only_here`.
python3 - "$SRC/dist/schede/index.json" "$DST" ${ONLY_HERE[@]+"${ONLY_HERE[@]}"} <<'EOF'
import json, pathlib, re, sys
src, dst, only_here = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3:]
if not only_here:
    (dst / "index.json").write_bytes(src.read_bytes())
    sys.exit(0)
index = json.loads(src.read_text(encoding="utf-8"))

def semver(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v))

for sid in only_here:
    versions = {}
    for f in sorted((dst / sid).glob("*.json")):
        head = json.loads(f.read_text(encoding="utf-8")).get("header") or {}
        if head.get("id") != sid or not head.get("version"):
            continue
        dm = head.get("datamodel") or {}
        versions[head["version"]] = {
            "path": f.relative_to(dst).as_posix(),
            "digest": head.get("digest"),
            "standard": {k: (head.get("standard") or {}).get(k)
                         for k in ("authority", "code", "version", "invented")},
            "datamodel": {k: dm[k] for k in ("nodes", "connections", "qualia", "em_ttl", "digest")
                          if k in dm},
        }
    if versions:
        ordered = sorted(versions, key=semver)
        index["schede"][sid] = {"versions": {v: versions[v] for v in ordered},
                                "latest": ordered[-1], "only_here": True}
index["schede"] = dict(sorted(index["schede"].items()))
(dst / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
EOF

commit=$(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo "?")
dirty=$(git -C "$SRC" status --porcelain -- dist/schede 2>/dev/null | head -1)
echo "synced the compiled schede from $SRC (commit $commit${dirty:+, dist/schede NOT committed there})"
python3 - "$DST/index.json" <<'EOF'
import json, sys
index = json.load(open(sys.argv[1], encoding="utf-8"))
for sid, entry in sorted(index["schede"].items()):
    versions = sorted(entry["versions"])
    latest = entry["latest"]
    dm = entry["versions"][latest]["datamodel"]
    print(f"  {sid:<18} {', '.join(versions):<12} latest {latest}  "
          f"datamodel nodes {dm['nodes']} · connections {dm['connections']}")
EOF
echo "  vendored size    $(du -sh "$DST" | cut -f1)"
for sid in ${ONLY_HERE[@]+"${ONLY_HERE[@]}"}; do
  last="$(git -C "$HERE" log -1 --format='%ad %h' --date=short -- "schede/$sid" 2>/dev/null || true)"
  edited="$(git -C "$HERE" status --porcelain -- "schede/$sid" 2>/dev/null | head -1 || true)"
  echo "  only here, not from templates: $sid  (last change ${last:-never committed}${edited:+; uncommitted edits})"
done

# ── THE DATAMODEL FINGERPRINT, BOTH SIDES (2026-10-01) ────────────────────────
#
# A compiled scheda carries s3Dgraphy's datamodel fingerprint in
# `header.datamodel.digest` (stratigraph-templates snapshot format 4); the app
# compares it at load with the s3dgraphy it runs on (`app/scheda.py`
# `check_datamodel`) and says so in the log and on the scheda. Printed here too,
# so that whoever syncs sees at once whether the schede and this node's
# s3dgraphy agree — the latest version of each scheda, and the installed
# package's own fingerprint, read with the python this app runs on. Since
# s3Dgraphy dev25 a scheda also carries `header.datamodel.files`, the files it
# was built from, and the mark compares those (as `check_datamodel` does); the
# one digest is printed beside it either way.
APP_PY="$HERE/.venv/bin/python"
[ -x "$APP_PY" ] || APP_PY="python3"
"$APP_PY" - "$DST" <<'EOF'
import json, pathlib, sys
dst = pathlib.Path(sys.argv[1])
index = json.loads((dst / "index.json").read_text(encoding="utf-8"))
try:
    import s3dgraphy
    from s3dgraphy.datamodel import datamodel_fingerprint
    fp = datamodel_fingerprint()
    here, here_d = fp["digest"], fp.get("digests") or {}
    print(f"  s3dgraphy here   {s3dgraphy.__version__}  datamodel {here}")
except Exception as exc:  # absent, or older than the fingerprint
    here, here_d = None, {}
    print(f"  s3dgraphy here   no fingerprint ({exc.__class__.__name__}: {exc})")
for sid, entry in sorted(index["schede"].items()):
    latest = entry["latest"]
    head = json.loads((dst / entry["versions"][latest]["path"]).read_text(encoding="utf-8"))
    dm = head["header"].get("datamodel") or {}
    digest, files = dm.get("digest"), dm.get("files")
    if files and here:
        moved = [n for n, e in sorted(files.items()) if (e or {}).get("digest") != here_d.get(n)]
        mark, on = ("≠" if moved else "="), f" on {', '.join(sorted(files))}"
    else:
        mark = ("=" if digest == here else "≠") if digest and here else "·"
        on = ""
    print(f"  {mark} {sid:<26} {latest:<8} datamodel "
          f"{digest or '— compiled before the fingerprint'}{on}")
EOF

# ── THE VOCABULARIES THE VENDORED SCHEDE NAME (2026-10-22) ────────────────────
#
# A `term` box offers the concepts of ITS scheme (SPEC §3), and the phone has to
# offer them in a trench. A compiled scheda names its schemes in the header but
# does not carry their concepts — a vocabulary has a life and a licence of its
# own — so they are resolved HERE, once, with `stratigraph-templates`' own
# resolver (own scheme → alignment, SPEC §3.1), and vendored beside the schede:
# `vocabolari/<scheme>.json`, one per scheme, in every language the schede that
# name it declare.
#
# A `declared` scheme (the ICCD field models: the norm prescribes a vocabulary
# and no SKOS exists) is vendored TOO, with no concepts: the node then SAYS it
# is declared instead of looking like a node that lost the file. Nothing here
# invents a concept. A declared scheme that names a PROVISIONAL one
# (stratigraph-templates SPEC §3.2) has its stand-in listed right after it in
# the header, so the stand-in is vendored here with its concepts.
#
# Beside `schede/` and not inside it: every `*.json` under `schede/` is read as
# a definition.
#
# The same rule as the schede (2026-10-26): what the sync resolves is written
# over its old copy, and a vocabulary it does not resolve is NOT deleted — it is
# listed as «only here», with the date and commit of its last change. Measured
# that day: none is (every vendored vocabulary is named by a vendored scheda,
# and `iaa-dana-locus-2026` names none), so the list is empty; it is there for
# the day a vocabulary is added here first.
VOC="$HERE/vocabolari"
PY="$SRC/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
mkdir -p "$VOC"
VOC_NEW="$(mktemp -d)"
trap 'rm -rf "$VOC_NEW"' EXIT
PYTHONPATH="$SRC/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - "$DST" "$VOC_NEW" <<'EOF'
import json, pathlib, sys
from stratigraph_templates.vocab import Vocabularies, VocabularyError

schede, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
vocab = Vocabularies.load()
wanted = {}                                   # scheme -> languages asked for
stands_in = {}                                # provisional scheme -> the norm's
for path in sorted(schede.rglob("*.json")):
    if path.name == "index.json":
        continue
    header = json.loads(path.read_text(encoding="utf-8"))["header"]
    for entry in header.get("vocabularies") or []:
        wanted.setdefault(entry["id"], set()).update(header.get("languages") or [])
        if entry.get("provisional_for"):
            stands_in[entry["id"]] = entry["provisional_for"]
for sid, langs in sorted(wanted.items()):
    scheme = vocab.schemes.get(sid)
    if scheme is None:
        sys.exit(f"  a vendored scheda names scheme '{sid}', which stratigraph-templates does not declare")
    concepts = []
    for uri, labels in sorted(vocab.concepts(sid).items()):
        if scheme.uri and uri == scheme.uri:
            continue                          # the ConceptScheme, not a concept
        said = {}
        for lang in sorted(langs):
            try:
                said[lang] = vocab.resolve(sid, uri, lang).label
            except VocabularyError:
                pass                          # no word in that language: none invented
        concepts.append({"concept": uri, "labels": said})
    doc = {"format": 1, "scheme": sid, "authority": scheme.authority,
           "status": scheme.status, "fixture": bool(scheme.fixture),
           "uri": scheme.uri, "license": scheme.license,
           # the licence travels with its ATTRIBUTION (2026-10-26): Apache-2.0
           # (iDAI.field) and CC BY-SA ask for both, and a vendored copy that
           # drops one is the copy that breaks the licence
           "attribution": scheme.attribution,
           "labels": scheme.labels, "languages": sorted(langs),
           "concepts": concepts}
    # SPEC §3.2-3.3 (2026-09-27): whom a provisional module stands in for, and
    # which of its languages nobody has verified yet — said, not hidden.
    if sid in stands_in:
        doc["provisional_for"] = stands_in[sid]
    if scheme.provisional:
        doc["provisional"] = scheme.provisional
    if scheme.unverified_languages:
        doc["unverified_languages"] = sorted(scheme.unverified_languages)
    (out / f"{sid}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"  vocabulary {sid:<28} {scheme.status:<10} {len(concepts)} concepts")
EOF
for f in "$VOC"/*.json; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  [ -f "$VOC_NEW/$name" ] && continue
  last="$(git -C "$HERE" log -1 --format='%ad %h' --date=short -- "vocabolari/$name" 2>/dev/null || true)"
  echo "  only here, not from templates: vocabolari/$name  (last change ${last:-never committed})"
done
for f in "$VOC_NEW"/*.json; do
  [ -f "$f" ] && cp "$f" "$VOC/"
done

# ── APACHE-2.0: THE LICENCE AND A NOTICE BESIDE WHAT IS VENDORED (2026-09-28) ──
#
# The DAI's words (iDAI.field, Apache-2.0) travel in two places: the compiled
# scheda (field labels de/en) and the `idai-field-*` vocabularies (valuelist
# labels). Apache-2.0 §4 asks whoever redistributes to give a copy of the
# licence and to keep the attribution: the `attribution` field in each json is
# not enough for someone who opens the image and not the json. So, beside each
# of them: `LICENSE-Apache-2.0.txt` (the text the DAI itself distributes, read
# from the iDAI.field checkout at the commit the schemes are read at — upstream
# has no NOTICE file of its own at that commit, measured) and a `NOTICE` saying
# what is the DAI's, from which commit, and that it is not modified in meaning.
# Generated, never hand-edited, like everything else here.
PYTHONPATH="$SRC/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - "$DST" "$VOC" <<'EOF'
import json, pathlib, sys
from stratigraph_templates import idai_extract as idai
from stratigraph_templates.vocab import Vocabularies

schede, voc = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
vocab = Vocabularies.load()
commits = sorted({s.resolve.get("commit") for s in vocab.schemes.values()
                  if s.resolve.get("kind") == "idai_field_valuelist"} - {None})
apache_voc = sorted(p for p in voc.glob("*.json")
                    if json.loads(p.read_text(encoding="utf-8")).get("license") == "Apache-2.0")
apache_schede = {}
for path in sorted(schede.rglob("*.json")):
    if path.name == "index.json":
        continue
    std = json.loads(path.read_text(encoding="utf-8"))["header"].get("standard") or {}
    if std.get("license") == "Apache-2.0":
        apache_schede.setdefault(path.parent, []).append((path.name, std.get("attribution", "")))
if not (apache_voc or apache_schede):
    sys.exit(0)
if len(commits) != 1:
    sys.exit(f"  Apache-2.0 material vendored, but the idai-field-* schemes name {len(commits)} "
             f"commits ({commits}): one licence text per directory needs one commit")
src = idai.Source.open(commit=commits[0])
licence = src.text("LICENSE")
assert "Apache License" in licence and "Version 2.0" in licence, "LICENSE at the commit is not Apache-2.0"

HEAD = ("This directory contains material from iDAI.field (Field Desktop), (c) Deutsches\n"
        "Archäologisches Institut (DAI), https://github.com/dainst/idai-field, licensed under\n"
        "the Apache License, Version 2.0 (copy in LICENSE-Apache-2.0.txt).\n"
        f"Read at commit {src.commit} ({src.date}).\n\n")
TAIL = ("\nThe DAI's labels are reproduced as published, not translated or changed; the\n"
        "reading around them (which box lands where in the graph, the notes, the\n"
        "alignments) is StratiGraph's own work and carries its own licence.\n"
        "Upstream has no NOTICE file at that commit; this one is written by\n"
        "stratigraph-chatbot/sync-schede.sh.\n")

def write(where, lines):
    (where / "LICENSE-Apache-2.0.txt").write_text(licence, encoding="utf-8")
    (where / "NOTICE").write_text(HEAD + "".join(f"  - {l}\n" for l in lines) + TAIL, encoding="utf-8")
    print(f"  Apache-2.0      LICENSE + NOTICE → {where.name}/ ({len(lines)} file(s))")

for where, files in sorted(apache_schede.items()):
    write(where, [f"{name}: field names and their de/en labels — {attr}" for name, attr in files])
if apache_voc:
    write(voc, [f"{p.name}: valuelist labels — "
                f"{json.loads(p.read_text(encoding='utf-8')).get('attribution', '')}" for p in apache_voc])
EOF
