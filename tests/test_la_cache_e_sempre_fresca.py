"""Il service worker non serve mai un file vecchio (2026-10-24, §A).

Referto del 22, §5: sulla porta :8024 il browser ha servito il `shell.css` di
una notte prima. Il nome della cache cambiava col digest, ed era giusto; ma
`install` riempiva la cache con `c.add(f)`, che passa dalla CACHE HTTP del
browser. Un file cambiato sul nodo poteva entrare VECCHIO nella cache nuova: il
nome giusto, il contenuto di ieri.

Due argini, e ognuno ha la sua prova:

* il nodo serve la shell con `Cache-Control: no-cache` e un ETag di contenuto, e
  risponde 304 a chi ha già quei byte (§1, senza browser);
* il worker scarica con `cache: "reload"` (§2, nel browser: shell servita, file
  cambiato sul disco, worker nuovo installato → nella cache c'è il file nuovo).
"""

from __future__ import annotations

import pathlib
import shutil
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


# ── 1 · il nodo obbliga a rivalidare, e la rivalidazione costa un 304 ────────

@pytest.mark.parametrize("path", ["/", "/sw.js", "/shell.css", "/widgets.js",
                                  "/brand/stratigraph-theme.css"])
def test_every_shell_file_says_ask_before_using(path):
    answer = _client().get(path)
    assert answer.status_code == 200, (path, answer.status_code)
    assert answer.headers["cache-control"] == "no-cache", path
    assert answer.headers.get("etag"), path


@pytest.mark.parametrize("path", ["/", "/sw.js", "/shell.css",
                                  "/brand/stratigraph-theme.css"])
def test_asking_again_with_the_etag_costs_a_304_without_a_body(path):
    client = _client()
    first = client.get(path)
    again = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304, (path, again.status_code)
    assert again.content == b""
    assert again.headers["cache-control"] == "no-cache"


def test_the_etag_follows_the_bytes_and_not_the_clock(tmp_path, monkeypatch):
    """Un ETag di CONTENUTO: lo stesso file riscritto uguale resta lo stesso,
    un byte cambiato lo cambia — anche a parità di lunghezza."""
    import app.main as main

    copy = tmp_path / "web"
    shutil.copytree(WEB, copy)
    monkeypatch.setattr(main, "_WEB", copy)
    client = _client()
    css = copy / "shell.css"

    before = client.get("/shell.css").headers["etag"]
    css.write_bytes(css.read_bytes())                 # riscritto, identico
    assert client.get("/shell.css").headers["etag"] == before
    body = css.read_bytes()
    css.write_bytes(body[:-1] + (b"x" if body[-1:] != b"x" else b"y"))
    after = client.get("/shell.css")
    assert after.headers["etag"] != before
    # e chi aveva il vecchio non riceve un 304: riceve il file nuovo
    stale = client.get("/shell.css", headers={"If-None-Match": before})
    assert stale.status_code == 200 and stale.content == css.read_bytes()


def test_the_worker_downloads_past_the_http_cache():
    source = (WEB / "sw.js").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("//"))
    assert 'new Request(f, { cache: "reload" })' in code
    assert "c.add(f)" not in code


# ── 2 · nel browser: file cambiato sul disco → worker nuovo → cache nuova ────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def served_copy(tmp_path, monkeypatch):
    """L'app vera, in un uvicorn vero, sopra una COPIA di `web/`.

    `copytree` conserva le date dei file: il `Last-Modified` di un file vecchio
    di giorni è proprio ciò che, senza `no-cache`, dà al browser una freschezza
    euristica di ore — il caso della :8024.
    """
    uvicorn = pytest.importorskip("uvicorn")
    import app.main as main

    copy = tmp_path / "web"
    shutil.copytree(WEB, copy)
    monkeypatch.setattr(main, "_WEB", copy)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "uvicorn non è partito"
    yield f"http://127.0.0.1:{port}/", copy
    server.should_exit = True
    thread.join(timeout=5)


def _chrome(playwright):
    try:
        return playwright.chromium.launch(channel="chrome", headless=True)
    except Exception:
        try:
            return playwright.chromium.launch(headless=True)
        except Exception as problem:                     # pragma: no cover
            pytest.skip(f"nessun Chromium utilizzabile: {problem}")


