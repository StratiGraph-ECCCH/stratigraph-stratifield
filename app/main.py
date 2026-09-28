"""stratigraph-chatbot — the field assistant, as a service.

*An orchestrator.* Voice or text comes in, an intent comes out, a tool acts, and
what changes is a **DTC-attributed write on the shared graph**. It does not
rebuild the pieces that exist: ARC's ATRIUM captures voice, Whisper transcribes
on the Field Computing Node, PyArchInit and iDAI.field record contexts, Tropy
and the object store hold media. What was missing — and what this is — is the
**convergence and orchestration layer** (design note §1).

The centre of gravity is `contract.py`, not this file. Everything here is
plumbing over it: a route that takes audio or text, the engine that turns it
into words, the parser that turns words into an intent, the registry that turns
an intent into an act. Read that file first; this one only wires.

**Three rules, inherited and not re-litigated:**

1. **the domain lives in s3Dgraphy.** What a stratigraphic unit is, what a
   resource attached to one means — the library decides, and the tools ask it;
2. **the author is the token's.** Never a field the client filled in. A record
   without a verifiable hand behind it is one nobody can defend;
3. **offline-first.** The node is the host. Nothing here calls out to a cloud,
   and everything works with no network beyond the trench — the room adds reach,
   it is not a precondition.

`/health` says what this node can actually do: which tools are registered, which
speech engine is listening, whether an intent model is loaded, where writes are
going. On a dig, "is what I just said reaching the others?" is the first
question anybody asks, and it deserves an answer that is one GET away.
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import pathlib
import time

from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Body, FastAPI, File, Form, HTTPException,
                     Request, UploadFile)
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from . import assets, handoff
from .assets import describe as asset_describe
from .bridge import bridge_for, queues_beside
from .spool import describe as larder_describe
from .spool import shared_name, spool_from_env
from .auth import _TOKEN_SUFFIX as TOKEN_SUFFIX
from .auth import AuthDependency, authenticator, principal_orcid
from .contract import GraphDelta, ToolResult, invoke, stable_id
from . import conversazione
from .intent import COMMAND_LANGUAGE, understand
from .intent import describe as intent_describe
from .intent import intent_model_from_env
from .speech import describe as stt_describe
from .speech import stt_from_env
from .tools import build_registry
from .scrivani import NotTrusted, Scrivani
from .writer import AccessRefused, LocalWriter, RoomRefused, RoomWriter
from .writer import describe as writer_describe
from .writer import writer_from_env

try:
    import s3dgraphy  # noqa: F401  — the domain; a clear failure beats a mystery
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "stratigraph-chatbot needs s3dgraphy importable: pip install s3dgraphy "
        f"(or -e ../s3Dgraphy). {exc}") from exc

# THE VERSION, and the convention is not this service's to invent.
#
#     <major EM>.<minor EM>.<the tool's own iteration>
#
# The first two segments declare which Extended Matrix language this build
# speaks; the third is its own history. **A tool cannot be more stable than the
# language it speaks**: while s3Dgraphy is `1.6.0.devN`, so is this.
#
# Measured, not assumed: s3Dgraphy is `1.6.0.dev17`, and EM-blender-tools
# already carries `1.6.0-dev.8` beside an s3dgraphy wheel of `1.6.0.dev16`, so
# the convention existed and was adopted half-way. `0.1.0.dev0` meant this
# service had never been versioned at all.
#
# The third segment is the COORDINATE OF A TEST REPORT: «on dev2 this no longer
# happens» is information, «on the latest version» is not.
__version__ = "1.6.0.dev1"

log = logging.getLogger("stratigraph.chatbot")


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Sedersi all'avvio, e alzarsi quando il servizio finisce.

    **All'avvio e non alla prima consegna**, ed è tutta la differenza fra un
    seduto e un corrispondente: se il posto si prendesse alla prima operazione,
    un assistente aperto e fermo — che è la maggior parte del tempo di un
    telefono in cantiere — non sarebbe nella stanza, e nessuno lì dentro
    saprebbe che c'è.

    **Non può impedire l'avvio.** La stanza può essere giù, il token scaduto, il
    telefono senza campo: sono i casi normali, non guasti di configurazione. Ci
    si siede alla prima occasione utile (`_seated`), e nel frattempo il servizio
    lavora sul container locale — che è il ponte già costruito.
    """
    sit = getattr(WRITER, "_seated", None)
    if sit is not None:
        try:
            sit()
            log.info("seduti nella stanza")
        except Exception as exc:      # noqa: BLE001
            log.info("non seduti (per ora): %s", exc)
        # …e si RESTA seduti: il sorvegliante riprende il posto quando cade,
        # che è quello che succede a ogni riavvio del relay e a ogni buco di
        # rete. Senza, «seduto» durerebbe fino al primo singhiozzo.
        seat = getattr(getattr(WRITER, "session", None), "keep_seated", None)
        if seat is not None:
            seat()
    yield
    leave = getattr(WRITER, "close", None)
    if leave is not None:
        try:
            leave()
        except Exception:             # noqa: BLE001 — alzarsi non deve fallire
            pass
    # …e si alzano anche le persone: ognuna sedeva a nome suo
    SCRIVANI.close_all()


app = FastAPI(
    lifespan=_lifespan,
    title="stratigraph-chatbot",
    version=__version__,
    summary="The StratiGraph field assistant: voice → intent → tool → a "
            "DTC-attributed write on the shared graph.",
    description=__doc__,
)

#: Built at import, so a misconfiguration fails at STARTUP rather than in a
#: trench. The order matters: the writer may refuse (a room with no token).
#: LA DISPENSA, costruita UNA VOLTA e data a tutti e due — lo scrivano, che
#: decide quando i byte salgono, e i tool, che ce li mettono. Due istanze sulla
#: stessa directory sarebbero due processi con la stessa coda: il difetto che il
#: `flock` di `bridge.py` esiste per chiudere, riaperto un metro più in là.
#:
#: E costruita QUI e non dentro `writer_from_env` per una ragione misurata
#: stanotte: senza stanza lo scrivano è un `LocalWriter`, che non ha una
#: dispensa — e un nodo senza stanza è esattamente il nodo di campo, cioè
#: quello che ne ha più bisogno. La prima versione la prendeva dal writer e
#: `/health` diceva «nessuna» con la variabile impostata.
LARDER = spool_from_env()

#: IL CONTAINER LOCALE, costruito qui e passato: dal 2 ottobre lo scrivano si
#: può sostituire a caldo (`POST /v1/room`), e ogni scrivano nuovo deve ricevere
#: **questo** container e non costruirsene un secondo sullo stesso file.
LOCAL = LocalWriter(os.environ.get("EM_CHATBOT_CONTAINER")
                    or "data/scavo.em.json",
                    study=os.environ.get("EM_CHATBOT_STUDY") or "Scavo")
WRITER = writer_from_env(spool=LARDER, local=LOCAL)

STT = stt_from_env()

#: LO STORE CHE I TOOL VEDONO. Se questo nodo ha una dispensa è quella, e non
#: MinIO: `Spool` implementa lo stesso `AssetStore`, quindi nessun tool sa la
#: differenza — cambia solo QUANDO si parla con la rete. Un nodo di scrivania
#: senza dispensa continua a scrivere diritto nel bucket, che è la cosa giusta
#: quando la rete è sotto il tavolo.
#: E `assets.ASSET_STORE` si LEGGE solo se non c'è una dispensa: leggerlo è
#: quello che lo costruisce, e costruirlo è un giro di rete. Un nodo di campo
#: con la dispensa non deve chiedere niente a nessuno per accendersi.
STORE = LARDER if LARDER is not None else assets.ASSET_STORE
REGISTRY = build_registry(WRITER, STORE)

#: The intent model is OPTIONAL and absent by default. The rules answer the
#: field card's commands, which is what the MVP needs; a model is used on the
#: node when the node names one, and `/health` says WHICH.
#:
#: Built at import for the reason `WRITER` and `STT` are: a HALF configuration
#: must refuse where somebody is watching, not on the first dictation in a
#: trench. Until 2026-09-02 this was a bare `None` and nothing could set it —
#: `/health` declared a capability that had no switch.
#:
#: The order is untouched and stays untouched: **rules first, model second.** The
#: field vocabulary is closed and designed on purpose; asking a model to
#: interpret a sentence that matches it exactly would be slower, less
#: predictable, and occasionally wrong. And the model still chooses only among
#: the tools the registry declares (`llm_parse`).
INTENT_MODEL = intent_model_from_env()

v1 = APIRouter(prefix="/v1", dependencies=[AuthDependency])
public = APIRouter()


# ── health ────────────────────────────────────────────────────────────────────

