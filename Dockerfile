# stratigraph-chatbot — the field assistant, containerised for the node.
#
# The Field Computing Node must be trivial to stand up: `docker compose` on an
# always-on laptop or a mini-PC that boots and offers every service. So this
# image carries no model and no GPU assumption — the heavy AI is configured on
# the node, and without it the assistant still works (the client sends the
# transcript, which is the ATRIUM case).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# The s3Dgraphy this image installs: the VERSION from one place, the EXTRAS
# from this service.
#
# `S3DGRAPHY_VERSION` has NO DEFAULT, and that is the whole point rather than an
# omission. A default here would be a second spelling of a number that must agree
# with `dev-stack/.env.dev`, and two spellings of one version are two versions the
# day somebody edits one — which is exactly what happened: this image sat
# on dev12 while the catalogue and the field assistant had drifted to dev16, in a
# stack that shares em.json files and one semantic vocabulary. A build without the
# argument REFUSES, the way `auth.py` refuses a half-configured realm, instead of
# falling back to a pin nobody chose.
#
#   docker build --build-arg S3DGRAPHY_VERSION=<version> -t stratigraph-chatbot .
#
# The EXTRAS stay here because they are legitimately this service's own — here,
# NONE: the field assistant reads and writes containers and has no use for pyproj
# or rdflib, and an image that ships to a node in a trench should not carry them.
# A service may choose what it needs; it may not move the version by itself.
ARG S3DGRAPHY_VERSION
ARG S3DGRAPHY_EXTRAS=""

WORKDIR /srv/stratigraph-chatbot

COPY pyproject.toml README.md ./
# PyJWT and minio are not behind a build arg, for StratiGraph Server's reason: an image
# that cannot verify a token comes up open, and this one WRITES to a shared
# graph; an image that cannot reach the store keeps photos in a process.
RUN set -eu; \
    : "${S3DGRAPHY_VERSION:?required — dev-stack/.env.dev holds it}"; \
    spec="s3dgraphy${S3DGRAPHY_EXTRAS:+[${S3DGRAPHY_EXTRAS}]}==${S3DGRAPHY_VERSION}"; \
    pip install --upgrade pip && \
    pip install "$spec" "fastapi>=0.110" "uvicorn[standard]>=0.27" \
                "PyJWT[crypto]>=2.8" "minio>=7.2" "python-multipart>=0.0.9"

COPY app ./app
COPY web ./web

# The licence text travels WITH the software, and not only in the repository.
# Publishing an image IS distributing, which is the act the GPL's obligations
# attach to, so the text has to be inside the thing that gets distributed.
# `/licenses` rather than a path of our own: it is where OpenShift and the Red
# Hat container guidelines look, so a machine can find it too.
COPY LICENSE /licenses/LICENSE


# ── NOT ROOT, AND NOT A NAMED USER EITHER ────────────────────────────────────
#
# `USER chatbot` was not wrong, it was not ENOUGH, and the gap is a whole class of
# deployment: OpenShift — which is what PSNC runs — IGNORES the name. It assigns
# the pod a RANDOM uid out of the project's range and puts it in group 0 as a
# supplementary group. So the process that starts is a user that owns NOTHING,
# and `/srv/chatbot-data` (which it must write) was `chatbot:chatbot` mode 755.
# The container then either dies at boot or comes up unable to save, which is
# worse because it looks fine.
#
# Two changes, and they are the pattern Red Hat documents for arbitrary-uid
# images:
#
#   · the writable paths belong to GROUP 0 and the group bits equal the user
#     bits (`chown -R <uid>:0` + `chmod -R g=u`). Any uid the orchestrator
#     invents lands in group 0, so it can write them. Note that this is NOT
#     "world-writable": it is one group, the one the platform guarantees.
#   · `USER` is a NUMBER. Kubernetes evaluates `runAsNonRoot` against the UID,
#     and a name is not a uid: the kubelet cannot resolve it from outside the
#     image, so depending on the runtime it either refuses the pod or lets it
#     through unchecked. A number is verifiable.
#
# And `HOME`, which is the one that is invisible until it bites: Docker derives
# `HOME` from `/etc/passwd`, and a uid that is not in there gets `HOME=/`, which
# is not writable. Anything that wants a dot-directory then fails with an error
# about a path nobody configured. So HOME is named here and made group-writable
# like the rest.
#
# The proof is a RUN, not a reading: `docker run --user 12345:0` with a uid that
# does not exist in this image's `/etc/passwd` — see `../stratigraph-server/dev-stack/uid-arbitrario.sh`.
#
# The paragraph this block replaces still holds, and is kept because it explains
# why the empty directory is created at all:
# Not root, and the node's own container lives on a volume: a field node is
# switched off by unplugging it, and what was recorded must survive that.
ARG APP_UID=10001
RUN useradd --uid ${APP_UID} --gid 0 --create-home --shell /usr/sbin/nologin chatbot && \
    mkdir -p /srv/chatbot-data && \
    chown -R ${APP_UID}:0 /srv/stratigraph-chatbot /srv/chatbot-data /home/chatbot && \
    chmod -R g=u /srv/stratigraph-chatbot /srv/chatbot-data /home/chatbot
ENV HOME=/home/chatbot
USER ${APP_UID}

ENV EM_CHATBOT_CONTAINER=/srv/chatbot-data/scavo.em.json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
