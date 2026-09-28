"""La porta si apre da dentro: una persona firma e il nodo va nella sua stanza.

════════════════════════════════════════════════════════════════════════════════
## IL CASO CHE LO FA SCATTARE

`handoff.writer_from_link` esiste dal 14 agosto e non la chiamava nessuno: il
nodo si puntava a una stanza **solo all'avvio, dall'ambiente**. Una persona che
apriva l'assistente e firmava diceva CHI parla e non DOVE arriva.

E la ragione per cui non bastava aggiungere una rotta e basta è misurata nel
primo blocco di questo file: **lo scrivano è un singleton**, e la coda del ponte
apparteneva al nodo e non alla stanza. Una rotta che ripunta, sopra quelle due
cose, avrebbe consegnato il lavoro di una stanza dentro un'altra.

*Cambiare destinazione a un lavoro già accodato non è ripuntare, è perderlo con
un'altra faccia.*

## DAL 25 OTTOBRE IL NODO NON SI PRENDE PIÙ

La presa (`holding.py`, «un nodo, una persona alla volta») esisteva perché lo
scrivano era uno e il suo token era del nodo: l'unica configurazione onesta era
dirlo. Adesso lo scrivano è **di una persona in una stanza** (`app/scrivani.py`)
e porta il suo token, quindi due persone sullo stesso nodo scrivono ciascuna a
nome suo e la presa non ha più niente da proteggere. `POST /v1/room` prova la
porta per chi chiama e non sposta il nodo; il posto lo tiene il browser e lo
manda con ogni richiesta. Le prove della presa sono uscite con lei; quelle delle
code, dell'ambiente e del disco restano, riscritte sulla forma nuova.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")
pytest.importorskip("websockets", reason="serve il client websockets")

from fastapi.testclient import TestClient                     # noqa: E402

from app import handoff                                       # noqa: E402
from app import main as main_module                           # noqa: E402
from app.assets import InMemoryAssetStore                     # noqa: E402
from app.auth import OidcSettings, authenticator              # noqa: E402
from app.bridge import bridge_for, queues_beside, room_key    # noqa: E402
from app.contract import GraphDelta                           # noqa: E402
from app.tools import build_registry                          # noqa: E402
from app.writer import LocalWriter, RoomWriter                # noqa: E402
from tests.test_room_writer_wire import FakeRelay             # noqa: E402

ISSUER = "https://keycloak.example/realms/stratigraph"
AUDIENCE = "stratigraph-chatbot"
KID = "field-key-1"
DEV = "0000-0002-1825-0097"
VIEWER = "0000-0001-5109-3700"


# ═══ l'impalcatura ═══════════════════════════════════════════════════════════

@pytest.fixture()
def realm():
    """Un realm di cui questo test possiede la chiave, con due identità."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _Keys:
        def key_for(self, kid):
            assert kid == KID
            return key.public_key()

    prima = (authenticator.settings, authenticator._jwks)
    authenticator.settings = OidcSettings(
        issuer=ISSUER, audience=AUDIENCE,
        jwks_uri=f"{ISSUER}/protocol/openid-connect/certs")
    authenticator._jwks = _Keys()

    def firma(orcid=DEV):
        adesso = datetime.datetime.now(datetime.timezone.utc)
        return jwt.encode({"sub": orcid, "iss": ISSUER, "aud": AUDIENCE,
                           "orcid": orcid, "iat": adesso,
                           "exp": adesso + datetime.timedelta(minutes=30)},
                          key, algorithm="RS256", headers={"kid": KID})

    try:
        yield firma
    finally:
        authenticator.settings, authenticator._jwks = prima


@pytest.fixture()
def nodo(tmp_path, monkeypatch):
    """Un nodo con il suo container locale, nessuna stanza, e un registro di
    scrivani per persona che si fida dei server che il test gli dà."""
    from app.scrivani import Scrivani

    local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Saggio B")
    store = InMemoryAssetStore()
    monkeypatch.setattr(main_module, "LOCAL", local)
    monkeypatch.setattr(main_module, "WRITER", local)
    monkeypatch.setattr(main_module, "LARDER", None)
    monkeypatch.setattr(main_module, "STORE", store)
    monkeypatch.setattr(main_module, "REGISTRY", build_registry(local, store))
    scrivani = Scrivani(local=local, spool=None, trusted={},
                        build_registry=lambda w: build_registry(w, store))
    monkeypatch.setattr(main_module, "SCRIVANI", scrivani)
    # niente scambio configurato e nessun token d'ambiente, se non lo dice il test
    for nome in handoff.EXCHANGE_KEYS + ("EM_CHATBOT_TOKEN",):
        monkeypatch.delenv(nome, raising=False)
    return local, scrivani


