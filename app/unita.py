"""CHE COSA È UN'UNITÀ, e dove è stata scritta (NIGHT la scrivania, 14 nov 2026).

Due domande che l'elenco delle unità fa a ogni nodo, in un posto solo.

## 1 · È UN'UNITÀ STRATIGRAFICA?

Fino a stanotte la risposta era una tupla di prefissi scritta a mano in
`writer.py` (`"US", "SF", "BR", "SE", …`): un `startswith` che prendeva per
unità anche i nodi di continuità (`BR`) e gli eventi (`SE`), e che non vedeva
il problema misurato da Cowork sulle schermate del 12 novembre — nell'elenco
«Unità (US)» c'erano `1.CON500`, `1.DOC4001`, `1.Extractor400`,
`1.property800`. Misurato nel container della prova: sono **nodi di tipo `US`**
(`node_type: "US"`, `data.label: "US (or SU)"`). Il DB demo di PyArchInit
scrive nel suo `unita_tipo` i nomi dei nodi di EM (CON, DOC, Extractor,
property) e l'importer, che allora leggeva solo il tipo del mapping, li ha
portati dentro come US. Il nome è l'unica cosa che lo dice ancora.

La lista dei tipi viene dal DATAMODEL di s3Dgraphy, non da qui:

* sono unità i sottotipi di `StratigraphicNode` in
  `s3Dgraphy_node_datamodel.json` **la cui classe non è un `…Node`**. Nello
  stesso blocco il datamodel tiene `BR` (`ContinuityNode`, «la fine di
  un'unità») e `SE` (`StratigraphicEventNode`, «un evento che crea, modifica o
  distrugge un'unità»): sono nodi che parlano di unità, non unità. La regola è
  il nome della classe, che è del datamodel;
* un nodo di tipo unità il cui NOME dichiara un altro tipo del datamodel
  (`1.DOC4001` → `DocumentNode`, `1.Extractor400` → `ExtractorNode`,
  `1.property800` → `PropertyNode`, `1.CON500` → `ContinuityNode`) resta
  fuori, e si conta: l'elenco lo dice una volta. Il nome si legge così: si
  toglie il prefisso d'area (`1.`), si prende la parte di lettere prima del
  numero; se è un codice di unità (un'abbreviazione stratigrafica, o un genere
  di s3Dgraphy come USM/USR) è un'unità; se è l'abbreviazione, o l'inizio (tre
  lettere almeno) della classe o dell'etichetta di un tipo che NON è un'unità,
  non lo è. Altrimenti si crede al tipo del nodo.

La cura vera è nell'importer (s3Dgraphy, che stanotte non si tocca): il
referto lo dice. Qui si smette di mostrare come unità ciò che non lo è.

## 2 · DOVE È STATA SCRITTA LA DESCRIZIONE?

Intrasis e FieldRec al CHNT: le descrizioni migliori nascono in trincea e si
finiscono alla scrivania. Per dire «da rifinire» serve sapere DOVE una
descrizione è stata scritta, e il nodo — misurato stanotte — non lo
conservava: i timbri `created_by`/`modified_by` dicono chi e quando, il
marcatore `authorship.<casella>` dice persona o modello, il D7 dell'atto dice
lo strumento; il trasporto (seduti nella stanza, o corrispondenti per la porta
REST, o il container locale) si conosce al momento della scrittura e non si
scriveva da nessuna parte. L'oplog della stanza tiene la sorgente
dell'involucro (`stratigraph-chatbot`) e l'ora d'arrivo, non la postura, e non
esiste per il container locale.

Quindi da stanotte si SCRIVE, accanto al valore, nella stessa lista di
operazioni: `data.written_in.description` = l'insieme delle posture da cui la
descrizione dell'unità è stata scritta (`["trench"]`, `["desk"]`,
`["desk", "trench"]`). La postura è quella che il dispositivo DICHIARA
(`X-SG-Posture`, cioè l'interruttore Scrivania / In campo, o la postura della
nota quando è stata messa in coda); se non la dichiara, quella del trasporto
con la regola che la superficie usa già (`room.js::postureOf`): seduti nella
stanza = scrivania, altrimenti = in campo. Una descrizione scritta prima di
stanotte, o da un altro strumento, non porta il segno: la sua origine è
**sconosciuta**, la colonna lo dice e il filtro non la prende.

Affidabilità, detta: è una dichiarazione del dispositivo, buona quanto
l'interruttore; un merge di due scritture concorrenti della stessa descrizione
da posture diverse può perderne una (LWW sul campo). Non è un'ora: è un luogo.
"""