class Health(BaseModel):
    ok: bool = True
    service: str = "stratigraph-chatbot"
    version: str
    #: WHICH graph language this process is actually running. The other two
    #: services of the stack publish it already; this one did not, and that is
    #: how three images installing three different specs went unnoticed. They
    #: share em.json files and one vocabulary — a version that differs is a study
    #: the catalogue indexes differently from how the server wrote it.
    s3dgraphy: str = ""
    auth: str = "dev-no-auth"
    #: WHERE what you say ends up. `local container` means the others will see
    #: it at the next sync, not now — and an operator has to be able to tell.
    writes_to: str = "local container"
    asset_store: str = "memory"
    #: LA DISPENSA: i byte che non hanno ancora raggiunto lo store condiviso.
    #: Detta anche quando è vuota, perché «nessuna dispensa» è una
    #: configurazione — su un nodo di campo vuol dire che una foto scattata
    #: senza rete si perde — e non un dettaglio.
    larder: str = "nessuna (i byte vanno diritti allo store: senza rete si perdono)"
    #: SE IL NODO È SEDUTO NELLA STANZA, adesso: una sessione tenuta di
    #: `app/session.py` — quella del nodo o quella di una persona (dal 25
    #: ottobre ogni persona ha la sua) — letta dal suo `seated` e non dedotta
    #: da `writes_to`. È una proprietà della RETE fra il nodo e la stanza.
    #: È ciò da cui il browser ricava la POSTURA (spec del Foglio §4 bis):
    #: seduto = scrivania, nessuna sessione = in campo, dove il dispositivo
    #: consegna per REST e se ne va. Un booleano e non una frase, perché una
    #: frase si legge male il giorno che cambia forma.
    seated: bool = False
    #: LE CODE CHE QUESTO NODO HA SUL DISCO, una per stanza, con quanto c'è
    #: dentro. Da quando le code sono per stanza esiste un modo nuovo di perdere
    #: del lavoro — ripuntare via da una stanza e dimenticarsene — e l'unica
    #: difesa è che si veda.
    queues: List[Dict[str, Any]] = Field(default_factory=list)
    #: IL SERVER CHE QUESTO NODO USEREBBE, se chi punta dice solo una stanza.
    #: Un indirizzo non è un permesso — è la stessa cosa che il link di consegna
    #: porta in chiaro — e senza, la pagina dovrebbe chiedere di scrivere due
    #: campi per fare una cosa sola.
    server_hint: str = ""
    speech: str = "passthrough"
    #: Kept, and DERIVED from the line below: a probe that only ever asked
    #: "is there one?" must not break the day the answer got longer.
    intent_model: bool = False
    #: WHICH engine is interpreting, and which model — or which variable would
    #: name one. A boolean was not enough (design note §4): that string is
    #: PROVENANCE, and a datum without the name of the engine that produced it
    #: is a datum nobody can argue about later. Same shape as `speech` above.
    intent: str = "rules only"
    #: The node's AI capabilities, in the shape design note §4 asks for: a name,
    #: a state, the engine when there is one, and what would configure it when
    #: there is not. This is what `/v1/node`'s public reduction forwards, so a
    #: surface never keeps a list of its own.
    capabilities: List["Capability"] = Field(default_factory=list)
    #: The language this node's command vocabulary is written in. A surface
    #: localised into another language still has to show ITS examples, or it
    #: offers a phrase the node would refuse.
    command_language: str = COMMAND_LANGUAGE
    #: Whether a dictation can be accepted AT ALL. False when no identity
    #: provider is configured: the tools would refuse the write anyway ("Non
    #: posso scrivere senza sapere chi sei"), so a field page that offered an
    #: input box would be collecting words it could never attribute.
    accepts_dictation: bool = True
    #: …and when it cannot, WHAT IS IN THE WAY, by name. Empty otherwise.
    missing: List[str] = Field(default_factory=list)
    #: The registry IS the documentation: what this node can do, by name.
    tools: List[Dict[str, Any]] = Field(default_factory=list)


class Capability(BaseModel):
    """One AI capability of this node, as design note §4 asks it to be said."""

    name: str
    #: `absent` — this node does not do it · `configured` — it names an engine
    #: and the configuration is coherent · `active` — it is loaded here.
    #:
    #: There is no `active` for `intent`, and that is honest rather than lazy:
    #: knowing it would mean reaching the model's endpoint, and a health probe
    #: that makes a network call at import is a health probe that can hang. A
    #: model that does not answer surfaces on FIRST USE, with a line in the log
    #: and an «I did not understand» — the rules having already had their turn.
    state: str = "absent"
    #: which engine and which model. Never empty: when nothing is configured it
    #: says so, because "" would read as a missing field.
    engine: str = ""
    #: the variable(s) that would configure it, when it is absent
    missing: List[str] = Field(default_factory=list)


def _capabilities() -> List[Capability]:
    """What this node can do, and what would make it able.

    ONE builder, so `/health` and — through the room server's probe — the public
    reduction in `/v1/node` cannot tell two different stories. A probe and a gate
    that disagree send two people looking in two places.
    """
    from .intent import INTENT_ENDPOINT_VAR, INTENT_MODEL_VAR

    speech_engine = stt_describe(STT)
    on_node = not speech_engine.startswith("passthrough")
    capabilities = [
        Capability(
            name="speech",
            state="active" if on_node else "absent",
            engine=speech_engine,
            missing=[] if on_node else ["EM_CHATBOT_WHISPER_MODEL"],
        ),
        Capability(
            name="intent",
            state="configured" if INTENT_MODEL is not None else "absent",
            engine=intent_describe(INTENT_MODEL),
            missing=([] if INTENT_MODEL is not None
                     else [INTENT_MODEL_VAR, INTENT_ENDPOINT_VAR]),
        ),
    ]
    # …and the one configuration that can send an excavation's words off the
    # site is SAID here as well as logged at startup. Design note §5: silent is
    # what makes it an incident.
    local = getattr(INTENT_MODEL, "local", True)
    if INTENT_MODEL is not None and not local:
        capabilities[-1].missing.append(
            "WARNING: the intent endpoint is NOT local — every dictated "
            "sentence leaves this node")
    return capabilities


def _identity_gaps() -> List[str]:
    """What stands between this node and an ATTRIBUTABLE dictation, by name.

    The habit this follows is the one `auth.py` set when it refuses to start on
    a half-configured realm: say what is not there, rather than behave oddly.
    A field page that meets a bare gate cannot tell «sign in» from «somebody
    forgot a variable», and the person meeting it is standing in a trench.

    Empty when this node enforces tokens — there is then nothing in the way.
    """
    settings = authenticator.settings
    if getattr(settings, "enforcing", False):
        return []
    gaps: List[str] = []
    if not getattr(settings, "issuer", ""):
        gaps.append("OIDC_ISSUER (or TOKEN_ENDPOINT)")
    if not getattr(settings, "audience", ""):
        gaps.append("OIDC_AUDIENCE (or CLIENT_ID_em)")
    if getattr(settings, "anon_declared", False):
        # Not a missing variable — a declared one, and it is still in the way:
        # an anonymous dictation has nobody to attribute.
        gaps.append("EM_CHATBOT_ALLOW_ANON is on, and an anonymous dictation "
                    "has no author")
    return gaps


def _s3dgraphy_version() -> str:
    try:
        import s3dgraphy

        return str(getattr(s3dgraphy, "__version__", "") or "")
    except Exception:                                  # noqa: BLE001
        return ""


def _health() -> Health:
    return Health(
        version=__version__,
        s3dgraphy=_s3dgraphy_version(),
        auth=authenticator.settings.describe(),
        writes_to=writer_describe(WRITER),
        # Con la dispensa, lo store condiviso si NOMINA dalla configurazione e
        # non si costruisce: costruirlo è un giro di rete, e una spia che si
        # blocca quando la rete manca è la spia che si spegne quando serve.
        asset_store=(asset_describe(assets.ASSET_STORE) if LARDER is None
                     else shared_name()),
        larder=larder_describe(LARDER),
        seated=(bool(getattr(getattr(WRITER, "session", None), "seated", False))
                or SCRIVANI.seated()),
        queues=queues_beside(LOCAL.path),
        server_hint=(getattr(WRITER, "base_url", "")
                     or (os.environ.get("EM_SERVER_URL") or "").strip()),
        speech=stt_describe(STT),
        intent_model=INTENT_MODEL is not None,
        intent=intent_describe(INTENT_MODEL),
        capabilities=_capabilities(),
        accepts_dictation=bool(authenticator.settings.enforcing),
        missing=_identity_gaps(),
        tools=[{"name": d.name, "intents": d.intents, "writes": d.writes,
                "service": d.service} for d in REGISTRY.list()],
    )


@public.get("/health", response_model=Health, tags=["meta"])
def health() -> Health:
    return _health()


@public.get("/v1/health", response_model=Health, tags=["meta"])
def health_v1() -> Health:
    """Same answer as `/health`. A probe belongs to the infrastructure and must
    not have to be edited the day the API is versioned."""
    return _health()


# ── how a browser signs in ────────────────────────────────────────────────────