@pytest.fixture()
def client(nodo, realm):
    with TestClient(main_module.app) as c:
        yield c


def _con(firma, orcid=DEV):
    return {"Authorization": "Bearer " + firma(orcid)}


def _fidato(nodo, *indirizzi):
    """Il nodo nomina questi server: la firma di una persona ci può andare."""
    for indirizzo in indirizzi:
        nodo[1].trusted[indirizzo] = indirizzo


def _qui(indirizzo, stanza):
    """Il posto che il browser manda con ogni richiesta."""
    return {"X-StratiGraph-Server": indirizzo, "X-StratiGraph-Room": stanza}


# ═══ 1 · cosa succede OGGI con due firme ═════════════════════════════════════

def test_due_firme_scrivono_nello_stesso_posto_ma_con_nomi_diversi(
        client, realm, nodo):
    """La misura di §1, dentro la suite perché una misura che vale la pena fare
    vale la pena tenerla.

    Sul container locale **l'autore è già giusto per ciascuno**: `_author` lo
    prende dal token a ogni richiesta. Quello che i due condividono è **dove**
    finisce il lavoro, non a nome di chi risulta.
    """
    local, _ = nodo
    scrivano_prima = main_module.WRITER
    for chi, numero in ((DEV, "10"), (VIEWER, "20")):
        risposta = client.post(
            "/v1/say", json={"transcript": f"crea una nuova scheda, US {numero}"},
            headers=_con(realm, chi))
        assert risposta.status_code == 200, risposta.text

    assert main_module.WRITER is scrivano_prima, "un solo scrivano, per tutti"
    doc = json.loads(pathlib.Path(local.path).read_text(encoding="utf-8"))
    sezione = next(iter(doc["graphs"].values()))
    autori = {n["id"]: (n.get("data") or {}).get("created_by")
              for n in sezione["nodes"] if n.get("node_type") == "US"}
    assert autori == {"US10": DEV, "US20": VIEWER}


def test_nella_stanza_il_nome_e_quello_del_TOKEN_che_consegna(tmp_path):
    """La ragione per cui lo scrivano è per persona (`app/scrivani.py`).

    Il relay prende l'autore dal token e non dal payload — lo dice la sua
    docstring, letta e non dedotta. Qui si misura il lato client: le operazioni
    partono **senza autore**, quindi nella stanza il nome è quello del token di
    chi consegna. Con uno scrivano del nodo era il nodo; ora è la persona.
    """
    with FakeRelay() as relay:
        local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
        writer = RoomWriter(f"http://127.0.0.1:{relay.port}", "stanza", "tok",
                            timeout=2.0, fallback=local,
                            bridge=bridge_for(local.path, "stanza"))
        writer.apply(GraphDelta(
            nodes=[{"id": "US1", "node_type": "US", "name": "US 1",
                    "data": {"created_by": VIEWER}}],
            edges=[], process=None, author=VIEWER))
        [operazione] = [op for op in relay.ops if op.get("id") == "US1"]
        assert "author" not in operazione, (
            "il client non dichiara l'autore: lo mette il token di chi consegna")
        assert operazione["node"]["data"]["created_by"] == VIEWER, (
            "nel payload c'è chi ha parlato — e le due cose possono "
            "contraddirsi, che è il fatto")


# ═══ 2 · due persone, due scrivani ══════════════════════════════════════════

