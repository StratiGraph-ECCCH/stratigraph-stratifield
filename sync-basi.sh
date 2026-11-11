#!/usr/bin/env bash
# Vendor the CATALOGUE OF BASE MAPS from s3Dgraphy — the single source the two
# clients read (`s3dgraphy/JSON_config/em_basemap_sources.json`, moved there from
# EMStudio's `geoglobe.ts` SOURCES on 12 Nov 2026). Same shape and reasoning as
# `sync-schede.sh`: the app does not read another repository at runtime, so the
# file is COPIED in and committed.
#
#   ./sync-basi.sh                 # from the sibling checkout ../s3Dgraphy
#   ./sync-basi.sh ../s3Dgraphy    # from an explicit path
#
# Never edit `app/basi.json` by hand: the next sync overwrites it. A source
# whose `offline` CHANGED is the thing to look for in the diff — it decides
# whether the node may keep its tiles.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REL="src/s3dgraphy/JSON_config/em_basemap_sources.json"
SRC=""
for cand in "${1:-}" "$(cd "$HERE/.." && pwd)/s3Dgraphy"; do
  [ -n "$cand" ] && [ -f "$cand/$REL" ] && { SRC="$cand/$REL"; break; }
done
[ -n "$SRC" ] || { echo "em_basemap_sources.json not found (s3Dgraphy beside this repo, or pass its path)" >&2; exit 1; }
cp "$SRC" "$HERE/app/basi.json"
python3 - "$HERE/app/basi.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
for s in doc["sources"]:
    print(f"  {s['id']:18} {s['kind']:8} offline={str(s['offline']).lower():5} {s['licence']}")
PY
echo "app/basi.json ← $SRC"
