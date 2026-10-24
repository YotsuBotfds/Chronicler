"""Sound systems and regular sound change for the in-world languages layer.

Pure functions over segment strings: one character per segment (``θ`` for
"th", ``ʃ`` for "sh", ``ā`` for a long a, ``ə`` for schwa, ...), rendered for
display by :func:`roman`. Nothing here draws a simulation random number:
every choice is a ``stable_hash_int("languages", seed, ...)`` draw made by
the caller's keys. See docs/integration/languages.md.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

from pydantic import BaseModel, Field

from chronicler.utils import stable_hash_int

NAMESPACE = "languages"

# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

LONG = {"a": "ā", "e": "ē", "i": "ī", "o": "ō", "u": "ū"}
SHORT_OF = {v: k for k, v in LONG.items()}
SHORT_VOWELS = "aeiouə"
VOWELS = frozenset(SHORT_VOWELS + "āēīōū")
FRONT = frozenset("ieīē")
#: Consonant features: (place, manner, voiced).
CFEAT: dict[str, tuple[int, str, int]] = {
    "p": (0, "stop", 0), "b": (0, "stop", 1), "f": (0, "fric", 0), "v": (0, "fric", 1),
    "m": (0, "nasal", 1), "w": (0, "glide", 1),
    "θ": (1, "fric", 0), "ð": (1, "fric", 1),
    "t": (2, "stop", 0), "d": (2, "stop", 1), "s": (2, "fric", 0), "z": (2, "fric", 1),
    "ʦ": (2, "affr", 0), "n": (2, "nasal", 1), "l": (2, "lat", 1), "r": (2, "rho", 1),
    "ʃ": (3, "fric", 0), "ʒ": (3, "fric", 1), "ʧ": (3, "affr", 0), "ʤ": (3, "affr", 1),
    "j": (3, "glide", 1),
    "k": (4, "stop", 0), "g": (4, "stop", 1), "x": (4, "fric", 0), "ɣ": (4, "fric", 1),
    "ŋ": (4, "nasal", 1), "q": (5, "stop", 0), "h": (6, "fric", 0),
}
CONSONANTS = frozenset(CFEAT)
#: Vowel features: (height, backness).
VFEAT = {"i": (0, 0), "e": (1, 0), "a": (2, 1), "o": (1, 2), "u": (0, 2), "ə": (1, 1)}
_MANNER_COST = {
    frozenset(("stop", "affr")): 1.0, frozenset(("stop", "fric")): 1.5,
    frozenset(("fric", "affr")): 1.0, frozenset(("lat", "rho")): 1.0,
    frozenset(("nasal", "stop")): 2.0, frozenset(("glide", "lat")): 2.0,
}
ROMAN = {"θ": "th", "ð": "dh", "ʃ": "sh", "ʒ": "zh", "x": "kh", "ɣ": "gh", "ʦ": "ts",
         "ʧ": "ch", "ʤ": "j", "ŋ": "ng", "j": "y", "ə": "e"}
VOICE = {"p": "b", "t": "d", "k": "g", "f": "v", "θ": "ð", "s": "z", "ʃ": "ʒ", "x": "ɣ",
         "ʧ": "ʤ"}
DEVOICE = {v: k for k, v in VOICE.items()}
_SEGMENT_ORDER = {c: i for i, c in enumerate(SHORT_VOWELS + "āēīōū" + "".join(CFEAT))}


def unit(seed: int, *parts: object) -> float:
    """A namespaced deterministic draw in [0, 1) (never a simulation stream)."""
    return stable_hash_int(NAMESPACE, seed, *parts) / 2.0**64


def pick(items: Sequence, weights: Sequence[float], u: float):
    """The item a draw ``u`` in [0, 1) selects, by weight."""
    x = u * float(sum(weights))
    for item, w in zip(items, weights):
        x -= w
        if x < 0:
            return item
    return items[-1]


def seg_name(c: str) -> str:
    return ROMAN.get(c, c)


def sorted_segs(segs: Iterable[str]) -> str:
    return "".join(sorted(set(segs), key=lambda c: _SEGMENT_ORDER.get(c, 999)))


def roman(form: str, *, title: bool = True) -> str:
    """Display spelling: "θorn" -> "Thorn"; a glide after a vowel and not
    before one is written as a vowel ("kaj" -> "Kai")."""
    words = []
    for w in form.split(" "):
        out = []
        n = len(w)
        for i, ch in enumerate(w):
            if (ch in "jw" and i > 0 and w[i - 1] in VOWELS
                    and (i + 1 >= n or w[i + 1] not in VOWELS)):
                out.append("i" if ch == "j" else "u")
            else:
                out.append(ROMAN.get(ch, ch))
        s = "".join(out)
        words.append(s[:1].upper() + s[1:] if title else s)
    return " ".join(words)


_DIGRAPHS = (
    ("tch", "ʧ"), ("sch", "ʃ"), ("th", "θ"), ("dh", "ð"), ("sh", "ʃ"), ("zh", "ʒ"),
    ("kh", "x"), ("gh", "ɣ"), ("ch", "ʧ"), ("ph", "f"), ("ts", "ʦ"), ("tz", "ʦ"),
    ("ck", "k"), ("qu", "kw"), ("ee", "ī"), ("oo", "ū"), ("aa", "ā"), ("ii", "ī"),
    ("uu", "ū"), ("ae", "ē"),
)


def parse_stem(text: str) -> str:
    """An English-spelled proper stem as segments: "Thornwall" -> "θornwal"."""
    s = "".join(ch for ch in text.lower() if "a" <= ch <= "z")
    out: list[str] = []
    i = 0
    while i < len(s):
        for dg, seg in _DIGRAPHS:
            if s.startswith(dg, i):
                out.extend(seg)
                i += len(dg)
                break
        else:
            ch = s[i]
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if ch == "n" and nxt == "g" and (i + 2 >= len(s) or s[i + 2] not in "aeiouy"):
                out.append("ŋ")
                i += 2
                continue
            if ch == "c":
                out.append("s" if nxt in ("e", "i", "y") else "k")
            elif ch == "y":
                out.append("j" if nxt in ("a", "e", "i", "o", "u") else "i")
            elif ch == "x":
                out.extend("ks")
            elif ch == "j":
                out.append("ʤ")
            else:
                out.append(ch)
            i += 1
    # Doubled consonants are written, not spoken; i/u after a vowel and
    # before a consonant are glides ("Tamurai" -> tamuraj).
    segs: list[str] = []
    for k, ch in enumerate(out):
        if segs and ch == segs[-1] and ch in CONSONANTS:
            continue
        if (ch in "iu" and segs and segs[-1] in "aeo"
                and (k + 1 >= len(out) or out[k + 1] not in VOWELS)):
            segs.append("j" if ch == "i" else "w")
            continue
        segs.append(ch)
    return "".join(segs) or "a"


# ---------------------------------------------------------------------------
# Phonology and phonotactics
# ---------------------------------------------------------------------------


class Phonology(BaseModel):
    """A language's sound system (segment strings in a fixed order)."""
    consonants: str
    vowels: str
    onsets: list[str] = Field(default_factory=list)       # two-consonant onsets
    codas: str = ""                                        # word-internal codas
    finals: str = ""                                       # word-final consonants
    final_clusters: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=lambda: ["CV", "CVC"])
    weights: list[int] = Field(default_factory=lambda: [1, 1])
    stress: str = "initial"     # initial, penult
    order: str = "mh"           # mh: modifier-head ("green plain"); hm: head-modifier
    join: str = "word"          # word: compounds are one word; space: "Ashkel Vor"
    link: str = "a"             # epenthetic / linking vowel
    repair: str = "epenthesis"  # or deletion