class AuthConfig(BaseModel):
    """What a BROWSER needs to sign in against this node's realm.

    Public by construction — an issuer and a client id are not secrets, and the
    one thing that would be (a client secret) does not exist for this client: the
    field page is a PUBLIC OIDC client and uses PKCE instead.

    **Why this node answers it rather than the room server.** StratiGraph Server
    exposes the same document, and behind Caddy it is one fetch away at
    `/em/v1/auth-config`. Reaching for it would mean this page knowing that the
    room server lives under `/em` — a second deployment fact, true today,
    invisible when it stops being true, and wrong in the development loop where
    the page is served bare at `:8020`. The page derives everything from its own
    URL (`new URL(".", location.href)`); this route is what makes that enough.
    The SHAPE is deliberately the room server's, field for field, so a client
    that speaks to one speaks to the other.
    """

    #: the realm, e.g. `https://sso.example.org/realms/em`. Empty when this node
    #: runs in dev-no-auth, and the page then SAYS so instead of offering a
    #: sign-in that cannot work.
    issuer: str = ""
    #: the PUBLIC client the browser authenticates as
    client_id: str = ""
    #: where the IdP sends the browser back. Advertised so a deployment can be
    #: read from one place, but the page computes its OWN from the document's
    #: URL — it is served bare at `:8020/` and under `/chat/` behind the proxy —
    #: and sends that. The two must agree with what the realm allows.
    redirect_uri: str = ""
    #: derived from the issuer the way Keycloak lays them out, for the reason
    #: `auth.py` gives about the issuer and the JWKS: two URLs that must agree
    #: are two URLs that will one day disagree.
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    #: the one that closes the shared-device trap. Without it "esci" only
    #: forgets a token, and the next sign-in walks back in on Keycloak's cookie
    #: as the previous person — a tablet that changes hands without changing
    #: author.
    end_session_endpoint: str = ""
    scope: str = "openid profile email"
    #: False when this node enforces nothing. The page then shows the gate with
    #: the honest sentence — a node that cannot attribute must not be offered a
    #: dictation box, because `contract.py` would refuse the write anyway.
    enforcing: bool = False
    #: When it is False, WHAT IS IN THE WAY, by name — the same list `/health`
    #: publishes, from the same helper, so the gate and the probe cannot tell
    #: two different stories. A bare gate leaves the person in front of it
    #: unable to tell «sign in» from «somebody forgot a variable».
    missing: List[str] = Field(default_factory=list)


@public.get("/v1/auth-config", response_model=AuthConfig, tags=["meta"])
def auth_config() -> AuthConfig:
    """How a browser signs in to THIS node. No secret, by construction.

    `EM_CHATBOT_CLIENT_ID` names the public client. It defaults to `em-console`,
    which is the stack's existing PUBLIC browser client, rather than inventing a
    second one: a realm object that does not exist yet produces a Sign in that
    fails at the last step, and this stack already argues (in `auth.py`, about
    the issuer and the JWKS) that two spellings of one thing are two things that
    will disagree. A deployment that wants the field client to be its own realm
    client sets the variable; what it must NOT be is `CLIENT_ID_em`, which is
    confidential and does not do this flow.

    Whichever client it is, the realm must list this page's URL among its valid
    redirect URIs — bare at `:8020/` in development, `…/chat/` behind the node's
    Caddy. That is configuration, not code.
    """
    import os

    settings = authenticator.settings
    issuer = str(getattr(settings, "issuer", "") or "")
    client_id = os.environ.get("EM_CHATBOT_CLIENT_ID", "em-console").strip()
    return AuthConfig(
        issuer=issuer,
        client_id=client_id if issuer else "",
        redirect_uri=os.environ.get("EM_CHATBOT_REDIRECT_URI", "").strip(),
        authorization_endpoint=(f"{issuer}/protocol/openid-connect/auth"
                                if issuer else ""),
        token_endpoint=(f"{issuer}/protocol/openid-connect/token"
                        if issuer else ""),
        end_session_endpoint=(f"{issuer}/protocol/openid-connect/logout"
                              if issuer else ""),
        scope=os.environ.get("EM_CHATBOT_SCOPE",
                             "openid profile email").strip(),
        enforcing=bool(getattr(settings, "enforcing", False)),
        missing=_identity_gaps(),
    )


# ── the tools, declared ───────────────────────────────────────────────────────

@public.get("/v1/tools", tags=["contract"])
def list_tools() -> Dict[str, Any]:
    """The registry, in full — the interoperability surface, readable.

    Unauthenticated on purpose: a partner writing an adapter needs to see what
    the contract looks like on a node, and a descriptor names capabilities, not
    data. What is behind them is protected; what they ARE is public.
    """
    return {"tools": [d.as_dict() for d in REGISTRY.list()],
            "intents": REGISTRY.intents(),
            # …and WHICH LANGUAGE those phrases are in. Without it a client can
            # read the vocabulary and not know that it is a vocabulary — that
            # these are the words, not a translation of the words.
            "command_language": COMMAND_LANGUAGE}


# ── the schede, as DATA ──────────────────────────────────────────────────────
#
# THE CONSTRAINT THIS SERVES, and it is a hard one (E.D., 5 September): a new
# definition must reach the telephone **without a release of the app**. If
# showing the Spanish sheet meant rebuilding the front-end, the format would not
# be travelling as data — it would be getting compiled into the code.
#
# So: a directory of definitions, listed and served. Dropping a file in makes it
# appear. The JS renderer reads what comes back and draws the module; nothing
# here draws anything, and nothing here knows what a field means to the graph.

@public.get("/v1/schede", tags=["scheda"])
def list_schede() -> Dict[str, Any]:
    """Which definitions this node can serve.

    Unauthenticated for the same reason as `/v1/tools`: a definition names a
    STANDARD, not somebody's excavation. What is behind a scheda is protected;
    which schede exist is public — and a partner writing a client needs to be
    able to see it.
    """
    from . import scheda as schede

    found = schede.available()
    return {
        "schede": [{"id": s.id,
                    # WHICH version is served, and whether it can be saved
                    # (compiled, with a recipe) or only drawn (a YAML source
                    # from the development override)
                    "version": s.version,
                    "saveable": s.recipe is not None,
                    "languages": s.languages,
                    "standard": {k: s.standard.get(k) for k in
                                 ("authority", "code", "version", "invented")},
                    "fields": len(s.fields),
                    # The three counts, so a client can SEE that a definition
                    # has not been decided yet instead of discovering it as an
                    # empty phone form.
                    "recorded_in": s.counts()}
                   for s in found],
        # Said out loud rather than left to be inferred from an empty list: a
        # node with no definitions is not broken, it is a node that takes
        # dictation. Absent means the assistant is exactly what it was.
        "serving": schede.schede_dir() is not None,
    }


@public.get("/v1/schede/{scheda_id}", tags=["scheda"])
def get_scheda(scheda_id: str, lang: str = "it") -> Dict[str, Any]:
    """ONE definition, in ONE language, as the data the module is drawn from.

    `lang` is not a preference with a fallback: a language the definition does
    not declare is a **400**. The alternative is serving a label nobody wrote
    for that standard, which is the measured defect this whole arc exists to
    avoid (`pdf_export` in pyarchinit-mini printed «Notifica» where the sheet
    says FLOTTAZIONE).
    """
    from . import scheda as schede

    found = schede.find(scheda_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"questo nodo non serve una scheda «{scheda_id}»")
    try:
        return found.for_browser(lang)
    except schede.SchedaError as problem:
        raise HTTPException(status_code=400, detail=str(problem)) from problem


@public.get("/v1/vocabolario/{scheme_id}", tags=["scheda"])
def get_vocabulary(scheme_id: str, lang: str = "it") -> Dict[str, Any]:
    """The CONCEPTS of one scheme, labelled in ONE language — what a `term` box
    offers (2026-10-22).

    Public like the definitions: a vocabulary is not somebody's record, and the
    phone has to cache it before it goes into the trench. Vendored by
    `sync-schede.sh`, resolved by `stratigraph-templates` (own scheme, then
    alignment): a concept with no word in `lang` comes back with `label: null`
    and the word it has elsewhere, never with a translation made up here.

    A `declared` scheme answers too, with no concepts and its status: the norm
    prescribes a vocabulary that nobody has published as SKOS, and the widget
    then says so and writes a word without a concept.
    """
    from . import scheda as schede

    found = schede.vocabulary(scheme_id, lang)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=f"questo nodo non ha il vocabolario «{scheme_id}»")
    return found


# ── the act ───────────────────────────────────────────────────────────────────

class Say(BaseModel):
    """What the device sends when it already has words."""
    transcript: str = ""
    #: Slots the device knows and the sentence cannot carry — the photo it just
    #: took, the GPS fix. Never the author.
    slots: Dict[str, Any] = Field(default_factory=dict)


