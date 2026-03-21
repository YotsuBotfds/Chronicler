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


def _next_artifact_id(world) -> int:
    if not world.artifacts:
        return 1
    return max(a.artifact_id for a in world.artifacts) + 1


def _default_anchored(artifact_type: ArtifactType) -> bool:
    """Return default portability for a type."""
    if artifact_type == ArtifactType.MONUMENT:
        return True
    if artifact_type in (ArtifactType.WEAPON, ArtifactType.TRADE_GOOD,
                         ArtifactType.TREATISE, ArtifactType.MANIFESTO):
        return False
    if artifact_type == ArtifactType.RELIC:
        return True
    return False


def _add_history(artifact: Artifact, entry: str) -> None:
    """Append a history entry, capping at HISTORY_CAP."""
    artifact.history.append(entry)
    if len(artifact.history) > HISTORY_CAP:
        artifact.history = [artifact.history[0]] + artifact.history[-(HISTORY_CAP - 1):]


def tick_artifacts(world) -> list[Event]:
    """Phase 10: Process artifact intents, lifecycle, and prestige."""
    events: list[Event] = []
    existing_names = {a.name for a in world.artifacts}

    # 1. Process creation intents
    for intent in world._artifact_intents:
        anchored = intent.anchored if intent.anchored is not None else _default_anchored(intent.artifact_type)
        if intent.holder_name is not None:
            anchored = False

        civ = None
        for c in world.civilizations:
            if c.name == intent.civ_name:
                civ = c
                break
        civ_values = civ.values if civ else []
        base_seed = world.seed + world.turn + _next_artifact_id(world)

        name = generate_artifact_name(
            intent.artifact_type, intent.creator_name,
            intent.region_name, civ_values, seed=base_seed,
        )
        for salt in range(1, 3):
            if name not in existing_names:
                break
            name = generate_artifact_name(
                intent.artifact_type, intent.creator_name,
                intent.region_name, civ_values, seed=base_seed + salt * 7919,
            )
        if name in existing_names:
            suffix = 2
            while f"{name} {_roman(suffix)}" in existing_names:
                suffix += 1
            name = f"{name} {_roman(suffix)}"
        existing_names.add(name)

        artifact = Artifact(
            artifact_id=_next_artifact_id(world),
            name=name,
            artifact_type=intent.artifact_type,
            anchored=anchored,
            origin_turn=world.turn,
            origin_event=intent.context,
            origin_region=intent.region_name,
            creator_name=intent.creator_name,
            creator_civ=intent.civ_name,
            owner_civ=intent.civ_name,
            holder_name=intent.holder_name,
            holder_born_turn=intent.holder_born_turn,
            anchor_region=intent.region_name if anchored else None,
            prestige_value=PRESTIGE_BY_TYPE.get(intent.artifact_type, 1),
            status=ArtifactStatus.ACTIVE,
            history=[f"{intent.context}, turn {world.turn}"],
            mule_origin=intent.mule_origin,
        )
        world.artifacts.append(artifact)

        actors = [intent.creator_name or intent.civ_name, name]
        events.append(Event(
            turn=world.turn,
            event_type="artifact_created",
            actors=actors,
            description=f"{name} created by {intent.civ_name}",
            importance=6,
        ))

    # 2. Process lifecycle intents (Task 5)

    # 3. Holder lifecycle (Task 5)

    # 4. Compute ephemeral prestige
    world._artifact_prestige_by_civ = {}
    for a in world.artifacts:
        if a.status == ArtifactStatus.ACTIVE and a.owner_civ:
            world._artifact_prestige_by_civ[a.owner_civ] = (
                world._artifact_prestige_by_civ.get(a.owner_civ, 0) + a.prestige_value
            )

    # 5. Clear intents
    world._artifact_intents = []
    world._artifact_lifecycle_intents = []

    return events


def _roman(n: int) -> str:
    """Simple roman numeral for small collision suffixes."""
    numerals = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
                6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
    return numerals.get(n, str(n))
