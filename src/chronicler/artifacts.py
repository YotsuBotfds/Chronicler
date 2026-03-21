"""M52: Artifacts & Significant Items.

Central artifact logic: naming, creation, lifecycle, prestige computation.
Model types live in models.py; behavior lives here.
"""
from __future__ import annotations

from chronicler.models import (
    Artifact, ArtifactType, ArtifactStatus,
    ArtifactIntent, ArtifactLifecycleIntent, Event,
)

# --- Calibration constants [CALIBRATE M53] ---

CULTURAL_PRODUCTION_CHANCE = 0.15
GP_PRESTIGE_THRESHOLD = 50
RELIC_CONVERSION_BONUS = 0.15
PROSPERITY_STABILITY_THRESHOLD = 70
PROSPERITY_TREASURY_THRESHOLD = 20
HISTORY_CAP = 10

PRESTIGE_BY_TYPE = {
    ArtifactType.MONUMENT: 4,
    ArtifactType.RELIC: 3,
    ArtifactType.WEAPON: 2,
    ArtifactType.ARTWORK: 2,
    ArtifactType.TREATISE: 2,
    ArtifactType.MANIFESTO: 1,
    ArtifactType.TRADE_GOOD: 1,
}

# --- Naming vocabulary ---

_ADJECTIVES = {
    "Honor": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Strength": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Self-reliance": ["Iron", "Crimson", "Bloodforged", "Unyielding"],
    "Trade": ["Golden", "Gilded", "Silver-wrought", "Precious"],
    "Knowledge": ["Ancient", "Illuminated", "Sage", "Inscribed"],
    "Tradition": ["Ancestral", "Hallowed", "Timeless", "Venerable"],
    "Order": ["Sovereign", "Imperial", "Lawbound", "Exalted"],
    "Destiny": ["Sovereign", "Imperial", "Lawbound", "Exalted"],
    "Cunning": ["Shadow", "Veiled", "Serpentine", "Subtle"],
    "Piety": ["Sacred", "Blessed", "Radiant", "Divine"],
    "Freedom": ["Wild", "Untamed", "Windsworn", "Bold"],
    "Liberty": ["Wild", "Untamed", "Windsworn", "Bold"],
}
_DEFAULT_ADJECTIVES = ["Great", "Renowned", "Storied", "Fabled"]

_NOUNS = {
    ArtifactType.WEAPON: ["Blade", "Shield", "Banner", "Spear", "Standard"],
    ArtifactType.RELIC: ["Chalice", "Tome", "Seal", "Vessel", "Shard"],
    ArtifactType.MONUMENT: ["Pillar", "Arch", "Colossus", "Obelisk", "Gate"],
    ArtifactType.ARTWORK: ["Tapestry", "Mosaic", "Fresco", "Idol", "Mask"],
    ArtifactType.TREATISE: ["Codex", "Scrolls", "Commentaries", "Meditations"],
    ArtifactType.MANIFESTO: ["Manifesto", "Declarations", "Edicts", "Theses"],
    ArtifactType.TRADE_GOOD: ["Silk", "Jade", "Amber", "Ivory", "Incense"],
}

_TEMPLATES = {
    ArtifactType.RELIC: [
        "The Sacred {adj} of {place}",
        "The {adj} Relic of {creator}",
        "The Holy {noun} of {place}",
    ],
    ArtifactType.WEAPON: [
        "The {noun} of {creator}",
        "{adj} {noun}",
        "The Blade of {place}",
    ],
    ArtifactType.MONUMENT: [
        "The {adj} {noun} of {place}",
        "The Great {noun} of {place}",
        "{creator_poss} {noun}",
    ],
    ArtifactType.ARTWORK: [
        "The {adj} {noun}",
        "The {noun} of {place}",
        "{creator_poss} {adj} {noun}",
    ],
    ArtifactType.TREATISE: [
        "The {noun} of {creator}",
        "The {adj} Codex",
        "The Letters of {creator}",
    ],
    ArtifactType.MANIFESTO: [
        "The {adj} Manifesto",
        "The Declarations of {creator}",
        "{creator_poss} {noun}",
    ],
    ArtifactType.TRADE_GOOD: [
        "The {adj} {noun} of {place}",
        "{place} {noun}",
    ],
}


def _possessive(name: str) -> str:
    """Generate possessive form: Ashara -> Ashara's."""
    if name.endswith("s"):
        return f"{name}'"
    return f"{name}'s"


def generate_artifact_name(
    artifact_type: ArtifactType,
    creator_name: str | None,
    origin_region: str,
    civ_values: list[str],
    seed: int,
) -> str:
    """Generate a deterministic canonical artifact name."""
    import random as _random
    rng = _random.Random(seed)

    dominant_value = civ_values[0] if civ_values else None
    adjs = _ADJECTIVES.get(dominant_value, _DEFAULT_ADJECTIVES)
    nouns = _NOUNS[artifact_type]
    templates = _TEMPLATES[artifact_type]

    adj = rng.choice(adjs)
    noun = rng.choice(nouns)
    template = rng.choice(templates)

    creator = creator_name or origin_region
    creator_poss = _possessive(creator)
    place = origin_region

    name = template.format(
        adj=adj, noun=noun, creator=creator,
        creator_poss=creator_poss, place=place,
    )
    return name
