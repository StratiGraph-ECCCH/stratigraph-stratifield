"""V1 (4 ottobre 2026) · un vocabolario solo di operazioni, anche qui.

Misurato: EMtools mandava nella stanza `update_node`, il verbo del Sidecar, e la
libreria lo rifiutava. StratiField costruisce già le sue operazioni con le
cinque della libreria (`app/operazioni.py`); questa prova lo tiene fermo: ogni
operazione che una scheda produce passa `s3dgraphy.crdt.validate_op`, e nessuna
è un verbo di una scrivania (`crdt.LOCAL_VERBS` fuori da `crdt.OPS`).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import operazioni as O                                  # noqa: E402
from app import scheda as S                                      # noqa: E402

crdt = pytest.importorskip("s3dgraphy.crdt")
if not hasattr(crdt, "validate_op"):                             # pragma: no cover
    pytest.skip("s3dgraphy senza validate_op (prima della V1)", allow_module_level=True)
pytest.importorskip("yaml")

TS = "2026-10-04T10:00:00Z"


@pytest.mark.parametrize("values", [
    {"colore": "bruno", "descrizione": "strato di crollo"},
    {"copre": ["18"], "posteriore_a": ["19"]},
    {"formazione_segno": "negativa"},
])
def test_every_operation_of_a_scheda_is_one_the_room_speaks(values):
    plan = O.plan(S.find("iccd-us-2021", {}), values, number="12", section={},
                  ts=TS, create=True)
    assert plan.ops
    for op in plan.ops:
        assert crdt.validate_op(op) is None, (op, crdt.validate_op(op))
        assert op["op"] in crdt.OPS
