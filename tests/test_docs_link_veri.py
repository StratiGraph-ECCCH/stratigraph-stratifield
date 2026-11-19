"""Un collegamento del manuale che non porta da nessuna parte (19 novembre 2026).

Il manuale di StratiField è nato il 19 novembre con tredici collegamenti scritti
come percorsi relativi fra una cartella e l'altra del disco di chi li ha
scritti: `../../stratigraph-server/docs/ROOM-GUIDE.md`, `../README.md`. Sul
computer dove sono stati scritti funzionavano tutti; una volta pubblicati
sarebbero stati tredici 404, e `sphinx-build -W` non li vede, perché per Sphinx
un collegamento a un file che non è una pagina del progetto non è un avviso.

È la famiglia di difetti solita: la prova guarda una cosa (la build) e si crede
che ne garantisca un'altra (che i collegamenti portino da qualche parte).

Questa prova chiede una cosa sola: **ogni collegamento relativo di `docs/`
arriva a un file che esiste**. Quello che esce dal repository si scrive come
indirizzo intero (`https://…`), che è onesto: dice a chi legge che sta per
uscire di casa.
"""

from __future__ import annotations

import pathlib
import re

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

#: `[testo](destinazione)`, saltando le immagini `![...]`
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def _relative_links():
    for page in sorted(DOCS.rglob("*.md")):
        for raw in _LINK.findall(page.read_text(encoding="utf-8")):
            target = raw.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            yield page, target


#: la radice del repository: un collegamento relativo non ne esce
ROOT = DOCS.parent


def _guasto(page: pathlib.Path, target: str) -> str | None:
    """Perché questo collegamento non va, o None se va."""
    dove = (page.parent / target).resolve()
    try:
        dove.relative_to(ROOT)
    except ValueError:
        # esce dal repository: sul disco di chi scrive funziona, perché i
        # repository sono cartelle sorelle; una volta pubblicato è un 404.
        return f"{page.name} → {target} (esce dal repository)"
    if not dove.exists():
        return f"{page.name} → {target} (il file non c'è)"
    return None


def test_ogni_collegamento_relativo_resta_in_casa_e_arriva_a_un_file():
    rotti = [g for g in (_guasto(page, target) for page, target in _relative_links())
             if g]
    assert rotti == [], (
        "collegamenti che non portano da nessuna parte una volta pubblicati: "
        + ", ".join(rotti)
        + ". Un documento di un altro repository si cita con l'indirizzo intero.")
