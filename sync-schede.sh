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