def test_due_persone_nella_stessa_stanza_hanno_DUE_scrivani_e_due_token(
        client, realm, nodo):
    """Il cuore della notte. Stessa stanza, due firme: ognuna entra col suo
    token, e il relay (che firma dal token) vede due persone."""
    _, scrivani = nodo
    with FakeRelay() as relay:
        indirizzo = f"http://127.0.0.1:{relay.port}"
        _fidato(nodo, indirizzo)
        mia, sua = realm(DEV), realm(VIEWER)
        for firma, numero in ((mia, "10"), (sua, "20")):
            risposta = client.post(
                "/v1/say",
                json={"transcript": f"crea una nuova scheda, US {numero}"},
                headers={"Authorization": "Bearer " + firma,
                         **_qui(indirizzo, "A")})
            assert risposta.status_code == 200, risposta.text
            assert risposta.json()["ok"], risposta.json()
        assert mia in relay.tokens and sua in relay.tokens, relay.tokens
        assert len(scrivani.mine(DEV)) == 1 and len(scrivani.mine(VIEWER)) == 1
        assert scrivani.mine(DEV)[0] is not scrivani.mine(VIEWER)[0]
    assert main_module.WRITER is nodo[0], "il nodo non si è mosso"


def test_senza_firma_non_si_entra(client, realm, nodo):
    risposta = client.post("/v1/room", json={"server": "http://x", "room": "A"})
    assert risposta.status_code == 401


def test_un_server_che_il_nodo_non_ha_nominato_NON_riceve_la_firma(
        client, realm, nodo):
    """Il *confused deputy* che `_room_credential` teneva chiuso rifiutando
    l'inoltro: il server lo sceglie il LINK, e un link lo scrive chiunque. Ora
    la firma va solo ai server che chi amministra il nodo ha scritto."""
    mia = realm(DEV)
    with FakeRelay() as relay:
        estraneo = f"http://127.0.0.1:{relay.port}"
        risposta = client.post("/v1/room",
                               json={"server": estraneo, "room": "A"},
                               headers={"Authorization": "Bearer " + mia})
        assert risposta.status_code == 403, risposta.text
        assert "EM_ROOM_SERVERS" in risposta.json()["detail"]
        # …né per la porta di ogni giorno, gli header
        detto = client.post("/v1/say", json={"transcript": "crea una nuova scheda, US 3"},
                            headers={"Authorization": "Bearer " + mia,
                                     **_qui(estraneo, "A")})
        assert detto.status_code == 403
        assert relay.tokens == [], "la firma è uscita verso un server estraneo"


# ═══ 3 · IL CANCELLO: la coda non cambia destinazione ════════════════════════

def test_IL_CANCELLO_la_coda_di_A_non_finisce_in_B(client, realm, nodo,
                                                   monkeypatch):
    """Operazioni accodate per A, si ripunta a B, e **in B non arrivano**.

    Costruito apposta: si scrive verso A con A irraggiungibile (le operazioni
    finiscono in coda), poi si ripunta a B che invece risponde, e si guarda cosa
    ha ricevuto B.
    """
    local, scrivani = nodo
    with FakeRelay() as relay:
        vivo = f"http://127.0.0.1:{relay.port}"
        morto = "http://127.0.0.1:9"           # nessuno ascolta
        _fidato(nodo, vivo, morto)

        # ── A, irraggiungibile: il lavoro si accoda ──
        client.post("/v1/say", json={"transcript": "crea una nuova scheda, US 77"},
                    headers={**_con(realm, DEV), **_qui(morto, "A")})
        [scrivano_a] = scrivani.mine(DEV)
        assert len(scrivano_a.bridge) >= 1, "in coda per A"
        in_coda_per_a = [op.get("id") for op in scrivano_a.bridge.pending()]
        assert "US77" in in_coda_per_a

        # ── si va in B, che risponde ──
        prima_in_b = len(relay.ops)
        risposta = client.post("/v1/room", json={"server": vivo, "room": "B"},
                               headers=_con(realm, DEV))
        assert risposta.status_code == 200, risposta.text

        # ── e in B non è arrivato niente di A ──
        arrivate = [op.get("id") for op in relay.ops[prima_in_b:]]
        assert "US77" not in arrivate, (
            "il lavoro dettato per la stanza A è comparso nella stanza B")
        scrivano_b = next(w for w in scrivani.mine(DEV) if w.room_id == "B")
        assert len(scrivano_b.bridge) == 0, "B parte con la sua coda vuota"
        # e quello di A è ancora lì, suo — di DEV in A — e si vede
        code = {q["queue"]: q["pending"] for q in queues_beside(local.path)}
        mia = (f"{pathlib.Path(local.path).name}.{room_key('A')}."
               f"{room_key(DEV)}.pending.jsonl")
        assert code.get(mia, 0) >= 1, code
        assert risposta.json()["queues"], "e /v1/room lo dice a chi entra"


