# M22 Faction–Succession Interaction — Design Sketch

> Pre-spec design sketch for how M22 factions integrate with M17's landed succession system.
> Reference this when writing the full M22 spec.

---

## M17 Succession System (Landed Code)

Quick reference for the spec writer — this is what exists today:

### State Machine

```
[Normal] ─── leader_death + crisis_prob hit ──→ [Crisis (1-5 turns)]
                                                      │
                                               tick_crisis() each Phase 8
                                                      │
                                               timer == 0
                                                      │
                                               resolve_crisis() ──→ [Normal]
                                                      └→ generate_successor(force_type)
                                                      └→ old leader → exile GP (maybe)
                                                      └→ grudge inheritance at 50%
```

### Crisis Probability

```python
base = 0.15
region_factor = num_regions / 5
instability_factor = 1 - (stability / 100)

modifiers:
  × 1.5 if succession_type != "heir"
  × 1.3 if has_active_vassals
  × 1.2 if reign < 5 turns
  × 0.6 if asabiya > 0.7
  × 0.8 if "martial" or "resilience" traditions
  × 0.7 if reign > 15 turns

final = clamp(base × region_factor × instability_factor × Π(modifiers), 0.05, 0.40)
```

### Candidate Structure

```python
civ.succession_candidates = [
    {"backer_civ": "OtherCiv", "type": "diplomatic"},  # default
    ...
]
```

Currently all other civs are added as candidates with type "diplomatic". Resolution picks one at random, checks type, maps to `force_type` for `generate_successor`.

### Succession Types

`"heir"`, `"general"`, `"usurper"`, `"elected"`, `"founder"`, `"restoration"`

### Key Functions

- `compute_crisis_probability(civ, world) → float`
- `trigger_crisis(civ, world) → None` — sets timer, populates candidates
- `tick_crisis(civ, world) → None` — decrements timer
- `resolve_crisis(civ, world) → list[Event]` — picks candidate, generates successor
- `create_exiled_leader(old_leader, origin_civ, world) → str | None`
- `check_exile_restoration(world) → list[Event]` — fires when origin stability < 20

---

## Faction Influence on Crisis Probability

M22 adds a faction modifier to `compute_crisis_probability`:

```python
# New modifiers added to crisis probability calculation
faction_modifier = 1.0

# Power struggle increases crisis chance
if civ.factions.power_struggle:
    faction_modifier *= 1.4  # internal instability from competing factions

# Dominant faction stabilizes if it matches the leader's trait
leader_faction_alignment = get_leader_faction_alignment(civ.leader, civ.factions)
if leader_faction_alignment > 0.5:
    faction_modifier *= 0.8  # leader aligned with dominant faction = stability
elif leader_faction_alignment < 0.2:
    faction_modifier *= 1.3  # leader misaligned with dominant faction = tension
```

### Leader–Faction Alignment

```python
def get_leader_faction_alignment(leader: Leader, factions: FactionState) -> float:
    """
    How well the leader's trait aligns with the dominant faction.
    Returns 0.0 (misaligned) to 1.0 (perfect alignment).
    """
    TRAIT_FACTION_MAP = {
        # Military-aligned traits
        "aggressive": FactionType.MILITARY,
        "expansionist": FactionType.MILITARY,
        "martial": FactionType.MILITARY,
        # Merchant-aligned traits
        "diplomatic": FactionType.MERCHANT,
        "cautious": FactionType.MERCHANT,
        "mercantile": FactionType.MERCHANT,
        # Cultural-aligned traits
        "visionary": FactionType.CULTURAL,
        "scholarly": FactionType.CULTURAL,
        "pious": FactionType.CULTURAL,
    }
    leader_faction = TRAIT_FACTION_MAP.get(leader.trait)
    if leader_faction is None:
        return 0.5  # neutral traits (e.g., "resilient") don't help or hurt

    dominant = max(factions.influence, key=factions.influence.get)
    return factions.influence.get(leader_faction, 0.33)
```

This creates a feedback loop: a military leader in a merchant-dominated civ faces higher crisis probability. If the crisis resolves with a merchant-aligned candidate, the new leader is better aligned and the civ stabilizes.

---

## Faction Influence on Candidate Generation

When `trigger_crisis` populates `succession_candidates`, M22 replaces the "all civs as diplomatic" default with faction-weighted candidates:

