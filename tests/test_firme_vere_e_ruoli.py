"""Firme vere e ruoli nella stanza — il lato di StratiField.

════════════════════════════════════════════════════════════════════════════════
## COSA DIFENDE QUESTO FILE

Dal 25 ottobre ogni scrittura porta chi la fa e dove (`app/scrivani.py`): lo
scrivano è di una persona in una stanza, col token di quella persona. Qui si
prova quello che ne segue, contro una stanza finta che fa quello che fa il relay
vero — il ruolo dal token, 4403 a chi non è membro, `denied` a chi non può
scrivere — e contro una porta REST finta che risponde 401 a un token vecchio e
403 a un ruolo tolto:

1. **chi non è membro** non entra, e legge una frase, non «rete assente»;
2. **un viewer** entra e legge, e la sua scrittura è `refused` — non in coda;
3. **il token nuovo** riapre la sessione: la stanza non vede mai il vecchio
   dopo il rinnovo;
4. **in campo**, con la coda REST: token scaduto nel frattempo → alla consegna
   parte col token nuovo; ruolo tolto → la coda resta, e la risposta lo dice;
5. **la coda è per persona**: la nota di Anna non parte col token di Marco.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import http.server
import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("websockets", reason="serve il client websockets")

from fastapi.testclient import TestClient                     # noqa: E402

from app import main as main_module                           # noqa: E402
from app.assets import InMemoryAssetStore                     # noqa: E402
from app.auth import OidcSettings, authenticator              # noqa: E402
from app.bridge import bridge_for, room_key                   # noqa: E402
from app.scrivani import Scrivani                             # noqa: E402
from app.tools import build_registry                          # noqa: E402
from app.writer import AccessRefused, LocalWriter, RoomWriter  # noqa: E402

ISSUER = "https://keycloak.example/realms/stratigraph"
AUDIENCE = "stratigraph-chatbot"
KID = "k1"
ANNA = "0000-0003-1111-1112"        # editor
MARCO = "0000-0003-2222-2221"       # editor
VERA = "0000-0001-5109-3700"        # viewer
OSCAR = "0000-0003-3333-3330"       # nessun ruolo


def _orcid_of(token: str) -> str:
    try:
        corpo = token.split(".")[1]
        corpo += "=" * (-len(corpo) % 4)
        return json.loads(base64.urlsafe_b64decode(corpo)).get("orcid") or token
    except Exception:                                       # noqa: BLE001
        return token


# ═══ la stanza finta, che conosce i ruoli ════════════════════════════════════

class RoleRelay:
    """Il relay vero in piccolo: ruolo dal token, 4403 a chi non c'è."""

    def __init__(self, roles):
        self.roles = dict(roles)
        self.joins = []                   # (orcid, token)
        self.ops = []                     # (orcid, op)
        self.port = None
        self._ready = threading.Event()
        self._stop = None
        self._loop = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(10)
        return self

    def __exit__(self, *exc):
        self._loop.call_soon_threadsafe(
            lambda: self._stop.done() or self._stop.set_result(None))
        self._thread.join(timeout=5)
        return False

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def _run(self):
        import websockets

        async def handler(socket):
            target = getattr(getattr(socket, "request", None), "path", "") or ""
            token = target.split("token=", 1)[1].split("&")[0] if "token=" in target else ""
            who = _orcid_of(token)
            self.joins.append((who, token))
            role = self.roles.get(who)
            if role is None:
                await socket.close(code=4403, reason="not a member of this room")
                return
            can_write = role in ("editor", "admin", "owner")
            for frame in ({"type": "host_info", "payload": {
                               "author": who, "role": role, "can_write": can_write}},
                          {"type": "snapshot", "payload": {"doc": {"graphs": {}}}},
                          {"type": "presence", "payload": {"members": []}}):
                await socket.send(json.dumps({"v": 2, "source": "em-server", **frame}))
            try:
                async for raw in socket:
                    message = json.loads(raw)
                    kind = message.get("type")
                    if kind == "request_snapshot":
                        await socket.send(json.dumps({
                            "v": 2, "type": "snapshot", "source": "em-server",
                            "payload": {"doc": {"graphs": {}}}}))
                    elif kind == "op":
                        # IL RUOLO SI RILEGGE A OGNI SCRITTURA, come nel relay vero
                        now = self.roles.get(who)
                        if now not in ("editor", "admin", "owner"):
                            await socket.send(json.dumps({
                                "v": 2, "type": "denied", "source": "em-server",
                                "payload": {"verb": "op", "reason":
                                            "your access to this room has been withdrawn"
                                            if now is None else
                                            "this room is read-only for your role"}}))
                            continue
                        self.ops.append((who, message.get("payload")))
                        await socket.send(json.dumps({
                            "v": 2, "type": "op_result", "source": "em-server",
                            "payload": {"applied": True, "reason": "",
                                        "op": message.get("payload")}}))
            except Exception:                               # noqa: BLE001
                pass

        async def main():
            async with websockets.serve(handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                self._stop = asyncio.get_running_loop().create_future()
                self._ready.set()
                await self._stop

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(main())
        finally:
            self._loop.close()


# ═══ la porta REST finta ═════════════════════════════════════════════════════

class RestDoor:
    """`POST /v1/rooms/{id}/ops` e basta: 401 a un token scaduto, 403 a un
    ruolo tolto, 200 al resto. Il websocket non c'è — è il campo."""

    def __init__(self):
        self.expired = set()              # token scaduti
        self.revoked = set()              # orcid senza più ruolo
        self.received = []                # (orcid, token, n ops)

    def __enter__(self):
        door = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):                                # noqa: N802
                token = (self.headers.get("Authorization") or "").split(" ", 1)[-1]
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                who = _orcid_of(token)
                if token in door.expired:
                    code, answer = 401, {"detail": "the token has expired"}
                elif who in door.revoked:
                    code, answer = 403, {"detail": "writing operations into this "
                                                   "room needs editor or above"}
                else:
                    door.received.append((who, token, len(body["ops"])))
                    code, answer = 200, {"applied": len(body["ops"]),
                                         "refused": [], "kept": None}
                raw = json.dumps(answer).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):                     # noqa: A003
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        return False