def runs(w: str) -> list[tuple[int, int, bool]]:
    """(start, end, vowel?) runs of a word."""
    out: list[tuple[int, int, bool]] = []
    i = 0
    n = len(w)
    while i < n:
        v = w[i] in VOWELS
        j = i + 1
        while j < n and (w[j] in VOWELS) == v:
            j += 1
        out.append((i, j, v))
        i = j
    return out


def problem(w: str, ph: Phonology) -> tuple[str, int] | None:
    """The first phonotactic violation of a word: (kind, index) or None."""
    rs = runs(w)
    if not any(v for _, _, v in rs):
        return ("novowel", len(w))
    for k, (a, b, v) in enumerate(rs):
        if v:
            continue
        c = w[a:b]
        if k == 0:
            if len(c) == 1 or (len(c) == 2 and c in ph.onsets):
                continue
            return ("initial", a)
        if k == len(rs) - 1:
            if (len(c) == 1 and c in ph.finals) or (len(c) == 2 and c in ph.final_clusters):
                continue
            return ("final", a)
        if len(c) == 1:
            continue
        if len(c) == 2 and (c[0] in ph.codas or c in ph.onsets):
            continue
        if len(c) == 3 and c[0] in ph.codas and c[1:] in ph.onsets:
            continue
        return ("medial", a)
    return None