```python
def generate_faction_candidates(civ, world) -> list[dict]:
    """
    Generate succession candidates weighted by faction influence.
    Each faction produces one internal candidate.
    External backers still possible from other civs.
    """
    candidates = []
    dominant = get_dominant_faction(civ.factions)

    # Internal candidates — one per faction, weighted
    for faction_type in FactionType:
        influence = civ.factions.influence[faction_type]
        if influence < 0.15:
            continue  # faction too weak to field a candidate

        candidate = {
            "type": FACTION_CANDIDATE_TYPE[faction_type],
            "faction": faction_type.value,
            "weight": influence,
            "backer_civ": None,  # internal candidate
        }
        candidates.append(candidate)

    # External candidates — other civs can back a faction
    for other in world.civilizations:
        if other.name == civ.name or not other.regions:
            continue
        rel = world.relationships.get(other.name, {}).get(civ.name)
        if rel and rel.disposition in ("allied", "friendly"):
            # Allied civs back the faction that matches their own dominant faction
            other_dominant = get_dominant_faction(other.factions)
            candidate = {
                "type": FACTION_CANDIDATE_TYPE[other_dominant],
                "faction": other_dominant.value,
                "weight": 0.1,  # external backing is weaker than internal
                "backer_civ": other.name,
            }
            candidates.append(candidate)

    # Great person candidates — M17's general-to-leader pathway
    for gp in civ.great_persons:
        if gp.alive and gp.active and gp.role in ("general", "merchant", "prophet"):
            gp_faction = GP_ROLE_TO_FACTION[gp.role]
            faction_boost = 0.10 if gp_faction == dominant else 0.0
            candidate = {
                "type": GP_SUCCESSION_TYPE[gp.role],
                "faction": gp_faction.value,
                "weight": civ.factions.influence[gp_faction] + faction_boost,
                "backer_civ": None,
                "great_person": gp.name,
            }
            candidates.append(candidate)

    return candidates

# Mapping tables
FACTION_CANDIDATE_TYPE = {
    FactionType.MILITARY: "general",
    FactionType.MERCHANT: "elected",  # merchant faction favors "elected" (council)
    FactionType.CULTURAL: "heir",     # cultural faction favors legitimacy
}

GP_ROLE_TO_FACTION = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CULTURAL,
}

GP_SUCCESSION_TYPE = {
    "general": "general",
    "merchant": "elected",
    "prophet": "heir",
}
```

---

## Faction Influence on Crisis Resolution

Resolution uses weighted random selection instead of uniform random:

```python
def resolve_crisis_with_factions(civ, world) -> list[Event]:
    """
    Resolve succession crisis using faction-weighted candidate selection.
    """
    rng = random.Random(world.seed + world.turn + hash(civ.name))

    candidates = civ.succession_candidates
    if not candidates:
        # Fallback: immediate heir succession (no factions involved)
        return resolve_crisis(civ, world)

    # 10% outsider chance — populist surprise, ignores faction weights
    if rng.random() < 0.10:
        # Random candidate regardless of weight
        winner = rng.choice(candidates)
    else:
        # Weighted selection by faction influence
        weights = [c["weight"] for c in candidates]
        winner = rng.choices(candidates, weights=weights, k=1)[0]

    force_type = winner["type"]
    new_leader = generate_successor(civ, world, seed=world.seed, force_type=force_type)

    # Faction influence shift from resolution
    winning_faction = FactionType(winner["faction"])
    shift_faction_influence(civ.factions, winning_faction, +0.15)

    # If great person won, mark them as leader (remove from great_persons)
    if "great_person" in winner:
        gp = next((g for g in civ.great_persons if g.name == winner["great_person"]), None)
        if gp:
            new_leader.name = gp.name
            new_leader.trait = gp.trait
            gp.alive = False
            gp.fate = "ascended_to_leadership"

    # External backer relationship bonus
    if winner.get("backer_civ"):
        backer = next((c for c in world.civilizations if c.name == winner["backer_civ"]), None)
        if backer:
            # New leader is grateful to the backer
            improve_disposition(world, civ.name, backer.name, +1)

    # Exile old leader (existing M17 logic)
    # ... existing create_exiled_leader call ...

    return events
```

---

## Simultaneous Power Struggle + Succession Crisis

This is the key interaction the roadmap flagged but didn't resolve. Rules:

### Rule 1: Power struggle accelerates crisis probability

A civ in a faction power struggle (two factions within 0.05 influence, both above 0.3) gets `× 1.4` crisis probability modifier. This is already covered above.

### Rule 2: Crisis pauses power struggle timer

If a succession crisis triggers while a power struggle is active, the power struggle timer freezes. The crisis is the priority — you can't resolve internal faction competition while the throne is empty.

```python
if is_in_crisis(civ) and civ.factions.power_struggle:
    # Don't tick power struggle — it's frozen
    pass
```

### Rule 3: Crisis resolution can end power struggle

If the crisis resolves with a candidate from one of the struggling factions, that faction gets +0.15 (from resolution) which likely pushes it past the 0.05 gap threshold, ending the power struggle. If the outsider (10% chance) wins with a different faction, the power struggle continues after the crisis.

### Rule 4: No double stability drain

During a crisis, the civ already loses stability from `succession_crisis_turns_remaining > 0`. The power struggle's `-3/turn` stability drain is paused (Rule 2 above). This prevents catastrophic double drain that would make every power-struggle-triggered crisis a death spiral.

---

## Exile Restoration and Factions

M17's `check_exile_restoration` fires when `origin_civ.stability < 20`. M22 adds a faction check:

```python
# Additional restoration condition:
# Exile's original faction must not be dominant in the origin civ.
# A military exile returning to a military-dominated civ doesn't make narrative sense —
# they wouldn't have been exiled in the first place.

exile_faction = GP_ROLE_TO_FACTION.get(gp.role, None)
origin_dominant = get_dominant_faction(origin_civ.factions)

if exile_faction == origin_dominant:
    restoration_prob *= 0.3  # unlikely — their faction is already in charge
else:
    restoration_prob *= 1.5  # likely — the opposing faction welcomes them back
```

This creates a pattern: a general exiled by merchant-faction-dominated civ can return when stability drops (military is needed) and the military faction has regained influence.

---

## Grudge Interaction

M17 grudges persist at 50% intensity across succession. M22 adds faction coloring:

- If new leader's aligned faction matches the grudge holder's aligned faction, grudge inheritance increases to 70% (same faction, same enemies)
- If misaligned, inheritance drops to 30% (new faction, clean slate)

```python
def inherit_grudges_with_factions(old_leader, new_leader, old_factions, new_factions):
    old_alignment = get_leader_faction_alignment(old_leader, old_factions)
    new_alignment = get_leader_faction_alignment(new_leader, new_factions)

    # Same faction dominant = higher inheritance
    old_dominant = get_dominant_faction(old_factions)
    new_dominant = get_dominant_faction(new_factions)

    if old_dominant == new_dominant:
        inheritance_rate = 0.7  # faction continuity preserves grudges
    else:
        inheritance_rate = 0.3  # faction change dilutes grudges

    for g in old_leader.grudges:
        inherited_intensity = g["intensity"] * inheritance_rate
        if inherited_intensity >= 0.01:
            new_leader.grudges.append({**g, "intensity": inherited_intensity})
```

---

## Summary: Integration Points

| M17 Function | M22 Addition | Change Type |
|---|---|---|
| `compute_crisis_probability` | Power struggle × 1.4, leader–faction alignment modifier | Multiplicative modifier |
| `trigger_crisis` | `generate_faction_candidates` replaces default candidate list | Override candidate generation |
| `resolve_crisis` | Weighted random selection by faction influence, 10% outsider | Override resolution logic |
| `tick_crisis` | Power struggle timer frozen during crisis | Guard added |
| `inherit_grudges` | Faction-aware inheritance rate (0.3–0.7 instead of flat 0.5) | Parameter change |
| `check_exile_restoration` | Faction alignment modifies restoration probability | Multiplicative modifier |
| `create_exiled_leader` | No change | Unchanged |

All changes are additive. M17's state machine (trigger → tick → resolve) is preserved. Factions influence the inputs and weights, not the flow.

---

## P4 Input: Secession Viability Problem

> Added by Phoebe after P4 tuning pass (50-seed, 1000-turn batch analysis).

P4's iterative tuning revealed that single-region secession fragments in low-capacity terrain (desert, tundra) are structurally capped at population 4–8 by `effective_capacity`. These splinter civs survive indefinitely (passive repopulation keeps them at floor) but can never grow meaningfully. They drag the median civ population below target (9 vs 15) and create a long tail of zombie civs.

This is a game design question, not a tuning problem. Three options for the M22 spec to consider:

1. **Minimum viability gate** — Secession requires the breakaway region set to have total `effective_capacity >= N` (e.g., 15). Prevents civs from seceding into a single desert/tundra region where they're structurally unviable. Simplest fix, but removes some emergent variety.

2. **Absorption of unviable civs** — If a civ's total carrying capacity across all regions stays below a threshold for M turns, it gets absorbed by a neighbor (similar to twilight absorption but triggered by structural incapacity rather than decline). More emergent, but adds a new mechanic.

3. **Secession region selection reform** — Instead of picking the farthest regions from the capital (which can select a lone desert), weight secession region selection by capacity. Seceding factions prefer viable territory. Most realistic, requires reworking the `sorted_regions` logic in `politics.py:123`.

> **Phoebe answer: Option 3 (region selection reform) as primary fix, Option 2 as safety net.**
>
> Option 1 is too blunt — it prevents small desert/tundra secessions entirely, removing some of the most narratively interesting fragments. A single-region desert rebel state *should* be possible; it just shouldn't be the common case.
>
> **Option 3 implementation:** Change `sorted_regions` in politics.py to weight by both distance and capacity. Replace pure distance sort with a composite score: `graph_distance * 0.7 + (1 / effective_capacity) * 0.3`. Distance still dominates (far regions secede), but among equidistant regions, higher-capacity ones are preferred. A civ with distant plains AND distant desert loses the plains to secession, not the desert. The seceding faction takes viable territory because viable territory is worth fighting for.
>
> **Option 2 as safety net (~5 lines):** If a civ's total effective capacity across all regions stays below 10 for 30 turns, absorb into culturally closest neighbor. This is a variant of twilight absorption (already exists) but triggered by structural incapacity instead of stat decline. Catches edge cases where Option 3's weighting still produces a desert splinter. Add the check inside the existing twilight tick — one additional condition, same absorption logic.
>
> Option 1 is not needed if both 3 and 2 are implemented.