class Answer(BaseModel):
    ok: bool
    #: The sentence to read out loud. Present on every path, including failure.
    message: str
    #: WHAT WAS HEARD. Only interesting on `/listen`, where the node did the
    #: transcribing and the device has no idea what it sent — `intent.py` keeps
    #: it for exactly this ("so a caller can show it and a person can correct
    #: it"), and until now nothing carried it back out.
    said: str = ""
    intent: Optional[str] = None
    tool: Optional[str] = None
    slots: Dict[str, Any] = Field(default_factory=dict)
    via: str = "none"
    data: Dict[str, Any] = Field(default_factory=dict)
    #: LA STANZA HA DETTO DI NO A CHI SCRIVE, durante questa richiesta — un
    #: ruolo in sola lettura, un accesso revocato, una firma che non vale più.
    #: Non un errore di questa rotta (la risposta è 200, e `message` porta la
    #: frase della stanza): un FATTO che il browser deve poter distinguere da
    #: «non ho capito», perché una nota rifiutata non si mette in coda come se
    #: la rete mancasse, e una già in coda non se ne va come se fosse arrivata.
    refused: bool = False
    #: …E SE QUELLO CHE NON È PASSATO È RIMASTO IN CODA SUL NODO. Con
    #: `refused` vero, dice al browser se la sua copia serve ancora: se il nodo
    #: la tiene (la stanza ha rifiutato la CONSEGNA), la copia del telefono
    #: sarebbe un doppione; se no (la stanza ha rifiutato l'ATTO), la nota resta
    #: sul dispositivo.
    queued: bool = False


def _author(request: Request) -> Optional[str]:
    """Who is speaking — from the token. In dev mode there is no identity, and
    the tools then refuse to write, which is the correct outcome: a node with
    auth off must not produce records attributed to nobody."""
    principal = authenticator.require_token(request)
    if principal.get("em_dev_mode"):
        return None
    return principal_orcid(principal)


def _refusals(scope: "Scope") -> int:
    """Quante volte la stanza ha detto di no a questa persona IN QUESTA
    richiesta (`RoomWriter._access`, per thread). Letto prima e dopo un atto."""
    here = getattr(scope.writer, "refusals_here", None)
    return int(here()) if here else 0


def _queued(scope: "Scope") -> int:
    here = getattr(scope.writer, "queued_here", None)
    return int(here()) if here else 0


def _told(result: ToolResult, scope: "Scope", prima: tuple) -> Dict[str, Any]:
    """`refused`, `queued` e la frase giusta, dopo un atto.

    Se la stanza ha rifiutato la CONSEGNA di qualcosa che il nodo ha tenuto,
    il tool dice «ho creato» — ed è vero per il container locale — ma la
    persona deve leggere l'altra metà.
    """
    refused = _refusals(scope) > prima[0]
    queued = _queued(scope) > prima[1]
    message = result.message
    if refused and queued and result.ok:
        message = (f"{message} La stanza ha rifiutato la consegna "
                   f"({getattr(scope.writer, 'last_access_refusal', '')}): "
                   f"resta in coda su questo nodo.")
    elif queued and result.ok and len(getattr(scope.writer, "bridge", None) or ()):
        # …e la stanza che semplicemente NON RISPONDE si dice anche lei: «ho
        # creato la US 310» era vero per il container locale e taceva che nella
        # stanza non c'era ancora (misurato in campo il 28 settembre)
        message = (f"{message} La stanza non risponde: è in coda su questo "
                   f"nodo, e parte al ritorno.")
    return {"refused": refused, "queued": queued, "message": message}


def _run(transcript: str, slots: Dict[str, Any], scope: "Scope") -> Answer:
    """La frase, capita e portata allo strumento — con lo scrivano di CHI la
    dice, nel posto dove la dice (`_scope`)."""
    registry = scope.registry
    prima = (_refusals(scope), _queued(scope))
    understood = understand(transcript, registry, model=INTENT_MODEL)
    descriptor = registry.route(understood.tool or "")
    merged = {**understood.slots, **{k: v for k, v in slots.items()
                                     if v is not None}}
    result: ToolResult = invoke(descriptor, merged, scope.who, registry=registry)
    return Answer(ok=result.ok, said=understood.transcript or "",
                  intent=understood.intent or None, tool=understood.tool,
                  slots={k: v for k, v in merged.items()
                         if not isinstance(v, (bytes, bytearray))},
                  via=understood.via, data=result.data,
                  **_told(result, scope, prima))


@v1.post("/say", response_model=Answer, tags=["assistant"])
def say(request: Request, body: Say = Body(...)) -> Answer:
    """A sentence in, an act and a sentence out.

    The whole assistant in one route, on purpose: a field device should have one
    thing to call, and everything that varies (which tool, which engine) varies
    behind it rather than in the client's code.
    """
    return _run(body.transcript, body.slots, _scope(request))


class SchedaIn(BaseModel):
    """A filled scheda, on its way to the tools that already exist."""

    #: The unit the scheda is about. Not derived from the values, even when a
    #: field of the definition holds it: WHICH unit a record is about is the
    #: caller's statement, and reading it out of a box would make a typo in that
    #: box silently address a different unit.
    us: str = ""
    #: `{field id: value}`, with the ids the DEFINITION declares. Anything else
    #: is refused — a form is not a way to put arbitrary keys into the graph.
    #: A field sent as `null` is EMPTIED (its operations of removal); a field
    #: not sent is not touched.
    values: Dict[str, Any] = Field(default_factory=dict)
    #: WHICH version of the definition the form was drawn from. Absent means
    #: the latest this node serves.
    version: str = ""
    #: `{field id: "human"|"ai"}`. Absent means human: whoever said nothing
    #: wrote it themselves.
    authored_by: Dict[str, str] = Field(default_factory=dict)
    #: Which model composed the `ai` ones — what stays legible after a person
    #: validates them.
    model: str = ""
    #: True the first time, so a unit that does not exist yet gets created
    #: before its boxes are filled. Declared by the caller rather than guessed
    #: from whether the unit is there: «create it if missing» is how a mistyped
    #: number becomes a new unit, which is the whole reason `update_su` exists.
    create: bool = False


@v1.post("/scheda/{scheda_id}", response_model=Answer, tags=["scheda"])
def submit_scheda(scheda_id: str, request: Request,
                  body: SchedaIn = Body(...)) -> Answer:
    """A filled scheda becomes the SAME act a voice would have produced.

    THE POINT OF THE WHOLE ARC, in one route: this does not write to the graph.
    It hands the values to `update_su` — the tool a sentence reaches too — and
    the tool hands them to the generator (`app/operazioni.py`), which reads the
    definition's RECIPE and says which of s3Dgraphy's five operations to send.
    The browser talks to the service; the service talks to the tools; the tools
    talk to the writer — and `tests/test_one_write_path.py` keeps that the only
    road.

    **Since 2026-10-19 one act, not two.** A first save used to be `create_su`
    then `update_su`; now the generator creates the unit inside the same list
    when `create` is declared — with the TYPE the scheda decides (`formazione_
    segno: negativa` → USN), which `create_su` could not know.
    """
    from . import scheda as schede

    found = schede.find(scheda_id, version=body.version or None)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=(f"questo nodo non serve una scheda «{scheda_id}»"
                    + (f" nella versione {body.version}" if body.version else "")))
    if not (body.us or "").strip():
        raise HTTPException(
            status_code=400,
            detail="una scheda è di un'unità: manca il numero")
    unknown = sorted(k for k in body.values if k not in found._by_id)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(f"«{found.id}» non ha i campi {unknown}: una scheda compila "
                    f"le caselle che lo standard dichiara, non altre."))

    scope = _scope(request)
    author, registry = scope.who, scope.registry
    # Il campo-identità non è un valore da scrivere: è il numero, e viaggia in
    # `us` (lo stesso motivo per cui `payloadFor` lo toglie nel browser).
    values = {k: v for k, v in body.values.items() if k != found.unit_field}
    slots: Dict[str, Any] = {"us": body.us.strip(), "fields": values,
                             "scheda": found.id, "version": found.version,
                             "create": bool(body.create),
                             "authored_by": dict(body.authored_by)}
    if body.model:
        slots["model"] = body.model
    prima = (_refusals(scope), _queued(scope))
    if not values:
        # una scheda che dice solo il numero: crearla è l'atto intero
        if not body.create:
            raise HTTPException(status_code=400,
                                detail="nessuna casella da scrivere")
        slots["fields"] = {}
    result: ToolResult = invoke(registry.get("update_su"), slots, author,
                                registry=registry) if values else invoke(
        registry.get("create_su"), {"us": slots["us"]}, author,
        registry=registry)
    return Answer(ok=result.ok,
                  tool="update_su" if values else "create_su",
                  slots={"us": slots["us"], "fields": sorted(values)},
                  data=result.data, **_told(result, scope, prima))


