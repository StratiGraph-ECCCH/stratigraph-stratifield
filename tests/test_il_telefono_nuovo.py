"""Il telefono nuovo (scrivania StratiField, 31 ottobre 2026 · D2, D5).

In alto: la stanza, lo stato, le iniziali di chi firma — che aprono il foglio
«Tu e l'aspetto» con skin, tema, lingua, soglia ed Esci. In basso, fuori dalla
scheda, quattro voci: Detta, Le US, Foto, Stanza. ☰ resta in barra in entrambe
le forme: è la porta che non si mura (`test_la_porta_del_telefono.py`).
"""

import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
PAGE = (WEB / "index.html").read_text(encoding="utf-8")
SHELL = (WEB / "shell.js").read_text(encoding="utf-8")
CSS = (WEB / "scheda.css").read_text(encoding="utf-8")


def test_i_controlli_di_aspetto_stanno_nel_foglio_e_ci_si_spostano():
    assert 'id="me-controls"' in PAGE and 'id="me-sheet"' in PAGE
    assert 'const MOVABLE = ["modes", "theme", "skin", "lang"];' in SHELL
    place = SHELL[SHELL.index("function placeControls"):]
    place = place[:place.index("\n}\n")]
    # spostati, non copiati: nessun cloneNode, un solo append
    assert "cloneNode" not in place and "home.append(node)" in place


def test_le_quattro_voci_ci_sono_e_la_porta_resta():
    bar = PAGE[PAGE.index('<div class="thumbbar"'):]
    bar = bar[:bar.index("</div>")]
    order = [m for m in re.findall(r'id="(tb-[a-z]+)"', bar)]
    assert order[:4] == ["tb-voice", "tb-units", "tb-photo", "tb-nav"], order
    paint = SHELL[SHELL.index("function paintThumbbar"):]
    paint = paint[:paint.index("\n}\n")]
    assert "const tabs = plan.bar && !plan.steps;" in paint
    # ☰ non si nasconde mai qui: resta l'unica maniglia della colonna
    assert '"tb-nav"' not in paint


def test_chi_firma_sta_nelle_iniziali_e_la_fascia_non_si_vede_piu():
    assert 'class="avatar" id="me"' in PAGE and "initialsOf(" in PAGE
    assert "#signature { display: none !important; }" in CSS
    # …ma «Esci» è lo stesso gesto di prima, non un secondo logout
    assert '$("me-signout").addEventListener("click", () => { openMe(false); $("signout").click(); });' in PAGE


def test_il_microfono_scende_dove_arriva_il_pollice():
    assert '#surface[data-sg-mode="phone"] #work > #rec { order: 6; }' in CSS
    assert '#surface[data-sg-mode="phone"] #work > #typed { order: 7; grid-column: 1; }' in CSS
    assert '#surface[data-sg-mode="phone"] #work > #send { order: 7; grid-column: 2; }' in CSS
