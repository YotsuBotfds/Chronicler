"""In-world languages and names: sound systems, sound change, daughter
languages, borrowing, and the names each people gives to the world.

An observational layer (docs/integration/languages.md), built like the
in-world historiography. After every completed turn :func:`observe_turn`
reads the world and updates a :class:`LanguagesState` kept beside it
(``WorldState._languages``), never in it. Every choice is a namespaced
``stable_hash_int("languages", seed, ...)`` draw; the layer builds none of
the world's lookup caches and no simulation code reads it, so the
simulation, its snapshots and ``state.json`` are byte-identical with the
layer on or off. The state is saved in a sidecar next to the state file
(``state.json`` -> ``state.languages.json``).

The world's canonical names (``Verdant Plains``, ``Thornwall Confederacy``,
regnal names) stay the identifiers: entity names feed simulation RNG keys.
This layer adds what the peoples call things, as a gloss.

* **Proto-languages.** Each founding culture group (founding civs that share
  a phonological style: maritime, steppe, mountain, ...) gets a
  proto-language: consonants and vowels, syllable templates, phonotactics
  and a root lexicon of naming morphemes (river, hill, ford, new, holy,
  king, people, town, ...). A group of two or more founding civs is a
  family whose daughters differ by one or two prehistoric sound changes.
* **Sound change.** A living language undergoes a regular sound change
  every 25-55 turns (lenition, vowel shifts, umlaut, cluster
  simplification, syncope, loss of final vowels, mergers, ...). It applies
  to every word of the language, roots and names alike, and is recorded,
  so every name keeps its history of forms.
* **Splits.** A seceding civ speaks a daughter of its regions' language. A
  province cut off from its people's state for 100 turns grows its own
  dialect: an exclave with no path to the capital through the civ's own
  land, or a conquered province that keeps the language of a people still
  ruling elsewhere, unless contact-ledger flow with the home land is
  strong. A daughter starts from its parent's words and changes on its
  own; a change can still spread between related languages in contact
  (wave model).
* **Contact.** The contact ledger's goods, migrant, soldier and pilgrim
  flows between civs (shared borders without the ledger) bring loanwords
  (trade, everyday, war and religious words) adapted to the borrower's
  sounds, and exonyms: a neighbour's self-name borrowed and adapted, or a
  descriptive name ("wood people").
* **Toponym layering.** A region's people name it from the canonical
  meaning of its name. A conqueror takes over the local name adapted to its
  own sounds (a substrate name); when the region's people shift to the
  conqueror's language that name becomes the local one and drifts with it.
  New settlements get names built from the founders' lexicon.
* **People.** Rulers and great persons get the native form of their name
  and title in their civ's language, beside the canonical regnal names.

Identity follows the world's: civs by index in ``world.civilizations``,
regions by index in ``world.regions``, faiths by faith id, settlements by
settlement id, persons by canonical name and the turn they appeared.

:func:`export` builds the bundle's optional ``languages`` field;
:class:`NameIndex` reads it back for narration.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from pydantic import BaseModel, Field

from chronicler.languages_phonology import (
    Phonology, Rule, adapt, choose_change, join_morphs, make_root, parse_stem, profile,
    proto_phonology, roman, rule_by_id, syllables, unit,
)

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState

logger = logging.getLogger(__name__)

#: New worlds keep languages unless ``--no-languages`` (see the doc's
#: "Default" section): the layer is observational and proven outcome-neutral.
DEFAULT_ENABLED_FOR_NEW_WORLDS = True
FORMAT = "chronicler.languages"
VERSION = 1
SIDECAR_SUFFIX = ".languages.json"

# ---------------------------------------------------------------------------
# Parameters (illustrative; they shape names and narration only)
# ---------------------------------------------------------------------------

CHANGE_INTERVAL = (25, 55)    # turns between a language's own sound changes
PREHISTORIC_CHANGES = (1, 2)  # changes a daughter of a founding family starts with
SEPARATION_TURNS = 100        # a cut-off province grows its own dialect after this long ...
SEPARATION_CONTACT = 2.0      # ... unless its contact with the rest of its civ is this strong
CONTACT_WEIGHTS = (1.0, 1.0, 0.25, 2.0)  # trade, people, soldiers, pilgrims (the ledger's)
BORDER_WEIGHT = 0.5           # contact per shared border (people channel)
EXONYM_CONTACT = 1.0          # civ contact at which a people names a neighbour
REGION_CONTACT = 0.5          # region contact at which a people knows a region
WAVE_CONTACT = 2.0            # related languages in this much contact may share a change
WAVE_SCALE = 20.0             # P(share) = min(WAVE_MAX, contact / WAVE_SCALE)
WAVE_MAX = 0.6
LOAN_RATE = 0.02              # per channel and turn: P(loan) = rate * v / (v + LOAN_HALF)
LOAN_HALF = 5.0
CALQUE_P = 0.3                # a known place name is translated instead of borrowed
NAME_PARTS_MAX = 2            # morphemes in a place name
STEM_SYLLABLES = 3            # a proper name is cut to this many syllables when adapted
LOAN_SYLLABLES = 4            # ... and a borrowed name to this many
MAX_LANGUAGES = 64            # no new daughters beyond this many languages
#: Suffix-like morphemes, always one syllable.
MONO_MEANINGS = frozenset({"people", "town", "land", "ford", "fort", "holy"})

#: Naming morphemes: meaning -> vocabulary class (which contact borrows it).
MEANINGS: dict[str, str] = {
    "water": "core", "river": "core", "sea": "core", "lake": "core", "hill": "core",
    "mountain": "core", "peak": "core", "stone": "core", "field": "core", "plain": "core",
    "valley": "core", "wood": "core", "tree": "core", "marsh": "core", "sand": "core",
    "ice": "core", "snow": "core", "sun": "core", "moon": "core", "star": "core",
    "fire": "core", "wind": "core", "storm": "core", "mist": "core", "shore": "core",
    "cliff": "core", "island": "core", "grass": "core", "land": "core", "thorn": "core",
    "break": "core", "green": "core", "white": "core", "black": "core", "red": "core",
    "blue": "core", "bright": "core", "dark": "core", "high": "core", "low": "core",
    "great": "core", "little": "core", "old": "core", "new": "core", "far": "core",
    "cold": "core", "deep": "core", "east": "core", "west": "core", "north": "core",
    "south": "core", "free": "core", "people": "core", "ford": "core", "wolf": "core",
    "iron": "trade", "gold": "trade", "silver": "trade", "salt": "trade", "market": "trade",
    "ship": "trade", "harbor": "trade", "way": "trade", "bridge": "trade",
    "town": "people", "house": "people", "horse": "people",
    "fort": "war", "wall": "war", "war": "war", "king": "war", "queen": "war",
    "chief": "war", "lord": "war",
    "god": "faith", "holy": "faith", "priest": "faith", "temple": "faith",
}
MEANING_ORDER = tuple(MEANINGS)
#: Ledger channel -> the vocabulary class its contact lends.
CHANNEL_CLASSES = ("trade", "people", "war", "faith")
CHANNELS = ("trade", "people", "soldiers", "pilgrims")

#: English words of canonical names -> meanings.
VOCAB: dict[str, tuple[str, ...]] = {
    "verdant": ("green",), "green": ("green",), "greenwood": ("green", "wood"),
    "plains": ("plain",), "plain": ("plain",), "fields": ("field",), "field": ("field",),
    "meadows": ("field",), "downs": ("hill",), "prairie": ("grass",), "expanse": ("plain",),
    "vale": ("valley",), "valley": ("valley",), "lowlands": ("low", "land"),
    "steppe": ("grass",), "grasslands": ("grass", "land"),
    "iron": ("iron",), "peaks": ("peak",), "peak": ("peak",), "mountains": ("mountain",),
    "mountain": ("mountain",), "crags": ("cliff",), "range": ("mountain",), "spires": ("peak",),
    "sapphire": ("blue",), "coast": ("shore",), "shore": ("shore",), "shores": ("shore",),
    "strand": ("shore",), "coastlands": ("shore", "land"),
    "thorn": ("thorn",), "wood": ("wood",), "woods": ("wood",), "forest": ("wood",),
    "weald": ("wood",), "jungle": ("wood",), "rainforest": ("water", "wood"),
    "wilds": ("wood",), "tangle": ("thorn",),
    "desert": ("sand",), "wastes": ("sand",), "sands": ("sand",), "dunes": ("sand",),
    "barrens": ("sand",), "crystal": ("bright",), "marsh": ("marsh",), "fen": ("marsh",),
    "mire": ("marsh",), "wetlands": ("marsh",), "bog": ("marsh",),
    "storm": ("storm",), "break": ("break",), "cliffs": ("cliff",), "sun": ("sun",),
    "fire": ("fire",), "mist": ("mist",), "obsidian": ("black", "stone"),
    "frost": ("ice",), "holm": ("island",), "tundra": ("cold", "land"),
    "frostlands": ("ice", "land"), "icefields": ("ice", "field"),
    "snowfields": ("snow", "field"), "amber": ("gold",), "hills": ("hill",),
    "highlands": ("high", "land"), "uplands": ("high", "land"), "heights": ("high",),
    "wall": ("wall",), "free": ("free",), "eastern": ("east",), "western": ("west",),
    "northern": ("north",), "southern": ("south",), "new": ("new",), "upper": ("high",),
    "lower": ("low",), "greater": ("great",), "reformed": ("new",),
}
POLITY_WORDS = frozenset({
    "empire", "confederacy", "republic", "nomads", "kingdom", "dominion", "federation",
    "league", "sultanate", "khanate", "union", "commonwealth", "theocracy", "clans",
    "tribes", "realm", "principality", "duchy", "horde", "assembly", "state", "states",
    "hegemony", "compact", "covenant", "collective", "directorate", "protectorate",
    "caliphate", "shogunate", "tribe", "marches", "march", "throne", "thalassocracy",
})
_SKIP_WORDS = frozenset({"the", "of", "and", "settlement", "faith"})
#: Titles (leaders.TITLES and the procedural polity titles) -> meanings.
TITLE_PARTS: dict[str, tuple[str, ...]] = {
    "emperor": ("great", "king"), "empress": ("great", "queen"), "king": ("king",),
    "queen": ("queen",), "warchief": ("war", "chief"), "high priestess": ("high", "priest"),
    "chancellor": ("lord",), "archon": ("lord",), "consul": ("lord",), "regent": ("lord",),
    "sovereign": ("king",), "tribune": ("chief",), "patriarch": ("high", "priest"),
    "matriarch": ("high", "priest"), "chieftain": ("chief",), "elder": ("old",),
    "khan": ("chief",),
}
_TITLES_LONGEST = sorted(TITLE_PARTS, key=len, reverse=True)
#: A people's homeland as outsiders describe it (descriptive exonyms).
TERRAIN_FEATURE = {
    "plains": "plain", "steppe": "grass", "coast": "sea", "forest": "wood", "jungle": "wood",
    "marsh": "marsh", "hills": "hill", "mountains": "mountain", "desert": "sand",
    "tundra": "ice",
}
FAMILY_LABELS = {
    "maritime": "Coastal", "steppe": "Steppe", "mountain": "Highland", "forest": "Woodland",
    "desert": "Desert", "jungle": "Jungle", "marsh": "Fenland", "tundra": "Northern",
}
TERRAIN_STYLE = {
    "coast": "maritime", "plains": "steppe", "steppe": "steppe", "hills": "mountain",
    "mountains": "mountain", "forest": "forest", "jungle": "jungle", "marsh": "marsh",
    "desert": "desert", "tundra": "tundra",
}
DOMAIN_STYLE = {
    "maritime": "maritime", "commerce": "maritime", "coastal": "maritime",
    "nomadic": "steppe", "pastoral": "steppe", "plains": "steppe",
    "highland": "mountain", "mining": "mountain", "fortress": "mountain", "mountain": "mountain",
    "woodland": "forest", "sylvan": "forest", "nature": "forest", "forest": "forest",
    "arid": "desert", "oasis": "desert", "desert": "desert",
}
_ROMAN_TAIL = re.compile(r"\s+((?:X{0,3})(?:IX|IV|V?I{0,3}))$")

# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------


class Change(BaseModel):
    """A sound change a language underwent."""
    turn: int
    rule: str
    desc: str
    words: int = 0                  # words it altered
    source: int | None = None       # the related language it spread from (wave)
    prehistoric: bool = False       # before the record began (a founding family's split)


class Language(BaseModel):
    lang_id: int                    # index in LanguagesState.languages
    name: str                       # "Kethani", "Proto-Highland", "Iron Peaks Kethani"
    parent: int | None = None
    family: int                     # the root ancestor's id
    origin: str                     # proto, founding, prehistory, secession, separation
    turn: int                       # created or branched
    style: str
    phonology: Phonology
    changes: list[Change] = Field(default_factory=list)
    lexicon: dict[str, int] = Field(default_factory=dict)   # meaning -> current root word id
    status: str = "living"          # living, extinct, reconstructed
    last_spoken: int | None = None
    next_change: int = 0


class Word(BaseModel):
    """A root or a name in one language, with its history of forms.

    ``forms`` rows are ``[turn, phonemic form, change index]``: the coined
    form (change index None), then one row per sound change that altered
    it (an index into the language's ``changes``). ``parts`` are the
    morphemes it was built from, in the word's own order, as
    ``[phonemic morpheme, gloss]``; a borrowed or inherited word has none
    and names its ``source`` word instead.
    """
    word_id: int
    lang: int
    kind: str                       # root, civ, region, settlement, faith, person
    ref: int | str                  # meaning, civ index, region index, settlement id, faith id, person key
    turn: int
    how: str                        # native, loan, calque, substrate, inherited, descriptive
    source: int | None = None
    parts: list[list[str]] = Field(default_factory=list)
    forms: list[list] = Field(default_factory=list)
    tail: str = ""                  # shown after the name (a regnal ordinal)
    until: int | None = None        # a root replaced by a loan at this turn

    @property
    def form(self) -> str:
        return self.forms[-1][1]


class RegionRecord(BaseModel):
    """What the languages layer remembers of one region (index in world.regions)."""
    speech: list[list[int]] = Field(default_factory=list)   # [[turn, lang], ...]
    story: list[list] = Field(default_factory=list)         # [[turn, kind, civ or lang], ...]
    controller: int | None = None   # civ index at the last observation
    cut_since: int | None = None    # turn it was first cut off from its civ's capital


class LanguagesState(BaseModel):
    """Every language and name of the world (never read by the simulation)."""
    version: int = VERSION
    enabled_turn: int = 0
    last_turn: int = 0
    founded: bool = False
    languages: list[Language] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)
    civ_lang: list[list[list[int]]] = Field(default_factory=list)  # per civ: [[turn, lang], ...]
    regions: list[RegionRecord] = Field(default_factory=list)
    faiths: dict[int, str] = Field(default_factory=dict)       # faith id -> canonical name named
    persons: dict[str, list] = Field(default_factory=dict)     # key -> [canonical name, civ, role]
    settlements: dict[int, list] = Field(default_factory=dict)  # id -> [canonical name, region]
    counts: dict[str, int] = Field(default_factory=dict)


class LanguagesSlot:
    """``WorldState._languages``: the state plus derived lookups.

    Equality-neutral (like the historiography slot), so a world compares
    equal with the layer on or off; copies carry a deep copy of the state
    and fresh lookups.
    """

    __slots__ = ("state", "_names", "_by_lang")

    def __init__(self, state: LanguagesState) -> None:
        self.state = state
        self._names: dict[tuple, int] | None = None
        self._by_lang: dict[int, list[int]] | None = None

    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, LanguagesSlot)

    __hash__ = None  # type: ignore[assignment]

    def __copy__(self) -> "LanguagesSlot":
        return LanguagesSlot(self.state.model_copy(deep=True))

    def __deepcopy__(self, memo: dict) -> "LanguagesSlot":
        return self.__copy__()

    def __reduce__(self):
        return (_slot_from_dump, (self.state.model_dump(mode="json"),))

    def _build(self) -> None:
        self._names = {}
        self._by_lang = {}
        for w in self.state.words:
            self._by_lang.setdefault(w.lang, []).append(w.word_id)
            if w.until is None:
                self._names[(w.lang, w.kind, w.ref)] = w.word_id

    def name(self, lang: int, kind: str, ref: int | str) -> Word | None:
        if self._names is None:
            self._build()
        wid = self._names.get((lang, kind, ref))  # type: ignore[union-attr]
        return None if wid is None else self.state.words[wid]

    def words_of(self, lang: int) -> list[int]:
        if self._by_lang is None:
            self._build()
        return self._by_lang.get(lang, [])  # type: ignore[union-attr]

    def add(self, word: Word) -> None:
        if self._names is None:
            self._build()
        self.state.words.append(word)
        self._by_lang.setdefault(word.lang, []).append(word.word_id)  # type: ignore[union-attr]
        if word.until is None:
            self._names[(word.lang, word.kind, word.ref)] = word.word_id  # type: ignore[index]

    def retire(self, word: Word, turn: int) -> None:
        if self._names is None:
            self._build()
        word.until = turn
        key = (word.lang, word.kind, word.ref)
        if self._names.get(key) == word.word_id:  # type: ignore[union-attr]
            del self._names[key]  # type: ignore[union-attr]


def _slot_from_dump(data: dict) -> LanguagesSlot:
    return LanguagesSlot(LanguagesState.model_validate(data))


# ---------------------------------------------------------------------------
# Switch and persistence
# ---------------------------------------------------------------------------


def languages_on(world: Any) -> bool:
    return isinstance(getattr(world, "_languages", None), LanguagesSlot)


def state_of(world: Any) -> LanguagesState | None:
    slot = getattr(world, "_languages", None)
    return slot.state if isinstance(slot, LanguagesSlot) else None


def _fresh_state(world: "WorldState") -> LanguagesState:
    return LanguagesState(enabled_turn=world.turn, last_turn=world.turn)


def set_languages_enabled(world: "WorldState", enabled: bool) -> None:
    """Switch on (languages are founded at the next completed turn) or off (dropped)."""
    if enabled:
        if not languages_on(world):
            world._languages = LanguagesSlot(_fresh_state(world))
    else:
        world._languages = None


def sidecar_path(state_path: Path) -> Path:
    """``state.json`` -> ``state.languages.json`` (same directory)."""
    state_path = Path(state_path)
    stem = state_path.name[:-5] if state_path.name.endswith(".json") else state_path.name
    return state_path.with_name(stem + SIDECAR_SUFFIX)


def sidecar_text(world: "WorldState") -> str | None:
    st = state_of(world)
    if st is None:
        return None
    head = json.dumps({"format": FORMAT, "version": VERSION, "turn": world.turn},
                      separators=(",", ":"))
    return head[:-1] + ',"state":' + st.model_dump_json() + "}"


def save_sidecar(world: "WorldState", state_path: Path, *, atomic: bool = False) -> None:
    """Write the languages next to the state file; remove a stale one while off."""
    path = sidecar_path(state_path)
    text = sidecar_text(world)
    if text is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover - unusual filesystem
            logger.warning("could not remove stale languages sidecar %s", path)
        return
    if atomic:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    else:
        path.write_text(text, encoding="utf-8")


def load_sidecar(world: "WorldState", state_path: Path) -> bool:
    """Attach the languages saved next to ``state_path``; False when there are none.

    A sidecar from another turn is not trusted: the languages are founded
    afresh at the loaded turn, with a warning.
    """
    path = sidecar_path(state_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        data = json.loads(raw)
        if data.get("format") != FORMAT or int(data.get("version", 0)) > VERSION:
            raise ValueError("unknown languages sidecar format")
        state = LanguagesState.model_validate(data["state"])
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("ignoring unreadable languages sidecar %s: %s", path, exc)
        world._languages = LanguagesSlot(_fresh_state(world))
        return True
    if data.get("turn") != world.turn or state.last_turn != world.turn:
        logger.warning("languages sidecar %s does not match the saved world (turn %s); "
                       "languages are founded afresh at turn %s", path, data.get("turn"), world.turn)
        state = _fresh_state(world)
    world._languages = LanguagesSlot(state)
    return True


# ---------------------------------------------------------------------------
# Names from canonical names
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z]+")


def _split_compound(low: str) -> tuple[str, ...] | None:
    for k in range(3, len(low) - 2):
        a, b = low[:k], low[k:]
        if a in VOCAB and b in VOCAB:
            return VOCAB[a] + VOCAB[b]
    return None


def name_tokens(text: str) -> list[tuple[str, str]]:
    """A canonical name as morphemes in English order: ("m", meaning) or ("s", stem).

    Polity words, articles and numbers are dropped: "Free Verdant Plains" ->
    free, green, plain; "Kethani Empire" -> "Kethani"; "Thornwood" -> thorn, wood.
    """
    out: list[tuple[str, str]] = []
    for tok in _TOKEN.findall(text):
        low = tok.lower()
        if low in _SKIP_WORDS or low in POLITY_WORDS:
            continue
        if low in VOCAB:
            out.extend(("m", m) for m in VOCAB[low])
            continue
        split = _split_compound(low)
        if split:
            out.extend(("m", m) for m in split)
        else:
            out.append(("s", tok))
    return out


def short_name(name: str) -> str:
    """"Kethani Empire" -> "Kethani"; "Kingdom of Tamurai" -> "Tamurai"."""
    words = [w for w in name.split() if w.lower() not in POLITY_WORDS and w.lower() != "of"]
    return " ".join(words) or name


def _civ_style(civ, world) -> str:
    for domain in civ.domains:
        style = DOMAIN_STYLE.get(domain.lower())
        if style:
            return style
    terrain = None
    if civ.capital_region:
        for region in world.regions:
            if region.name == civ.capital_region:
                terrain = region.terrain
                break
    if terrain is None and civ.regions:
        for region in world.regions:
            if region.name == civ.regions[0]:
                terrain = region.terrain
                break
    return TERRAIN_STYLE.get(terrain or "", "steppe")


# ---------------------------------------------------------------------------
# One observation
# ---------------------------------------------------------------------------


class _Turn:
    """Read-only views of the world for one observation (local dicts only)."""

    def __init__(self, world: "WorldState", slot: LanguagesSlot) -> None:
        self.world = world
        self.slot = slot
        self.st = slot.state
        self.seed = world.seed
        self.t = world.turn - 1                       # the completed turn
        civs = world.civilizations
        self.alive = [bool(c.regions) for c in civs]
        self.civ_index: dict[str, int] = {}
        for i, civ in enumerate(civs):
            j = self.civ_index.get(civ.name)
            if j is None or (not self.alive[j] and self.alive[i]):
                self.civ_index[civ.name] = i
        self.region_index = {}
        for i, region in enumerate(world.regions):
            self.region_index.setdefault(region.name, i)
        self.adjacent = [[self.region_index[a] for a in r.adjacencies if a in self.region_index]
                         for r in world.regions]
        self.controller = [self.civ_index.get(r.controller) if r.controller else None
                           for r in world.regions]

    def u(self, *parts: object) -> float:
        return unit(self.seed, *parts)

    def lang_of(self, civ: int | None) -> int | None:
        if civ is None or civ >= len(self.st.civ_lang) or not self.st.civ_lang[civ]:
            return None
        return self.st.civ_lang[civ][-1][1]

    def speech(self, ri: int) -> int | None:
        rec = self.st.regions[ri]
        return rec.speech[-1][1] if rec.speech else None

    def lang(self, lid: int) -> Language:
        return self.st.languages[lid]

    def descends(self, lid: int, ancestor: int) -> bool:
        """``lid`` is ``ancestor`` or one of its descendants."""
        while lid is not None:
            if lid == ancestor:
                return True
            lid = self.st.languages[lid].parent  # type: ignore[assignment]
        return False


def _count(st: LanguagesState, key: str, n: int = 1) -> None:
    st.counts[key] = st.counts.get(key, 0) + n


def observe_turn(world: "WorldState") -> None:
    """Update the languages after the turn that just completed (no-op while off)."""
    slot = getattr(world, "_languages", None)
    if not isinstance(slot, LanguagesSlot):
        return
    ctx = _Turn(world, slot)
    st = ctx.st
    if not st.founded:
        _found(ctx)
        st.founded = True
    _new_civs(ctx)
    _track_regions(ctx)
    _separation(ctx)
    _update_status(ctx)
    contacts = _contacts(ctx)
    _sound_changes(ctx, contacts)
    _borrow(ctx, contacts)
    _name_all(ctx, contacts)
    st.last_turn = world.turn


# --- languages --------------------------------------------------------------


def _next_change(ctx: _Turn, lid: int, after: int) -> int:
    lo, hi = CHANGE_INTERVAL
    return after + lo + int(ctx.u("interval", lid, after) * (hi - lo + 1))


def _new_language(ctx: _Turn, *, name: str, parent: int | None, origin: str, style: str,
                  phonology: Phonology, turn: int, status: str = "living") -> Language:
    st = ctx.st
    lid = len(st.languages)
    family = lid if parent is None else st.languages[parent].family
    lang = Language(lang_id=lid, name=name, parent=parent, family=family, origin=origin,
                    turn=turn, style=style, phonology=phonology, status=status,
                    next_change=_next_change(ctx, lid, turn))
    st.languages.append(lang)
    _count(st, f"languages:{origin}")
    return lang


def _add_word(ctx: _Turn, lang: int, kind: str, ref: int | str, how: str, form: str, *,
              parts: list[list[str]] | None = None, source: int | None = None,
              tail: str = "", turn: int | None = None) -> Word:
    st = ctx.st
    t = ctx.t if turn is None else turn
    word = Word(word_id=len(st.words), lang=lang, kind=kind, ref=ref, turn=t, how=how,
                source=source, parts=parts or [], forms=[[t, form, None]], tail=tail)
    ctx.slot.add(word)
    if kind != "root":
        _count(st, f"{kind}:{how}")
    return word


def _root_forms(ctx: _Turn, lang: Language) -> list[str]:
    words = ctx.st.words
    return [words[wid].form for wid in lang.lexicon.values()]


def _proto(ctx: _Turn, name: str, style: str, origin: str, turn: int, key: object,
           status: str = "living") -> Language:
    ph = proto_phonology(ctx.seed, key, style)
    lang = _new_language(ctx, name=name, parent=None, origin=origin, style=style,
                         phonology=ph, turn=turn, status=status)
    taken: set[str] = set()
    for meaning in MEANING_ORDER:
        form = make_root(ctx.seed, (key, "root"), ph, meaning, taken,
                         short=MEANINGS[meaning] == "core", mono=meaning in MONO_MEANINGS)
        word = _add_word(ctx, lang.lang_id, "root", meaning, "native", form, turn=turn)
        lang.lexicon[meaning] = word.word_id
    lang.phonology = profile(ph, _root_forms(ctx, lang))
    return lang


def _branch(ctx: _Turn, parent: Language, *, name: str, origin: str, turn: int) -> Language:
    """A daughter language: the parent's current roots and place, people and faith names."""
    lang = _new_language(ctx, name=name, parent=parent.lang_id, origin=origin, style=parent.style,
                         phonology=parent.phonology.model_copy(deep=True), turn=turn)
    words = ctx.st.words
    for wid in list(ctx.slot.words_of(parent.lang_id)):
        w = words[wid]
        if w.until is not None or w.kind == "person":
            continue
        new = _add_word(ctx, lang.lang_id, w.kind, w.ref, "inherited", w.form, source=w.word_id,
                        tail=w.tail, turn=turn)
        if w.kind == "root":
            lang.lexicon[w.ref] = new.word_id  # type: ignore[index]
    return lang


def _apply_change(ctx: _Turn, lang: Language, rule: Rule, *, turn: int,
                  source: int | None = None, prehistoric: bool = False) -> int:
    words = ctx.st.words
    index = len(lang.changes)
    changed = 0
    for wid in ctx.slot.words_of(lang.lang_id):
        w = words[wid]
        if w.until is not None:
            continue
        new = rule.apply(w.form)
        if new != w.form:
            w.forms.append([turn, new, index])
            changed += 1
    lang.changes.append(Change(turn=turn, rule=rule.rid, desc=rule.desc, words=changed,
                               source=source, prehistoric=prehistoric))
    lang.phonology = rule.update(lang.phonology, _root_forms(ctx, lang))
    _count(ctx.st, "changes")
    return changed


def _applied(lang: Language) -> set[str]:
    return {f"{c.rule}:{c.desc}" for c in lang.changes}


def _found(ctx: _Turn) -> None:
    """Founding languages: one per culture group; a group of two or more is a family."""
    st, world = ctx.st, ctx.world
    t0 = st.enabled_turn
    groups: dict[str, list[int]] = {}
    for i, civ in enumerate(world.civilizations):
        groups.setdefault(_civ_style(civ, world), []).append(i)
    for style in sorted(groups, key=lambda s: groups[s][0]):
        members = groups[style]
        if len(members) == 1:
            i = members[0]
            lang = _proto(ctx, short_name(world.civilizations[i].name), style, "founding", t0,
                          ("proto", style, i))
            _set_civ_lang(ctx, i, lang.lang_id, t0)
            continue
        proto = _proto(ctx, f"Proto-{FAMILY_LABELS[style]}", style, "proto", t0,
                       ("proto", style, members[0]), status="reconstructed")
        for i in members:
            lang = _branch(ctx, proto, name=short_name(world.civilizations[i].name),
                           origin="prehistory", turn=t0)
            lo, hi = PREHISTORIC_CHANGES
            n = lo + int(ctx.u("prehistory", lang.lang_id) * (hi - lo + 1))
            for k in range(n):
                rule = choose_change(ctx.seed, ("prehistory", lang.lang_id, k), lang.phonology,
                                     _root_forms(ctx, lang), _applied(lang))
                if rule is not None:
                    _apply_change(ctx, lang, rule, turn=t0, prehistoric=True)
            _set_civ_lang(ctx, i, lang.lang_id, t0)


def _set_civ_lang(ctx: _Turn, civ: int, lid: int, turn: int) -> None:
    st = ctx.st
    while len(st.civ_lang) <= civ:
        st.civ_lang.append([])
    rows = st.civ_lang[civ]
    if not rows or rows[-1][1] != lid:
        rows.append([turn, lid])


def _new_civs(ctx: _Turn) -> None:
    """Languages of civs founded since the last observation."""
    st, world = ctx.st, ctx.world
    for i in range(len(st.civ_lang), len(world.civilizations)):
        civ = world.civilizations[i]
        earlier = [j for j in range(i) if world.civilizations[j].name == civ.name]
        old = ctx.lang_of(earlier[-1]) if earlier else None
        if old is not None:  # a restored people speaks its old language
            _set_civ_lang(ctx, i, old, ctx.t)
            continue
        prior: dict[int, int] = {}
        for rname in civ.regions:
            ri = ctx.region_index.get(rname)
            if ri is not None and ri < len(st.regions):
                prev = st.regions[ri].controller
                if prev is not None and prev != i:
                    prior[prev] = prior.get(prev, 0) + 1
        if not prior:
            style = _civ_style(civ, world)
            lang = _proto(ctx, short_name(civ.name), style, "founding", ctx.t, ("proto", style, i))
            _set_civ_lang(ctx, i, lang.lang_id, ctx.t)
            continue
        parent = min(prior, key=lambda c: (-prior[c], c))
        cap = ctx.region_index.get(civ.capital_region) if civ.capital_region else None
        base = ctx.speech(cap) if cap is not None and cap < len(st.regions) else None
        if base is None:
            base = ctx.lang_of(parent)
        if base is None:
            continue
        spoken_by_civ = any(ctx.lang_of(j) == base and ctx.alive[j] and j != i
                            for j in range(len(st.civ_lang)))
        if not spoken_by_civ or len(st.languages) >= MAX_LANGUAGES:
            lid = base  # a provincial dialect becomes the new state's language
        else:
            lid = _branch(ctx, ctx.lang(base), name=short_name(civ.name), origin="secession",
                          turn=ctx.t).lang_id
        _set_civ_lang(ctx, i, lid, ctx.t)
        for rname in civ.regions:
            ri = ctx.region_index.get(rname)
            if ri is None or ri >= len(st.regions):
                continue
            cur = ctx.speech(ri)
            if cur is not None and cur != lid and ctx.descends(lid, cur):
                rec = st.regions[ri]
                rec.speech.append([ctx.t, lid])
                rec.story.append([ctx.t, "dialect", lid])


# --- regions ----------------------------------------------------------------


def _track_regions(ctx: _Turn) -> None:
    """Rulers, and the speech of each region's people (settlement, shift, dialect)."""
    st, world = ctx.st, ctx.world
    while len(st.regions) < len(world.regions):
        st.regions.append(RegionRecord())
    for ri, region in enumerate(world.regions):
        rec = st.regions[ri]
        ctrl = ctx.controller[ri]
        if ctrl != rec.controller:
            if ctrl is not None:
                rec.story.append([ctx.t, "ruled", ctrl])
            rec.controller = ctrl
            rec.cut_since = None
        ident = ctx.civ_index.get(region.cultural_identity) if region.cultural_identity else ctrl
        target = ctx.lang_of(ident)
        if target is None:
            continue
        cur = ctx.speech(ri)
        if cur is None:
            rec.speech.append([ctx.t, target])
            rec.story.append([ctx.t, "settled", target])
        elif cur == target or ctx.descends(cur, target):
            continue
        else:
            kind = "dialect" if ctx.descends(target, cur) else "shift"
            rec.speech.append([ctx.t, target])
            rec.story.append([ctx.t, kind, target])
            _count(st, f"speech:{kind}")
            if kind == "shift":
                _keep_substrate(ctx, ri, cur, target)


def _origin(ctx: _Turn, word: Word) -> Word:
    """The word a loan, calque, substrate or inherited name goes back to."""
    words = ctx.st.words
    for _ in range(16):
        if word.source is None:
            break
        word = words[word.source]
    return word


def _keep_substrate(ctx: _Turn, ri: int, old: int, new: int) -> None:
    """A people that shifts language keeps its place name, adapted to the new
    language, unless that language's name already goes back to it."""
    local = ctx.slot.name(old, "region", ri)
    if local is None:
        return
    mine = ctx.slot.name(new, "region", ri)
    if mine is not None:
        if _origin(ctx, mine).word_id == _origin(ctx, local).word_id:
            return
        ctx.slot.retire(mine, ctx.t)   # the conqueror's own name gives way
    _add_word(ctx, new, "region", ri, "substrate",
              adapt(local.form, ctx.lang(new).phonology, max_syllables=LOAN_SYLLABLES),
              source=local.word_id)


def _ledger_edges(world: "WorldState") -> list:
    from chronicler.contact_ledger import ledger_enabled
    return world.contact_ledger.edges if ledger_enabled(world) else []


def _separation(ctx: _Turn) -> None:
    """A province cut off from its people's state for long grows its own dialect.

    Cut off: a province of a civ that speaks the civ's language but has no
    path to the capital through the civ's own land (an exclave), or a
    conquered province that keeps the language of a people who still rule
    land elsewhere. Strong contact-ledger flow with the home land keeps it
    in the fold.
    """
    st, world = ctx.st, ctx.world
    owned: dict[int, list[int]] = {}
    for ri, ctrl in enumerate(ctx.controller):
        if ctrl is not None:
            owned.setdefault(ctrl, []).append(ri)
    groups: list[tuple[int, list[int], set[int]]] = []   # (language, cut off, home land)
    for civ_i in sorted(owned):
        regions = owned[civ_i]
        civ = world.civilizations[civ_i]
        lid = ctx.lang_of(civ_i)
        cap = ctx.region_index.get(civ.capital_region) if civ.capital_region else None
        if lid is None or len(regions) < 2 or cap is None or ctx.controller[cap] != civ_i:
            continue
        own = set(regions)
        reached = {cap}
        frontier = [cap]
        while frontier:
            nxt = []
            for r in frontier:
                for a in ctx.adjacent[r]:
                    if a in own and a not in reached:
                        reached.add(a)
                        nxt.append(a)
            frontier = nxt
        cut = [ri for ri in sorted(own - reached) if ctx.speech(ri) == lid]
        if cut:
            groups.append((lid, cut, reached))
    homes: dict[int, set[int]] = {}
    for civ_i, regions in owned.items():
        lid = ctx.lang_of(civ_i)
        if lid is not None:
            homes.setdefault(lid, set()).update(regions)
    foreign: dict[int, list[int]] = {}
    for ri, ctrl in enumerate(ctx.controller):
        local = ctx.speech(ri)
        if ctrl is not None and local is not None and local != ctx.lang_of(ctrl) and local in homes:
            foreign.setdefault(local, []).append(ri)
    for lid in sorted(foreign):
        groups.append((lid, foreign[lid], homes[lid]))
    edges = _ledger_edges(world) if groups else []
    cut_now: set[int] = set()
    for lid, cut, home in groups:
        cut_set = set(cut)
        contact = 0.0
        for src, dst, *flows in edges:
            if (src in cut_set and dst in home) or (dst in cut_set and src in home):
                contact += sum(w * v for w, v in zip(CONTACT_WEIGHTS, flows))
        for ri in cut:
            cut_now.add(ri)
            if st.regions[ri].cut_since is None:
                st.regions[ri].cut_since = ctx.t
        if contact >= SEPARATION_CONTACT or len(st.languages) >= MAX_LANGUAGES:
            continue
        # One dialect per connected group of regions cut off long enough.
        ready = [ri for ri in cut if ctx.t - st.regions[ri].cut_since >= SEPARATION_TURNS]
        done: set[int] = set()
        for ri in ready:
            if ri in done:
                continue
            group, frontier = {ri}, [ri]
            while frontier:
                nxt = []
                for r in frontier:
                    for a in ctx.adjacent[r]:
                        if a in ready and a not in group:
                            group.add(a)
                            nxt.append(a)
                frontier = nxt
            done |= group
            first = min(group)
            dialect = _branch(ctx, ctx.lang(lid), origin="separation", turn=ctx.t,
                              name=f"{world.regions[first].name} {ctx.lang(lid).name}")
            for r in sorted(group):
                rec = st.regions[r]
                rec.speech.append([ctx.t, dialect.lang_id])
                rec.story.append([ctx.t, "dialect", dialect.lang_id])
                rec.cut_since = None
    for ri, rec in enumerate(st.regions):
        if ri not in cut_now:
            rec.cut_since = None


def _update_status(ctx: _Turn) -> None:
    st = ctx.st
    spoken = {ctx.lang_of(i) for i, a in enumerate(ctx.alive) if a}
    spoken |= {ctx.speech(ri) for ri, c in enumerate(ctx.controller) if c is not None}
    for lang in st.languages:
        if lang.status == "reconstructed":
            continue
        if lang.lang_id in spoken:
            if lang.status != "living":
                lang.status, lang.last_spoken = "living", None
                lang.next_change = max(lang.next_change, _next_change(ctx, lang.lang_id, ctx.t))
        elif lang.status == "living":
            lang.status, lang.last_spoken = "extinct", ctx.t
            _count(st, "extinct")


# --- contact ----------------------------------------------------------------


def _contacts(ctx: _Turn) -> dict[tuple[int, int], list[float]]:
    """Civ pair (i < j) -> [trade, people, soldiers, pilgrims, borders, war]."""
    world = ctx.world
    out: dict[tuple[int, int], list[float]] = {}

    def row(a: int, b: int) -> list[float]:
        key = (a, b) if a < b else (b, a)
        r = out.get(key)
        if r is None:
            r = out[key] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return r

    from chronicler.contact_ledger import ledger_enabled
    if ledger_enabled(world):
        for a, b, *flows in world.contact_ledger.pairs:
            ia, ib = ctx.civ_index.get(a), ctx.civ_index.get(b)
            if ia is None or ib is None or ia == ib:
                continue
            r = row(ia, ib)
            for k in range(4):
                r[k] += flows[k]
    for ri, adj in enumerate(ctx.adjacent):
        ca = ctx.controller[ri]
        if ca is None:
            continue
        for rj in adj:
            cb = ctx.controller[rj]
            if rj > ri and cb is not None and cb != ca:
                row(ca, cb)[4] += 1.0
    for pair in world.active_wars:
        if len(pair) >= 2:
            ia, ib = ctx.civ_index.get(pair[0]), ctx.civ_index.get(pair[1])
            if ia is not None and ib is not None and ia != ib:
                row(ia, ib)[5] = 1.0
    return out


def intensity(row: Sequence[float]) -> float:
    return sum(w * v for w, v in zip(CONTACT_WEIGHTS, row)) + BORDER_WEIGHT * row[4]


def _lang_contacts(ctx: _Turn, contacts: dict[tuple[int, int], list[float]]
                   ) -> dict[tuple[int, int], list[float]]:
    out: dict[tuple[int, int], list[float]] = {}
    for (a, b), r in contacts.items():
        la, lb = ctx.lang_of(a), ctx.lang_of(b)
        if la is None or lb is None or la == lb:
            continue
        key = (la, lb) if la < lb else (lb, la)
        acc = out.setdefault(key, [0.0] * 6)
        for k in range(6):
            acc[k] += r[k]
    return out


def _sound_changes(ctx: _Turn, contacts: dict[tuple[int, int], list[float]]) -> None:
    st = ctx.st
    lcontact = None
    for lang in list(st.languages):
        if lang.status != "living" or lang.next_change > ctx.t:
            continue
        lang.next_change = _next_change(ctx, lang.lang_id, ctx.t)
        rule = choose_change(ctx.seed, ("own", lang.lang_id, ctx.t), lang.phonology,
                             _root_forms(ctx, lang), _applied(lang))
        if rule is None:
            continue
        _apply_change(ctx, lang, rule, turn=ctx.t)
        if lcontact is None:
            lcontact = _lang_contacts(ctx, contacts)
        for other in st.languages:
            if (other.lang_id == lang.lang_id or other.status != "living"
                    or other.family != lang.family):
                continue
            key = tuple(sorted((lang.lang_id, other.lang_id)))
            c = intensity(lcontact.get(key, ()) or [0.0] * 6)  # type: ignore[arg-type]
            if c < WAVE_CONTACT or ctx.u("wave", lang.lang_id, other.lang_id, ctx.t) >= min(
                    WAVE_MAX, c / WAVE_SCALE):
                continue
            spread = rule_by_id(other.phonology, rule.rid, rule.desc)
            if spread is None or f"{rule.rid}:{rule.desc}" in _applied(other):
                continue
            if any(spread.apply(f) != f for f in _root_forms(ctx, other)):
                _apply_change(ctx, other, spread, turn=ctx.t, source=lang.lang_id)
                _count(st, "changes:spread")


def _borrow(ctx: _Turn, contacts: dict[tuple[int, int], list[float]]) -> None:
    """Loanwords along contact: each channel lends its own vocabulary."""
    st = ctx.st
    words = st.words
    lcontact = _lang_contacts(ctx, contacts)
    for (la, lb) in sorted(lcontact):
        r = lcontact[(la, lb)]
        for borrower, donor in ((la, lb), (lb, la)):
            bl, dl = ctx.lang(borrower), ctx.lang(donor)
            if bl.status != "living" or dl.status != "living":
                continue
            for k, cls in enumerate(CHANNEL_CLASSES):
                v = r[k] + (BORDER_WEIGHT * r[4] if k == 1 else 0.0)
                if v <= 0 or ctx.u("loan", borrower, donor, k, ctx.t) >= LOAN_RATE * v / (v + LOAN_HALF):
                    continue
                pool = []
                for meaning in MEANING_ORDER:
                    if MEANINGS[meaning] != cls or meaning not in bl.lexicon or meaning not in dl.lexicon:
                        continue
                    own, theirs = words[bl.lexicon[meaning]], words[dl.lexicon[meaning]]
                    if own.how == "loan" and own.source is not None and words[own.source].lang == donor:
                        continue
                    if adapt(theirs.form, bl.phonology) != own.form:
                        pool.append(meaning)
                if not pool:
                    continue
                meaning = pool[int(ctx.u("loanword", borrower, donor, k, ctx.t) * len(pool))]
                old, theirs = words[bl.lexicon[meaning]], words[dl.lexicon[meaning]]
                ctx.slot.retire(old, ctx.t)
                new = _add_word(ctx, borrower, "root", meaning, "loan",
                                adapt(theirs.form, bl.phonology), source=theirs.word_id)
                bl.lexicon[meaning] = new.word_id
                _count(st, f"loans:{CHANNELS[k]}")


# --- naming -----------------------------------------------------------------


def _morph(ctx: _Turn, lid: int, token: tuple[str, str]) -> list[str]:
    """[phonemic form, gloss] of one morpheme in a language."""
    kind, value = token
    lang = ctx.lang(lid)
    if kind == "m":
        return [ctx.st.words[lang.lexicon[value]].form, value]
    return [adapt(parse_stem(value), lang.phonology, max_syllables=STEM_SYLLABLES), value]


def _compose(ctx: _Turn, lid: int, tokens: Sequence[tuple[str, str]], *,
             one_word: bool = False) -> tuple[str, list[list[str]]]:
    """A name from morphemes in English order (modifiers, then the head)."""
    ph = ctx.lang(lid).phonology
    morphs = [_morph(ctx, lid, tok) for tok in tokens]
    if ph.order == "hm" and len(morphs) >= 2:
        morphs = morphs[-1:] + morphs[:-1]
    forms = [m[0] for m in morphs]
    if one_word or ph.join == "word" or len(morphs) == 1:
        return join_morphs(forms, ph), morphs
    if ph.order == "hm":
        return f"{forms[0]} {join_morphs(forms[1:], ph)}", morphs
    return f"{join_morphs(forms[:-1], ph)} {forms[-1]}", morphs


def _cap(tokens: list[tuple[str, str]], n: int) -> list[tuple[str, str]]:
    return tokens if len(tokens) <= n else tokens[: n - 1] + tokens[-1:]


def _ensure_civ_endonym(ctx: _Turn, civ: int) -> Word | None:
    lid = ctx.lang_of(civ)
    if lid is None:
        return None
    word = ctx.slot.name(lid, "civ", civ)
    if word is not None:
        return word
    # A people named after a proper stem: stem + "people" ("Kethani" -> Kithan-ur),
    # with at most one modifier before it ("Greater Selurian"); a people named
    # in plain words keeps two of them ("Thornwall" -> thorn wall).
    tokens = name_tokens(ctx.world.civilizations[civ].name)
    stems = [k for k, t in enumerate(tokens) if t[0] == "s"]
    if stems:
        first = stems[0]
        tokens = tokens[max(0, first - 1): first + 1] + [("m", "people")]
    else:
        tokens = _cap(tokens, 2) or [("m", "people")]
    form, parts = _compose(ctx, lid, tokens, one_word=True)
    if len(tokens) == 3 and len(syllables(form)) > 4:  # too long: drop the modifier
        form, parts = _compose(ctx, lid, tokens[1:], one_word=True)
    return _add_word(ctx, lid, "civ", civ, "native", form, parts=parts)


def _ensure_exonym(ctx: _Turn, lid: int, civ: int, row: Sequence[float]) -> None:
    if ctx.slot.name(lid, "civ", civ) is not None:
        return
    endo = _ensure_civ_endonym(ctx, civ)
    if endo is None or endo.lang == lid:
        return
    peaceful = row[0] + row[1] + row[3]
    total = peaceful + row[2] + BORDER_WEIGHT * row[4]
    p_loan = 0.35 + 0.5 * (peaceful / total if total > 0 else 0.0) - (0.2 if row[5] else 0.0)
    if ctx.u("exonym", lid, civ) < p_loan:
        _add_word(ctx, lid, "civ", civ, "loan",
                  adapt(endo.form, ctx.lang(lid).phonology, max_syllables=LOAN_SYLLABLES),
                  source=endo.word_id)
        return
    target = ctx.world.civilizations[civ]
    cap = ctx.region_index.get(target.capital_region) if target.capital_region else None
    terrain = ctx.world.regions[cap].terrain if cap is not None else ""
    feature = TERRAIN_FEATURE.get(terrain, "far")
    form, parts = _compose(ctx, lid, [("m", feature), ("m", "people")], one_word=True)
    _add_word(ctx, lid, "civ", civ, "descriptive", form, parts=parts, source=endo.word_id)


def _region_native(ctx: _Turn, lid: int, ri: int) -> tuple[str, list[list[str]]]:
    tokens = _cap(name_tokens(ctx.world.regions[ri].name), NAME_PARTS_MAX) or [("m", "land")]
    return _compose(ctx, lid, tokens)


def _ensure_region_name(ctx: _Turn, lid: int, ri: int, *, ruled: bool, depth: int = 0) -> Word:
    word = ctx.slot.name(lid, "region", ri)
    if word is not None:
        return word
    local = ctx.speech(ri)
    if local is None or local == lid or depth > 0:
        form, parts = _region_native(ctx, lid, ri)
        return _add_word(ctx, lid, "region", ri, "native", form, parts=parts)
    src = _ensure_region_name(ctx, local, ri, ruled=False, depth=depth + 1)
    ph = ctx.lang(lid).phonology
    if ruled:
        return _add_word(ctx, lid, "region", ri, "substrate",
                         adapt(src.form, ph, max_syllables=LOAN_SYLLABLES), source=src.word_id)
    if src.parts and src.how == "native" and ctx.u("calque", lid, ri) < CALQUE_P:
        tokens = [("m", g) if g in MEANINGS else ("s", g) for _f, g in src.parts]
        if ctx.lang(src.lang).phonology.order == "hm" and len(tokens) >= 2:
            tokens = tokens[1:] + tokens[:1]
        form, parts = _compose(ctx, lid, tokens)
        return _add_word(ctx, lid, "region", ri, "calque", form, parts=parts, source=src.word_id)
    return _add_word(ctx, lid, "region", ri, "loan",
                     adapt(src.form, ph, max_syllables=LOAN_SYLLABLES), source=src.word_id)


def _known_regions(ctx: _Turn) -> dict[int, set[int]]:
    """Civ index -> regions its people know: held, bordering, or in ledger contact."""
    known: dict[int, set[int]] = {}
    for ri, ctrl in enumerate(ctx.controller):
        if ctrl is None:
            continue
        s = known.setdefault(ctrl, set())
        s.add(ri)
        s.update(ctx.adjacent[ri])
    for src, dst, *flows in _ledger_edges(ctx.world):
        if src >= len(ctx.controller) or dst >= len(ctx.controller):
            continue
        if sum(w * v for w, v in zip(CONTACT_WEIGHTS, flows)) < REGION_CONTACT:
            continue
        for a, b in ((src, dst), (dst, src)):
            ctrl = ctx.controller[a]
            if ctrl is not None:
                known.setdefault(ctrl, set()).add(b)
    return known


def _title_and_stem(name: str) -> tuple[str | None, str, str]:
    """"Warchief Seren II" -> ("warchief", "Seren", " II")."""
    tail = ""
    m = _ROMAN_TAIL.search(name)
    if m and m.group(1):
        tail = " " + m.group(1)
        name = name[: m.start()]
    low = name.lower()
    for title in _TITLES_LONGEST:
        if low.startswith(title + " "):
            return title, name[len(title) + 1:].strip(), tail
    return None, name.strip(), tail


def _ensure_person(ctx: _Turn, lid: int, key: str, name: str, civ: int, role: str) -> None:
    if ctx.slot.name(lid, "person", key) is not None:
        return
    title, stem, tail = _title_and_stem(name)
    ph = ctx.lang(lid).phonology
    base = [adapt(parse_stem(stem.split()[0] if stem else "a"), ph,
                  max_syllables=STEM_SYLLABLES), stem]
    parts = [base]
    form = base[0]
    if title is not None:
        tmorphs = [_morph(ctx, lid, ("m", m)) for m in TITLE_PARTS[title]]
        if ph.order == "hm" and len(tmorphs) >= 2:
            tmorphs = tmorphs[-1:] + tmorphs[:-1]
        tform = join_morphs([m[0] for m in tmorphs], ph)
        tpart = [tform, " ".join(TITLE_PARTS[title])]  # the title's meaning, in English order
        if ph.order == "hm":
            form, parts = f"{form} {tform}", [base, tpart]
        else:
            form, parts = f"{tform} {form}", [tpart, base]
    ctx.st.persons.setdefault(key, [name, civ, role])
    _add_word(ctx, lid, "person", key, "native", form, parts=parts, tail=tail)


def _settlement_tokens(ctx: _Turn, sid: int, ri: int) -> list[tuple[str, str]]:
    region = ctx.world.regions[ri]
    options: list[list[tuple[str, str]]] = []
    tokens = name_tokens(region.name)
    if tokens:
        options.append([tokens[0], ("m", "town")])
    options.append([("m", "new"), ("m", "town")])
    if region.river_mask:
        options.append([("m", "river"), ("m", "ford")])
    if region.terrain in ("mountains", "hills"):
        options.append([("m", "high"), ("m", "fort")])
    if region.terrain == "coast":
        options.append([("m", "sea"), ("m", "harbor")])
    ctrl = ctx.controller[ri]
    if ctrl is not None:
        leader = ctx.world.civilizations[ctrl].leader
        stem = leader.throne_name or _title_and_stem(leader.name)[1]
        if stem:
            options.append([("s", stem.split()[0]), ("m", "town")])
    return options[int(ctx.u("settlement", sid) * len(options))]


def _name_all(ctx: _Turn, contacts: dict[tuple[int, int], list[float]]) -> None:
    st, world = ctx.st, ctx.world
    known = _known_regions(ctx)
    partners: dict[int, list[tuple[int, list[float]]]] = {}
    for (a, b), r in sorted(contacts.items()):
        if intensity(r) >= EXONYM_CONTACT or r[4] or r[5]:
            partners.setdefault(a, []).append((b, r))
            partners.setdefault(b, []).append((a, r))
    for i, civ in enumerate(world.civilizations):
        if not ctx.alive[i]:
            continue
        lid = ctx.lang_of(i)
        if lid is None:
            continue
        _ensure_civ_endonym(ctx, i)
        for j, r in partners.get(i, []):
            if ctx.alive[j]:
                _ensure_exonym(ctx, lid, j, r)
        for ri in sorted(known.get(i, ())):
            _ensure_region_name(ctx, lid, ri, ruled=ctx.controller[ri] == i)
        if civ.leader is not None:
            _ensure_person(ctx, lid, f"{civ.leader.name}|{civ.leader.reign_start}",
                           civ.leader.name, i, "ruler")
        for gp in civ.great_persons:
            if gp.active:
                origin = ctx.civ_index.get(gp.origin_civilization, i)
                glid = ctx.lang_of(origin)
                _ensure_person(ctx, lid if glid is None else glid, f"{gp.name}|{gp.born_turn}",
                               gp.name, origin, gp.role)
    for ri, region in enumerate(world.regions):
        local = ctx.speech(ri)
        if local is not None:
            _ensure_region_name(ctx, local, ri, ruled=False)
        ctrl = ctx.controller[ri]
        clid = ctx.lang_of(ctrl)
        for s in region.settlements:
            sid = s.settlement_id
            if sid <= 0:
                continue
            namer = local if local is not None else clid
            if namer is None:
                continue
            if sid not in st.settlements:
                st.settlements[sid] = [s.name, ri]
                form, parts = _compose(ctx, namer, _settlement_tokens(ctx, sid, ri))
                _add_word(ctx, namer, "settlement", sid, "native", form, parts=parts)
            if clid is not None and clid != namer and ctx.slot.name(clid, "settlement", sid) is None:
                src = ctx.slot.name(namer, "settlement", sid)
                if src is not None:
                    _add_word(ctx, clid, "settlement", sid, "substrate",
                              adapt(src.form, ctx.lang(clid).phonology), source=src.word_id)
    for belief in world.belief_registry:
        fid = belief.faith_id
        if st.faiths.get(fid) not in (None, belief.name):  # a faith id reused for a new faith
            for w in [w for w in st.words if w.kind == "faith" and w.ref == fid and w.until is None]:
                ctx.slot.retire(w, ctx.t)
            del st.faiths[fid]
        origin = belief.civ_origin if 0 <= belief.civ_origin < len(world.civilizations) else None
        olid = ctx.lang_of(origin)
        if olid is None:
            continue
        endo = ctx.slot.name(olid, "faith", fid)
        if endo is None:
            st.faiths[fid] = belief.name
            tokens = name_tokens(belief.name)
            new = [t for t in tokens if t == ("m", "new")]
            rest = [t for t in tokens if t != ("m", "new")][:1]
            form, parts = _compose(ctx, olid, new + rest + [("m", "holy")])
            endo = _add_word(ctx, olid, "faith", fid, "native", form, parts=parts)
        for i, civ in enumerate(world.civilizations):
            if not ctx.alive[i] or civ.civ_majority_faith != fid:
                continue
            alid = ctx.lang_of(i)
            if alid is not None and alid != olid and ctx.slot.name(alid, "faith", fid) is None:
                _add_word(ctx, alid, "faith", fid, "loan",
                          adapt(endo.form, ctx.lang(alid).phonology), source=endo.word_id)


# ---------------------------------------------------------------------------
# Export (the bundle field)
# ---------------------------------------------------------------------------

#: Column order of the exported ``words`` rows (append only).
WORD_COLUMNS: tuple[str, ...] = (
    "id", "lang", "kind", "ref", "turn", "how", "source", "parts", "forms", "tail", "until",
)


def _display_forms(w: Word) -> list[list]:
    """[[turn, display form, change index], ...], dropping changes that look the same."""
    title = w.kind != "root"
    out: list[list] = []
    for turn, form, change in w.forms:
        shown = roman(form, title=title)
        if out and out[-1][1] == shown:
            continue
        out.append([turn, shown, change])
    return out


def export(world: "WorldState") -> dict | None:
    """The bundle field: languages, their changes, every word and the entity tables."""
    st = state_of(world)
    if st is None:
        return None
    civs = world.civilizations
    regions = world.regions
    slot = world._languages
    first_civ: dict[int, int] = {}
    for i, civ_rows in enumerate(st.civ_lang):
        for _turn, lid in civ_rows:
            first_civ.setdefault(lid, i)
    langs = []
    for lang in st.languages:
        ph = lang.phonology
        endo = (slot.name(lang.lang_id, "civ", first_civ[lang.lang_id])
                if lang.lang_id in first_civ else None)
        native = roman(endo.form) if endo is not None else None
        speakers = [i for i, rows in enumerate(st.civ_lang) if rows and rows[-1][1] == lang.lang_id]
        langs.append({
            "id": lang.lang_id, "name": lang.name, "parent": lang.parent, "family": lang.family,
            "origin": lang.origin, "turn": lang.turn, "status": lang.status,
            "last_spoken": lang.last_spoken, "style": lang.style, "civs": speakers,
            "native": native,
            "phonology": {
                "consonants": " ".join(roman(c, title=False) for c in ph.consonants),
                "vowels": " ".join(roman(v, title=False) for v in ph.vowels),
                "onsets": [roman(o, title=False) for o in ph.onsets],
                "finals": " ".join(roman(c, title=False) for c in ph.finals),
                "syllables": ph.templates, "order": ph.order, "join": ph.join, "stress": ph.stress,
            },
            "changes": [[c.turn, c.rule, c.desc, c.words, c.source, c.prehistoric]
                        for c in lang.changes],
        })
    rows = []
    for w in st.words:
        parts = [[roman(f, title=False), g] for f, g in w.parts]
        rows.append([w.word_id, w.lang, w.kind, w.ref, w.turn, w.how, w.source, parts,
                     _display_forms(w), w.tail, w.until])
    return {
        "version": VERSION, "enabled_turn": st.enabled_turn,
        "counts": dict(sorted(st.counts.items())),
        "languages": langs,
        "word_columns": list(WORD_COLUMNS), "words": rows,
        "civs": [{"civ": i, "name": civs[i].name if i < len(civs) else None, "lang": rows_}
                 for i, rows_ in enumerate(st.civ_lang) if rows_],
        "regions": [{"region": ri, "name": regions[ri].name if ri < len(regions) else None,
                     "speech": rec.speech, "story": rec.story}
                    for ri, rec in enumerate(st.regions)],
        "settlements": [{"id": sid, "name": v[0], "region": v[1]}
                        for sid, v in sorted(st.settlements.items())],
        "faiths": [{"faith": b.faith_id, "name": b.name, "civ": b.civ_origin}
                   for b in world.belief_registry if b.faith_id in st.faiths],
        "persons": [{"key": k, "name": v[0], "civ": v[1], "role": v[2]}
                    for k, v in st.persons.items()],
    }


# ---------------------------------------------------------------------------
# Reading the field back for narration
# ---------------------------------------------------------------------------


def _at(rows: Sequence[Sequence], turn: int):
    """The value of a [[turn, value], ...] history at ``turn`` (None before it began)."""
    value = None
    for row in rows:
        if row[0] > turn:
            break
        value = row[1]
    return value


class NameIndex:
    """Read-only view of a bundle's ``languages`` field for narration.

    Names are read as they stood at a turn: the form a word had then, the
    language a civ or region spoke then, and the earlier local names a
    region had before its people changed language.
    """

    MAX_ENTITIES = 6

    def __init__(self, data: dict) -> None:
        self.data = data
        self.langs = {lang["id"]: lang for lang in data.get("languages", [])}
        columns = tuple(data.get("word_columns") or WORD_COLUMNS)
        self.words: dict[int, dict] = {}
        self.names: dict[tuple, list[dict]] = {}
        self.native_of: dict[tuple, int] = {}
        for raw in data.get("words", []):
            w = dict(zip(columns, raw))
            self.words[w["id"]] = w
            self.names.setdefault((w["lang"], w["kind"], w["ref"]), []).append(w)
            if w["how"] == "native":
                self.native_of.setdefault((w["kind"], w["ref"]), w["lang"])
        self.civs = {c["civ"]: c for c in data.get("civs", [])}
        self.regions = {r["region"]: r for r in data.get("regions", [])}
        self.settlements = {s["id"]: s for s in data.get("settlements", [])}
        self.faiths = {f["faith"]: f for f in data.get("faiths", [])}
        self.persons = {p["key"]: p for p in data.get("persons", [])}
        canonical: dict[str, list[tuple[str, Any]]] = {}

        def add(name: str | None, kind: str, ref: Any) -> None:
            if name and len(name) >= 3:
                entry = canonical.setdefault(name, [])
                if (kind, ref) not in entry:
                    entry.append((kind, ref))

        for i, c in sorted(self.civs.items()):
            add(c.get("name"), "civ", i)
            add(short_name(c.get("name") or ""), "civ", i)
        for ri, r in sorted(self.regions.items()):
            add(r.get("name"), "region", ri)
        for sid, s in sorted(self.settlements.items()):
            add(s.get("name"), "settlement", sid)
        for fid, f in sorted(self.faiths.items()):
            add(f.get("name"), "faith", fid)
            name = f.get("name") or ""
            if name.startswith("Faith of "):
                add("the Faith of " + short_name(name[len("Faith of "):]), "faith", fid)
        for key, p in self.persons.items():
            add(p.get("name"), "person", key)
        self.canonical = canonical
        alternatives = sorted(canonical, key=lambda s: (-len(s), s))
        self._pattern = (re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in alternatives)
                                    + r")(?!\w)") if alternatives else None)

    @classmethod
    def from_bundle(cls, bundle: dict | None) -> "NameIndex | None":
        data = (bundle or {}).get("languages")
        return cls(data) if isinstance(data, dict) else None

    def __bool__(self) -> bool:
        return bool(self.words)

    # --- lookups ------------------------------------------------------------

    def lang_name(self, lid: int | None) -> str:
        lang = self.langs.get(lid) if lid is not None else None
        return lang["name"] if lang else "?"

    def civ_lang(self, civ: int, turn: int) -> int | None:
        rows = self.civs.get(civ, {}).get("lang") or []
        value = _at(rows, turn)
        return value if value is not None else (rows[0][1] if rows else None)

    def speech(self, region: int, turn: int) -> int | None:
        return _at(self.regions.get(region, {}).get("speech") or [], turn)

    def form_at(self, w: dict, turn: int) -> str | None:
        """A word's display form at ``turn`` (None before it was coined or after it was replaced)."""
        if w["turn"] > turn or (w.get("until") is not None and w["until"] <= turn):
            return None
        form = _at(w["forms"], turn) or w["forms"][0][1]
        return form + (w.get("tail") or "")

    def name(self, kind: str, ref: Any, lang: int | None, turn: int) -> tuple[str, dict] | None:
        """(display form, word) of what ``lang`` called an entity at ``turn``."""
        if lang is None:
            return None
        best = None
        for w in self.names.get((lang, kind, ref), ()):
            form = self.form_at(w, turn)
            if form is not None:
                best = (form, w)
        return best

    def own_lang(self, kind: str, ref: Any, turn: int) -> int | None:
        """The language of the entity's own people at ``turn``."""
        if kind == "civ":
            return self.civ_lang(ref, turn)
        if kind == "region":
            return self.speech(ref, turn)
        return self.native_of.get((kind, ref))

    def gloss(self, w: dict) -> str | None:
        """The English meaning of a word ("green plain"), following loans to their source."""
        seen = 0
        if w is not None and w["kind"] == "person":  # the title's meaning ("high priest")
            titles = [g for _f, g in w.get("parts") or []
                      if g and all(x in MEANINGS for x in g.split())]
            return titles[0] if titles else None
        while w is not None and seen < 8:
            parts = w.get("parts") or []
            if parts:
                glosses = [g for _f, g in parts]
                order = self.langs.get(w["lang"], {}).get("phonology", {}).get("order")
                if order == "hm" and len(glosses) >= 2 and w["kind"] != "person":
                    glosses = glosses[1:] + glosses[:1]
                return " ".join(glosses)
            src = w.get("source")
            w = self.words.get(src) if src is not None else None
            seen += 1
        return None

    def lookup(self, canonical: str, turn: int) -> tuple[str, Any] | None:
        entries = self.canonical.get(canonical)
        if not entries:
            return None
        if len(entries) == 1 or entries[0][0] != "person":
            return entries[0]
        # Persons of one name: the latest who appeared by then.
        best = entries[0]
        for kind, key in entries:
            appeared = int(str(key).rsplit("|", 1)[-1]) if "|" in str(key) else 0
            if appeared <= turn:
                best = (kind, key)
        return best

    def entities(self, events: Sequence["Event"]) -> list[tuple[str, Any]]:
        """Civs, regions, persons, settlements and faiths an event list mentions, in order."""
        out: list[tuple[str, Any]] = []
        for ev in events:
            turn = ev.turn
            names = list(ev.actors) + list(ev.civs)
            for name in names:
                found = self.lookup(name, turn)
                if found and found not in out:
                    out.append(found)
            for region in (ev.region, ev.shock_region):
                found = self.lookup(region, turn) if region else None
                if found and found not in out:
                    out.append(found)
            if self._pattern is not None and ev.description:
                for m in self._pattern.finditer(ev.description):
                    found = self.lookup(m.group(0), turn)
                    if found and found not in out:
                        out.append(found)
        return out

    def _canonical(self, kind: str, ref: Any) -> str:
        table = {"civ": self.civs, "region": self.regions, "settlement": self.settlements,
                 "faith": self.faiths, "person": self.persons}[kind]
        return (table.get(ref) or {}).get("name") or str(ref)

    def views(self, kind: str, ref: Any, turn: int, others: Iterable[int] = ()) -> dict | None:
        """The entity's own name, what ``others`` called it, and earlier local names."""
        own = self.own_lang(kind, ref, turn)
        mine = self.name(kind, ref, own, turn)
        if mine is None:
            return None
        out = {"canonical": self._canonical(kind, ref), "kind": kind, "lang": own,
               "name": mine[0], "gloss": self.gloss(mine[1]), "others": [], "former": []}
        for lid in others:
            if lid == own:
                continue
            got = self.name(kind, ref, lid, turn)
            if got is not None and got[0] != mine[0]:
                out["others"].append((lid, got[0], self.gloss(got[1])))
        if kind == "region":
            seen = {own}
            for row_turn, lid in reversed(self.regions.get(ref, {}).get("speech") or []):
                if row_turn > turn or lid in seen:
                    continue
                seen.add(lid)
                got = self.name(kind, ref, lid, turn)
                if got is not None and got[0] != mine[0]:
                    out["former"].append((lid, got[0]))
        return out

    def _perspectives(self, entities: Sequence[tuple[str, Any]], turn: int) -> list[int]:
        langs: list[int] = []
        for kind, ref in entities:
            if kind == "civ":
                lid = self.civ_lang(ref, turn)
                if lid is not None and lid not in langs:
                    langs.append(lid)
        return langs

    # --- narration ------------------------------------------------------------

    def prompt_block(self, events: Sequence["Event"], turn: int, sheet=None) -> str:
        """Narrator prompt block: the moment's entities as their peoples name them.
        With ``sheet`` (``narration_provenance.FactSheet``) each line is
        registered and tagged with its fact id."""
        ents = self.entities(events)
        persp = self._perspectives(ents, turn)
        lines = []
        example = None
        for kind, ref in ents[: self.MAX_ENTITIES]:
            v = self.views(kind, ref, turn, persp)
            if v is None or (v["name"] == v["canonical"] and not v["others"]):
                continue
            if example is None:
                example = f"{v['name']}, the {v['canonical']}"
            gloss = f", '{v['gloss']}'" if v["gloss"] else ""
            lead = "they call themselves" if kind == "civ" else "its people say"
            if kind == "person":
                lead = "in their own tongue"
            parts = [f"{lead} \"{v['name']}\" ({self.lang_name(v['lang'])}{gloss})"]
            for lid, form, g in v["others"][:2]:
                parts.append(f"{self.lang_name(lid)} \"{form}\"" + (f" ('{g}')" if g and kind == "civ" else ""))
            for lid, form in v["former"][:1]:
                parts.append(f"formerly \"{form}\" ({self.lang_name(lid)})")
            line = f"- {v['canonical']}: " + "; ".join(parts)
            if sheet is not None:
                line = sheet.line(line, [(sheet.ids.names_entity(kind, ref), turn)])
            lines.append(line)
        if not lines:
            return ""
        head = ("\n\nIN-WORLD NAMES (what the peoples of these events call themselves, each other "
                "and their lands; the names above stay authoritative. To tell part of the story "
                "from a people's perspective, use their names and gloss the canonical one at "
                f"first use, e.g. \"{example}\"):\n")
        return head + "\n".join(lines) + "\n"

    def passage(self, events: Sequence["Event"], turn: int, glossed: set | None = None,
                limit: int = 2) -> str:
        """Mechanical chronicle text ("In their own tongues: ..."); each entity once per chronicle."""
        parts = self.passage_parts(events, turn, glossed, limit)
        return " ".join(text for text, _kind, _ref, _record in parts)

    def passage_parts(self, events: Sequence["Event"], turn: int, glossed: set | None = None,
                      limit: int = 2) -> list[tuple[str, str, Any, str]]:
        """``passage`` as its sentences, each with the entity it glosses and
        the names-bearing text of that entity's names (the first sentence
        led by "In their own tongues: ")."""
        glossed = set() if glossed is None else glossed
        ents = self.entities(events)
        persp = self._perspectives(ents, turn)
        parts = []
        out: list[tuple[str, str, Any, str]] = []
        for kind, ref in ents:
            if len(parts) >= limit:
                break
            if (kind, ref) in glossed or kind not in ("civ", "region"):
                continue
            v = self.views(kind, ref, turn, persp)
            if v is None or v["name"] == v["canonical"]:
                continue
            glossed.add((kind, ref))
            g = f" ('{v['gloss']}')" if v["gloss"] else ""
            if kind == "civ":
                text = f"{v['canonical']}, {v['name']} to themselves{g}"
            else:
                text = f"{v['canonical']}, {v['name']} in {self.lang_name(v['lang'])}{g}"
            for lid, form, _g in v["others"][:1]:
                text += f", {form} in {self.lang_name(lid)}"
            for lid, form in v["former"][:1]:
                text += f", once {form} in {self.lang_name(lid)}"
            parts.append(text + ".")
            record = [v["canonical"], v["name"], self.lang_name(v["lang"]), v["gloss"] or ""]
            for lid, form, g in v["others"]:
                record += [form, self.lang_name(lid), g or ""]
            for lid, form in v["former"]:
                record += [form, self.lang_name(lid)]
            out.append((text + ".", kind, ref, " | ".join(r for r in record if r)))
        if out:
            out[0] = ("In their own tongues: " + out[0][0], *out[0][1:])
        return out

    def localize(self, text: str, lang: int | None, turn: int) -> str:
        """Canonical names in ``text`` as ``lang`` said them at ``turn``: "Ashkel Vor
        [Verdant Plains]" at first mention, the native name after."""
        if lang is None or self._pattern is None or not text:
            return text
        seen: set = set()

        def repl(m: re.Match) -> str:
            canon = m.group(0)
            found = self.lookup(canon, turn)
            got = self.name(found[0], found[1], lang, turn) if found else None
            if got is None or got[0] == canon:
                return canon
            if found in seen:
                return got[0]
            seen.add(found)
            return f"{got[0]} [{canon}]"

        return self._pattern.sub(repl, text)

    def chronicler_lang(self, chronicler: str, turn: int) -> int | None:
        """The language a historiography chronicler writes in: its court's, or its faith's."""
        kind, _, ref = chronicler.partition(":")
        if not ref.isdigit():
            return None
        if kind == "court":
            return self.civ_lang(int(ref), turn)
        if kind == "temple":
            return self.own_lang("faith", int(ref), turn)
        return None

    def localize_account(self, row: dict) -> str:
        """A historiography account's text in its chronicler's own names."""
        text = row.get("text") or ""
        turn = int(row.get("turn") or 0)
        return self.localize(text, self.chronicler_lang(row.get("chronicler", ""), turn), turn)