@v1.get("/scheda/{scheda_id}/unita", tags=["scheda"])
def read_scheda(scheda_id: str, request: Request, us: str = "",
                lente: bool = False) -> Dict[str, Any]:
    """IL RITORNO (audit B4): i valori di un'unità, riletti dal grafo.

    Dal nodo dell'unità nella sezione — la stanza, o il container locale —
    attraverso la STESSA ricetta che li ha scritti, ai valori della scheda.
    È ciò che il modulo (Foglio e Campi) mostra riaprendo un'unità: prima di
    stanotte una scheda riaperta era vuota, perché nessuno sapeva leggere
    all'indietro.

    **Se l'unità dichiara un'altra definizione** (`data.scheda`) e questo nodo
    la serve, si rilegge con quella, e lo si dice (`read_with`, `note`): le
    caselle di uno standard non sono quelle di un altro, e rileggere una US
    ungherese con la ricetta ICCD darebbe una scheda vuota che sembra vera.

    **Con `lente=1` si legge con QUELLA chiesta, e lo si dice** (2026-10-26): è
    la lente ICCD ↔ DAI sulla stessa unità. Non è la rilettura per correggere —
    le caselle di un altro standard non si riscrivono su un'unità compilata con
    questo — ma la risposta a «che cosa di questa unità sa dire la scheda X».
    `lens` dice con che cosa è stata scritta, quali caselle il grafo riempie e
    quali restano vuote.
    """
    from . import scheda as schede
    from .operazioni import MARK, OperazioniError, values_from_graph
    from .tools import unit_id_for

    scope = _scope(request)            # firma valida, o 401 dall'autenticatore
    number = (us or "").strip()
    if not number:
        raise HTTPException(status_code=400, detail="quale unità? manca `us`")
    asked = schede.find(scheda_id)
    if asked is None:
        raise HTTPException(status_code=404,
                            detail=f"questo nodo non serve una scheda «{scheda_id}»")
    try:
        section = scope.writer.section()
    except RoomRefused as chiusa:
        raise _refused(chiusa) from None
    except Exception as chiusa:        # noqa: BLE001 — rete o porta chiusa
        raise HTTPException(status_code=502,
                            detail=f"Non riesco a leggere il grafo: {chiusa}") from None
    from .operazioni import _Context, _find_unit
    unit = _find_unit(_Context(section), number)
    unit_id = str(unit["id"]) if unit else unit_id_for(number)
    declared = ((unit or {}).get("data") or {}).get(MARK) or {}
    read_with, note = asked, ""
    if lente:
        pass                           # si legge con quella chiesta: è la lente
    elif isinstance(declared, dict) and declared.get("template") and not declared.get("stub"):
        if (declared.get("template"), declared.get("version")) != (asked.id, asked.version):
            other = schede.find(str(declared["template"]),
                                version=str(declared.get("version") or "") or None)
            if other is not None:
                read_with = other
                note = (f"l'unità è stata compilata con «{other.id}» "
                        f"{other.version}: riletta con quella, non con "
                        f"«{asked.id}» {asked.version}")
            else:
                note = (f"l'unità dichiara «{declared.get('template')}» "
                        f"{declared.get('version') or ''}, che questo nodo non "
                        f"serve: riletta con «{asked.id}» {asked.version}")
    try:
        read = values_from_graph(read_with, section, unit_id, lens=lente)
    except OperazioniError as problem:
        raise HTTPException(status_code=404, detail=str(problem)) from None
    unread = read.pop("unread", [])
    out = {"us": number, "node_id": unit_id,
           "read_with": read_with.ref, "declared": read.pop("declared"),
           "note": note, **read,
           "where": writer_describe(scope.writer)}
    if lente:
        written = ({"template": declared.get("template"), "version": declared.get("version")}
                   if isinstance(declared, dict) and declared.get("template") else None)
        filled = sorted(k for k, v in read["values"].items() if v not in (None, "", [], {}))
        out["lens"] = {"read_with": read_with.ref, "written_with": written,
                       "filled": filled,
                       "holes": [str(f.get("id")) for f in read_with.fields
                                 if str(f.get("id")) not in filled],
                       # ciò che l'unità dice e nessun campo di questa scheda
                       # legge (2026-09-28): detto, non perso
                       "unread": unread}
    return out


class ValidateIn(BaseModel):
    us: str = ""
    fields: List[str] = Field(default_factory=list)


@v1.post("/validate", response_model=Answer, tags=["scheda"])
def validate(request: Request, body: ValidateIn = Body(...)) -> Answer:
    """A person confirms the boxes a model composed. One gesture, one act."""
    scope = _scope(request)
    prima = (_refusals(scope), _queued(scope))
    result: ToolResult = invoke(
        scope.registry.get("validate_field"),
        {"us": body.us, "fields": list(body.fields)},
        scope.who, registry=scope.registry)
    return Answer(ok=result.ok, tool="validate_field", data=result.data,
                  **_told(result, scope, prima))


@v1.post("/listen", response_model=Answer, tags=["assistant"])
async def listen(request: Request,
                 audio: UploadFile = File(...),
                 us: Optional[str] = Form(default=None),
                 language: Optional[str] = Form(default=None),
                 photo: Optional[UploadFile] = File(default=None),
                 photo_sha256: Optional[str] = Form(default=None)) -> Answer:
    """Audio in — transcribed on the node, then exactly as `/say`.

    A photo may ride along, because that is how the gesture actually happens:
    somebody takes a picture and says what it is of, in one act. Making them two
    requests would mean the device has to hold state between them, in a place
    where the network drops.

    `language` is WHICH language to transcribe as, and it was not being passed at
    all: the call fell through to the engine's default, which used to be a
    hard-coded `"it"`. A wrong transcription language does not fail — it produces
    words, the wrong ones, and the fault presents itself as "the assistant
    misunderstands me", which sends somebody looking in the wrong place for an
    afternoon. Absent means "let the engine decide", which for Whisper is
    detection; it no longer means "assume Italian".

    The caller that knows is the page: it sends the language its NODE speaks
    (`command_language`), not the one its own chrome is drawn in.
    """
    raw = await audio.read()
    try:
        transcript = (STT.transcribe(raw, language=language)
                      if language else STT.transcribe(raw))
    except Exception as exc:                       # noqa: BLE001
        raise HTTPException(
            status_code=501,
            detail=f"this node cannot transcribe audio: {exc}") from None
    slots: Dict[str, Any] = {}
    if us:
        slots["us"] = us
    if photo is not None:
        slots["photo"] = await photo.read()
        slots["filename"] = photo.filename
        slots["media_type"] = photo.content_type
        if photo_sha256:
            slots["sha256"] = photo_sha256
    return _run(transcript, slots, _scope(request))


class PhotoBody(BaseModel):
    """A photo the device already has, base64'd — the PWA's path when it is
    sending a picture with a sentence rather than a recording."""
    transcript: str = ""
    us: Optional[str] = None
    photo_base64: str = ""
    filename: Optional[str] = None
    media_type: str = "image/jpeg"
    #: IL DIGEST CHE IL MITTENTE SI ASPETTA — `sha256:<hex>`, o il solo hex.
    #: Facoltativo, e verificato quando c'è: un base64 troncato a un multiplo
    #: di 4 si decodifica in mezza foto con un riferimento valido, e senza
    #: questa riga nessuno può più accorgersene. Chi non lo manda passa come
    #: prima, dichiaratamente (vedi `spool.verify`).
    sha256: str = ""


@v1.post("/photo", response_model=Answer, tags=["assistant"])
def photo(request: Request, body: PhotoBody = Body(...)) -> Answer:
    try:
        raw = base64.b64decode(body.photo_base64 or "", validate=True)
    except Exception:                              # noqa: BLE001
        raise HTTPException(status_code=400,
                            detail="photo_base64 is not base64") from None
    slots: Dict[str, Any] = {"photo": raw, "media_type": body.media_type}
    if body.sha256:
        slots["sha256"] = body.sha256
    if body.us:
        slots["us"] = body.us
    if body.filename:
        slots["filename"] = body.filename
    return _run(body.transcript or "questa foto è per la US", slots,
                _scope(request))




# ── chi scrive, e dove ────────────────────────────────────────────────────────
#
# DAL 25 OTTOBRE OGNI SCRITTURA PORTA CHI E DOVE. Il chi è il token (come
# sempre); il dove sono due header che il browser manda con ogni richiesta,
# `X-StratiGraph-Server` e `X-StratiGraph-Room`, e in loro assenza la stanza che
# il NODO ha nell'ambiente. Lo scrivano è di quella persona in quel posto
# (`app/scrivani.py`), col suo token: nella stanza l'autore è chi ha scritto, e
# i permessi sono i suoi. La scelta e le forme scartate sono nella docstring di
# quel modulo.
#
# Senza stato fra una richiesta e l'altra: il posto lo tiene il browser (è un
# luogo, non una credenziale), e un riavvio del nodo non sposta nessuno.

#: I due header del dove. Nomi e non un link intero: un header è una riga che
#: si legge nei log, un link è una stringa che si deve saper spezzare.
HEADER_SERVER = "X-StratiGraph-Server"
HEADER_ROOM = "X-StratiGraph-Room"

