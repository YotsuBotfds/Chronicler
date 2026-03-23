# M24 Information Asymmetry — Design Sketch

> Pre-spec design sketch for M24. Locks down open design questions and maps exact callsites.
> Reference this when writing the full M24 spec.

---

## Design Decisions (Locked)

### Decision 1: Accuracy Does NOT Decay Over Time

**Question:** Should accuracy decay without ongoing contact?

**Answer: No.** Accuracy is recomputed from scratch each turn based on current relationships (adjacency, trade, federation, war, vassal). There's no "memory" of past intelligence. If you lose a trade route, you immediately lose that +0.2 accuracy. If you go to war, you immediately gain +0.3.

**Rationale:** Decay-based systems require tracking per-pair accuracy history, adding a `last_contact_turn` field, and tuning decay rates. The recompute-from-state approach is simpler, deterministic from world state alone, and produces the same narrative effects: losing trade routes makes you blind, going to war gives you intel from the front lines. The M19 analytics pipeline can verify whether the recompute model produces enough variance; if not, decay can be added in a later pass.

### Decision 2: Espionage is NOT an Action Type

**Question:** Should espionage be a separate action civs can take?

**Answer: No.** Intelligence accuracy is a passive computation derived from existing relationships. Adding an "espionage" action creates a new decision branch the LLM action selector must evaluate, adds complexity to the action weight system, and is hard to balance (is +0.2 accuracy worth an action when you could WAR or TRADE?).

**Rationale:** M24 is designed to be the lightest milestone in Phase 4 (~150 lines). Adding espionage as an action would double the scope and couple it to the action engine rebalancing that M19b handles. If espionage-as-action proves desirable after M24 ships, it can be added as a Phase 5 enhancement. The passive model already creates meaningful asymmetry: trade-heavy civs know more, isolated civs know less, war reveals truth.

### Decision 3: Perceived Stats Affect Decisions, Not Outcomes

**Question:** Should perceived stats affect war resolution (actual combat) or just the decision to go to war?

**Answer: Decisions only.** When a civ decides whether to attack, it reads perceived military. When combat resolves, it uses actual military. This creates the asymmetry the system is designed for: you attack because you *think* they're weak, but you fight their *actual* army.

**Rationale:** If perceived stats affected combat outcomes, information asymmetry would change who wins wars, not just who starts them. That's a much larger design surface — does a civ that "thinks it's winning" fight harder? Do morale effects scale with perceived advantage? These are interesting questions, but they belong in a more complex combat model (Phase 5), not in M24's lightweight introduction of the concept.

**Exception:** Trade gains use perceived economy. If you trade with a civ you think is rich (perceived economy 80) but they're actually poor (actual economy 30), you still get the perceived-based gain — you overestimated the deal's value. This is narratively interesting (naivety in trade) and mechanically simple (just read perceived instead of actual).

### Decision 4: Perception Noise is Gaussian, Not Uniform

**Question:** What's the noise distribution?

**Answer: Seeded normal distribution, clipped to ±noise_range.**

```python
def get_perceived_stat(observer, target, stat, world) -> int:
    accuracy = compute_accuracy(observer, target, world)
    noise_range = int((1.0 - accuracy) * 20)
    if noise_range == 0:
        return getattr(target, stat)

    rng = random.Random(hash((world.seed, observer.name, target.name, world.turn, stat)))
    noise = int(rng.gauss(0, noise_range / 2))  # σ = half the range
    noise = max(-noise_range, min(noise_range, noise))  # clip
    return max(0, min(100, getattr(target, stat) + noise))
```

Gaussian means most perceptions are close to truth with occasional large errors, which is more realistic than uniform (where +14 and +1 are equally likely at accuracy 0.3).

**Determinism:** Same observer, same target, same turn, same stat = same perceived value. The seed ensures this. A civ's perception of another doesn't change mid-turn.

---

## Accuracy Computation

Recomputed from state each turn. No persistence.

```python
def compute_accuracy(observer: Civilization, target: Civilization, world: WorldState) -> float:
    if observer.name == target.name:
        return 1.0  # you always know yourself perfectly

    accuracy = 0.0  # start at zero, add sources

    # Geographic proximity
    if shares_adjacent_region(observer, target, world):
        accuracy += 0.3

    # Trade relationship
    if has_active_trade_route(observer, target, world):
        accuracy += 0.2

    # Federation membership
    if in_same_federation(observer, target, world):
        accuracy += 0.4

    # Vassal/overlord
    if is_vassal_of(observer, target, world) or is_vassal_of(target, observer, world):
        accuracy += 0.5

    # At war (direct or proxy)
    if at_war(observer, target, world):
        accuracy += 0.3

    # M22 faction bonus (merchant-dominated civs have trade intelligence networks)
    if has_faction_system(observer):
        dominant = get_dominant_faction(observer.factions)
        if dominant == FactionType.MERCHANT:
            accuracy += 0.1
        elif dominant == FactionType.CULTURAL:
            accuracy += 0.05

    # M17 great person bonuses
    for gp in observer.great_persons:
        if gp.alive and gp.active:
            if gp.role == "merchant":
                accuracy += 0.05  # trade connections = intelligence
            # Hostage held: +0.3 toward the holding civ
            if gp.is_hostage and gp.civilization == target.name:
                accuracy += 0.3

    # M17 grudge bonus
    for g in observer.leader.grudges:
        if g["rival_civ"] == target.name and g["intensity"] > 0.3:
            accuracy += 0.1  # you study your enemies

    return min(1.0, accuracy)
```

### Accuracy Ranges by Relationship