# ═══ l'impalcatura del nodo ══════════════════════════════════════════════════

@pytest.fixture()
def realm():
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _Keys:
        def key_for(self, kid):
            return key.public_key()

    prima = (authenticator.settings, authenticator._jwks)
    authenticator.settings = OidcSettings(
        issuer=ISSUER, audience=AUDIENCE,
        jwks_uri=f"{ISSUER}/protocol/openid-connect/certs")
    authenticator._jwks = _Keys()

    def firma(orcid, *, jti="1"):
        adesso = datetime.datetime.now(datetime.timezone.utc)
        return jwt.encode({"sub": orcid, "iss": ISSUER, "aud": AUDIENCE,
                           "orcid": orcid, "iat": adesso, "jti": jti,
                           "exp": adesso + datetime.timedelta(minutes=15)},
                          key, algorithm="RS256", headers={"kid": KID})
    try:
        yield firma
    finally:
        authenticator.settings, authenticator._jwks = prima


@pytest.fixture()
def nodo(tmp_path, monkeypatch):
    local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
    store = InMemoryAssetStore()
    monkeypatch.setattr(main_module, "LOCAL", local)
    monkeypatch.setattr(main_module, "WRITER", local)
    monkeypatch.setattr(main_module, "LARDER", None)
    monkeypatch.setattr(main_module, "STORE", store)
    monkeypatch.setattr(main_module, "REGISTRY", build_registry(local, store))
    scrivani = Scrivani(local=local, spool=None, trusted={},
                        build_registry=lambda w: build_registry(w, store))
    monkeypatch.setattr(main_module, "SCRIVANI", scrivani)
    return local, scrivani


@pytest.fixture()
def client(nodo, realm):
    with TestClient(main_module.app) as c:
        yield c


def _qui(server, room="scavo"):
    return {"X-StratiGraph-Server": server, "X-StratiGraph-Room": room}


def _h(token, server, room="scavo"):
    return {"Authorization": "Bearer " + token, **_qui(server, room)}


US = "crea una nuova scheda, US {n}"


# ═══ 1 · chi non è membro ════════════════════════════════════════════════════