#: IL REGISTRO DEGLI SCRIVANI PER PERSONA. Riceve il container e la dispensa
#: costruiti qui sopra — gli stessi, per la ragione scritta accanto a `LOCAL`.
SCRIVANI = Scrivani(local=LOCAL, spool=LARDER,
                    build_registry=lambda writer: build_registry(writer, STORE))


class Scope(BaseModel):
    """Chi scrive, con quale scrivano, e dove."""

    model_config = {"arbitrary_types_allowed": True}

    who: Optional[str] = None
    writer: Any = None
    registry: Any = None
    server: Optional[str] = None
    room: Optional[str] = None


def _bearer(request: Request) -> str:
    """La firma di chi chiama, cruda — per presentarla alla stanza.

    Solo a un server che il nodo ha nominato (`Scrivani.where`), mai scritta,
    mai registrata, e mai in un ambiente di processo.
    """
    raw = request.headers.get("authorization") or ""
    return raw.split(" ", 1)[1].strip() if raw.lower().startswith("bearer ") else ""


def _node_server() -> str:
    """Il server che il nodo ha nell'ambiente, se ne ha uno."""
    return (getattr(WRITER, "base_url", "")
            or (os.environ.get("EM_SERVER_URL") or "").strip()).rstrip("/")


def _scope_of(who: Optional[str], bearer: str, server: str, room: str) -> Scope:
    """Il posto dichiarato, o quello del nodo, per questa persona."""
    if not who:
        # NESSUNA PERSONA — il modo sviluppo, o un nodo headless: lo scrivano del
        # nodo, come è sempre stato. Senza un nome non si scrive niente nella
        # stanza (i tool rifiutano), quindi non c'è niente da attribuire.
        return Scope(who=None, writer=WRITER, registry=REGISTRY,
                     server=getattr(WRITER, "base_url", None),
                     room=getattr(WRITER, "room_id", None))
    if room:
        try:
            where = SCRIVANI.where(server or _node_server(), room)
        except NotTrusted as lontano:
            raise HTTPException(status_code=403, detail=str(lontano)) from None
        except ValueError as storto:
            raise HTTPException(status_code=400, detail=str(storto)) from None
    elif isinstance(WRITER, RoomWriter):
        # la stanza del NODO, ma con la firma della persona: l'ambiente sceglie
        # il posto, mai l'autore
        where = SCRIVANI.configured(WRITER.base_url, WRITER.room_id)
    else:
        # nessuna stanza da nessuna parte: il container locale, dove l'autore è
        # già quello del token (`created_by` dal `_author` di ogni richiesta)
        return Scope(who=who, writer=WRITER, registry=REGISTRY)
    writer, registry = SCRIVANI.writer(who, bearer, where)
    return Scope(who=who, writer=writer, registry=registry,
                 server=where.server, room=where.room)


def _scope(request: Request) -> Scope:
    """Chi (dal token, verificato) e dove (dagli header, o dal nodo)."""
    return _scope_of(_author(request), _bearer(request),
                     (request.headers.get(HEADER_SERVER) or "").strip(),
                     (request.headers.get(HEADER_ROOM) or "").strip())


def _refused(problem: Exception) -> HTTPException:
    """Una stanza che dice di no, detta come tale: 403 e la sua frase."""
    return HTTPException(status_code=403, detail=str(problem))


def _room_view(scope: Scope, *, enter: bool) -> Dict[str, Any]:
    """Dove scrive questa persona, con quale ruolo, e cosa le è rimasto indietro.

    `enter` apre la sessione per SAPERE il ruolo: è la stanza che lo dice alla
    porta (`host_info.role`), e un ruolo dedotto qui sarebbe una seconda
    implementazione dell'ACL. Una porta chiusa non è un errore di questa rotta:
    è la risposta, e si dice (`member: false`).
    """
    writer = scope.writer
    stato: Dict[str, Any] = {
        "writes_to": writer_describe(writer),
        "room": scope.room, "server": scope.server,
        "who": scope.who,
        "role": None, "can_write": True, "member": True, "reachable": True,
        "refused": None,
        "seated": bool(getattr(getattr(writer, "session", None), "seated", False)),
        "queues": queues_beside(LOCAL.path),
    }
    if not isinstance(writer, RoomWriter):
        stato["role"] = "local"
        return stato
    if enter:
        try:
            writer._seated(write=False)
        except RoomRefused as chiusa:
            stato.update(member=False, can_write=False, refused=str(chiusa))
        except Exception as lontana:   # noqa: BLE001 — rete, relay giù
            # IN CAMPO il socket può mancare con la porta REST aperta: si
            # chiede a lei il ruolo, e si resta corrispondenti (`seated` falso)
            porta = writer.role_by_rest()
            if porta["status"] == 200:
                ruolo = porta["role"]
                stato.update(role=ruolo, via="rest",
                             can_write=ruolo in ("editor", "admin", "owner"))
            elif porta["status"] in (401, 403):
                stato.update(member=False, can_write=False,
                             refused=writer.last_access_refusal)
            else:
                stato.update(reachable=False, refused=None,
                             unreachable=f"{type(lontana).__name__}: {lontana}")
    if stato.get("via") != "rest":
        stato["role"] = writer.role
        if writer.can_write is not None:
            stato["can_write"] = bool(writer.can_write) and stato["member"]
        if enter and stato["member"] and stato["reachable"]:
            # IL RUOLO DI ADESSO, non quello del join. Misurato nel browser: una
            # sessione aperta ripeteva il ruolo che la stanza aveva detto alla
            # porta, e una revoca a metà lavoro non si vedeva fino al primo
            # rifiuto. L'ACL la legge la stanza; qui le si chiede ancora.
            porta = writer.role_by_rest()
            if porta["status"] == 200 and porta["role"] != stato["role"]:
                ruolo = porta["role"]
                stato.update(role=ruolo,
                             can_write=ruolo in ("editor", "admin", "owner"))
                # la sessione sa un ruolo vecchio: si riapre al prossimo uso
                writer.session.close(quiet=True)
            elif porta["status"] in (401, 403):
                stato.update(member=False, can_write=False, role=None,
                             refused=writer.last_access_refusal)
                writer.session.close(quiet=True)
    stato["seated"] = bool(writer.session.seated)
    #: la coda DI QUESTA PERSONA per questa stanza, e perché non si svuota
    bridge = writer.bridge
    stato["pending"] = len(bridge) if bridge is not None else 0
    stato["pending_refused"] = getattr(bridge, "last_refusal", None) if bridge else None
    stato["last_refusal"] = writer.last_refusal
    return stato


class PointAt(BaseModel):
    """Dove vuole scrivere chi chiama. Un link, oppure le due cose che ci sono
    dentro — perché un tablet in tenda non sempre ha da dove incollare."""

    link: str = ""
    server: str = ""
    room: str = ""


@v1.get("/room", tags=["room"])
def room_state(request: Request) -> Dict[str, Any]:
    """Dove scrive CHI CHIAMA, e con quale ruolo — detto dalla stanza.

    Sotto `/v1` e non in `/health`: il ruolo è di una persona, e `/health` è
    pubblica.
    """
    return _room_view(_scope(request), enter=True)


@v1.post("/room", tags=["room"])
def point_at(request: Request, body: PointAt = Body(...)) -> Dict[str, Any]:
    """Prova la porta di una stanza a nome di chi chiama, e di' cosa si trova.

    **Non sposta il nodo**: dal 25 ottobre il nodo non ha un posto solo. La
    risposta dice se la porta si apre per questa persona e con quale ruolo; il
    browser tiene il posto e lo manda con ogni richiesta (`HEADER_ROOM`). Una
    porta che non si apre si dice con la frase della stanza — «non sei membro»,
    «sola lettura» — e non come una rete che manca.
    """
    who = _author(request)
    if not who:
        raise HTTPException(
            status_code=403,
            detail="Questo nodo non chiede una firma (auth in modo dev), quindi "
                   "non sa a nome di chi entreresti. Nella stanza quello che si "
                   "scrive porta il nome di chi scrive: senza un nome, non si "
                   "entra.")
    try:
        dove = (handoff.parse(body.link) if body.link.strip()
                else {"server": body.server.strip().rstrip("/") or _node_server(),
                      "room": body.room.strip()})
    except handoff.HandoffError as storto:
        raise HTTPException(status_code=400, detail=str(storto)) from None
    if not dove.get("server") or not dove.get("room"):
        raise HTTPException(
            status_code=400,
            detail="serve un link di consegna, oppure un server e una stanza.")
    scope = _scope_of(who, _bearer(request), dove["server"], dove["room"])
    stato = _room_view(scope, enter=True)
    if not stato["reachable"]:
        raise HTTPException(
            status_code=502,
            detail=f"La stanza «{dove['room']}» non ha risposto: "
                   f"{stato.get('unreachable')}.")
    if not stato["member"]:
        raise HTTPException(status_code=403, detail=stato["refused"])
    stato["ok"] = True
    stato["message"] = (
        f"Scrivo nella stanza «{dove['room']}» su {dove['server']}, a nome tuo."
        if stato["can_write"] else
        f"Entri nella stanza «{dove['room']}» per leggere: il tuo ruolo è "
        f"{stato['role'] or 'sconosciuto'}.")
    return stato


