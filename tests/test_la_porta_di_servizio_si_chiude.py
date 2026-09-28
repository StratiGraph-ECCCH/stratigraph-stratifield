"""La porta `?token=` è del banco, e si chiude quando il nodo firma davvero.

════════════════════════════════════════════════════════════════════════════════
## PERCHÉ UN TEST COL BROWSER

`?token=…` è come gli smoke e il banco guidano la pagina senza una persona
davanti a Keycloak (`SERVICE_TOKEN` in `web/index.html`). Nelle notti del 19 e
del 22 era l'unica firma esercitata: un JWT non firmato, accettato perché il
nodo girava senza autenticazione. Su un nodo che ha un realm la firma viene dal
realm e da nessun'altra parte, e una porta che resta aperta lì è un modo di
presentarsi con un nome che nessuno ha verificato — la pagina lo MOSTREREBBE,
anche se il nodo poi lo rifiuterebbe.

La prova è sulla pagina vera, in Chrome vero: lo stesso indirizzo con
`?token=`, una volta davanti a un nodo senza realm (il banco: si entra) e una
volta davanti a un nodo che dichiara `enforcing` (si resta al cancello).

E accanto, il rinnovo: un token che scade fra 10 secondi viene rinnovato col
refresh token PRIMA di scadere, senza che nessuno tocchi niente.
"""

from __future__ import annotations

import base64
import json
import pathlib
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests.test_la_cache_e_sempre_fresca import _chrome, _until  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _b64(obj) -> str:
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def fake_jwt(orcid: str, *, life: int = 600, jti: str = "1") -> str:
    """Un JWT NON firmato — quello del banco. La pagina lo legge per mostrare
    il nome e non decide niente: è il nodo che verifica."""
    now = int(time.time())
    return ".".join([_b64({"alg": "none"}),
                     _b64({"orcid": orcid, "name": "Banco", "iat": now,
                           "exp": now + life, "jti": jti}), "x"])


@pytest.fixture
def served():
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("playwright.sync_api")
    import app.main as main

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


ENFORCING = {"enforcing": True, "issuer": "https://kc.example/realms/em",
             "client_id": "stratifield", "scope": "openid",
             "authorization_endpoint": "https://kc.example/realms/em/protocol/openid-connect/auth",
             "token_endpoint": "https://kc.example/realms/em/protocol/openid-connect/token",
             "end_session_endpoint": "", "missing": []}


def _page(p, base, *, auth_config=None, token_answers=None, seen=None):
    browser = _chrome(p)
    context = browser.new_context(service_workers="block")
    page = context.new_page()
    if auth_config is not None:
        page.route("**/v1/auth-config", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(auth_config)))
    if token_answers is not None:
        def token(route):
            form = dict(p2.split("=", 1) for p2 in
                        (route.request.post_data or "").split("&") if "=" in p2)
            if seen is not None:
                seen.append(form)
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(token_answers(form)))
        page.route("https://kc.example/**/token", token)
    return browser, page


def test_SUL_BANCO_senza_realm_la_porta_si_apre(served):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = _page(p, served)
        page.goto(served + "?token=" + fake_jwt("0000-0002-1825-0097"))
        _until(page, "() => Boolean(window.SG && window.SG.signed)")
        assert page.evaluate("window.SG.subject") == "0000-0002-1825-0097"
        browser.close()


def test_CON_IL_REALM_la_porta_di_servizio_E_CHIUSA(served):
    """Lo stesso indirizzo, davanti a un nodo che firma davvero: nessuna firma,
    il cancello, e il bottone per andare dal realm."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = _page(p, served, auth_config=ENFORCING)
        page.goto(served + "?token=" + fake_jwt("0000-0002-1825-0097"))
        _until(page, "() => !document.getElementById('gate').hidden")
        assert page.evaluate("window.SG.signed") is False
        assert page.evaluate("window.SG.token") == ""
        assert page.is_visible("#signin"), "si firma dal realm, e il bottone c'è"
        assert page.is_hidden("#work")
        browser.close()


def test_IL_TOKEN_SI_RINNOVA_PRIMA_DI_SCADERE(served):
    """Un giro di firma finto ma completo (PKCE: stato in sessionStorage, codice
    nell'indirizzo, scambio al token endpoint), con un token da 10 s. La pagina
    deve chiedere il rinnovo col refresh token prima che scada."""
    from playwright.sync_api import sync_playwright

    seen = []
    orcid = "0000-0003-1111-1112"

    def answers(form):
        if form.get("grant_type") == "authorization_code":
            return {"access_token": fake_jwt(orcid, life=10, jti="primo"),
                    "refresh_token": "r-1", "expires_in": 10}
        assert form.get("grant_type") == "refresh_token"
        return {"access_token": fake_jwt(orcid, life=10, jti=f"r{len(seen)}"),
                "refresh_token": f"r-{len(seen)}", "expires_in": 10}

    with sync_playwright() as p:
        browser, page = _page(p, served, auth_config=ENFORCING,
                              token_answers=answers, seen=seen)
        page.goto(served)
        page.evaluate("""() => sessionStorage.setItem('sg.pkce' + location.pathname,
                          JSON.stringify({verifier: 'v', state: 's'}))""")
        page.goto(served + "?code=c&state=s")
        _until(page, "() => Boolean(window.SG && window.SG.signed)")
        primo = page.evaluate("window.SG.token")
        partito = time.monotonic()
        _until(page, "(t) => window.SG.token !== t", primo, timeout=12)
        dopo = time.monotonic() - partito
        grants = [f.get("grant_type") for f in seen]
        assert grants[:2] == ["authorization_code", "refresh_token"], grants
        assert seen[1]["refresh_token"] == "r-1"
        # prima della scadenza (10 s), non dopo
        assert dopo < 9.5, dopo
        # …e la firma resta della stessa persona
        assert page.evaluate("window.SG.subject") == orcid
        browser.close()


def test_LA_PORTA_si_decide_in_UN_posto():
    """`serviceDoorOpen` è l'unica decisione, e l'avvio la chiede."""
    page = (pathlib.Path(__file__).resolve().parent.parent / "web"
            / "index.html").read_text(encoding="utf-8")
    assert "Boolean(SERVICE_TOKEN) && !(config && config.enforcing)" in page
    assert "else if (serviceDoorOpen(AUTHCFG))" in page
    assert page.count("adopt(SERVICE_TOKEN)") == 1