from __future__ import annotations

import contextvars
import json
import pathlib
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── 1 · i tipi, dal datamodel ───────────────────────────────────────────────


def _datamodel_path() -> pathlib.Path:
    import s3dgraphy

    return (pathlib.Path(s3dgraphy.__file__).parent / "JSON_config"
            / "s3Dgraphy_node_datamodel.json")


def _walk_types(block: Any, out: List[Dict[str, Any]]) -> None:
    """Ogni dichiarazione di tipo del datamodel (quelle con una classe)."""
    if not isinstance(block, dict):
        return
    for key, value in block.items():
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("class"), str):
            out.append({"key": key, "class": value["class"],
                        "abbreviation": str(value.get("abbreviation") or ""),
                        "label": str(value.get("label") or "")})
        _walk_types(value.get("subtypes"), out)
        if key.endswith("_nodes") or key == "node_types":
            _walk_types(value, out)


@lru_cache(maxsize=1)
def unit_types() -> Dict[str, Any]:
    """`{units: {node_type: classe}, others: [tipi che non sono unità]}`,
    letto una volta dal datamodel di s3Dgraphy che questo nodo usa."""
    data = json.loads(_datamodel_path().read_text(encoding="utf-8"))
    strat = ((data.get("stratigraphic_nodes") or {}).get("StratigraphicNode")
             or {}).get("subtypes") or {}
    units = {key: str(v.get("class") or "") for key, v in strat.items()
             if isinstance(v, dict) and not str(v.get("class") or "").endswith("Node")}
    every: List[Dict[str, Any]] = []
    for name, block in data.items():
        if name.endswith("_nodes") or name == "node_types":
            _walk_types(block, every)
    unit_classes = set(units.values())
    #: solo i tipi CONCRETI (con un'abbreviazione): `Node`, `StratigraphicNode`,
    #: `GroupNode`, `ParadataNode` sono classi astratte, e «Strato 3» non è
    #: uno `StratigraphicNode` per via delle prime lettere
    others = [t for t in every if t["class"] not in unit_classes
              and t["key"] not in units and t["abbreviation"]]
    return {"units": units, "others": others,
            "version": str(data.get("s3Dgraphy_data_model_version") or "")}


def _unit_codes() -> set:
    """Le parole che, all'inizio di un nome, dicono «unità»."""
    from s3dgraphy.nodes.stratigraphic_node import KIND_OF_CODE

    codes = {k.upper() for k in unit_types()["units"]}
    codes |= {k.upper() for k in KIND_OF_CODE}
    return codes


#: `1.DOC4001` → `DOC`; `US 12` → `US`; `USM-3` → `USM`; il prefisso d'area
#: (`1.`, `A.`) si toglie. Lettere di ogni alfabeto (ΤΣΜ è un codice vero).
_NAME = re.compile(r"^(?:[^.\s]{1,8}\.)?\s*(?P<word>[^\W\d_]+)[\s._-]*\d", re.UNICODE)


def _name_word(name: Any) -> str:
    m = _NAME.match(str(name or "").strip())
    return m.group("word") if m else ""


def _other_type_named(word: str) -> Optional[Dict[str, Any]]:
    """Il tipo NON-unità che una parola del nome dichiara, o None."""
    if not word:
        return None
    low = word.lower()
    for t in unit_types()["others"]:
        if t["abbreviation"] and low == t["abbreviation"].lower():
            return t
    if len(low) < 3:
        return None
    for t in unit_types()["others"]:
        klass = t["class"].lower()
        label = t["label"].lower()
        if klass.startswith(low) or (label and label.startswith(low)):
            return t
    return None


# ── i codici pyArchInit che NON sono unità (15 novembre 2026) ─────────────
#
# `1.Combinar900` è un CombinerNode: `Combinar` è il codice che pyArchInit
# scrive nel suo `unita_tipo` per un combiner, e la regola per nome qui sopra
# non lo vedeva («combinar» non è l'inizio di «combiner»). Non si allarga la
# somiglianza: si legge IL DATO. La tabella è quella di s3Dgraphy,
# `sync/yed_import_pipeline._CLASSIFIED_KIND_TO_UNITA_TIPO` (DOC, Combinar,
# Extractor, property), più `CON`, la riga di continuità del DB demo — la
# stessa che `importer/unit_numbers.NOT_UNIT_CODES` tiene accanto al numero.
# `s3dgraphy.sync` vuole SQLAlchemy, che questo servizio non installa; e
# `unit_numbers` non è ancora in una release: si prende da là quando c'è,
# altrimenti questa copia, tenuta uguale da un test che legge il sorgente.