@v1.delete("/room", tags=["room"])
def unpoint(request: Request) -> Dict[str, Any]:
    """Torna al posto del nodo — la sua stanza, o il container locale.

    Non c'è niente da spostare sul nodo: il posto lo tiene il browser, e
    tornare indietro è smettere di mandarlo. La rotta resta per dire DOVE si
    torna, e per chiudere le sessioni di chi chiama nelle stanze che lascia.
    Il lavoro non si perde: la coda di quella stanza è su disco, ed è sua.
    """
    who = _author(request)
    lasciate = 0
    for writer in SCRIVANI.mine(who or ""):
        if (writer.base_url, writer.room_id) != (getattr(WRITER, "base_url", None),
                                                 getattr(WRITER, "room_id", None)):
            writer.session.close()
            lasciate += 1
    stato = _room_view(_scope_of(who, _bearer(request), "", ""), enter=False)
    stato["ok"] = True
    stato["message"] = (
        (f"Torno alla stanza del nodo, «{stato['room']}»." if stato["room"]
         else "Torno a scrivere nel container locale di questo nodo.")
        + (f" Restano {sum(q['pending'] for q in stato['queues'])} operazioni "
           f"in coda: ripartono quando torni nella loro stanza."
           if stato["queues"] else ""))
    return stato


@v1.post("/room/deliver", tags=["room"])
def deliver_now(request: Request) -> Dict[str, Any]:
    """«Consegna ora»: la coda di CHI CHIAMA per la sua stanza, adesso.

    Col token di questa richiesta — quello rinnovato dal browser — e non con
    quello con cui la coda era stata scritta: un'operazione in coda non porta
    l'autore, lo mette la stanza da chi consegna, ed è la stessa persona. Se la
    stanza le ha tolto il ruolo nel frattempo, **la coda resta sul nodo** e la
    risposta lo dice (`refused`), invece di sembrare consegnata o persa.
    """
    scope = _scope(request)
    writer = scope.writer
    if not isinstance(writer, RoomWriter):
        return {"ok": True, "delivered": 0, "left": 0, "refused": False,
                "message": "Questo nodo scrive nel container locale: non c'è "
                           "niente da consegnare."}
    try:
        esito = writer.deliver_pending()
    except AccessRefused as chiusa:
        rimaste = len(writer.bridge) if writer.bridge is not None else 0
        return {"ok": False, "delivered": 0, "left": rimaste, "refused": True,
                "room": scope.room,
                "message": (f"La stanza «{scope.room}» ha rifiutato la tua coda: "
                            f"{chiusa}. Le {rimaste} operazioni restano su "
                            f"questo nodo, non sono perse.")}
    return {"ok": not esito["left"], **esito, "refused": False,
            "room": scope.room,
            "message": (f"Consegnate {esito['delivered']}: la stanza le ha."
                        if not esito["left"] else
                        f"Consegnate {esito['delivered']}, ne restano "
                        f"{esito['left']} ({esito['stopped'] or 'la stanza non risponde'}).")}


class Detto(BaseModel):
    """Una frase, e basta. Non c'è dove scrivere un autore.

    L'identità la mette il relay dal token — `writer.py` non manda mai un
    `author` e il relay lo butterebbe comunque — quindi questo modello non offre
    la casella. Un campo che non esiste è più forte di un campo ignorato.
    """

    said: str = ""


@v1.post("/room/chat", tags=["room"])
def say_to_the_room(request: Request, body: Detto = Body(...)) -> Dict[str, Any]:
    """Dì una frase alla stanza.

    **Niente di nuovo sul filo**: una frase è un nodo, e lo scrivano sa già
    mandare un nodo. Il che porta in dote la cosa che serve di più in trincea —
    **la coda di quando non c'è rete**: se la stanza non risponde, il nodo
    finisce nel contenitore locale e parte al ritorno, esattamente come una
    fotografia. Una frase detta in un fosso senza campo non si perde.

    L'istante è di chi parla (`writer.apply` timbra col proprio clock), perché
    una frase detta alle dieci e sincronizzata alle diciotto porta le dieci.
    """
    #: SENZA UN NOME NON SI DICE NIENTE. Una riga di conversazione senza autore
    #: è peggio di una riga in meno — in una discussione «chi l'ha detto» è
    #: metà di quello che si legge.
    scope = _scope(request)
    if not scope.who:
        raise HTTPException(
            status_code=403,
            detail="Questo nodo non chiede una firma (auth in modo dev), quindi "
                   "una frase detta da qui non porterebbe il nome di nessuno. "
                   "In una conversazione «chi l'ha detto» è metà di quello che "
                   "si legge.")
    testo = body.said.strip()
    if not testo:
        raise HTTPException(status_code=400, detail="non hai detto niente.")
    #: l'id da CHI PARLA e QUANDO, non da un contatore: due nodi di campo che
    #: parlano insieme non si sovrascrivono a vicenda
    node_id = stable_id("chat", scope.who, testo, str(time.time()))
    try:
        scope.writer.apply(GraphDelta(
            nodes=[conversazione.message_node(testo, node_id=node_id)]))
    except RoomRefused as chiusa:
        raise _refused(chiusa) from None
    return {"ok": True, "id": node_id, "said": testo,
            "writes_to": writer_describe(scope.writer), "room": scope.room,
            "message": "Detto."}


@v1.get("/room/chat", tags=["room"])
def read_the_room(request: Request) -> Dict[str, Any]:
    """Rileggi cosa ci si è detti — dalla stanza, che è l'unica che lo sa.

    Non c'è una copia locale della conversazione, e la mancanza è dichiarata:
    una copia sarebbe un secondo database, e questo nodo ne ha già uno (il
    contenitore) che esiste per un'altra ragione. Senza rete si può **dire** e
    non si può **rileggere**, che è la metà onesta di quello che si può
    promettere.
    """
    scope = _scope(request)
    if not (getattr(scope.writer, "base_url", None)
            and getattr(scope.writer, "room_id", None)):
        raise HTTPException(
            status_code=409,
            detail="questo nodo scrive nel contenitore locale: non c'è una "
                   "stanza in cui si stia parlando.")
    #: LA DOMANDA LA FA CHI PARLA GIÀ CON LA STANZA — lo scrivano di questa
    #: persona, col suo token (`test_one_write_path`: niente `urlopen` qui).
    try:
        letto = scope.writer.conversation()
    except Exception as chiusa:        # noqa: BLE001 — rete o porta chiusa
        raise HTTPException(
            status_code=502,
            detail=f"La stanza «{scope.room}» non ha risposto: {chiusa}") from None
    letto["room"] = scope.room
    return letto


@v1.get("/room/units", tags=["room"])
def room_units(request: Request) -> Dict[str, Any]:
    """LE SCHEDE DI QUESTA STANZA — cioè le unità che ci sono già.

    Chi arriva dal link del server ha già scelto una stanza: sta continuando un
    lavoro, non ne comincia uno, e la prima cosa che deve trovare è **cosa
    c'è**. Risponde anche quando il nodo scrive nel contenitore locale, con la
    stessa forma; `where` dice quale dei due sta parlando. Un viewer legge
    (la sua sessione si siede per leggere); chi non è membro riceve la frase
    della stanza, 403.
    """
    scope = _scope(request)
    try:
        elenco = scope.writer.units()
    except RoomRefused as chiusa:
        raise _refused(chiusa) from None
    except Exception as chiusa:        # noqa: BLE001 — rete o porta chiusa
        raise HTTPException(
            status_code=502,
            detail=f"Non riesco a leggere le unità: {chiusa}") from None
    return {"units": elenco, "total": len(elenco), "room": scope.room,
            "where": writer_describe(scope.writer)}


@v1.get("/room/choices", tags=["room"])
def room_choices(request: Request) -> Dict[str, Any]:
    """FRA CHE COSA SI SCEGLIE in questa stanza: periodi, attività, foto.

    È ciò che i widget di una scheda offrono (22 ottobre), letto dal grafo e non
    da un elenco di questa pagina. Una lettura sola; scrivere resta di
    `POST /v1/scheda`.
    """
    scope = _scope(request)
    try:
        scelte = scope.writer.choices()
    except RoomRefused as chiusa:
        raise _refused(chiusa) from None
    except Exception as chiusa:        # noqa: BLE001 — rete o porta chiusa
        raise HTTPException(
            status_code=502,
            detail=f"Non riesco a leggere la stanza: {chiusa}") from None
    return {**scelte, "room": scope.room}


# ── the device ────────────────────────────────────────────────────────────────

