"""Le note senza firma si vedono e si scartano (E.D., 31 ott – 6 nov 2026).

Una nota dettata prima che la firma esistesse su un dispositivo non parte e non
si attribuisce a nessuno (`test_field_signature.py`, nota di progetto §3.2).
Ma la frase diceva «restano in coda» e basta, per sempre. Ora chi è firmato le
legge e, con due tocchi, le scarta; tutte le altre note restano dove sono.
"""
import json
import shutil
import subprocess

import pytest

from test_field_signature import CODE, LOCALES, _pure_queue_rules


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="no JS runtime here to RUN the rule")
def test_SI_SCARTANO_SOLO_quelle_senza_firma():
    harness = _pure_queue_rules() + """
const queue = [
  { subject: "0000-0001-0000-0001", by: "Anna", describe: "US 12" },
  { subject: "",                    by: "",     describe: "vecchia 1" },
  { subject: "0000-0002-0000-0002", by: "Marco", describe: "US 13" },
  { describe: "vecchia 2" },
];
console.log(JSON.stringify(withoutUnsigned(queue)));
"""
    out = subprocess.run([shutil.which("node"), "--input-type=module", "-e",
                          harness], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert [i["describe"] for i in got["kept"]] == ["US 12", "US 13"]
    assert [i["describe"] for i in got["dropped"]] == ["vecchia 1", "vecchia 2"]


def test_LE_PAROLE_ci_sono_in_italiano_e_in_inglese():
    """Le altre sei lingue sono le bozze dei partner, generate dal loro xlsx
    (`scripts/ui_strings.py`): una chiave che il file non ha lì manca, e la
    pagina ripiega sull'inglese. Tradurre è il loro lavoro."""
    for locale in ("en", "it"):
        strings = LOCALES[locale]
        for key in ("queue.unsigned.show", "queue.unsigned.discard",
                    "queue.unsigned.confirm", "queue.unsigned.gone"):
            assert strings.get(key), (locale, key)
        assert "{n}" in strings["queue.unsigned.confirm"], locale


def test_SCARTA_dalla_coda_di_ADESSO_e_solo_chi_e_firmato():
    body = CODE[CODE.index("function renderQueue()"):]
    body = body[:body.index("\n}\n")]
    #: senza firma niente pulsante: le note di nessuno non le scarta nessuno
    assert "if (!dropped.length || !WHO?.subject) return;" in body
    #: il secondo tocco rilegge la coda: una nota entrata nel frattempo resta
    assert "const now = withoutUnsigned(readQueue());" in body
    assert "writeQueue(now.kept);" in body
