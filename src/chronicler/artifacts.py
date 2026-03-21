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


def _find_gp(world, name: str, born_turn: int | None):
    """Find a GreatPerson by (name, born_turn) across all civs and retired list."""
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.name == name and gp.born_turn == born_turn:
                return gp
    for gp in getattr(world, 'retired_persons', []):
        if gp.name == name and gp.born_turn == born_turn:
            return gp
    return None


def _process_conquest(world, intent: ArtifactLifecycleIntent, events: list) -> None:
    """Handle artifact transfers on conquest or twilight absorption."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE:
            continue
        if a.holder_name is not None:
            continue
        if a.anchored and a.anchor_region == intent.region:
            if intent.is_destructive:
                a.status = ArtifactStatus.DESTROYED
                a.owner_civ = None
                _add_history(a, f"Destroyed during the sack of {intent.region}, turn {world.turn}")
                events.append(Event(
                    turn=world.turn, event_type="artifact_destroyed",
                    actors=[intent.gaining_civ or "unknown", a.name],
                    description=f"{a.name} destroyed in {intent.region}",
                    importance=7,
                ))
            else:
                a.owner_civ = intent.gaining_civ
                _add_history(a, f"Claimed by {intent.gaining_civ} after the fall of {intent.region}, turn {world.turn}")
            continue
        if not a.anchored and a.owner_civ == intent.losing_civ:
            if intent.is_capital or intent.is_full_absorption:
                a.owner_civ = intent.gaining_civ
                _add_history(a, f"Captured by {intent.gaining_civ} during the fall of {intent.region}, turn {world.turn}")
                events.append(Event(
                    turn=world.turn, event_type="artifact_captured",
                    actors=[intent.gaining_civ, intent.losing_civ, a.name],
                    description=f"{a.name} captured by {intent.gaining_civ}",
                    importance=7,
                ))


def _process_civ_destruction(world, intent: ArtifactLifecycleIntent, events: list) -> None:
    """Handle artifacts when a civ is destroyed without absorber."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE or a.owner_civ != intent.losing_civ:
            continue
        if a.holder_name is not None:
            gp = _find_gp(world, a.holder_name, a.holder_born_turn)
            if gp and gp.active:
                continue
        a.status = ArtifactStatus.LOST
        a.owner_civ = None
        a.holder_name = None
        a.holder_born_turn = None
        _add_history(a, f"Lost when {intent.losing_civ} fell, turn {world.turn}")
        events.append(Event(
            turn=world.turn, event_type="artifact_lost",
            actors=[intent.losing_civ, a.name],
            description=f"{a.name} lost when {intent.losing_civ} fell",
            importance=6,
        ))


def _process_holder_lifecycle(world, events: list) -> None:
    """Check character-held artifacts for inactive holders."""
    for a in world.artifacts:
        if a.status != ArtifactStatus.ACTIVE or a.holder_name is None:
            continue
        gp = _find_gp(world, a.holder_name, a.holder_born_turn)
        if gp is None or not gp.active:
            revert_civ = gp.civilization if gp else a.owner_civ
            fate = gp.fate if gp else "unknown fate"
            holder_name = a.holder_name

            if a.mule_origin:
                events.append(Event(
                    turn=world.turn, event_type="mule_artifact_relinquished",
                    actors=[holder_name, revert_civ or "", a.name],
                    description=f"{a.name} relinquished after {holder_name}'s {fate}",
                    importance=7,
                ))

            _add_history(a, f"Returned to {revert_civ} after {holder_name}'s {fate}, turn {world.turn}")
            a.holder_name = None
            a.holder_born_turn = None
            a.owner_civ = revert_civ


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

    # 2. Process lifecycle intents
    for intent in world._artifact_lifecycle_intents:
        if intent.action == "conquest_transfer":
            _process_conquest(world, intent, events)
        elif intent.action == "twilight_absorption":
            _process_conquest(world, intent, events)  # same rules
        elif intent.action == "civ_destruction":
            _process_civ_destruction(world, intent, events)

    # 2b. Auto-detect dead civs with active artifacts not already handled
    for civ in world.civilizations:
        if len(civ.regions) == 0:
            has_active = any(
                a.status == ArtifactStatus.ACTIVE and a.owner_civ == civ.name
                for a in world.artifacts
            )
            if has_active:
                already_handled = any(
                    intent.losing_civ == civ.name
                    for intent in world._artifact_lifecycle_intents
                )
                if not already_handled:
                    emit_civ_destruction_intent(world, civ.name)
                    _process_civ_destruction(
                        world, world._artifact_lifecycle_intents[-1], events,
                    )

    # 3. Holder lifecycle — check for inactive holders
    _process_holder_lifecycle(world, events)

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


_GP_ROLE_TO_ARTIFACT = {
    "general": (ArtifactType.WEAPON, True),
    "prophet": (ArtifactType.RELIC, False),
    "merchant": (ArtifactType.ARTWORK, False),
    "scientist": (ArtifactType.TREATISE, False),
}