def test_E_CON_UNA_CODA_SOLA_il_lavoro_di_A_FINISCE_IN_B(tmp_path):
    """La gemella della rottura, e misura **l'effetto**: con la coda del nodo —
    quella di ieri, non per stanza — le stesse operazioni entrano nell'altra
    stanza e nessuno può accorgersene, perché sono valide."""
    with FakeRelay() as relay:
        local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
        # ── la rottura: `bridge_for` senza stanza, come prima del 2 ottobre ──
        coda_del_nodo = bridge_for(local.path)
        a = RoomWriter("http://127.0.0.1:9", "A", "tok", timeout=1.0,
                       fallback=local, bridge=coda_del_nodo)
        a.apply(GraphDelta(nodes=[{"id": "US77", "node_type": "US",
                                   "name": "US 77"}],
                           edges=[], process=None, author=DEV))
        assert len(coda_del_nodo) == 1

        b = RoomWriter(f"http://127.0.0.1:{relay.port}", "B", "tok",
                       timeout=2.0, fallback=local, bridge=coda_del_nodo)
        b._seated()                                   # il rientro attraversa
        arrivate = [op.get("id") for op in relay.ops]
        assert "US77" in arrivate, (
            "ed ecco il danno: una scheda dettata per A è nella stanza B")


def test_la_coda_che_cera_gia_viene_adottata(tmp_path):
    """Un nodo che gira da ieri ha una coda senza nome di stanza, e magari del
    lavoro dentro. Lasciarla in un file che nessuno guarda più sarebbe la
    perdita del 27 settembre ripetuta da capo."""
    local = LocalWriter(str(tmp_path / "scavo.em.json"), study="Scavo")
    vecchia = bridge_for(local.path)              # la forma di prima
    vecchia.keep([{"op": "add_node", "id": "US1"}], why="prima del 2 ottobre")
    assert vecchia.path.is_file()

    mia = bridge_for(local.path, "A")
    assert not vecchia.path.exists(), "adottata, non copiata"
    assert [op["id"] for op in mia.pending()] == ["US1"]


def test_due_stanze_che_si_somigliano_non_condividono_la_coda():
    """`saggio/B` e `saggio-B` sono due stanze diverse. Due code che si
    confondono sarebbero lo stesso difetto del cancello, in miniatura."""
    assert room_key("saggio/B") != room_key("saggio-B")
    assert room_key("saggio/B").startswith("saggio-B.")


# ═══ 4 · la dispensa al momento del cambio ═══════════════════════════════════

def test_la_dispensa_NON_e_per_stanza_e_cè_una_ragione(client, realm, nodo,
                                                       monkeypatch, tmp_path):
    """I byte in attesa restano dove sono, e non è una dimenticanza.

    Un'operazione appartiene a una stanza; **dei byte no**. La dispensa consegna
    allo store condiviso, che è configurato sul NODO (`MINIO_*`) e non sulla
    stanza: gli stessi byte, con lo stesso digest, servono a chiunque li citi.
    Dividerla per stanza vorrebbe dire caricare due volte la stessa foto.

    Il limite che ne segue, dichiarato: ripuntare il nodo a una stanza **su un
    altro server** non cambia il bucket. Oggi non succede — un nodo di campo ha
    un solo store — e il giorno che succedesse la dispensa andrebbe divisa per
    store, non per stanza.
    """
    from app.spool import Spool

    local, scrivani = nodo
    dispensa = Spool(tmp_path / "dispensa", remote=InMemoryAssetStore())
    monkeypatch.setattr(main_module, "LARDER", dispensa)
    scrivani.spool = dispensa
    dispensa.put(b"\xff\xd8\xff\xe0 foto \xff\xd9", "image/jpeg")
    prima = list(dispensa.waiting())
    assert len(prima) == 1

    with FakeRelay() as relay:
        _fidato(nodo, f"http://127.0.0.1:{relay.port}")
        risposta = client.post(
            "/v1/room",
            json={"server": f"http://127.0.0.1:{relay.port}", "room": "B"},
            headers=_con(realm, DEV))
        assert risposta.status_code == 200, risposta.text
        # la dispensa sale quando si SCRIVE, non quando si entra a guardare
        detto = client.post("/v1/say", json={"transcript": "crea una nuova scheda, US 8"},
                            headers={**_con(realm, DEV),
                                     **_qui(f"http://127.0.0.1:{relay.port}", "B")})
        assert detto.status_code == 200, detto.text
    # …e al rientro nella stanza nuova sono SALITI, non spariti: `_seated`
    # attraversa la dispensa prima del ponte, che è la regola del 30 settembre.
    # Il punto di questo test è che la dispensa è **una sola** — non una per
    # stanza — e che quei byte non sono stati né persi né caricati due volte.
    assert dispensa.waiting() == [], "consegnati allo store condiviso"
    assert dispensa._remote.get(prima[0]) is not None
    assert dispensa._remote.count() == 1, "una volta sola"
    assert all(w.spool is dispensa for w in scrivani.everyone()), (
        "e la stessa dispensa, una sola, per tutte le persone")


