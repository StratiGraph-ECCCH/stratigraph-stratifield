"""«Non ho capito» dice frasi, non nomi di strumenti (31 ottobre 2026, iPhone
vero: «So fare: attach_photo_to_su, build_model, create_su, …»)."""

from app.contract import Slot, ToolDescriptor, ToolRegistry, ToolResult
from app.main import _not_understood


def _registry():
    r = ToolRegistry()
    ok = lambda s, a: ToolResult(True, "ok")  # noqa: E731
    r.register(ToolDescriptor(name="create_su", intents=["crea una nuova scheda", "nuova US"],
                              input_schema=[Slot("us")], handler=ok))
    r.register(ToolDescriptor(name="which_project", intents=["in che progetto sto lavorando"],
                              handler=ok))
    r.register(ToolDescriptor(name="build_model", intents=["costruisci il modello"], handler=ok))
    return r


def test_dice_frasi_che_il_nodo_capisce_e_non_nomi_di_strumenti():
    said = _not_understood(_registry())
    assert said.startswith("Non ho capito.")
    assert "«crea una nuova scheda»" in said and "«in che progetto sto lavorando»" in said
    assert "create_su" not in said and "build_model" not in said and "_" not in said


def test_senza_strumenti_resta_la_frase_sola():
    assert _not_understood(ToolRegistry()) == "Non ho capito."
