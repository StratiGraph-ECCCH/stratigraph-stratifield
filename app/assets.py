"""The photos — content-addressed, the same store the rest of the stack uses.

Copied from StratiGraph Server, deliberately and with the same reasoning: a field photo
and a promoted 3D model are the same KIND of thing (bytes somebody will cite),
so they get the same name (their sha256), the same bucket and the same guarantee
— a reference a client can verify without asking anybody.

**A deliberate duplicate.** Like `auth.py`, this is StratiGraph Server's module with the
service name changed. At the third service it becomes a shared package; until
then a change here is a change there, and the environment variables are the same
names on purpose so one configuration serves both.

Original docstring follows.

The asset store: a room provides a graph AND the bytes it refers to.

P4.2 gave a room its graph (the snapshot store). This is the other half: a study
is not only a set of assertions, it is also the models and the photographs those
assertions point at, and a room that could hold the first without the second
would push every collaborator back to sending files by hand.

Same shape as `store.py`, and for the same reason: **the durable truth is not on
the process's disk.** The interface is three methods, the implementation for
tests keeps bytes in memory, and the production one is an S3 object store
(RustFS in the dev stack) — a line of
configuration, not a rewrite.

**Content-addressed.** The reference IS the digest of the content
(`sha256:<hex>`), which buys three things at once and no cleverness:

* **dedup is free** — the same bytes put twice are one object, because they have
  the same name. Two people who promote the same model do not fill a bucket.
* **the reference is verifiable** — a client that fetches an asset can check what
  it got, without asking anybody. That is what makes `checksum` on a ResourceNode
  a fact rather than a hope.
* **immutability** — an object cannot be replaced under a reference that still
  points at it. A citation stays a citation.

The digest travels WITH its algorithm (`sha256:…`), the same rule the shelf's
checksum follows: a bare hex string is unreadable in two years.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import threading
from typing import Any, Dict, Optional, Protocol

from . import s3client


#: What a room's assets are addressed by. The prefix is not decoration: it is
#: what lets a reader know how to verify, and what lets us change algorithm one
#: day without every old reference becoming ambiguous.
DIGEST_PREFIX = "sha256"


def content_id(data: bytes) -> str:
    """`sha256:<hex>` of the bytes — the name an asset has for ever."""
    return f"{DIGEST_PREFIX}:{hashlib.sha256(data).hexdigest()}"


class AssetStore(Protocol):
    """Put bytes, get bytes, ask about bytes. Nothing else lives here."""

    def put(self, data: bytes, media_type: str) -> Dict[str, Any]:
        """Store `data`; return `{ref, sha256, media_type, size, created}`.

        `created` is False when the object was already there — a caller that
        wants to report "dedup" can, and one that does not can ignore it.
        """

    def get(self, ref: str) -> Optional[bytes]:
        """The bytes behind a reference, or None."""

    def head(self, ref: str) -> Optional[Dict[str, Any]]:
        """`{ref, sha256, media_type, size}` without moving the bytes."""


class InMemoryAssetStore:
    """For tests and a single-process laptop run — and it says so.

    Not the deployment target: it dies with the process, which is exactly the
    property the S3 implementation exists to remove.
    """

    def __init__(self) -> None:
        self._blobs: Dict[str, bytes] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, data: bytes, media_type: str) -> Dict[str, Any]:
        ref = content_id(data)
        with self._lock:
            existed = ref in self._blobs
            if not existed:
                self._blobs[ref] = bytes(data)
                self._meta[ref] = {"ref": ref, "sha256": ref.split(":", 1)[1],
                                   "media_type": media_type, "size": len(data)}
        info = dict(self._meta[ref])
        info["created"] = not existed
        return info

    def get(self, ref: str) -> Optional[bytes]:
        with self._lock:
            return self._blobs.get(ref)

    def head(self, ref: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            meta = self._meta.get(ref)
        return dict(meta) if meta else None

    def count(self) -> int:
        """How many distinct objects — the number a dedup test measures."""
        with self._lock:
            return len(self._blobs)


class DirectoryAssetStore:
    """A directory of content-addressed files. Local runs and tests that want to
    see the bytes; explicitly not the answer for replicas."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ref: str) -> pathlib.Path:
        digest = ref.split(":", 1)[-1]
        safe = "".join(c for c in digest if c.isalnum())
        # two levels of fan-out: a directory with a hundred thousand entries in
        # it is a directory nothing can list
        return self.root / safe[:2] / safe[2:4] / safe

    def put(self, data: bytes, media_type: str) -> Dict[str, Any]:
        ref = content_id(data)
        path = self._path(ref)
        existed = path.is_file()
        if not existed:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)                      # a reader never sees half a file
            path.with_suffix(".type").write_text(media_type, encoding="utf-8")
        return {"ref": ref, "sha256": ref.split(":", 1)[1], "media_type": media_type,
                "size": len(data), "created": not existed}

    def get(self, ref: str) -> Optional[bytes]:
        path = self._path(ref)
        return path.read_bytes() if path.is_file() else None

    def head(self, ref: str) -> Optional[Dict[str, Any]]:
        path = self._path(ref)
        if not path.is_file():
            return None
        type_file = path.with_suffix(".type")
        media = type_file.read_text(encoding="utf-8").strip() if type_file.is_file() \
            else "application/octet-stream"
        return {"ref": ref, "sha256": ref.split(":", 1)[1], "media_type": media,
                "size": path.stat().st_size}