#: codice `unita_tipo` → classe del datamodel che nomina
NOT_UNIT_CODES_PINNED: Dict[str, str] = {
    "DOC": "DocumentNode",
    "Combinar": "CombinerNode",
    "Extractor": "ExtractorNode",
    "property": "PropertyNode",
    "CON": "ContinuityNode",
}

#: la chiave in cui un importer ha scritto il codice (`sync/graph_projector`;
#: s3Dgraphy dev103 per l'importer PyArchInit, tolto dal 12 novembre)
CODE_KEY = "unita_tipo"


def not_unit_codes() -> Dict[str, str]:
    try:
        from s3dgraphy.importer.unit_numbers import NOT_UNIT_CODES
        return dict(NOT_UNIT_CODES)
    except Exception:                                   # noqa: BLE001
        return dict(NOT_UNIT_CODES_PINNED)


def _code_names_other(code: str) -> str:
    """La classe che un codice pyArchInit dichiara se NON è un'unità, o `""`.
    Uguale come pyArchInit lo scrive, o a meno delle maiuscole."""
    code = str(code or "").strip()
    if not code:
        return ""
    table = not_unit_codes()
    if code in table:
        return table[code]
    low = {k.lower(): v for k, v in table.items()}
    return low.get(code.lower(), "")


#: il codice in fondo a un nome costruito col template dell'importer
#: (`{area}.{settore}.{unita_tipo}{us}`): `1.Combinar900` → `Combinar`
_TEMPLATE_CODE = re.compile(r"(?:^|\.)(?P<code>[^\W\d_]+)\d[^.]*$", re.UNICODE)


def unit_verdict(node: Dict[str, Any]) -> Tuple[bool, str]:
    """`(è un'unità, perché no)`. Il perché è `""` per un'unità, o la classe del
    datamodel che il nodo (o il suo nome) dichiara."""
    kind = str((node or {}).get("node_type") or "")
    units = unit_types()["units"]
    if kind not in units:
        return False, kind or "?"
    # 1 · IL DATO DELL'IMPORTER: `data.unita_tipo`, se c'è, decide
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    declared = str(data.get(CODE_KEY) or "").strip()
    if declared:
        other = _code_names_other(declared)
        if other:
            return False, other
        return True, ""
    # 2 · UNA STANZA IMPORTATA PRIMA che l'importer scrivesse `unita_tipo`: il
    # codice è nel nome, perché il template lo mette lì (`{unita_tipo}{us}`).
    # Si confronta con la STESSA tabella, uguale — non una somiglianza.
    m = _TEMPLATE_CODE.search(str(node.get("name") or "").strip())
    if m:
        other = _code_names_other(m.group("code"))
        if other:
            return False, other
    word = _name_word(node.get("name"))
    if word and word.upper() in _unit_codes():
        return True, ""
    other = _other_type_named(word)
    if other is not None:
        return False, other["class"]
    return True, ""


def is_unit(node: Dict[str, Any]) -> bool:
    return unit_verdict(node)[0]


def left_out(nodes: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """I nodi DI TIPO UNITÀ che il nome dice essere altro, contati per classe:
    è la riga che l'elenco mostra una volta."""
    units = unit_types()["units"]
    out: Dict[str, int] = {}
    for node in nodes:
        if str(node.get("node_type") or "") not in units:
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        if data.get("removed"):
            continue
        ok, why = unit_verdict(node)
        if not ok:
            out[why] = out.get(why, 0) + 1
    return out


# ── 2 · dove, e quante parole ───────────────────────────────────────────────

TRENCH = "trench"
DESK = "desk"
POSTURES = (TRENCH, DESK)

#: LA SOGLIA DI «DA RIFINIRE»: una descrizione scritta solo in trincea con meno
#: di tante parole. Trenta: due righe di taccuino. Nel mockup v7 le descrizioni
#: dettate e lasciate a metà stanno fra 6 e 17 parole, quelle finite fra 39 e
#: 64; trenta le separa con margine da entrambe. UNA costante, letta anche dal
#: browser (`/v1/room/units` la restituisce): non c'è una seconda copia.
REFINE_UNDER_WORDS = 30

#: la chiave, in `data`, delle posture da cui la descrizione è stata scritta
WRITTEN_IN = "written_in.description"

#: L'intestazione con cui il dispositivo dichiara la sua postura.
HEADER = "X-SG-Posture"

_POSTURE_NOW: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "sg_posture", default=None)


