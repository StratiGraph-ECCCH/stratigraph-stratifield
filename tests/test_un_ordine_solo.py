"""Identità dal token: l'ordine è del SERVER, e questo nodo lo usa identico.

Prima (misurato il 28 settembre 2026) StratiField leggeva `orcid, orcid_id,
https://orcid.org/id, preferred_username, sub` e la stanza `orcid, ORCID,
preferred_username, sub`: con l'ORCID solo in `orcid_id` il nodo firmava con
l'ORCID e la stanza con lo username — due autori per una persona. Adesso
l'ordine lo decide `stratigraph-server/app/identity.py`; qui ce n'è una copia
(nessun endpoint del server lo pubblica: `/v1/whoami` dice CHI, non in che
ordine), e questo test la confronta con l'originale.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib

import pytest

from app.auth import ORCID_CLAIMS, principal_orcid

SERVER_IDENTITY = (pathlib.Path(__file__).resolve().parents[2]
                   / "stratigraph-server" / "app" / "identity.py")
needs_server = pytest.mark.skipif(not SERVER_IDENTITY.is_file(),
                                  reason="stratigraph-server non è accanto: niente da confrontare")

ORCID = "0000-0002-1825-0097"
SOLO_ORCID_ID = {"orcid_id": ORCID, "preferred_username": "elisa", "sub": "3f1c-uuid"}


def _server_module():
    spec = importlib.util.spec_from_file_location("server_identity", SERVER_IDENTITY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@needs_server
def test_la_costante_e_quella_del_server_byte_per_byte():
    # letta due volte: dal sorgente (AST, senza eseguire niente) e dal modulo
    tree = ast.parse(SERVER_IDENTITY.read_text(encoding="utf-8"))
    declared = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                    if isinstance(node, ast.AnnAssign)
                    and getattr(node.target, "id", "") == "IDENTITY_CLAIMS")
    assert ORCID_CLAIMS == tuple(declared) == _server_module().IDENTITY_CLAIMS


@needs_server
@pytest.mark.parametrize("claims", [
    SOLO_ORCID_ID,
    {"https://orcid.org/id": ORCID, "preferred_username": "elisa"},
    {"ORCID": ORCID, "sub": "x"},
    {"orcid": " ", "orcid_id": ORCID},
    {"preferred_username": " elisa ", "sub": "x"},
    {"sub": 42},
    {},
])
def test_stesso_autore_da_tutte_e_due_le_parti(claims):
    assert principal_orcid(claims) == _server_module().identity_of(claims)


def test_con_l_orcid_solo_in_orcid_id_l_autore_e_l_orcid():
    assert principal_orcid(SOLO_ORCID_ID) == ORCID