class S3AssetStore:
    """The deployment implementation: one bucket, one object per digest.

    **This is the production store**, not a development double. A local FCN and
    an institutional node are the same service with different addresses, so they
    run the same class; `dev-stack/` only puts an S3-compatible store (RustFS)
    next to it on a laptop. The client is `boto3`, built by `s3client.make_client`.

    The object KEY is the digest itself (`<hex>`, without the `sha256:` prefix —
    the prefix belongs to the reference, not to the bucket's namespace). That is
    what buys the three properties the interface promises, and it buys them from
    S3 rather than from code we would have to keep correct:

    * **dedup** — the same bytes have the same key, so a second upload overwrites
      an identical object instead of making a second one;
    * **immutability in practice** — an object cannot change under a reference
      that still points at it, because a different content is a different key;
    * **verifiability** — anybody can hash what they fetched and check.

    The `boto3` client is an OPTIONAL dependency (`pip install stratigraph-chatbot[s3]`).
    A build without it fails **here**, at construction, with a sentence — not at
    the first upload with a stack trace from inside a request.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, secure: bool = True) -> None:
        try:
            self._client = s3client.make_client(endpoint, access_key,
                                                secret_key, secure)
        except ImportError as exc:   # pragma: no cover — depends on the build
            raise RuntimeError(
                "the S3 asset store needs the `boto3` client (an S3 client, "
                "whatever the store behind it), which this build does not "
                "have: install stratigraph-chatbot[s3] (or unset the S3 "
                "environment and use EM_ASSET_DIR)") from exc
        self.bucket = bucket
        self.endpoint = endpoint
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """The bucket must exist before the first upload, and saying WHY it does
        not is the whole value of checking at start-up.

        Created when missing, because a room that cannot store its first asset is
        not a room. If creation fails the process refuses to start with the two
        causes named — a bucket that is not there and credentials that may not be
        allowed to make one look identical from a stack trace.
        """
        ClientError = s3client.client_error()
        try:
            s3client.ensure_bucket(self._client, self.bucket)
        except ClientError as exc:
            raise RuntimeError(
                f"the asset bucket '{self.bucket}' is not usable at "
                f"{self.endpoint}: {s3client.error_code(exc)}. Either it does "
                f"not exist and these credentials may not create it, or they "
                f"may not read it — create the bucket in the object store, or "
                f"give the key access to it") from exc
        except Exception as exc:      # network, DNS, TLS: not an S3 answer at all
            raise RuntimeError(
                f"the object store at {self.endpoint} did not answer: {exc}. "
                f"the field node will not start without the store it is configured "
                f"to write to") from exc

    # ── the interface ────────────────────────────────────────────────────────

    def _key(self, ref: str) -> str:
        return ref.split(":", 1)[-1]

    def put(self, data: bytes, media_type: str) -> Dict[str, Any]:
        ref = content_id(data)
        key = self._key(ref)
        existed = s3client.exists(self._client, self.bucket, key)
        if not existed:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=bytes(data),
                                    ContentLength=len(data),
                                    ContentType=media_type)
        return {"ref": ref, "sha256": key, "media_type": media_type,
                "size": len(data), "created": not existed}

    def get(self, ref: str) -> Optional[bytes]:
        try:
            response = self._client.get_object(Bucket=self.bucket,
                                               Key=self._key(ref))
        except Exception as exc:                   # noqa: BLE001 — re-raised
            if s3client.is_not_found(exc):
                return None
            raise
        return s3client.read_body(response)

    def head(self, ref: str) -> Optional[Dict[str, Any]]:
        """Size and type **without moving the bytes** — a `HEAD`, not a `GET`.

        Worth its own method precisely because an asset can be a hundred
        megabytes: asking "is it there, how big is it" must not cost a download.
        """
        try:
            stat = self._client.head_object(Bucket=self.bucket, Key=self._key(ref))
        except Exception as exc:                   # noqa: BLE001 — re-raised
            if s3client.is_not_found(exc):
                return None
            raise
        return {"ref": ref, "sha256": self._key(ref),
                "media_type": stat.get("ContentType") or "application/octet-stream",
                "size": int(stat.get("ContentLength") or 0)}


#: The S3 settings, under ONE name each — the names StratiGraph Server reads
#: and the dev-stack compose and the Ansible role write, so one configuration
#: serves both services.
_S3_KEYS = {
    "endpoint": "EM_ASSET_S3_ENDPOINT",
    "access_key": "EM_ASSET_S3_ACCESS_KEY",
    "secret_key": "EM_ASSET_S3_SECRET_KEY",
    "bucket": "EM_ASSET_S3_BUCKET",
    "secure": "EM_ASSET_S3_SECURE",
}

def _setting(env: Dict[str, str], field: str) -> str:
    return (env.get(_S3_KEYS[field]) or "").strip()


def _s3_settings(env: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """The S3 configuration, or None when there is none at all.

    Raises when it is HALF there. That is the whole point of this function: a
    deployment that believes it writes to the shared bucket and quietly writes
    to a local directory instead is a data-loss story, and it is silent until it
    is expensive — the same rule `auth.py` applies to a half-configured realm.
    """
    found: Dict[str, Any] = {field: _setting(env, field)
                             for field in ("endpoint", "access_key",
                                           "secret_key", "bucket")}
    given = [field for field, value in found.items() if value]
    if not given:
        return None
    missing = [field for field, value in found.items() if not value]
    if missing:
        raise RuntimeError(
            "the S3 asset store is half configured: "
            f"{', '.join(sorted(given))} given, {', '.join(sorted(missing))} "
            "missing. The field node will not fall back to a local directory the "
            "operator did not ask for — set all four "
            "(EM_ASSET_S3_ENDPOINT / EM_ASSET_S3_ACCESS_KEY / "
            "EM_ASSET_S3_SECRET_KEY / EM_ASSET_S3_BUCKET) or none of them.")
    secure_raw = _setting(env, "secure").lower()
    if secure_raw:
        secure = secure_raw in ("1", "true", "yes", "on")
    else:
        # not stated: believe the endpoint. `http://` means somebody chose plain
        # HTTP (a laptop, a private network); anything else defaults to TLS,
        # because guessing wrong in that direction is the safe way to be wrong.
        secure = not found["endpoint"].startswith("http://")
    found["secure"] = secure
    return found


def asset_store_from_env(environ: Optional[Dict[str, str]] = None) -> AssetStore:
    """The asset store this process should use, chosen by configuration.

    Precedence, and each step is a deliberate answer to "what did the operator
    actually ask for?":

    1. **S3** when its settings are there — the deployment store, durable and
       outside this process (rule #2). Half-configured **refuses to start**.
    2. `EM_ASSET_DIR` — a directory. Honest for one instance, wrong for replicas.
    3. nothing — in-memory, which dies with the process. Loudly wrong for a
       deployment, which is why `/v1/health` reports which one is in use.
    """
    env = environ if environ is not None else os.environ
    s3 = _s3_settings(env)
    if s3:
        return S3AssetStore(endpoint=s3["endpoint"],
                            access_key=s3["access_key"],
                            secret_key=s3["secret_key"],
                            bucket=s3["bucket"], secure=s3["secure"])
    directory = env.get("EM_ASSET_DIR")
    if directory:
        return DirectoryAssetStore(directory)
    return InMemoryAssetStore()


#: This process's asset store — built on FIRST USE, not at import.
#:
#: **A declared divergence from StratiGraph Server's copy of this module**, and
#: the only one. There it is `ASSET_STORE = asset_store_from_env()` at import,
#: and that is right for a relay: a server that cannot reach its bucket is
#: misconfigured and should refuse to start where somebody is watching.
#:
#: It is wrong for a FIELD NODE, and it was measured on 2026-09-27 and again on
#: 2026-09-30: with the object store unplugged the whole service refuses to
#: come up — `RuntimeError: the object store at http://…:9000 did not answer … the
#: field node will not start without the store it is configured to write to`.
#: On a node that switches on inside a tunnel, that line says the assistant does
#: not open. A node with a LARDER (`app/spool.py`) does not need the bucket to
#: work: it needs it to deliver, later, when there is a network.
#:
#: So the construction moved behind PEP 562's module `__getattr__`: importing
#: this module touches nothing, and the first READ of `ASSET_STORE` builds it
#: and raises there if it is misconfigured. A process that never reads it —
#: which is exactly a node running on its larder — never asks the network
#: anything at start-up.
_ASSET_STORE: Optional[AssetStore] = None


def __getattr__(name: str) -> Any:
    if name == "ASSET_STORE":
        global _ASSET_STORE
        if _ASSET_STORE is None:
            _ASSET_STORE = asset_store_from_env()
        return _ASSET_STORE
    raise AttributeError(name)

_HEX = set("0123456789abcdef")


def asset_ref_valid(ref: str) -> bool:
    """Is this a reference this store could ever have minted?

    Checked before touching the store: a reference comes from a URL, and a
    directory-backed implementation that took an arbitrary string would be one
    `../` away from reading somebody else's file. Content-addressing makes the
    check trivial — a valid reference has exactly one shape.
    """
    prefix, _, digest = str(ref).partition(":")
    return (prefix == DIGEST_PREFIX and len(digest) == 64
            and all(c in _HEX for c in digest.lower()))


def describe(store: AssetStore) -> str:
    if isinstance(store, S3AssetStore):
        # the bucket and the host, never the key: `/v1/health` is public enough
        # that a credential printed there is a credential in a screenshot
        return f"s3 ({store.endpoint}, bucket {store.bucket})"
    return {
        "InMemoryAssetStore": "memory (not durable — dies with the process)",
        "DirectoryAssetStore": "directory (local only — not for replicas)",
    }.get(type(store).__name__, type(store).__name__)
