"""La coda parte quando la stanza torna (prova 8 del tavolo, 12 ottobre).

Misurato contro la stanza con s3Dgraphy dev47, una persona seduta (editor) e
la rete tagliata da un proxy: la scheda della US 11 → `ok`, `queued`, la stanza
non la ha. Rete ricucita: in 10 s non arriva niente. `POST /v1/room/deliver` →
«Consegnate 12: la stanza le ha.» — e dopo, `GET /v1/room` diceva ancora
`last_refusal: "SessionClosed: la stanza non risponde: riprovo fra 1s"`.

Due cause. Il sorvegliante della sessione (`RoomSession.keep_seated`) riapriva
il socket senza attraversare il ponte; e gli scrivani PER PERSONA non avevano
nemmeno il sorvegliante — solo quello del nodo lo accendeva, all'avvio.
"""

from __future__ import annotations

import pathlib
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

pytest.importorskip("websockets", reason="serve il client websockets")

from app import scheda as S                                 # noqa: E402
from app.bridge import bridge_for                           # noqa: E402
from app.contract import GraphDelta, ToolResult             # noqa: E402
from app.scrivani import Scrivani, Where                    # noqa: E402
from app.writer import LocalWriter, RoomWriter              # noqa: E402
from tests.test_il_ponte import CHIUSO, ORCID, _rientra     # noqa: E402
from tests.test_room_writer_wire import FakeRelay           # noqa: E402


def _delta(node_id):
    return GraphDelta(nodes=[{"id": node_id, "node_type": "US",
                              "name": f"US {node_id}"}],
                      edges=[], process=None, author=ORCID)


def _arriva(relay, node_id, entro=6.0):
    fine = time.monotonic() + entro
    while time.monotonic() < fine:
        if node_id in [op.get("id") for op in relay.ops]:
            return True
        time.sleep(0.05)
    return False


def test_when_the_room_comes_back_the_queue_leaves_by_itself(tmp_path):
    """Nessuna scheda nuova, nessun «consegna ora»: la stanza torna e basta."""
    import app.main as M

    with FakeRelay() as relay:
        local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
        writer = RoomWriter(CHIUSO, "stanza", "tok", timeout=2.0,
                            fallback=local, bridge=bridge_for(local.path))
        writer.session._watch_every = 0.05
        writer.keep_seated()
        try:
            writer.apply(_delta("US11"))             # la rete non c'è
            assert len(writer.bridge) == 1 and writer.last_refusal

            _rientra(writer, relay)                  # la rete torna
            assert _arriva(relay, "US11"), "la coda aspetta ancora qualcuno"
            assert len(writer.bridge) == 0
            assert writer.last_refusal is None, writer.last_refusal
            assert writer.last_delivery["count"] == 1

            stato = M._room_view(M.Scope(who=ORCID, writer=writer), enter=False)
            assert stato["last_refusal"] is None
            assert stato["pending"] == 0
            assert stato["last_delivery"]["message"].startswith(
                "ultima consegna: 1 operazioni, alle ")
        finally:
            writer.close()


def test_a_read_only_seat_does_not_deliver_the_queue(tmp_path):
    """Seduti per leggere (`can_write: false`): il sorvegliante rientra, ma la
    coda non parte — un ruolo tolto non è la rete, e la coda resta sul nodo."""
    with FakeRelay(can_write=False) as relay:
        local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
        writer = RoomWriter(f"http://127.0.0.1:{relay.port}", "stanza", "tok",
                            timeout=2.0, fallback=local,
                            bridge=bridge_for(local.path))
        writer.bridge.keep([{"op": "add_node", "id": "US7",
                             "node": {"id": "US7"}}], why="prova")
        writer.session._watch_every = 0.05
        writer.keep_seated()
        try:
            time.sleep(0.5)
            assert "US7" not in [op.get("id") for op in relay.ops]
            assert len(writer.bridge) == 1, "la coda resta sul nodo"
        finally:
            writer.close()


def test_every_person_s_writer_keeps_its_seat():
    """Lo scrivano di una persona si siede e resta sorvegliato, come quello
    del nodo — anche dopo che `sweep` o un'uscita gli hanno chiuso il posto."""
    accesi = []

    class Finto:
        def __init__(self, *a, **k):
            self.path = "x"

        def keep_seated(self):
            accesi.append(self)

        def renew(self, token):
            pass

    scrivani = Scrivani(local=SimpleNamespace(path="/tmp/sf-scrivani-test.em.json"),
                        spool=None, build_registry=lambda w: None,
                        trusted={}, make=Finto)
    where = Where(server="https://s", room="r", dial="https://s")
    first, _ = scrivani.writer(ORCID, "tok", where)
    again, _ = scrivani.writer(ORCID, "tok2", where)
    assert first is again and accesi == [first, first]


def test_a_queued_scheda_says_which_unit_waits():
    import app.main as M

    class Coda:
        bridge = [object()]
        _n = 0

        def queued_here(self):
            return self._n

        def refusals_here(self):
            return 0

    writer = Coda()
    scope = SimpleNamespace(writer=writer)
    prima = (0, 0)
    writer._n = 12
    detto = M._told(ToolResult(ok=True, message="US 11: 3 campi aggiornati."),
                    scope, prima,
                    in_coda=(f"La scheda {M._della(S.find('iccd-us-2021'), '11')} "
                             f"è sul nodo: la consegno appena la stanza risponde."))
    assert detto["queued"] is True
    assert detto["message"] == ("US 11: 3 campi aggiornati. La scheda della US 11 "
                                "è sul nodo: la consegno appena la stanza risponde.")
    assert M._della(S.find("es-ue-demo-2026"), "14") == "della Contexto 14"
    assert M._della(S.find("dai-idaifield-layer-2026"), "B3") == "dell'unità B3"