def repair(w: str, ph: Phonology) -> str:
    """Make a word legal: epenthesis of the linking vowel, or deletion."""
    segs = list(w)
    for _ in range(16):
        word = "".join(segs)
        found = problem(word, ph)
        if found is None:
            return word
        kind, i = found
        if kind == "novowel":
            segs.append(ph.link)
        elif kind == "initial":
            if ph.repair == "deletion":
                del segs[0]
            else:
                segs.insert(1, ph.link)
        elif kind == "medial":
            if ph.repair == "deletion":
                del segs[i]
            else:
                segs.insert(i + 1, ph.link)
        elif ph.repair == "deletion" and len(segs) > 2:
            del segs[-1]
        else:
            segs.append(ph.link)
    return "".join(segs)


def _cdist(a: str, b: str) -> float:
    pa, ma, va = CFEAT[a]
    pb, mb, vb = CFEAT[b]
    manner = 0.0 if ma == mb else _MANNER_COST.get(frozenset((ma, mb)), 3.0)
    return abs(pa - pb) + manner + 0.75 * abs(va - vb)


def _vdist(a: str, b: str) -> float:
    ha, ba = VFEAT[SHORT_OF.get(a, a)]
    hb, bb = VFEAT[SHORT_OF.get(b, b)]
    return abs(ha - hb) + abs(ba - bb) + 0.5 * ((a in SHORT_OF) != (b in SHORT_OF))


def nearest(seg: str, ph: Phonology) -> str:
    """The language's closest segment ("" drops it)."""
    if seg in VOWELS:
        if seg in ph.vowels:
            return seg
        return min(ph.vowels, key=lambda v: (_vdist(seg, v), ph.vowels.index(v)))
    if seg in ph.consonants:
        return seg
    if seg in "jw":
        return nearest("i" if seg == "j" else "u", ph)
    if seg == "h":
        for alt in ("x", "ɣ", "k"):
            if alt in ph.consonants:
                return alt
        return ""
    if seg not in CFEAT:
        return ""
    return min(ph.consonants, key=lambda c: (_cdist(seg, c), ph.consonants.index(c)))


def adapt(form: str, ph: Phonology, *, max_syllables: int | None = None) -> str:
    """A foreign form as this language would say it (each word repaired;
    with ``max_syllables``, each word cut to that many syllables)."""
    words = []
    for w in form.split(" "):
        mapped = "".join(nearest(s, ph) for s in w)
        word = repair(mapped or ph.link, ph)
        if max_syllables is not None:
            word = cap_syllables(word, max_syllables, ph)
        words.append(word)
    return " ".join(words)


def syllables(w: str) -> list[int]:
    return [i for i, ch in enumerate(w) if ch in VOWELS]


def stressed(w: str, ph: Phonology) -> int:
    nuclei = syllables(w)
    if not nuclei:
        return -1
    if ph.stress == "penult" and len(nuclei) >= 2:
        return nuclei[-2]
    return nuclei[0]


def join_morphs(forms: Sequence[str], ph: Phonology) -> str:
    """Compound morphemes into one word, repairing the junctions."""
    word = ""
    for f in forms:
        if word and word[-1] == f[0] and f[0] in VOWELS:
            word = word[:-1] + (LONG[f[0]] if f[0] in LONG and LONG[f[0]] in ph.vowels else f[0])
            f = f[1:]
        elif word and word[-1] == f[0]:
            f = f[1:]
        word += f
    return repair(word, ph)


def profile(ph: Phonology, forms: Iterable[str], *, keep: bool = True) -> Phonology:
    """The sound system observed in ``forms`` (with ``keep``, merged into ``ph``)."""
    cons, vowels = set(), set()
    onsets, codas, finals, fclusters = set(), set(), set(), set()
    for form in forms:
        for w in form.split(" "):
            for ch in w:
                (vowels if ch in VOWELS else cons).add(ch)
            rs = runs(w)
            for k, (a, b, v) in enumerate(rs):
                if v:
                    continue
                c = w[a:b]
                if k == 0:
                    if len(c) == 2:
                        onsets.add(c)
                elif k == len(rs) - 1:
                    if len(c) == 1:
                        finals.add(c)
                    elif len(c) == 2:
                        fclusters.add(c)
                elif len(c) >= 2:
                    codas.add(c[0])
    cons &= CONSONANTS
    if keep:
        cons |= set(ph.consonants)
        vowels |= set(ph.vowels)
        onsets |= set(ph.onsets)
        codas |= set(ph.codas)
        finals |= set(ph.finals)
        fclusters |= set(ph.final_clusters)
    return ph.model_copy(update=dict(
        consonants=sorted_segs(cons), vowels=sorted_segs(vowels), onsets=sorted(onsets),
        codas=sorted_segs(codas & cons), finals=sorted_segs(finals & cons),
        final_clusters=sorted(fclusters)))


