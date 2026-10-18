"""Lo store S3: i nomi che si leggono, quelli che si rifiutano, e il bucket vero.

Due metà, e la seconda si salta da sola.

**1 · La configurazione, senza rete.** Si leggono SOLO `EM_ASSET_S3_*` — gli
stessi nomi di StratiGraph Server, perché una configurazione serve entrambi. I
nomi di prima, quelli del vecchio fornitore, non si leggono più, e non si
ignorano in silenzio: un nome vecchio senza il suo nuovo è un rifiuto all'avvio
che dice cosa rinominare.
Altrimenti un nodo crederebbe di consegnare al bucket e terrebbe le foto altrove.

**2 · Il bucket vero.** `S3AssetStore` e la dispensa che gli consegna, contro un
server S3 vero: la RustFS del dev stack, o qualunque endpoint compatibile.

    EM_TEST_S3_ENDPOINT=http://host:9000 \\
    EM_TEST_S3_ACCESS_KEY=… EM_TEST_S3_SECRET_KEY=… pytest tests/test_lo_store_s3.py

Senza quelle variabili le chiavi si leggono dal `.env.dev` del dev stack
(`../stratigraph-server/dev-stack/.env.dev`, `RUSTFS_ACCESS_KEY` /
`RUSTFS_SECRET_KEY`). **Nessuna chiave di default**: un test che ripiega sulla
password nota di un fornitore misura uno store che nessuno dovrebbe avere. Senza
chiavi, senza server o senza `boto3` questi test si SALTANO, col motivo: un
salto vuol dire «non misurato», mai «passato». Ogni test lavora in un bucket
usa-e-getta suo, tolto alla fine: il bucket condiviso non si tocca.
"""

from __future__ import annotations

import os
import pathlib
import socket
import sys
import uuid
from urllib.parse import urlsplit

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from app.assets import (S3AssetStore, asset_store_from_env,  # noqa: E402
                        content_id, describe)
from app.spool import Spool, shared_name, spool_from_env    # noqa: E402

_PIENO = {"EM_ASSET_S3_ENDPOINT": "http://rustfs:9000",
          "EM_ASSET_S3_ACCESS_KEY": "x",
          "EM_ASSET_S3_SECRET_KEY": "y",
          "EM_ASSET_S3_BUCKET": "em-assets"}


# ═══ 1 · la configurazione ═══════════════════════════════════════════════════

def _costruzione_finta(monkeypatch):
    fatto = {}

    def finto(self, endpoint, access_key, secret_key, bucket, secure=True):
        fatto.update(endpoint=endpoint, bucket=bucket, secure=secure)
        self.endpoint, self.bucket = endpoint, bucket

    monkeypatch.setattr(S3AssetStore, "__init__", finto)
    return fatto


def test_i_nomi_nuovi_scelgono_lo_store_S3(monkeypatch):
    fatto = _costruzione_finta(monkeypatch)
    store = asset_store_from_env(dict(_PIENO))
    assert isinstance(store, S3AssetStore)
    assert fatto == {"endpoint": "http://rustfs:9000", "bucket": "em-assets",
                     "secure": False}, "http:// vuol dire che qualcuno ha scelto il chiaro"
    assert describe(store) == "s3 (http://rustfs:9000, bucket em-assets)"


def test_SECURE_detto_vince_sullo_schema(monkeypatch):
    fatto = _costruzione_finta(monkeypatch)
    asset_store_from_env(dict(_PIENO, EM_ASSET_S3_ENDPOINT="rustfs:9000",
                              EM_ASSET_S3_SECURE="false"))
    assert fatto["secure"] is False


def test_mezza_configurazione_si_rifiuta():
    with pytest.raises(RuntimeError, match="half configured"):
        asset_store_from_env({"EM_ASSET_S3_ENDPOINT": "http://rustfs:9000"})


def test_health_dice_s3_senza_chiamarlo(tmp_path):
    assert shared_name(dict(_PIENO)) == (
        "s3 (http://rustfs:9000, bucket em-assets) — non contattato all'avvio")


# ═══ 2 · il bucket vero ══════════════════════════════════════════════════════

def _env_dev() -> dict:
    out = {}
    try:
        testo = (_REPO.parent / "stratigraph-server" / "dev-stack"
                 / ".env.dev").read_text(encoding="utf-8")
    except OSError:
        return out
    for riga in testo.splitlines():
        chiave, sep, valore = riga.partition("=")
        if sep and not chiave.lstrip().startswith("#"):
            out[chiave.strip()] = valore.strip()
    return out


_DEV = _env_dev()
ENDPOINT = (os.environ.get("EM_TEST_S3_ENDPOINT")
            or f"http://localhost:{_DEV.get('RUSTFS_API_PORT') or '9000'}")
