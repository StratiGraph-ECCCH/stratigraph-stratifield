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
# Never edit `schede/` by hand: the next sync overwrites it. Review the diff —
# a version that CHANGED rather than appeared is the thing to look for, and
# `stratigraph-templates build` already refuses to produce one.
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

# The whole directory, replaced: `index.json` names every version present, and
# a version file left behind that the index no longer names would be served by
# nobody and believed by whoever reads the directory.
rm -rf "$DST"
mkdir -p "$DST"
cp "$SRC/dist/schede/index.json" "$DST/"
( cd "$SRC/dist/schede" && find . -mindepth 2 -name '*.json' -print0 ) |
  while IFS= read -r -d '' rel; do
    mkdir -p "$DST/$(dirname "$rel")"
    cp "$SRC/dist/schede/$rel" "$DST/$rel"
  done

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
VOC="$HERE/vocabolari"
PY="$SRC/.venv/bin/python"
[ -x "$PY" ] || PY="python3"
rm -rf "$VOC"
mkdir -p "$VOC"
PYTHONPATH="$SRC/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - "$DST" "$VOC" <<'EOF'
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