# ═══ 5 · il ritorno indietro ═════════════════════════════════════════════════

def test_si_torna_al_posto_del_nodo_e_le_sessioni_si_chiudono(client, realm,
                                                                nodo):
    local, scrivani = nodo
    with FakeRelay() as relay:
        indirizzo = f"http://127.0.0.1:{relay.port}"
        _fidato(nodo, indirizzo)
        client.post("/v1/room", json={"server": indirizzo, "room": "A"},
                    headers=_con(realm, DEV))
        [mio] = scrivani.mine(DEV)
        assert mio.session.seated
        indietro = client.delete("/v1/room", headers=_con(realm, DEV))
        assert indietro.status_code == 200, indietro.text
        assert not mio.session.seated, "la sessione in A si è chiusa"
        assert main_module.WRITER is local, "il nodo non si era mai mosso"
        assert "container locale" in indietro.json()["message"]


# ═══ 6 · il nodo lo dice ═════════════════════════════════════════════════════

def test_ognuno_legge_DOVE_scrive_LUI(client, realm, nodo):
    with FakeRelay() as relay:
        indirizzo = f"http://127.0.0.1:{relay.port}"
        _fidato(nodo, indirizzo)
        a = client.get("/v1/room", headers={**_con(realm, DEV),
                                            **_qui(indirizzo, "A")}).json()
        b = client.get("/v1/room", headers={**_con(realm, VIEWER),
                                            **_qui(indirizzo, "B")}).json()
        assert (a["room"], a["who"]) == ("A", DEV)
        assert (b["room"], b["who"]) == ("B", VIEWER)
        assert a["role"] == "owner" and a["can_write"] is True
        salute = client.get("/health").json()
        assert DEV not in json.dumps(salute) and VIEWER not in json.dumps(salute), (
            "/health è pubblica: chi lavora qui non si dice a chi non firma")
        assert salute["seated"] is True, "la rete verso la stanza c'è"


# ═══ 7 · la porta si prova PRIMA di scambiare lo scrivano ════════════════════

def test_una_stanza_che_non_risponde_si_dice_come_rete(client, realm, nodo):
    _fidato(nodo, "http://127.0.0.1:9")
    rifiuto = client.post("/v1/room",
                          json={"server": "http://127.0.0.1:9", "room": "Z"},
                          headers=_con(realm, DEV))
    assert rifiuto.status_code == 502
    assert "non ha risposto" in rifiuto.json()["detail"]


def test_una_stanza_in_sola_lettura_si_apre_PER_LEGGERE(client, realm, nodo):
    """Fino al 25 ottobre un viewer riceveva 502 e «read-only»: la porta si
    chiudeva e con lei la sola via per rileggere la stanza. Ora entra, legge,
    e la risposta dice il ruolo."""
    with FakeRelay(can_write=False) as relay:
        indirizzo = f"http://127.0.0.1:{relay.port}"
        _fidato(nodo, indirizzo)
        entra = client.post("/v1/room", json={"server": indirizzo, "room": "A"},
                            headers=_con(realm, VIEWER))
        assert entra.status_code == 200, entra.text
        assert entra.json()["can_write"] is False
        assert "per leggere" in entra.json()["message"]
        elenco = client.get("/v1/room/units",
                            headers={**_con(realm, VIEWER), **_qui(indirizzo, "A")})
        assert elenco.status_code == 200, elenco.text
        scrive = client.post("/v1/say", json={"transcript": "crea una nuova scheda, US 4"},
                             headers={**_con(realm, VIEWER), **_qui(indirizzo, "A")})
        assert scrive.json()["ok"] is False
        assert "read-only" in scrive.json()["message"]
        assert not [m for m in relay.received if m.get("type") == "op"], (
            "nessuna operazione è partita da un viewer")