def emit_gp_artifact_intent(world, civ, gp) -> None:
    """Emit artifact creation intent for a newly promoted GP, if prestige threshold is met."""
    if civ.prestige < GP_PRESTIGE_THRESHOLD:
        return
    mapping = _GP_ROLE_TO_ARTIFACT.get(gp.role)
    if mapping is None:
        return

    artifact_type, character_held = mapping
    region = gp.origin_region or civ.capital_region or (civ.regions[0] if civ.regions else "unknown")

    world._artifact_intents.append(ArtifactIntent(
        artifact_type=artifact_type,
        trigger="gp_promotion",
        creator_name=gp.name,
        creator_born_turn=gp.born_turn,
        holder_name=gp.name if character_held else None,
        holder_born_turn=gp.born_turn if character_held else None,
        civ_name=civ.name,
        region_name=region,
        anchored=None,
        context=f"Created at the rise of {gp.name}",
    ))


def emit_mule_artifact_intent(world, civ, gp, action_name: str) -> None:
    """Emit Mule artifact intent on first matching action success."""
    from chronicler.action_engine import MULE_ACTIVE_WINDOW
    if not gp.mule or not gp.active or gp.mule_artifact_created:
        return
    age = world.turn - gp.born_turn
    if age > MULE_ACTIVE_WINDOW:
        return

    if gp.utility_overrides.get(action_name, 1.0) <= 1.0:
        return

    _MULE_ACTION_ARTIFACTS = {
        ("general", "WAR"): ArtifactType.RELIC,
        ("general", "DEVELOP"): ArtifactType.TREATISE,
        ("merchant", "TRADE"): ArtifactType.TRADE_GOOD,
        ("merchant", "FUND_INSTABILITY"): ArtifactType.MANIFESTO,
        ("prophet", "BUILD"): ArtifactType.RELIC,
        ("scientist", "DEVELOP"): ArtifactType.TREATISE,
    }
    artifact_type = _MULE_ACTION_ARTIFACTS.get((gp.role, action_name))
    if artifact_type is None:
        return

    region = gp.origin_region or civ.capital_region or (civ.regions[0] if civ.regions else "unknown")
    world._artifact_intents.append(ArtifactIntent(
        artifact_type=artifact_type,
        trigger="mule_action",
        creator_name=gp.name,
        creator_born_turn=gp.born_turn,
        holder_name=gp.name,
        holder_born_turn=gp.born_turn,
        civ_name=civ.name,
        region_name=region,
        anchored=None,
        mule_origin=True,
        context=f"Born of {gp.name}'s influence over {civ.name}",
    ))
    gp.mule_artifact_created = True


def emit_conquest_lifecycle_intent(
    world, losing_civ: str, gaining_civ: str, region: str,
    is_capital: bool, is_destructive: bool,
) -> None:
    """Emit a lifecycle intent for conquest or twilight absorption."""
    losing = None
    for c in world.civilizations:
        if c.name == losing_civ:
            losing = c
            break
    is_full = losing is not None and len(losing.regions) == 0

    world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
        action="conquest_transfer",
        losing_civ=losing_civ,
        gaining_civ=gaining_civ,
        region=region,
        is_capital=is_capital,
        is_full_absorption=is_full,
        is_destructive=is_destructive,
    ))


def emit_civ_destruction_intent(world, civ_name: str) -> None:
    """Emit lifecycle intent when a civ reaches zero regions without absorber."""
    world._artifact_lifecycle_intents.append(ArtifactLifecycleIntent(
        action="civ_destruction",
        losing_civ=civ_name,
        gaining_civ=None,
        region="",
        is_capital=True,
        is_full_absorption=True,
        is_destructive=False,
    ))


def _prosperity_gate(civ, world) -> bool:
    """Check whether a civ is in a prosperous enough state for cultural production."""
    return (
        civ.stability > PROSPERITY_STABILITY_THRESHOLD
        and civ.treasury >= PROSPERITY_TREASURY_THRESHOLD
        and not any(civ.name in war for war in world.active_wars)
        and civ.decline_turns == 0
        and civ.succession_crisis_turns_remaining == 0
    )


def select_cultural_artifact_type(civ, seed: int) -> ArtifactType:
    """Select cultural artifact type, biased by faction dominance."""
    import random as _random
    rng = _random.Random(seed)

    weights = {
        ArtifactType.ARTWORK: 1.0,
        ArtifactType.TREATISE: 1.0,
        ArtifactType.MONUMENT: 1.0,
    }

    if hasattr(civ, 'factions') and civ.factions is not None:
        from chronicler.factions import get_dominant_faction
        try:
            dominant = get_dominant_faction(civ.factions).value
            if dominant == "cultural":
                weights[ArtifactType.ARTWORK] = 2.0
                weights[ArtifactType.TREATISE] = 1.5
            elif dominant == "military":
                weights[ArtifactType.MONUMENT] = 2.0
            elif dominant == "merchant":
                weights[ArtifactType.ARTWORK] = 1.5
        except (ValueError, AttributeError):
            pass

    types = list(weights.keys())
    w = [weights[t] for t in types]
    return rng.choices(types, weights=w, k=1)[0]


def _roman(n: int) -> str:
    """Simple roman numeral for small collision suffixes."""
    numerals = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
                6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
    return numerals.get(n, str(n))