def test_CHI_NON_E_MEMBRO_non_entra_e_legge_una_frase(client, realm, nodo):
    with RoleRelay({ANNA: "editor"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        entra = client.post("/v1/room", json={"server": stanza.url, "room": "scavo"},
                            headers={"Authorization": "Bearer " + realm(OSCAR)})
        assert entra.status_code == 403, entra.text
        detto = entra.json()["detail"]
        assert "4403" in detto and "not a member" in detto, detto
        # …e nella vista della stanza è un fatto, non un errore
        vista = client.get("/v1/room", headers=_h(realm(OSCAR), stanza.url)).json()
        assert vista["member"] is False and vista["can_write"] is False
        assert vista["reachable"] is True, "una porta chiusa NON è una rete che manca"


def test_CHI_NON_E_MEMBRO_e_detta_non_finisce_in_coda(client, realm, nodo):
    """Il difetto che la distinzione esiste per chiudere: un 4403 letto come
    «join fallito» mandava la nota nel ramo della rete, in coda per sempre."""
    local, scrivani = nodo
    with RoleRelay({ANNA: "editor"}) as stanza:
        scrivani.trusted[stanza.url] = stanza.url
        detto = client.post("/v1/say", json={"transcript": US.format(n=9)},
                            headers=_h(realm(OSCAR), stanza.url)).json()
        assert detto["ok"] is False and detto["refused"] is True, detto
        [suo] = scrivani.mine(OSCAR)
        assert len(suo.bridge) == 0, "una nota rifiutata non è una nota in coda"
        assert stanza.ops == []


# ═══ 2 · il viewer ═══════════════════════════════════════════════════════════

def test_IL_VIEWER_legge_la_stanza_e_la_sua_scrittura_e_refused(client, realm, nodo):
    with RoleRelay({ANNA: "editor", VERA: "viewer"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        vera = realm(VERA)
        vista = client.get("/v1/room", headers=_h(vera, stanza.url)).json()
        assert (vista["role"], vista["can_write"], vista["member"]) == ("viewer", False, True)
        assert client.get("/v1/room/units", headers=_h(vera, stanza.url)).status_code == 200
        detto = client.post("/v1/say", json={"transcript": US.format(n=4)},
                            headers=_h(vera, stanza.url)).json()
        assert detto["refused"] is True and "read-only" in detto["message"]
        assert stanza.ops == []
        # …mentre l'editor accanto scrive, col suo nome
        anna = client.post("/v1/say", json={"transcript": US.format(n=5)},
                           headers=_h(realm(ANNA), stanza.url)).json()
        assert anna["ok"] is True and anna["refused"] is False, anna
        assert {chi for chi, _ in stanza.ops} == {ANNA}


def test_IL_RUOLO_TOLTO_MENTRE_SI_E_DENTRO(client, realm, nodo):
    with RoleRelay({ANNA: "editor"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        anna = realm(ANNA)
        assert client.post("/v1/say", json={"transcript": US.format(n=1)},
                           headers=_h(anna, stanza.url)).json()["ok"]
        stanza.roles.pop(ANNA)                  # l'owner la toglie
        dopo = client.post("/v1/say", json={"transcript": US.format(n=2)},
                           headers=_h(anna, stanza.url)).json()
        assert dopo["ok"] is False and dopo["refused"] is True
        assert "withdrawn" in dopo["message"]
        assert [op.get("id") for _, op in stanza.ops if op.get("op") == "add_node"
                and op.get("id") == "US2"] == []


# ═══ 3 · il token nuovo riapre la sessione ═══════════════════════════════════

def test_IL_TOKEN_RINNOVATO_riapre_la_sessione_col_nuovo(client, realm, nodo):
    """Il relay rilegge la scadenza a ogni scrittura: una sessione tenuta col
    token di un'ora fa verrebbe chiusa a metà di una scheda. Quindi al primo
    token diverso la sessione si riapre, e la stanza vede il nuovo."""
    with RoleRelay({ANNA: "editor"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        vecchio, nuovo = realm(ANNA, jti="a"), realm(ANNA, jti="b")
        assert vecchio != nuovo
        client.post("/v1/say", json={"transcript": US.format(n=1)},
                    headers=_h(vecchio, stanza.url))
        client.post("/v1/say", json={"transcript": US.format(n=2)},
                    headers=_h(nuovo, stanza.url))
        gettoni = [tok for _, tok in stanza.joins]
        assert gettoni[0] == vecchio and gettoni[-1] == nuovo, gettoni
        assert len(nodo[1].mine(ANNA)) == 1, "sempre lo stesso scrivano"


# ═══ 4 · in campo, con la coda REST ══════════════════════════════════════════

def _coda_offline(local, who, door_url, token):
    """Uno scrivano di campo con due operazioni già in coda."""
    writer = RoomWriter(door_url, "scavo", token, timeout=2.0, fallback=local,
                        bridge=bridge_for(local.path, "scavo", who=who))
    writer.bridge.keep([{"op": "add_node", "id": "US70", "ts": "2026-10-25T09:00:00Z",
                         "node": {"id": "US70", "node_type": "US"}},
                        {"op": "add_node", "id": "US71", "ts": "2026-10-25T09:01:00Z",
                         "node": {"id": "US71", "node_type": "US"}}],
                       why="senza rete in trincea")
    return writer


def test_IN_CAMPO_il_token_scaduto_nel_frattempo_si_rinnova_e_si_consegna(
        realm, nodo):
    local, _ = nodo
    with RestDoor() as porta:
        ieri = realm(ANNA, jti="ieri")
        writer = _coda_offline(local, ANNA, porta.url, ieri)
        porta.expired.add(ieri)
        # con il token di ieri la porta dice 401: la coda resta, e lo si sa
        with pytest.raises(AccessRefused):
            writer.deliver_pending()
        assert len(writer.bridge) == 2
        # …la persona torna, col token di oggi
        writer.renew(realm(ANNA, jti="oggi"))
        esito = writer.deliver_pending()
        assert esito == {"delivered": 2, "left": 0, "via": "rest", "stopped": None}
        assert [(chi, n) for chi, _, n in porta.received] == [(ANNA, 2)]


def test_IN_CAMPO_col_ruolo_tolto_la_coda_RESTA_e_la_rotta_lo_dice(
        client, realm, nodo):
    local, scrivani = nodo
    with RestDoor() as porta:
        scrivani.trusted[porta.url] = porta.url
        anna = realm(ANNA)
        # la coda di Anna, scritta prima, dentro il SUO scrivano
        writer, _ = scrivani.writer(ANNA, anna, scrivani.where(porta.url, "scavo"))
        writer.bridge.keep([{"op": "add_node", "id": "US80", "ts": "2026-10-25T09:00:00Z",
                             "node": {"id": "US80", "node_type": "US"}}], why="offline")
        porta.revoked.add(ANNA)
        detto = client.post("/v1/room/deliver", headers=_h(anna, porta.url)).json()
        assert detto["refused"] is True and detto["left"] == 1, detto
        assert "restano su questo nodo" in detto["message"]
        assert porta.received == []
        vista = client.get("/v1/room", headers=_h(anna, porta.url)).json()
        assert vista["pending"] == 1, "e si vede"
        # …e quando il ruolo torna, la coda parte
        porta.revoked.clear()
        detto = client.post("/v1/room/deliver", headers=_h(anna, porta.url)).json()
        assert detto["ok"] is True and detto["delivered"] == 1, detto


# ═══ 5 · la coda è per persona ═══════════════════════════════════════════════

def test_LA_CODA_E_PER_PERSONA_la_nota_di_Anna_non_parte_col_token_di_Marco(
        realm, nodo):
    local, _ = nodo
    with RestDoor() as porta:
        di_anna = _coda_offline(local, ANNA, porta.url, realm(ANNA))
        di_marco = RoomWriter(porta.url, "scavo", realm(MARCO), timeout=2.0,
                              fallback=local,
                              bridge=bridge_for(local.path, "scavo", who=MARCO))
        assert di_anna.bridge.path != di_marco.bridge.path
        assert room_key(ANNA) in di_anna.bridge.path.name
        assert di_marco.deliver_pending()["delivered"] == 0
        assert porta.received == [], "Marco non ha consegnato niente di Anna"
        di_anna.deliver_pending()
        assert [chi for chi, _, _ in porta.received] == [ANNA]


def test_IL_SILENZIO_chiude_la_sessione_di_chi_se_n_e_andato(client, realm, nodo):
    """Il nodo non può rinnovare il token di una persona che non c'è più, e
    sedere a suo nome è la bugia che la presenza esiste per non dire."""
    with RoleRelay({ANNA: "editor"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        client.get("/v1/room", headers=_h(realm(ANNA), stanza.url))
        [suo] = nodo[1].mine(ANNA)
        assert suo.session.seated
        import time
        assert nodo[1].sweep(now=time.monotonic() + nodo[1].idle_after + 1) == 1
        assert not suo.session.seated


def test_LA_REVOCA_SI_VEDE_A_UNO_SGUARDO_non_al_primo_rifiuto(client, realm, nodo,
                                                              monkeypatch):
    """Misurato nel browser il 28 settembre: con la sessione aperta,
    `GET /v1/room` ripeteva il ruolo del JOIN, e una revoca a metà lavoro non si
    vedeva fino alla prima scrittura rifiutata. Ora a ogni sguardo il ruolo si
    richiede alla porta REST della stanza, che legge l'ACL di adesso."""
    with RoleRelay({ANNA: "editor"}) as stanza:
        nodo[1].trusted[stanza.url] = stanza.url
        anna = realm(ANNA)
        prima = client.get("/v1/room", headers=_h(anna, stanza.url)).json()
        assert prima["role"] == "editor" and prima["member"] is True
        [suo] = nodo[1].mine(ANNA)
        assert suo.session.seated

        def porta_chiusa(self):
            self._access("la porta REST della stanza ha rifiutato (403): "
                         "not a member of this room")
            return {"status": 403, "role": None}
        monkeypatch.setattr(RoomWriter, "role_by_rest", porta_chiusa)
        dopo = client.get("/v1/room", headers=_h(anna, stanza.url)).json()
        assert dopo["member"] is False and dopo["can_write"] is False
        assert "403" in dopo["refused"]
        assert not suo.session.seated, "la sessione col ruolo vecchio si chiude"


def test_IN_CAMPO_una_unita_dettata_parte_dalla_porta_REST_e_col_ruolo_tolto_resta(
        realm, nodo):
    """Misurato il 28 settembre: senza websocket `apply()` accodava sul nodo e
    non provava la porta REST, e la US restava lì finché qualcuno non chiedeva
    «consegna ora». Ora parte subito; e se la stanza rifiuta la consegna, la
    coda resta, e la richiesta lo sa (`refusals_here`, `queued_here`)."""
    from app.contract import GraphDelta

    local, _ = nodo
    with RestDoor() as porta:
        writer = RoomWriter(porta.url, "scavo", realm(ANNA), timeout=2.0,
                            fallback=local,
                            bridge=bridge_for(local.path, "scavo", who=ANNA))
        writer.apply(GraphDelta(nodes=[{"id": "US90", "node_type": "US"}],
                                edges=[], process=None, author=ANNA))
        assert [(chi, n) for chi, _, n in porta.received] == [(ANNA, 1)]
        assert len(writer.bridge) == 0

        porta.revoked.add(ANNA)
        prima = (writer.refusals_here(), writer.queued_here())
        writer.apply(GraphDelta(nodes=[{"id": "US91", "node_type": "US"}],
                                edges=[], process=None, author=ANNA))
        assert len(writer.bridge) == 1, "la coda resta sul nodo"
        assert writer.refusals_here() > prima[0] and writer.queued_here() > prima[1]


def test_I_RIFIUTI_SI_CONTANO_PER_RICHIESTA_non_per_scrivano(realm, nodo):
    """Il falso positivo misurato nel browser: il battito di un altro thread
    incrementava lo stesso contatore della dettatura."""
    local, _ = nodo
    writer = RoomWriter("http://127.0.0.1:9", "scavo", realm(ANNA), fallback=local)
    visto = []

    def battito():
        writer._access("403 dal battito")
        visto.append(writer.refusals_here())

    t = threading.Thread(target=battito)
    t.start(); t.join()
    assert visto == [1], "nel thread del battito il rifiuto c'è"
    assert writer.refusals_here() == 0, "nel thread della dettatura no"