# ═══ 8 · la credenziale ══════════════════════════════════════════════════════

def test_lo_scambio_chiede_al_realm_a_nome_di_chi_ha_firmato(monkeypatch):
    """Lo scambio, misurato su un endpoint finto: cosa parte davvero."""
    visto = {}

    class _Risposta:
        status = 200

        def read(self):
            return b'{"access_token": "tok-per-la-stanza"}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def finto_urlopen(request, timeout=None):
        import urllib.parse
        visto["url"] = request.full_url
        visto["body"] = dict(urllib.parse.parse_qsl(request.data.decode()))
        return _Risposta()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", finto_urlopen)
    ambiente = {"EM_ROOM_AUDIENCE": "em-server", "OIDC_CLIENT_ID": "em-chatbot",
                "OIDC_CLIENT_SECRET": "segreto-del-nodo"}
    fuori = handoff.exchange("la-firma-di-chi-chiama",
                             token_endpoint=ISSUER + "/protocol/openid-connect/token",
                             env=ambiente)
    assert fuori == "tok-per-la-stanza"
    assert visto["body"]["grant_type"] == \
        "urn:ietf:params:oauth:grant-type:token-exchange"
    assert visto["body"]["subject_token"] == "la-firma-di-chi-chiama"
    assert visto["body"]["audience"] == "em-server"
    assert visto["body"]["client_secret"] == "segreto-del-nodo"


def test_lo_scambio_non_configurato_dice_le_tre_cose(monkeypatch):
    with pytest.raises(handoff.NoCredential) as manca:
        handoff.exchange("x", token_endpoint="http://x", env={})
    for nome in handoff.EXCHANGE_KEYS:
        assert nome in str(manca.value)


# ═══ 9 · il ripiego dall'ambiente resta ══════════════════════════════════════

def test_un_nodo_headless_parte_dalla_sua_variabile(tmp_path, monkeypatch):
    """*«A field node that boots headless into a known room has no browser to
    sign in with»* — la rotta si aggiunge, non sostituisce."""
    from app.writer import writer_from_env

    with FakeRelay() as relay:
        monkeypatch.setenv("EM_SERVER_URL", f"http://127.0.0.1:{relay.port}")
        monkeypatch.setenv("EM_CHATBOT_ROOM", "stanza-dallambiente")
        monkeypatch.setenv("EM_CHATBOT_TOKEN", "tok")
        monkeypatch.setenv("EM_CHATBOT_CONTAINER", str(tmp_path / "scavo.em.json"))
        monkeypatch.delenv("EM_CHATBOT_HANDOFF", raising=False)
        monkeypatch.delenv("EM_ASSET_SPOOL", raising=False)
        scrivano = writer_from_env()
        assert scrivano.room_id == "stanza-dallambiente"
        # e la sua coda è quella DELLA SUA STANZA, come tutte le altre
        assert room_key("stanza-dallambiente") in scrivano.bridge.path.name


def test_un_nodo_headless_non_apre_nessun_browser(monkeypatch):
    """La regola del docstring, tenuta da un test: `writer_from_env` viene
    chiamata all'import, e aprire un browser come effetto del caricamento di un
    modulo è il modo di appendere un servizio all'avvio."""
    fonte = (pathlib.Path(__file__).resolve().parent.parent / "app"
             / "writer.py").read_text(encoding="utf-8")
    codice = "\n".join(riga for riga in fonte.split("\n")
                       if not riga.strip().startswith("#"))
    assert "webbrowser" not in codice
    assert "sign_in" not in codice


# ═══ 10 · nessun token in un ambiente di processo ════════════════════════════