# ---------------------------------------------------------------------------
# Proto-languages
# ---------------------------------------------------------------------------

#: Phonological styles of founding cultures (the keys of geography.PHONOLOGIES).
STYLES: dict[str, dict[str, Any]] = {
    "maritime": dict(core="ptkmnslr", extra="bdgθvhwj", vowels="aeiou", long=0.3,
                     onsets=("pr", "tr", "kr", "pl", "kl", "θr"), codas="nslr", finals="nsl",
                     templates={"CV": 6, "CVC": 3, "V": 1, "CCV": 1}),
    "steppe": dict(core="tkbdgmnsr", extra="qxʃʧjʤlh", vowels="aeiou", long=0.15,
                   onsets=(), codas="nrlsktm", finals="nrlsk",
                   templates={"CV": 4, "CVC": 5, "V": 1}),
    "mountain": dict(core="ptkbdgmnrs", extra="θhvxl", vowels="aeiou", long=0.2,
                     onsets=("gr", "dr", "kr", "br", "st", "sk", "tr"), codas="rnmlks",
                     finals="rnmkdlt", templates={"CVC": 5, "CCVC": 2, "CV": 3}),
    "forest": dict(core="lsnrmt", extra="fvθwgdkj", vowels="aeiou", long=0.4,
                   onsets=("fl", "sl", "gl", "θr"), codas="lnrs", finals="lnrs",
                   templates={"CV": 5, "CVC": 3, "V": 2}),
    "desert": dict(core="kzʃrmdsh", extra="qxbtnlj", vowels="aiu", long=0.6,
                   onsets=(), codas="rmnsʃdh", finals="rdnmh",
                   templates={"CV": 4, "CVC": 5}),
    "jungle": dict(core="ptkmnʦʧ", extra="xljwhs", vowels="aeiou", long=0.1,
                   onsets=(), codas="nl", finals="nl", templates={"CV": 7, "CVC": 2, "V": 1}),
    "marsh": dict(core="bmwfhsdl", extra="gnrtkp", vowels="aeiou", long=0.25,
                  onsets=("bl", "br", "gl", "fl"), codas="rnlmk", finals="rnlmk",
                  templates={"CVC": 5, "CV": 4}),
    "tundra": dict(core="kvhstrn", extra="bfjgdml", vowels="aeiou", long=0.3,
                   onsets=("sk", "br", "fr", "st"), codas="rnlkg", finals="rnlkd",
                   templates={"CVC": 4, "CV": 4, "CCVC": 1}),
}


def proto_phonology(seed: int, key: object, style: str) -> Phonology:
    """A proto-language's sound system, drawn from its culture's style."""
    st = STYLES[style]

    def u(*p: object) -> float:
        return unit(seed, "proto", key, *p)

    cons = set(st["core"]) | {c for c in st["extra"] if u("c", c) < 0.45}
    if u("drop") < 0.5 and len(cons) > 7:  # one core consonant missing
        order = sorted_segs(cons)
        cons.discard(order[int(u("dropc") * len(order))])
    vowels = set(st["vowels"])
    if len(vowels) == 5 and u("three") < 0.15:
        vowels = {"a", "i", "u"}
    if u("long") < st["long"]:
        vowels |= {LONG[v] for v in sorted_segs(vowels) if v in LONG and u("lv", v) < 0.6}
    onsets = [o for o in st["onsets"] if all(c in cons for c in o) and u("o", o) < 0.7]
    codas = "".join(c for c in st["codas"] if c in cons)
    finals = "".join(c for c in st["finals"] if c in cons and u("f", c) < 0.8)
    if u("open") < 0.2:
        finals = ""   # an open-syllable language: every word ends in a vowel
    templates = list(st["templates"])
    weights = [st["templates"][t] for t in templates]
    keep = [(t, w) for t, w in zip(templates, weights)
            if (onsets or "CC" not in t) and (codas or not t.endswith("C"))]
    templates, weights = ([t for t, _ in keep], [w for _, w in keep]) if keep else (["CV"], [1])
    short = [v for v in sorted_segs(vowels) if v in "aeiou"]
    link = "a" if "a" in vowels else short[0]
    if u("link") < 0.4:
        link = short[int(u("linkv") * len(short))]
    return Phonology(
        consonants=sorted_segs(cons), vowels=sorted_segs(vowels), onsets=sorted(onsets),
        codas=sorted_segs(codas), finals=sorted_segs(finals), templates=templates,
        weights=weights, stress="penult" if u("stress") < 0.4 else "initial",
        order="hm" if u("order") < 0.35 else "mh", join="space" if u("join") < 0.4 else "word",
        link=link, repair="deletion" if u("repair") < 0.3 else "epenthesis",
    )


