"""Dictation as the phone's recogniser writes it: «unità di grafica numero uno»,
«U.S. 42», «l'unità stratigrafica 220» are the same unit the archaeologist said."""
from app.intent import canonical, extract_us, rules_parse


def test_spoken_forms_become_the_unit():
    assert canonical("Crea l'unità di grafica numero uno") == "crea l us 1"
    assert canonical("Crea l'unità stratigrafica 220") == "crea l us 220"
    assert extract_us(canonical("questa foto è per la U.S. 42")) == "42"


def test_relations_are_left_alone():
    assert canonical("la 12 copre la 18") == "la 12 copre la 18"


def test_the_spoken_form_creates_the_unit():
    from app.tools import build_registry
    registry = build_registry(None, None)
    for said, us in (("Crea l'unità di grafica numero uno", "1"),
                     ("crea l'unità stratigrafica 220", "220")):
        found = rules_parse(said, registry)
        assert found is not None and found.tool == "create_su", said
        assert str(found.slots.get("us")) == us