ACCESS_KEY = (os.environ.get("EM_TEST_S3_ACCESS_KEY")
              or _DEV.get("RUSTFS_ACCESS_KEY") or "")
SECRET_KEY = (os.environ.get("EM_TEST_S3_SECRET_KEY")
              or _DEV.get("RUSTFS_SECRET_KEY") or "")
SECURE = ENDPOINT.startswith("https://")


def _raggiungibile() -> bool:
    parti = urlsplit(ENDPOINT if "://" in ENDPOINT else f"http://{ENDPOINT}")
    try:
        with socket.create_connection(
                (parti.hostname, parti.port or (443 if SECURE else 80)),
                timeout=1.5):
            return True
    except OSError:
        return False


@pytest.fixture()
def store():
    """Uno store su un bucket usa-e-getta, svuotato e tolto alla fine."""
    pytest.importorskip("boto3", reason="il client `boto3` non è installato")
    if not (ACCESS_KEY and SECRET_KEY):
        pytest.skip("nessuna chiave S3: né EM_TEST_S3_ACCESS_KEY / _SECRET_KEY "
                    "né RUSTFS_* nel .env.dev del dev stack — nessun default, "
                    "apposta")
    if not _raggiungibile():
        pytest.skip(f"a {ENDPOINT} non risponde nessuno — accendi l'object "
                    f"store del dev stack per misurarlo")
    from app import s3client
    bucket = f"em-test-chatbot-{uuid.uuid4().hex[:10]}"
    store = S3AssetStore(endpoint=ENDPOINT, access_key=ACCESS_KEY,
                         secret_key=SECRET_KEY, bucket=bucket, secure=SECURE)
    try:
        yield store
    finally:
        client = store._client
        for obj in list(s3client.iter_objects(client, bucket)):
            client.delete_object(Bucket=bucket, Key=obj["key"])
        client.delete_bucket(Bucket=bucket)


FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + bytes(4096) + b"\xff\xd9"


def test_put_get_head_sul_bucket_vero(store):
    esito = store.put(FOTO, "image/jpeg")
    assert esito["ref"] == content_id(FOTO) and esito["created"] is True
    assert store.put(FOTO, "image/jpeg")["created"] is False, "dedup"
    assert store.get(esito["ref"]) == FOTO
    testa = store.head(esito["ref"])
    assert testa == {"ref": esito["ref"], "sha256": esito["sha256"],
                     "media_type": "image/jpeg", "size": len(FOTO)}


def test_quello_che_non_ce_e_None_non_un_errore(store):
    assente = "sha256:" + "0" * 64
    assert store.get(assente) is None
    assert store.head(assente) is None


def test_la_dispensa_consegna_al_bucket_vero(store, tmp_path):
    dispensa = Spool(tmp_path / "dispensa", remote=store)
    ref = dispensa.put(FOTO, "image/jpeg")["ref"]
    assert dispensa.waiting() == [ref]
    esito = dispensa.deliver()
    assert esito["delivered"] == 1 and dispensa.waiting() == []
    assert store.head(ref)["size"] == len(FOTO)
    assert store.get(ref) == FOTO


def test_la_dispensa_aspetta_se_il_bucket_non_risponde_e_poi_consegna(store, tmp_path):
    """La semantica del ritentare: uno store che non risponde ferma la fila e non
    perde niente; al rientro successivo la stessa foto sale."""
    giu = S3AssetStore.__new__(S3AssetStore)
    from app import s3client
    giu._client = s3client.make_client("http://127.0.0.1:9", "x", "y", False)
    giu.bucket, giu.endpoint = store.bucket, "http://127.0.0.1:9"
    dispensa = Spool(tmp_path / "dispensa", remote=giu)
    ref = dispensa.put(FOTO, "image/jpeg")["ref"]
    esito = dispensa.deliver()
    assert esito["delivered"] == 0 and dispensa.waiting() == [ref]
    assert dispensa.get(ref) == FOTO, "la copia locale resta"
    dispensa._remote = store                       # la rete è tornata
    assert dispensa.deliver()["delivered"] == 1
    assert store.get(ref) == FOTO and dispensa.waiting() == []


def test_chiavi_sbagliate_si_rifiutano_alla_costruzione():
    pytest.importorskip("boto3", reason="il client `boto3` non è installato")
    if not _raggiungibile():
        pytest.skip(f"a {ENDPOINT} non risponde nessuno")
    with pytest.raises(RuntimeError, match="not usable|did not answer"):
        S3AssetStore(endpoint=ENDPOINT, access_key="non-una-chiave",
                     secret_key="non-un-segreto",
                     bucket=f"em-test-chatbot-{uuid.uuid4().hex[:10]}",
                     secure=SECURE)