def _until(page, predicate, arg=None, timeout=10.0):
    """Ripete `predicate` (asincrono) finché è vero.

    Non `wait_for_function`: misurato qui, con un predicato che restituisce una
    Promise tornava subito — la Promise è «vera» — e il test leggeva mentre la
    cache vecchia c'era ancora, cioè misurava la corsa e non il worker.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if page.evaluate(predicate, arg):
            return
        time.sleep(0.05)
    raise AssertionError(f"mai vero in {timeout}s: {predicate[:60]}")


#: Il worker ha FINITO: attivo, nessuno in installazione, una cache sola. Non
#: basta «c'è una cache»: `caches.open` la crea vuota all'inizio di `install`,
#: e leggerla lì è leggere a metà.
_SETTLED = """async () => {
  const r = await navigator.serviceWorker.getRegistration();
  return !!(r && r.active && r.active.state === "activated" && !r.installing
            && !r.waiting && (await caches.keys()).length === 1);
}"""

_CACHED = """async (name) => {
  const keys = await caches.keys();
  const hit = await caches.match(new URL(name, location.href).href);
  return { keys, text: hit ? await hit.text() : null };
}"""


def _old_node(request, body, media_type):
    """Il nodo DI PRIMA, rifatto apposta: `FileResponse` mandava un
    `Last-Modified` (qui di tre giorni fa) e nessun `Cache-Control`, niente 304.
    È la forma che dà al browser una freschezza euristica — il 10 % dell'età
    del file — e il caso della :8024."""
    from email.utils import formatdate

    from fastapi.responses import Response
    return Response(content=body, media_type=media_type, headers={
        "Last-Modified": formatdate(time.time() - 3 * 86400, usegmt=True)})


def _one_round(base, copy):
    """Shell servita e in cache; `shell.css` cambiato sul disco; il worker
    nuovo installato. Restituisce le due letture e il segno scritto."""
    sync_api = pytest.importorskip("playwright.sync_api")
    marker = "/* cambiato sul disco " + str(time.time_ns()) + " */"
    with sync_api.sync_playwright() as p:
        browser = _chrome(p)
        page = browser.new_context().new_page()
        page.goto(base)
        _until(page, _SETTLED)
        first = page.evaluate(_CACHED, "shell.css")
        assert first["text"] == (copy / "shell.css").read_text("utf-8")
        # la cache HTTP del browser ha anche lei il file: lo ha chiesto il <link>
        page.reload()

        (copy / "shell.css").write_text(
            (copy / "shell.css").read_text("utf-8") + "\n" + marker + "\n",
            encoding="utf-8")
        page.evaluate("navigator.serviceWorker.getRegistration()"
                      ".then(r => r.update())")
        _until(page, "(old) => caches.keys()"
                     ".then(k => k.length === 1 && k[0] !== old)",
               first["keys"][0])
        _until(page, _SETTLED)
        second = page.evaluate(_CACHED, "shell.css")
        browser.close()
    assert second["keys"] != first["keys"], "il nome della cache non è cambiato"
    assert second["text"] is not None, "shell.css non è nella cache nuova"
    return first, second, marker


def test_a_file_changed_on_disk_enters_the_new_cache_new(served_copy):
    """IL CANCELLO, con la shell com'è oggi."""
    base, copy = served_copy
    _first, second, marker = _one_round(base, copy)
    assert marker in second["text"], (
        "nella cache nuova c'è il shell.css VECCHIO: è entrato dalla cache HTTP")
    assert second["text"] == (copy / "shell.css").read_text("utf-8")


@pytest.mark.parametrize("worker_reloads, node_revalidates, fresh", [
    (False, False, False),      # la :8024: il guasto, RIPRODOTTO
    (True, False, True),        # basta il worker
    (False, True, True),        # basta il nodo
])
def test_each_safeguard_alone_suffices_and_without_both_yesterday_gets_in(
        served_copy, monkeypatch, worker_reloads, node_revalidates, fresh):
    """Il gruppo di controllo, perché un cancello che non si è mai visto chiuso
    non prova niente. Tolti TUTTI E DUE gli argini — `c.add(f)` e il nodo di
    prima — il `shell.css` vecchio entra nella cache nuova: il test vede il
    guasto. Con uno solo dei due, no: sono due argini, e ognuno regge da sé."""
    import app.main as main

    base, copy = served_copy
    if not worker_reloads:
        worker = copy / "sw.js"
        source = worker.read_text("utf-8")
        assert 'c.add(new Request(f, { cache: "reload" }))' in source
        worker.write_text(source.replace(
            'c.add(new Request(f, { cache: "reload" }))', "c.add(f)"), "utf-8")
    if not node_revalidates:
        monkeypatch.setattr(main, "_revalidated", _old_node)
    _first, second, marker = _one_round(base, copy)
    assert (marker in second["text"]) is fresh, (
        worker_reloads, node_revalidates, second["text"][-80:])