@public.get("/", response_class=HTMLResponse, tags=["device"])
def device(request: Request) -> Any:
    """The field client, served by the node itself (design note §6).

    A PWA rather than a native app: ATRIUM is already a web app, the ecosystem
    is web-first, and one codebase reaches phones and tablets on both platforms
    with camera, microphone and GPS through the browser. The heavy AI stays on
    the node; the device stays thin.
    """
    page = _WEB / "index.html"
    if not page.is_file():
        return HTMLResponse("<h1>stratigraph-chatbot</h1>"
                            "<p>Il client di campo non è installato su questo "
                            "nodo.</p>", status_code=200)
    return _revalidated(request, page.read_bytes(), "text/html")


# ── MAI UN FILE VECCHIO (2026-10-24) ─────────────────────────────────────────
#
# Il nome della cache del worker cambia col digest, ma `install` la riempie
# passando dalla CACHE HTTP del browser: senza istruzioni, il browser può tenersi
# un `shell.css` di ieri per euristica (misurato sulla :8024 il 22 ottobre) e
# metterlo DENTRO la cache nuova, che ha il nome giusto e il contenuto sbagliato.
#
# Due argini, uno per parte. Il worker scarica con `cache: "reload"` (web/sw.js);
# il nodo serve la shell con `Cache-Control: no-cache` e un ETag di CONTENUTO, e
# risponde 304 a chi ha già quei byte. `no-cache` non vuol dire «non tenere»: vuol
# dire «chiedi prima di usare». La domanda costa un 304 senza corpo, la risposta
# è sempre il file sul disco.
#
# L'ETag è un digest dei byte e non mtime+dimensione (quello di `FileResponse`):
# un file riscritto uguale non costa uno scaricamento, uno cambiato della stessa
# lunghezza nello stesso secondo non passa per vecchio.
_REVALIDATE = "no-cache"

#: La directory della shell, UNA per le tre rotte che la servono (`/`, `/sw.js`,
#: il jolly): un nome solo, così un test la può puntare su una copia e cambiare
#: un file «sul disco» senza toccare `web/`.
_WEB = pathlib.Path(__file__).resolve().parent.parent / "web"


def _etag_of(body: bytes) -> str:
    import hashlib
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def _revalidated(request: Request, body: bytes, media_type: str) -> Response:
    """`body` con ETag di contenuto e `no-cache`, o un 304 se chi chiede lo ha."""
    etag = _etag_of(body)
    headers = {"ETag": etag, "Cache-Control": _REVALIDATE}
    asked = request.headers.get("if-none-match", "")
    if etag in {tag.strip().removeprefix("W/") for tag in asked.split(",")}:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=media_type, headers=headers)


#: What never goes in the precache, whatever is on disk. Two kinds of thing:
#: the worker itself (the browser fetches it outside the cache, and caching it
#: is how a worker becomes impossible to update) and anything that is not part
#: of the shell.
_NOT_SHELL = {"sw.js"}
_SHELL_SUFFIXES = {".html", ".css", ".js", ".mjs", ".woff2", ".woff", ".svg",
                   ".png", ".webmanifest", ".json"}


def _shell_files(web: pathlib.Path) -> List[str]:
    """Everything under `web/` the device needs to open with no signal.

    GENERATED, and the prompt's §4 asks for exactly this: *«se dividi, la cache
    list si genera, non si scrive a mano»*. A file present is a file cached —
    so splitting the front-end into modules cannot leave one of them out of the
    cache, which is the failure that only shows up in a trench.

    `"./"` first, because the shell is the page and the page is served at the
    app's root rather than as `index.html`.
    """
    found = ["./"]
    for path in sorted(web.rglob("*")):
        if not path.is_file() or path.name in _NOT_SHELL:
            continue
        if path.suffix.lower() not in _SHELL_SUFFIXES:
            continue
        relative = path.relative_to(web).as_posix()
        if relative == "index.html":
            continue                       # already there as "./"
        found.append(f"./{relative}")
    return found


@public.get("/sw.js", tags=["device"])
def service_worker(request: Request) -> Any:
    """The service worker, with its precache list and cache name SUBSTITUTED.

    Two things are filled in, and both are things a person forgets:

    * **the file list**, from what is on disk (`_shell_files`);
    * **the cache name**, from a digest of those files' bytes. A hand-bumped
      version is a step somebody skips, and skipping it leaves a device serving
      yesterday's page from cache with no way to notice — an offline bug that
      looks like it works.

    Served as text rather than `FileResponse` because it is now rendered. The
    file on disk stays a valid worker on its own (the placeholders have literal
    fallbacks), so it can still be read and reasoned about without a server.
    """
    import hashlib
    import json as _json

    web = _WEB
    worker = web / "sw.js"
    if not worker.is_file():
        raise HTTPException(status_code=404, detail="no service worker")

    files = _shell_files(web)
    digest = hashlib.sha256()
    for relative in files:
        candidate = web / relative.removeprefix("./")
        if candidate.is_file():
            digest.update(candidate.read_bytes())
        else:
            digest.update(relative.encode("utf-8"))
    source = worker.read_text(encoding="utf-8")
    source = source.replace("__SHELL_FILES__", _json.dumps(files))
    source = source.replace("__SHELL_VERSION__", digest.hexdigest()[:12])
    # Il worker si rivalida come il resto: il browser lo ricontrolla da sé a
    # ogni navigazione (è la regola dei worker), e un 304 lì costa zero byte.
    return _revalidated(request, source.encode("utf-8"),
                        "application/javascript")


@public.get("/{shell_file:path}", tags=["device"], include_in_schema=False)
def shell_file(shell_file: str, request: Request) -> Any:
    """Any file of the shell, from `web/`.

    ONE DIRECTORY, ONE SOURCE. `_shell_files` decides what the service worker
    precaches; this decides what the node serves, and they read the same
    directory with the same suffix allowlist. Two lists would be two answers,
    and the failure mode is precisely the one §3 is about: a file that is
    cached and not served, or served and not cached, and neither shows up until
    somebody is in a trench.

    Registered LAST among the public routes so `/`, `/health` and `/v1/...`
    match first — a catch-all declared earlier would swallow them.

    The suffix allowlist is what keeps this from being a directory browser: a
    `.py` or a `.md` next to the page is not the shell, and the resolved path is
    checked to be INSIDE `web/` so `..` cannot walk out of it.
    """
    web = _WEB
    candidate = (web / shell_file).resolve()
    try:
        candidate.relative_to(web.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="not part of the shell")
    if (not candidate.is_file()
            or candidate.name in _NOT_SHELL
            or candidate.suffix.lower() not in _SHELL_SUFFIXES):
        raise HTTPException(status_code=404, detail="not part of the shell")
    kind = {".css": "text/css", ".js": "application/javascript",
            ".mjs": "application/javascript", ".html": "text/html",
            ".svg": "image/svg+xml", ".json": "application/json",
            ".webmanifest": "application/manifest+json"}.get(
                candidate.suffix.lower(), "application/octet-stream")
    return _revalidated(request, candidate.read_bytes(), kind)


# The BRAND, served beside the page that asks for it. Static files, no route of
# their own: they are the vendored copy from `stratigraph-brand/` (see
# `sync-brand.sh`), and the service worker precaches them so the assistant opens
# looking like itself on a device that has never had signal.
#
# Mounted rather than listed one by one because the set is data, not code:
# adding a font weight to the brand should not mean editing this file.
_BRAND = pathlib.Path(__file__).resolve().parent.parent / "web" / "brand"
if _BRAND.is_dir():
    from fastapi.staticfiles import StaticFiles

    class _BrandFiles(StaticFiles):
        """`StaticFiles` fa già ETag e 304; manca solo l'ordine di chiedere
        prima di usare, che è la metà che conta (vedi `_REVALIDATE`)."""

        def file_response(self, *args: Any, **kwargs: Any) -> Response:
            answer = super().file_response(*args, **kwargs)
            answer.headers["Cache-Control"] = _REVALIDATE
            return answer

    app.mount("/brand", _BrandFiles(directory=str(_BRAND)), name="brand")

# L'ORDINE CONTA, ED È QUESTO PER UNA RAGIONE MISURATA.
#
# `public` finisce con la rotta jolly della conchiglia (`/{shell_file:path}`), e
# FastAPI prova le rotte nell'ordine in cui sono registrate. Con `public` per
# primo, **ogni GET sotto `/v1/` che vive su questo router veniva raccolto dal
# jolly** e rispondeva `404 not part of the shell` senza mai arrivare al suo
# gestore: misurato il 2 ottobre su `GET /v1/room`, che esisteva e non si
# raggiungeva. Le altre `/v1/...` in GET non se n'erano accorte perché stanno
# tutte su `public`, dichiarate PRIMA del jolly.
#
# I due router non condividono nessun percorso, quindi invertirli non cambia
# niente per nessuno tranne che il jolly resta l'ultimo — che è l'unica cosa che
# un jolly deve essere. `test_la_conchiglia_non_mangia_le_rotte_di_v1` lo tiene.
app.include_router(v1)
app.include_router(public)