def cap_syllables(w: str, n: int, ph: Phonology) -> str:
    """Cut a word after its ``n``-th syllable (keeping a legal coda), repaired."""
    nuclei = syllables(w)
    if len(nuclei) <= n:
        return w
    cut = nuclei[n]  # the next nucleus; keep at most one consonant before it
    end = nuclei[n - 1] + 1
    if end < cut and w[end] in ph.finals:
        end += 1
    return repair(w[:end], ph)


def make_root(seed: int, key: object, ph: Phonology, meaning: str, taken: set[str], *,
              short: bool = False, mono: bool = False) -> str:
    """A new root for ``meaning`` from the syllable templates, unique in ``taken``.

    ``short`` roots (basic vocabulary) are more often one syllable; ``mono``
    roots (suffix-like morphemes: people, town, ...) always are.
    """
    cons = ph.consonants
    vowels = ph.vowels
    vweights = [1.0 if v in SHORT_VOWELS else 0.35 for v in vowels]
    word = ""
    for attempt in range(12):
        def u(*p: object) -> float:
            return unit(seed, "root", key, meaning, attempt, *p)

        x = u("n")
        n = 1 if mono or x < (0.4 if short else 0.2) else (2 if x < 0.97 else 3)
        parts = []
        for s in range(n):
            t = pick(ph.templates, ph.weights, u("t", s))
            syl = ""
            if t.startswith("CC") and ph.onsets:
                syl += ph.onsets[int(u("cc", s) * len(ph.onsets))]
            elif t.startswith("C"):
                syl += cons[int(u("c", s) * len(cons))]
            syl += pick(vowels, vweights, u("v", s))
            pool = ph.finals if s == n - 1 else ph.codas
            # A one-syllable root is heavy where the language allows it.
            if pool and ((t.endswith("C") and u("k", s) < 0.85) or (n == 1 and u("h", s) < 0.7)):
                syl += pool[int(u("kc", s) * len(pool))]
            parts.append(syl)
        word = repair("".join(parts), ph)
        if word not in taken and len(word) >= 2:
            taken.add(word)
            return word
    word = repair(word + ph.link + cons[0] + ph.link, ph)
    taken.add(word)
    return word


# ---------------------------------------------------------------------------
# Sound change
# ---------------------------------------------------------------------------


class Rule:
    """One regular sound change: ``fn`` maps a word (no spaces) to its new form.

    ``removes`` are segments the change eliminates everywhere; ``clears``
    names phonotactic slots it empties (onsets, codas); ``finals_remove``
    are consonants that can no longer end a word.
    """

    __slots__ = ("rid", "desc", "fn", "removes", "clears", "finals_remove")

    def __init__(self, rid: str, desc: str, fn: Callable[[str], str], *,
                 removes: Iterable[str] = (), clears: Iterable[str] = (),
                 finals_remove: Iterable[str] = ()) -> None:
        self.rid = rid
        self.desc = desc
        self.fn = fn
        self.removes = frozenset(removes)
        self.clears = frozenset(clears)
        self.finals_remove = frozenset(finals_remove)

    def apply(self, form: str) -> str:
        return " ".join(self.fn(w) if len(w) >= 2 else w for w in form.split(" "))

    def update(self, ph: Phonology, forms: Iterable[str]) -> Phonology:
        """The sound system after this change: what it removed, plus what ``forms`` show."""
        keep = ph.model_copy(update=dict(
            consonants=sorted_segs(set(ph.consonants) - self.removes),
            vowels=sorted_segs(set(ph.vowels) - self.removes),
            onsets=[] if "onsets" in self.clears else
            [o for o in ph.onsets if not set(o) & self.removes],
            codas="" if "codas" in self.clears else
            sorted_segs(set(ph.codas) - self.removes),
            finals=sorted_segs(set(ph.finals) - self.removes - self.finals_remove),
            final_clusters=[c for c in ph.final_clusters if not set(c) & self.removes],
        ))
        new = profile(keep, forms)
        if not new.vowels:
            new = new.model_copy(update={"vowels": ph.vowels})
        if new.link not in new.vowels:
            short = [v for v in new.vowels if v in "aeiou"] or list(new.vowels)
            new = new.model_copy(update={"link": short[0]})
        return new