| Relationship | Typical Accuracy | Noise Range (±) |
|---|---|---|
| No contact (fog of war) | 0.0 | ±20 |
| Adjacent regions only | 0.3 | ±14 |
| Adjacent + trade | 0.5 | ±10 |
| Federation member | 0.7+ | ±6 |
| Vassal/overlord | 0.8+ | ±4 |
| Adjacent + war + grudge | 0.7 | ±6 |
| Max (all sources stacked) | 1.0 | ±0 |

---

## Exact Callsite Map

Verified against the landed codebase. These are every location where one civ reads another civ's stats for decision-making:

### action_engine.py — War Resolution

```
resolve_war(), line ~318-327:
  att_asabiya = attacker.asabiya          → KEEP actual (Decision 3: outcomes use real stats)
  def_asabiya = defender.asabiya          → KEEP actual
  attacker.military ** 2                   → KEEP actual
  defender.military ** 2                   → KEEP actual
```

War resolution uses actual stats. The asymmetry comes from the *decision* to attack, not the outcome.

### action_engine.py — War Target Selection / Action Weights

The action engine's `_apply_situational()` and `get_eligible_actions()` currently use the civ's OWN stats to decide action eligibility. Target selection is relationship-based (disposition), not stat-based. However, there's an implicit stat comparison in the WAR weight calculation that needs M24 integration:

```
NEW callsite needed in compute_weights() or _apply_situational():
  When computing WAR weight, compare perceived military of potential targets.
  If observer perceives all neighbors as stronger → WAR weight reduced.
  If observer perceives a neighbor as weak → WAR weight toward that target increased.
```

This is the primary M24 integration point in the action engine. It doesn't exist today because the action engine doesn't compare cross-civ stats for WAR targeting. M24 adds it.

### action_engine.py — Trade Resolution

```
resolve_trade(), line ~392-393:
  gain1 = max(1, civ2.economy // 3)      → get_perceived_stat(civ1, civ2, "economy", world) // 3
  gain2 = max(1, civ1.economy // 3)      → get_perceived_stat(civ2, civ1, "economy", world) // 3
```

Trade gains based on what you *think* the partner's economy is. Decision 3 exception.

### politics.py — Tribute Collection

```
collect_tribute(), line ~355:
  tribute = floor(vassal.economy * rate)  → floor(get_perceived_stat(overlord, vassal, "economy", world) * rate)
```

Overlord collects tribute based on what they think the vassal produces. A vassal in decline can temporarily hide its weakness.

### politics.py — Vassal Rebellion

```
check_vassal_rebellion(), line ~376:
  overlord.stability >= 25                → get_perceived_stat(vassal, overlord, "stability", world) >= 25
  overlord.treasury >= 10                 → get_perceived_stat(vassal, overlord, "treasury", world) >= 10
```

Vassal decides to rebel based on perceived overlord strength. A weak overlord that *appears* strong deters rebellion.

### politics.py — Congress Power Calculation

```
check_congress(), line ~678:
  civ.military + civ.economy              → get_perceived_stat(observer, civ, "military", world)
                                            + get_perceived_stat(observer, civ, "economy", world)
```

Note: Congress involves multiple civs evaluating each other. Each civ perceives different power levels. This means congress outcomes can differ based on who perceives whom as strong. Implementation: each civ computes perceived power of all others; the "congress organizer" (highest actual culture) uses their perceptions for the power ranking.

### politics.py — Congress Host Selection

```
check_congress(), line ~699:
  key=lambda c: c.culture                 → KEEP actual
```

Congress host is the civ with highest actual culture, not perceived. This is a "world fact" (who actually has the most culture), not a decision by an observer.

### simulation.py — Mercenary Hiring

```
mercenary hiring loop, line ~272:
  candidates.sort(key=lambda c: (c.military, -c.treasury))
                                          → KEEP actual
```

Mercenaries know who's weakest because they're on the ground. This is a "world mechanism" not an observer decision.

### Summary: 6 Callsites to Change

| # | File | Function | Stat | Change |
|---|---|---|---|---|
| 1 | action_engine.py | NEW: war target evaluation | military | Add perceived comparison |
| 2 | action_engine.py | resolve_trade | economy | Perceived |
| 3 | politics.py | collect_tribute | economy | Perceived |
| 4 | politics.py | check_vassal_rebellion | stability, treasury | Perceived |
| 5 | politics.py | check_congress | military, economy | Perceived (per-observer) |
| 6 | — | — | — | — |

5 change sites + 1 new site = 6 total integration points. War resolution, congress host, and mercenary hiring stay actual. This matches the ~150 lines estimate in the roadmap.

---

## TurnSnapshot Extension for M19 Analytics

```python
# Added to TurnSnapshot for M24 visibility
per_pair_accuracy: dict[str, dict[str, float]]  # observer → target → accuracy
perception_errors: dict[str, dict[str, dict[str, int]]]  # observer → target → stat → error
```

This lets M19 analytics answer: "How often does information asymmetry lead to mistaken wars?" by checking whether the perception error on military was > 10 when a WAR action was selected against that target.

---

## What This Sketch Does NOT Cover

- **Action engine weight formula for WAR targeting.** The exact formula for how perceived military of neighbors affects WAR weight is a spec detail. The sketch identifies that this callsite needs to be created.
- **Event generation.** Whether "mistaken intelligence" events should be added to the timeline (e.g., "Vrashni attacked Kethani, believing them weaker than they were"). This is a narrative decision for the spec.
- **Viewer display.** How to show accuracy and perception in the viewer's relationship panel.