def test_ripuntare_non_scrive_nessun_token_da_nessuna_parte(
        client, realm, nodo, monkeypatch, tmp_path):
    """Dimostrato, non affermato: si guarda `os.environ` prima e dopo, e si
    cerca il token sul disco del nodo.

    *«un token che finisce in un processo è un token in `ps`, in un crash dump e
    nel file dell'unità»* — `handoff.py`, ed è la ragione per cui la rotta
    esiste invece delle tre variabili."""
    import os

    local, _ = nodo
    mia = realm(DEV)
    prima = dict(os.environ)
    with FakeRelay() as relay:
        _fidato(nodo, f"http://127.0.0.1:{relay.port}")
        risposta = client.post(
            "/v1/room",
            json={"server": f"http://127.0.0.1:{relay.port}", "room": "A"},
            headers={"Authorization": "Bearer " + mia})
        assert risposta.status_code == 200, risposta.text

    dopo = dict(os.environ)
    assert dopo == prima, "l'ambiente del processo non è cambiato"
    assert not [k for k, v in dopo.items() if mia in str(v)]
    # e niente sul disco del nodo
    for path in pathlib.Path(local.path).parent.rglob("*"):
        if path.is_file():
            assert mia not in path.read_text(encoding="utf-8", errors="ignore"), \
                f"la firma di chi ha chiamato è finita in {path.name}"
    # né nella risposta che il nodo dà
    assert mia not in json.dumps(risposta.json())


# ═══ 12 · la superficie ══════════════════════════════════════════════════════

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"


def test_la_pagina_dice_dove_scrive_senza_che_glielo_si_chieda():
    """`#room-name` esisteva nel DOM dal 23 settembre e **nessuno lo
    riempiva**. Un nodo che ha cambiato stanza e non lo mostra è la stessa
    famiglia di difetti di tutta questa settimana."""
    pagina = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="room-name"' in pagina
    assert 'id="nav-room"' in pagina
    assert "window.SGRoom?.(health)" in pagina, (
        "la riga si aggiorna a ogni /health, non una volta all'avvio: il nodo "
        "si può ripuntare da un altro dispositivo")
    modulo = (WEB / "room.js").read_text(encoding="utf-8")
    assert "export function headline" in modulo


def test_il_nome_di_chi_tiene_il_nodo_NON_passa_da_health():
    """`/health` è pubblica: il fatto sì, il nome no. Il nome si legge da
    `/v1/room`, che una firma la chiede."""
    modulo = (WEB / "room.js").read_text(encoding="utf-8")
    assert '"/v1/room"' in modulo and "Authorization" in modulo
    codice = "\n".join(riga for riga in modulo.split("\n")
                       if not riga.strip().startswith(("*", "/*", "//")))
    intestazione = codice.split("export function headline")[1].split(
        "export function leftBehind")[0]
    assert "who" not in intestazione, (
        "la riga pubblica dell'intestazione si costruisce da /health, che il "
        "nome non ce l'ha")


def test_la_pagina_ripete_la_frase_del_NODO_e_non_una_sua():
    """Un rifiuto dice chi tiene il nodo e da quanto, oppure cosa manca perché
    possa presentarsi alla stanza. Riscriverlo in «non riuscito» butterebbe via
    l'unica cosa utile."""
    modulo = (WEB / "room.js").read_text(encoding="utf-8")
    assert "detto.detail || t(\"room.refused\")" in modulo
    assert "detto.message || t(\"room.pointed\")" in modulo


def test_la_stanza_non_porta_colori_letterali():
    import re
    for nome in ("room.js",):
        testo = (WEB / nome).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", testo), nome


def test_la_conchiglia_non_mangia_le_rotte_di_v1():
    """Il jolly della conchiglia (`/{shell_file:path}`) raccoglieva ogni GET
    sotto `/v1/` che vivesse sul router `v1`: misurato il 2 ottobre su
    `GET /v1/room`, che esisteva e rispondeva `404 not part of the shell`.

    Un test sull'ORDINE e non sul sintomo: il jolly deve restare l'ultimo, che
    è l'unica cosa che un jolly deve essere.
    """
    fonte = (pathlib.Path(__file__).resolve().parent.parent / "app"
             / "main.py").read_text(encoding="utf-8")
    assert fonte.index("app.include_router(v1)") < \
        fonte.index("app.include_router(public)")


def test_GET_v1_room_arriva_al_suo_gestore(client, realm, nodo):
    """E lo stesso fatto, misurato invece che dedotto dall'ordine."""
    risposta = client.get("/v1/room", headers=_con(realm, DEV))
    assert risposta.status_code == 200, risposta.text
    assert "role" in risposta.json()