def _list(segs: Iterable[str]) -> str:
    return " ".join(seg_name(s) for s in segs)


def _map_desc(mapping: dict[str, str]) -> str:
    keys = list(mapping)
    return f"{_list(keys)} > {_list(mapping[k] for k in keys)}"


def _between_vowels(mapping: dict[str, str]) -> Callable[[str], str]:
    def fn(w: str) -> str:
        out = list(w)
        for i in range(1, len(w) - 1):
            if w[i] in mapping and w[i - 1] in VOWELS and w[i + 1] in VOWELS:
                out[i] = mapping[w[i]]
        return "".join(out)
    return fn


def _everywhere(mapping: dict[str, str]) -> Callable[[str], str]:
    def fn(w: str) -> str:
        return "".join(mapping.get(c, c) for c in w)
    return fn


def _keep_vowel(fn: Callable[[str], str]) -> Callable[[str], str]:
    """Guard a deleting change: a word keeps a vowel and two segments."""
    def guarded(w: str) -> str:
        new = fn(w)
        if len(new) < 2 or not any(c in VOWELS for c in new):
            return w
        return new
    return guarded


def rules(ph: Phonology) -> list[tuple[Rule, float]]:
    """The candidate sound changes for a sound system, in a fixed order, with weights."""
    cons, vowels = set(ph.consonants), set(ph.vowels)
    out: list[tuple[Rule, float]] = []

    def add(rule: Rule, weight: float) -> None:
        out.append((rule, weight))

    m = {c: VOICE[c] for c in "ptk" if c in cons}
    if m:
        add(Rule("lenition", f"{_map_desc(m)} between vowels", _between_vowels(m)), 3.0)
    m = {c: s for c, s in (("b", "v"), ("d", "ð"), ("g", "ɣ")) if c in cons}
    if m:
        add(Rule("spirantization", f"{_map_desc(m)} between vowels", _between_vowels(m)), 2.0)
    m = {c: DEVOICE[c] for c in "bdgvzðɣʒʤ" if c in cons}
    if m and any(c in ph.finals for c in m):
        def devoice(w: str, m=m) -> str:
            return w[:-1] + m[w[-1]] if w[-1] in m else w
        add(Rule("final_devoicing", f"{_map_desc(m)} at the end of a word", devoice,
                 finals_remove=m), 2.0)
    m = {c: s for c, s in (("k", "ʧ"), ("g", "ʤ")) if c in cons}
    if m and vowels & FRONT:
        def palatal(w: str, m=m) -> str:
            return "".join(m[c] if c in m and i + 1 < len(w) and w[i + 1] in FRONT else c
                           for i, c in enumerate(w))
        add(Rule("palatalization", f"{_map_desc(m)} before i and e", palatal), 2.0)
    if "t" in cons and ("i" in vowels or "ī" in vowels):
        def assib(w: str) -> str:
            return "".join("ʦ" if c == "t" and i + 1 < len(w) and w[i + 1] in "iī" else c
                           for i, c in enumerate(w))
        add(Rule("assibilation", "t > ts before i", assib), 1.0)
    if "s" in cons and ("i" in vowels or "ī" in vowels):
        def spal(w: str) -> str:
            return "".join("ʃ" if c == "s" and i + 1 < len(w) and w[i + 1] in "iī" else c
                           for i, c in enumerate(w))
        add(Rule("s_palatalization", "s > sh before i", spal), 1.0)
    um = {"a": "e", "o": "e", "u": "i", "ā": "ē", "ō": "ē", "ū": "ī"}
    if "i" in vowels and "e" in vowels:
        def umlaut(w: str) -> str:
            nuclei = syllables(w)
            res = list(w)
            for k, nxt in zip(nuclei, nuclei[1:]):
                if w[nxt] in "iī" and w[k] in um:
                    res[k] = um[w[k]]
            return "".join(res)
        add(Rule("umlaut", "a o u > e e i when the next syllable has i", umlaut), 1.0)
    m = {v: r for v, r in (("ē", "ī"), ("ō", "ū")) if v in vowels}
    if m:
        add(Rule("long_raising", _map_desc(m), _everywhere(m), removes=m), 1.0)
    if "ā" in vowels and "ō" not in vowels:
        add(Rule("long_backing", "ā > ō", _everywhere({"ā": "ō"}), removes="ā"), 0.7)
    m = {v: r for v, r in (("i", "e"), ("u", "o")) if v in vowels and r in vowels}
    if m and ph.codas:
        def lower(w: str, m=m) -> str:
            res = list(w)
            for i, c in enumerate(w):
                if c in m and i + 1 < len(w) and w[i + 1] in CONSONANTS and (
                        i + 2 >= len(w) or w[i + 2] in CONSONANTS):
                    res[i] = m[c]
            return "".join(res)
        add(Rule("lowering", f"{_map_desc(m)} in closed syllables", lower), 1.0)
    if "ə" not in vowels:
        def reduce_(w: str) -> str:
            nuclei = syllables(w)
            if len(nuclei) < 2:
                return w
            stress = stressed(w, ph)
            res = list(w)
            for k in nuclei:
                if k != stress and k != 0 and w[k] in "aeiou":
                    res[k] = "ə"
            return "".join(res)
        add(Rule("reduction", "unstressed vowels > e (schwa)", reduce_), 1.0)

    def apocope(w: str) -> str:
        if (len(syllables(w)) >= 2 and w[-1] in SHORT_VOWELS and len(w) >= 3
                and w[-2] in CONSONANTS and w[-3] in VOWELS):
            return w[:-1]
        return w
    add(Rule("apocope", "final short vowels are lost", apocope), 2.0)

    def syncope(w: str) -> str:
        nuclei = syllables(w)
        if len(nuclei) < 3:
            return w
        stress = stressed(w, ph)
        for k in nuclei[1:-1]:
            if (k != stress and w[k] in SHORT_VOWELS and 2 <= k <= len(w) - 3
                    and w[k - 1] in CONSONANTS and w[k + 1] in CONSONANTS
                    and w[k - 2] in VOWELS and w[k + 2] in VOWELS):
                return w[:k] + w[k + 1:]
        return w
    add(Rule("syncope", "short unstressed vowels are lost between single consonants",
             _keep_vowel(syncope)), 1.5)
    if ph.codas:
        def simplify(w: str) -> str:
            res: list[str] = []
            for i, c in enumerate(w):
                if (c in CONSONANTS and 0 < i < len(w) - 2 and w[i - 1] in VOWELS
                        and w[i + 1] in CONSONANTS and w[i + 2] in VOWELS):
                    if res and res[-1] in LONG:
                        res[-1] = LONG[res[-1]]
                    continue
                res.append(c)
            return "".join(res)
        add(Rule("cluster_simplification",
                 "the first of two consonants is lost, lengthening the vowel before it",
                 simplify, clears=("codas",)), 1.5)
    if "n" in cons and (cons & set("pbfvkgxɣ")):
        def assim(w: str) -> str:
            res = list(w)
            for i in range(len(w) - 1):
                if w[i] == "n" and w[i + 1] in "pbfvm":
                    res[i] = "m"
                elif w[i] == "n" and w[i + 1] in "kgxɣ":
                    res[i] = "ŋ"
            return "".join(res)
        add(Rule("nasal_assimilation", "n > m before labials and ng before velars", assim), 1.0)
    if ph.onsets:
        def initial(w: str) -> str:
            if len(w) >= 3 and w[0] in CONSONANTS and w[1] in CONSONANTS:
                return w[1:]
            return w
        add(Rule("initial_simplification", "initial clusters lose their first consonant",
                 initial, clears=("onsets",)), 1.0)
    stops = sorted_segs(set("ptk") & set(ph.finals))
    if stops:
        def stop_loss(w: str, stops=stops) -> str:
            if len(syllables(w)) >= 2 and w[-1] in stops and w[-2] in VOWELS:
                return w[:-1]
            return w
        add(Rule("final_stop_loss", f"final {_list(stops)} are lost", stop_loss,
                 finals_remove=stops), 1.0)
    if "z" in cons:
        add(Rule("rhotacism", "z > r between vowels", _between_vowels({"z": "r"})), 1.0)
    if "h" in cons:
        add(Rule("h_loss", "h is lost", _keep_vowel(lambda w: w.replace("h", "")),
                 removes="h"), 1.0)
    if "s" in cons and "h" not in cons:
        def debucc(w: str) -> str:
            return "".join("h" if c == "s" and (i + 1 >= len(w) or w[i + 1] in CONSONANTS) else c
                           for i, c in enumerate(w))
        add(Rule("debuccalization", "s > h before consonants and at the end of a word",
                 debucc, finals_remove="s"), 1.0)
    m = {c: s for c, s in (("p", "f"), ("t", "θ"), ("k", "x")) if c in cons}
    if m:
        def initial_spirant(w: str, m=m) -> str:
            return m[w[0]] + w[1:] if w[0] in m and w[1] in VOWELS else w
        add(Rule("initial_spirantization", f"{_map_desc(m)} at the start of a word",
                 initial_spirant), 0.7)
    for src, dst in (("θ", "t"), ("ð", "d"), ("ɣ", "g"), ("x", "h"), ("ʃ", "s"), ("q", "k"),
                     ("ʦ", "s"), ("v", "w"), ("ʤ", "ʒ"), ("ŋ", "n")):
        if src in cons:
            add(Rule(f"merger_{seg_name(src)}", f"{seg_name(src)} > {seg_name(dst)}",
                     _everywhere({src: dst}), removes=src), 0.6)
    if "j" in cons or "w" in cons:
        mono = {"aj": "ē", "aw": "ō", "ej": "ī", "ow": "ū"}

        def monoph(w: str) -> str:
            res = []
            i = 0
            while i < len(w):
                pair = w[i:i + 2]
                if pair in mono and (i + 2 >= len(w) or w[i + 2] not in VOWELS):
                    res.append(mono[pair])
                    i += 2
                    continue
                res.append(w[i])
                i += 1
            return "".join(res)
        add(Rule("monophthongization", "ai au ei ou > ē ō ī ū", monoph), 1.5)
    m = {v: d for v, d in (("ē", "ej"), ("ō", "ow")) if v in vowels}
    if m:
        add(Rule("diphthongization", "ē ō > ei ou", _everywhere(m), removes=m), 0.5)
    if "o" in vowels and "u" in vowels:
        add(Rule("vowel_merger_o", "o > u", _everywhere({"o": "u"}), removes="o"), 0.5)
    if "e" in vowels and "i" in vowels:
        add(Rule("vowel_merger_e", "e > i", _everywhere({"e": "i"}), removes="e"), 0.5)
    if vowels & set(SHORT_OF):
        add(Rule("shortening", "long vowels shorten", _everywhere(SHORT_OF),
                 removes=SHORT_OF), 0.7)

    def lengthen(w: str) -> str:
        k = stressed(w, ph)
        if (k >= 0 and w[k] in LONG and k + 2 < len(w) and w[k + 1] in CONSONANTS
                and w[k + 2] in VOWELS):
            return w[:k] + LONG[w[k]] + w[k + 1:]
        return w
    add(Rule("lengthening", "stressed vowels lengthen in open syllables", lengthen), 0.4)
    if any(o.startswith("s") for o in ph.onsets):
        pro = "i" if "i" in vowels else ph.link

        def prothesis(w: str, pro=pro) -> str:
            if len(w) >= 3 and w[0] == "s" and w[1] in CONSONANTS:
                return pro + w
            return w
        add(Rule("prothesis", f"{seg_name(pro)}- is added before initial s + consonant",
                 prothesis), 0.5)
    if "w" in cons:
        def w_loss(w: str) -> str:
            return "".join(c for i, c in enumerate(w)
                           if not (c == "w" and i + 1 < len(w) and w[i + 1] in "ouōū"))
        add(Rule("w_loss", "w is lost before o and u", _keep_vowel(w_loss)), 0.5)
    return out


def rule_by_id(ph: Phonology, rid: str, desc: str | None = None) -> Rule | None:
    """The candidate change ``rid`` for this sound system (None when it has none)."""
    for rule, _w in rules(ph):
        if rule.rid == rid and (desc is None or rule.desc == desc):
            return rule
    return None


def choose_change(seed: int, key: object, ph: Phonology, roots: Sequence[str],
                  applied: set[str]) -> Rule | None:
    """Draw a sound change that alters at least two roots and was not applied before."""
    candidates = []
    for rule, weight in rules(ph):
        if f"{rule.rid}:{rule.desc}" in applied:
            continue
        changed = sum(1 for r in roots if rule.apply(r) != r)
        if changed >= 2:
            candidates.append((rule, weight))
    if not candidates:
        return None
    return pick([r for r, _ in candidates], [w for _, w in candidates], unit(seed, "change", key))
