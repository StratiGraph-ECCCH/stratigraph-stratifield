"""Gli standard con un nome per persone, e le unità in ordine di numero.

Scrivania StratiField, 31 ottobre 2026: SF-06 («iccd-us-2021» e «25/59» che
nessuno spiega), SF-08 (da quale standard viene una US), decisione D4 (il nome
breve lo dichiara la definizione). Eseguito davvero con node, quando c'è.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"


def _run(expr: str):
    if not shutil.which("node"):
        pytest.skip("node non c'è")
    code = (f"import {{ standardName, byNumber, splitByUse }} from '{(WEB / 'indice.js').as_uri()}';"
            f"console.log(JSON.stringify({expr}));")
    out = subprocess.run(["node", "--input-type=module", "-e", code],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0 and "document" in out.stderr:
        pytest.skip("indice.js tocca il DOM al caricamento")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_il_nome_viene_dalla_definizione_quando_lo_dichiara():
    item = {"id": "iccd-us-2021", "standard": {"authority": "ICCD", "code": "US",
                                               "version": "2021",
                                               "short": {"it": "Scheda US ICCD", "en": "ICCD SU sheet"}}}
    assert _run(f"standardName({json.dumps(item)}, 'it')") == "Scheda US ICCD"
    assert _run(f"standardName({json.dumps(item)}, 'pl')") == "ICCD SU sheet"


def test_senza_nome_breve_autorita_e_codice_e_l_anno_solo_se_e_un_anno():
    iccd = {"id": "iccd-us-2021", "standard": {"authority": "ICCD", "code": "US", "version": "2021"}}
    dai = {"id": "dai-idaifield-layer-2026",
           "standard": {"authority": "DAI", "code": "iDAI.field Layer", "version": "config 4b5c1e2"}}
    assert _run(f"standardName({json.dumps(iccd)}, 'it')") == "ICCD · US 2021"
    assert _run(f"standardName({json.dumps(dai)}, 'it')") == "DAI · iDAI.field Layer"
    assert _run("standardName({id: 'x'}, 'it')") == "x"


def test_le_unita_vanno_in_ordine_di_numero():
    units = [{"number": "10"}, {"number": "2"}, {"number": "1"}, {"number": "11"}]
    assert [u["number"] for u in _run(f"{json.dumps(units)}.sort(byNumber)")] == ["1", "2", "10", "11"]


def test_la_riga_dice_con_quale_standard_e_il_controllo_non_disturba_la_scelta():
    indice = (WEB / "indice.js").read_text(encoding="utf-8")
    assert 't("index.with"' in indice and 't("index.noStandard")' in indice
    assert "asking = true;" in indice and "asking = false;" in indice
    shell = (WEB / "shell.js").read_text(encoding="utf-8")
    assert "refreshIndex: () => (indexAsking() ? null : repaintIndex())" in shell


def test_gli_standard_della_stanza_vengono_prima_e_gli_altri_dietro():
    lista = [{"id": "dai"}, {"id": "ue"}, {"id": "iccd"}, {"id": "dana"}]
    unita = [{"scheda": {"template": "iccd"}}, {"scheda": {"template": "iccd"}},
             {"scheda": {"template": "ue"}}, {}]
    got = _run(f"splitByUse({json.dumps(lista)}, {json.dumps(unita)})")
    assert [x["id"] for x in got["used"]] == ["iccd", "ue"]
    assert [x["id"] for x in got["others"]] == ["dai", "dana"]


def test_il_telefono_misura_lo_schermo_non_la_pagina_spinta():
    shell = (WEB / "shell.js").read_text()
    assert "window.innerWidth" not in shell.replace(
        "return Math.min(window.innerWidth, screenWide);", "")
    css = (WEB / "scheda.css").read_text()
    assert "text-overflow: ellipsis;\n  white-space: nowrap; cursor: pointer;" in css
