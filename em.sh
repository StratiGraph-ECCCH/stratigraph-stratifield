#!/usr/bin/env bash
# StratiField (stratigraph-chatbot) — a small entry point, the same ergonomics as
# the `em.sh` of s3Dgraphy, stratigraph-templates and EMStudio. It CALLS what the
# repository has — `./sync-schede.sh`, pytest — and replaces neither.
#
# Start with:  ./em.sh help
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"

log()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

need_venv() {
  [[ -x "$PY" ]] || die "no .venv here. Create it as the README says:
    python3 -m venv .venv && .venv/bin/pip install -e . -e ../s3Dgraphy"
}

help_overview() {
  cat <<'EOF'
StratiField — ./em.sh <command> [args]

  sync-schede [path]   Vendor the compiled schede from stratigraph-templates (./sync-schede.sh),
                       then show what changed. Does not commit.
                         ./em.sh sync-schede
                         ./em.sh sync-schede ../stratigraph-templates
  test [pytest args…]  The test suite (.venv/bin/python -m pytest).
                         ./em.sh test -q
  status               The s3dgraphy this node runs, and each vendored scheda's datamodel against it.
                         ./em.sh status
  help [command]       This list, or the long help of one command.
                         ./em.sh help sync-schede

After a datamodel change the order is: s3Dgraphy → stratigraph-templates
(./em.sh after-bump) → here (./em.sh sync-schede). s3Dgraphy's
`./em.sh propagate` runs the three in that order.
EOF
}

help_sync_schede() {
  cat <<'EOF'
./em.sh sync-schede [path]

WHAT IT DOES
  Runs ./sync-schede.sh [path], unchanged: it copies
  stratigraph-templates/dist/schede/ into schede/ (from the sibling checkout, or
  the path you give), resolves the vocabularies the schede name into
  vocabolari/ with templates' own Python, and prints:
    · one line per scheda: versions, latest, datamodel nodes/connections;
    · the schede that live ONLY HERE and are never overwritten (on 2026-10-01:
      iaa-dana-locus-2026, until its licence lets it move to templates);
    · the fingerprint of the latest version of each vendored scheda against the
      s3dgraphy this node runs (= aligned, ≠ moved, · compiled before the
      fingerprint).
  Then `git status --short` of schede/ and vocabolari/.

WHAT IT DOES NOT DO
  It does not build the schede (stratigraph-templates: ./em.sh build), does not
  commit, does not touch a scheda that only lives here.

WHEN
  After stratigraph-templates rebuilt dist/schede (its ./em.sh after-bump).

EXAMPLE
  $ ./em.sh sync-schede
  synced the compiled schede from …/stratigraph-templates (commit 16dafe8, dist/schede NOT committed there)
    iccd-us-2021   2.0.0 …
    only here, not from templates: iaa-dana-locus-2026  (last change 2026-10-26 …)
    s3dgraphy here   1.6.0.dev25  datamodel sha256:aab44dda…
    = iccd-us-2021   2.0.0  datamodel sha256:aab44dda… on connections, node_registry, nodes, qualia
   M schede/iccd-us-2021/2.0.0.json

IF IT FAILS
  "no dist/schede/index.json" → build in templates first, or pass its path.
  A ≠ line → the scheda was built on another datamodel: rebuild in templates
  (./em.sh after-bump there), then sync again. At run time StratiField does not
  block on it: it shows a notice on the scheda.
EOF
}

help_test() {
  cat <<'EOF'
./em.sh test [pytest args…]

  .venv/bin/python -m pytest [args] (testpaths = tests). Writes nothing.
  Example: ./em.sh test -q tests/test_la_scheda_diventa_operazioni.py
  test_the_vendored_copy_is_the_compiled_form_and_not_stale compares schede/
  with the sibling templates' dist/: red after templates rebuilt → ./em.sh sync-schede.
EOF
}

help_status() {
  cat <<'EOF'
./em.sh status

  The s3dgraphy this node runs (version, and where it is imported from: an
  editable ../s3Dgraphy or a PyPI release), its datamodel fingerprint, and, for
  the latest version of each vendored scheda, its datamodel against it —
  compared on the files the scheda was built from, as app/scheda.py
  check_datamodel does at load. Writes nothing.
  Example:
    $ ./em.sh status
    s3dgraphy 1.6.0.dev25  …/s3Dgraphy/src/s3dgraphy (editable)
    = iccd-us-2021  2.0.0  built on connections, node_registry, nodes, qualia
    · iaa-dana-locus-2026  0.1.1  compiled before the fingerprint (only here)
EOF
}

do_help() {
  case "${1:-}" in
    "") help_overview ;;
    sync-schede) help_sync_schede ;;
    test|status) "help_$1" ;;
    *) die "no command '$1'. ./em.sh help lists them." ;;
  esac
}

do_status() {
  need_venv
  "$PY" - "$ROOT/schede" <<'EOF'
import json, pathlib, sys
dst = pathlib.Path(sys.argv[1])
try:
    import s3dgraphy
    from s3dgraphy.datamodel import datamodel_fingerprint
except Exception as exc:
    print(f"s3dgraphy: no fingerprint here ({exc.__class__.__name__}: {exc})"); raise SystemExit(2)
where = s3dgraphy.__file__.rsplit("/__init__.py", 1)[0]
kind = "site-packages" if "site-packages" in where else "editable"
fp = datamodel_fingerprint(); here = fp.get("digests") or {}
print(f"s3dgraphy {s3dgraphy.__version__}  {where} ({kind})")
print(f"datamodel {fp['digest']}")
index = json.loads((dst / "index.json").read_text(encoding="utf-8"))
moved_any = False
for sid, e in sorted(index["schede"].items()):
    latest = e["latest"]
    head = json.loads((dst / e["versions"][latest]["path"]).read_text(encoding="utf-8"))["header"]
    dm = head.get("datamodel") or {}
    files = dm.get("files") or {}
    tag = "  (only here)" if e.get("only_here") else ""
    if files:
        moved = [n for n, x in sorted(files.items()) if (x or {}).get("digest") != here.get(n)]
        moved_any |= bool(moved)
        print(f"  {'≠' if moved else '='} {sid:<26} {latest:<8} s3dgraphy {dm.get('s3dgraphy', '?'):<12} built on "
              + ", ".join(sorted(files)) + (f" — moved: {', '.join(moved)}" if moved else "") + tag)
    else:
        print(f"  · {sid:<26} {latest:<8} {dm.get('digest') or 'compiled before the fingerprint'}{tag}")
raise SystemExit(1 if moved_any else 0)
EOF
}

cmd="${1:-help}"; shift || true
case "$cmd" in
  help|-h|--help) do_help "${1:-}" ;;
  sync-schede)
    log "./sync-schede.sh $*"
    (cd "$ROOT" && ./sync-schede.sh "$@")
    echo
    st="$(git -C "$ROOT" status --short -- schede vocabolari)"
    echo "changed here:"; printf '%s\n' "${st:-  (nothing)}"
    ok "sync done — nothing committed. Review: git diff schede vocabolari"
    ;;
  test)   need_venv; cd "$ROOT"; "$PY" -m pytest "$@" ;;
  status) do_status ;;
  *) echo "unknown command '$cmd'" >&2; echo >&2; help_overview >&2; exit 2 ;;
esac