def posture_from(declared: Any, writer: Any = None) -> str:
    """La postura di QUESTA scrittura: dichiarata, o dal trasporto."""
    said = str(declared or "").strip().lower()
    if said in ("field", "campo", TRENCH):
        return TRENCH
    if said == DESK:
        return DESK
    seated = bool(getattr(getattr(writer, "session", None), "seated", False))
    return DESK if seated else TRENCH


def set_posture(posture: Optional[str]) -> None:
    """All'inizio di ogni richiesta (`main._scope`): la postura, e il conto
    delle scritture di questa richiesta che riparte da zero."""
    _POSTURE_NOW.set(posture if posture in POSTURES else None)
    _WROTE.set(False)


#: QUESTA RICHIESTA HA SCRITTO? Lo segnano gli strumenti dopo ogni `send`,
#: `update`, `apply` andato a buon fine (`tools.py`): è ciò che separa un
#: «salvato alle…» da una domanda al grafo, che è un `ok` e non scrive niente.
_WROTE: contextvars.ContextVar[bool] = contextvars.ContextVar("sg_wrote", default=False)


def note_write() -> None:
    _WROTE.set(True)


def wrote() -> bool:
    return _WROTE.get()


def current_posture() -> Optional[str]:
    return _POSTURE_NOW.get()


def merged(previous: Any, posture: str) -> List[str]:
    """Le posture di prima più questa, in ordine fisso."""
    had = set(previous) if isinstance(previous, (list, tuple)) else set()
    had.add(posture)
    return sorted(p for p in had if p in POSTURES)


def origin_of(node: Dict[str, Any]) -> Optional[str]:
    """`trench`, `desk`, `both`, o None (non si sa)."""
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    said = data.get(WRITTEN_IN)
    if not isinstance(said, list):
        return None
    where = {p for p in said if p in POSTURES}
    if where == {TRENCH, DESK}:
        return "both"
    return next(iter(where)) if where else None


_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)


def words(text: Any) -> int:
    """Le parole di un testo: sequenze di lettere o cifre (l'apostrofo e il
    trattino dentro una parola non la spezzano)."""
    return len(_WORD.findall(str(text or "")))


def to_refine(origin: Optional[str], count: int) -> bool:
    """Scritta SOLO in trincea, e sotto la soglia. Un'origine ignota no."""
    return origin == TRENCH and count < REFINE_UNDER_WORDS


# ── 3 · i luoghi dello scavo, in albero (la sezione «Scavo») ────────────────


def places_tree(section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """I `LocationNodeGroup` di una sezione, con il loro posto nell'albero.

    Il genitore è l'arco `is_in_location` fra due luoghi (l'importer di
    PyArchInit lo scrive così: il saggio II `is_in_location` il sito); un
    luogo con più genitori prende il primo. `units` = le unità stratigrafiche
    che vi stanno DIRETTAMENTE (`is_in_location` da un'unità). Una lettura:
    nessuna scrittura accanto — questo nodo non sa ancora creare un luogo, e
    la sezione lo dice."""
    nodes = {str(n.get("id")): n for n in section.get("nodes") or []}
    places = {i: n for i, n in nodes.items()
              if n.get("node_type") == "LocationNodeGroup"
              and not ((n.get("data") or {}).get("removed"))}
    parent: Dict[str, str] = {}
    count: Dict[str, int] = {}
    for e in section.get("edges") or []:
        if e.get("edge_type") != "is_in_location":
            continue
        s, t = str(e.get("source")), str(e.get("target"))
        if t not in places:
            continue
        if s in places and s != t:
            parent.setdefault(s, t)
        elif s in nodes and is_unit(nodes[s]):
            count[t] = count.get(t, 0) + 1
    out = []
    for i, n in places.items():
        data = n.get("data") if isinstance(n.get("data"), dict) else {}
        out.append({"id": i, "name": str(n.get("name") or i),
                    "level": str(data.get("level") or ""),
                    "kind": str(data.get("kind") or data.get("group_kind") or ""),
                    "parent": parent.get(i) if parent.get(i) in places else None,
                    "units": count.get(i, 0)})
    out.sort(key=lambda p: (p["name"].casefold()))
    return out
