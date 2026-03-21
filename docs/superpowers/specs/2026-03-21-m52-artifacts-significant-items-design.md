# M52: Artifacts & Significant Items — Design Spec

> **Status:** Draft
> **Date:** 2026-03-21
> **Depends on:** M48 (Agent Memory) — merged
> **Independent of:** M51 (Multi-Generational Memory) — enrichment point only
> **Feeds into:** M53a (Depth Tuning)

---

## 1. Goal

Track significant objects — holy relics, hereditary weapons, monuments, works of art, scholarly treatises, political manifestos, and luxury prestige goods — with origin stories, ownership chains, and narrative significance. Artifacts are narrative hooks with limited mechanical effects, not a full item system.

Cultural production (artworks, monuments, treatises created during periods of peace and prosperity) is in scope. Mule artifact creation provides a lasting narrative anchor for outlier characters.

**Scope guard:** No inventory, no crafting, no equipment slots, no artifact trading between civs. Each artifact is a story-generating object with mechanical effects limited to prestige contribution and a narrow regional conversion bonus for relics.

---

## 2. Ownership Model

**Hybrid: civ-owned by default, character-held for select types.**

Most artifacts (relics, monuments, artworks, treatises, manifestos, trade goods) are owned at the civilization level. Individual GreatPerson holders are reserved for the artifact classes where the bearer is the narrative point:

- **Mule artifacts** — created by Mule character action success
- **Hereditary weapons** — created at GP promotion for generals

Character-held artifacts use `holder_name: str` + `holder_born_turn: int` as the holder key, not raw `agent_id`. This is stable for aggregate-sourced GPs, works across exile/hostage transitions, and avoids coupling M52 to the agent pool's ID space.

**Character-held lifecycle rules:**
- Artifacts stay with the living holder through exile and hostage capture.
- When the holder is no longer an active GP (death, retirement, ascension — any state where `gp.active == False`), the artifact reverts to the holder's **current** civ at time of reversion.
- **M51 enrichment point:** When dynasty/heir transfer lands, hereditary weapon transfer to a successor GP can be wired at the reversion check without changing the M52 architecture.

---

## 3. Data Model

### 3.1 Artifact Types and Portability

```python
class ArtifactType(str, Enum):
    RELIC = "relic"              # holy objects, sacred relics
    WEAPON = "weapon"            # hereditary weapons, war banners
    MONUMENT = "monument"        # permanent structures, statues
    ARTWORK = "artwork"          # paintings, sculptures, jewelry
    TREATISE = "treatise"        # scholarly works, philosophical texts
    MANIFESTO = "manifesto"      # political/ideological documents
    TRADE_GOOD = "trade_good"    # luxury prestige goods

class ArtifactStatus(str, Enum):
    ACTIVE = "active"            # held by a civ or character
    LOST = "lost"                # no owner (civ destroyed without absorber)
    DESTROYED = "destroyed"      # explicitly destroyed (destructive conquest of anchored artifact)
```

**Portability classification:**

| Type | Default | Override allowed? |
|------|---------|-------------------|
| MONUMENT | Always anchored | No — monuments never move |
| WEAPON | Always portable | No |
| TRADE_GOOD | Always portable | No |
| RELIC | Anchored (temple-bound) | Portable if character-held |
| ARTWORK | Portable | Anchored if created as site-specific (e.g., fresco) |
| TREATISE | Always portable | No |
| MANIFESTO | Always portable | No |

### 3.2 Artifact Model

```python
class Artifact(BaseModel):
    artifact_id: int             # sequential, world-unique (derived from max existing + 1)
    name: str                    # canonical, immutable after creation
    artifact_type: ArtifactType
    anchored: bool               # True = stays with region/site
    origin_turn: int
    origin_event: str            # brief description of creation context
    origin_region: str           # birthplace (immutable, distinct from anchor_region)
    creator_name: str | None     # GP name if character-created, None for ambient
    creator_civ: str             # civ that produced the artifact
    owner_civ: str | None        # current owning civ (None if lost/destroyed)
    holder_name: str | None      # GP name if character-held (Mule artifacts, hereditary weapons)
    holder_born_turn: int | None # disambiguator for holder identity
    anchor_region: str | None    # current region for anchored artifacts
    prestige_value: int          # per-turn prestige contribution to owner
    status: ArtifactStatus
    history: list[str]           # ownership/transfer narrative fragments (capped at 10)
    mule_origin: bool = False    # True if created by Mule character action
```

**Model invariants:**
- `MONUMENT` ⇒ `anchored == True`
- `holder_name is not None` ⇒ `anchored == False`
- `anchor_region is not None` ⇒ `anchored == True`
- `status != ACTIVE` ⇒ `owner_civ is None` (and usually `holder_name is None`, unless a live holder carries an artifact from a destroyed civ)

### 3.3 WorldState Integration

```python
class WorldState(BaseModel):
    artifacts: list[Artifact] = Field(default_factory=list)
    # Transient (PrivateAttr, not persisted):
    _artifact_intents: list = PrivateAttr(default_factory=list)
```

`artifact_id` assignment: derived from `max(a.artifact_id for a in world.artifacts, default=0) + 1` at creation time. No stored counter — the artifact list is the source of truth.

### 3.4 Model Placement

Type definitions (`Artifact`, `ArtifactType`, `ArtifactStatus`, `ArtifactIntent`) live in `models.py`. Behavior functions (`tick_artifacts()`, `generate_artifact_name()`, naming templates, prosperity gate) live in a new `artifacts.py`. This avoids circular imports between `models.py` and the behavior module.

---

## 4. Creation Pipeline

### 4.1 Intent Pattern

Triggers detect artifact-worthy moments inline and append typed `ArtifactIntent` objects to `world._artifact_intents`. A single `tick_artifacts(world)` function processes all intents centrally at the end of Phase 10.

```python
@dataclass
class ArtifactIntent:
    artifact_type: ArtifactType
    trigger: str              # "temple_construction", "gp_promotion", "conquest_capture",
                              # "mule_action", "cultural_work", "cultural_renaissance"
    creator_name: str | None  # GP name if character-driven
    creator_born_turn: int | None
    holder_name: str | None   # GP name if character-held (distinct from creator)
    holder_born_turn: int | None
    civ_name: str
    region_name: str
    anchored: bool | None     # None = use type default
    mule_origin: bool = False
    context: str = ""         # brief origin description for history[0]
```

### 4.2 Intent Emission Sites

| Trigger | File | Function | Intent shape |
|---------|------|----------|--------------|
| Temple construction | `infrastructure.py` | `tick_infrastructure()` on `infrastructure_completed` for TEMPLES | type=RELIC, anchored=True, region=temple region |
| GP promotion (high prestige) | `agent_bridge.py` | `_process_promotions()` when `civ.prestige > GP_PRESTIGE_THRESHOLD` | type varies by role (general→WEAPON with holder, prophet→RELIC, merchant→ARTWORK, scientist→TREATISE) |
| Conquest capture | `action_engine.py` | `_resolve_war_action()` on successful conquest | Transfer intent for defender artifacts, not creation (see Section 5) |
| Mule action success | `action_engine.py` | After action resolution when Mule's favored action succeeds | type varies by Mule role/action combo, mule_origin=True, holder=Mule GP |
| Cultural production (`cultural_work`) | `simulation.py` | `phase_cultural_milestones()` when milestone fires AND prosperity gate passes | type=ARTWORK/TREATISE/MONUMENT |
| Cultural production (`cultural_renaissance`) | `simulation.py` | `phase_random_events()` handler (line ~700) when event fires AND prosperity gate passes | type=ARTWORK/TREATISE/MONUMENT |

### 4.3 Conquest: Transfer Intents, Not Creation

Conquest does not create new artifacts. Instead, `_resolve_war_action()` emits explicit **transfer intents** for artifacts belonging to the defeated civ. Transfer logic lives in `tick_artifacts()`. See Section 5 for transfer rules.

### 4.4 Prosperity Gate

Cultural production (ambient artifacts from `cultural_work`/`cultural_renaissance`) requires prosperity conditions:

```python
def _prosperity_gate(civ, world) -> bool:
    """Check whether a civ is in a prosperous enough state for cultural production."""
    return (
        civ.stability > PROSPERITY_STABILITY_THRESHOLD          # [CALIBRATE M53] default 70
        and civ.treasury >= PROSPERITY_TREASURY_THRESHOLD        # [CALIBRATE M53] default 20
        and not any(civ.name in war for war in world.active_wars)
        and civ.decline_turns == 0
        and civ.succession_crisis_turns_remaining == 0
    )
```

**Note:** The war check covers declared wars in `active_wars` (list of `(str, str)` tuples). Proxy wars via `FUND_INSTABILITY` are not checked — a civ being destabilized covertly can still produce cultural artifacts. This is a deliberate simplification; proxy war gate is deferred to M53a calibration.

When the prosperity gate passes, artifact creation has a per-event probability: `CULTURAL_PRODUCTION_CHANCE` (`[CALIBRATE M53]`, default 0.15).

**Region selection for civ-wide cultural events:** Both `cultural_work` (from `phase_cultural_milestones()`) and `cultural_renaissance` (from `phase_random_events()`) are civ-level events with no inherent region. The intent uses `civ.regions[0]` as the `origin_region` — the capital/primary region. This determines where anchored cultural artifacts (monuments) are placed.

Cultural faction dominance biases **what kind** of artifact gets produced (ARTWORK vs TREATISE vs MONUMENT), not **whether** production happens.

### 4.5 `tick_artifacts()` — Central Processing

**Placement:** End of Phase 10, after GP/conquest/exile state has settled, before timeline write. Called from `simulation.py`.

**Responsibilities:**
1. Process `_artifact_intents` → create `Artifact` objects with generated names
2. Handle conquest transfers (from transfer intents)
3. Handle holder lifecycle (scan character-held artifacts for inactive GPs)
4. Compute artifact prestige contributions through accumulator
5. Emit events for significant transitions
6. Clear `_artifact_intents`

### 4.6 GP-Driven Artifact Types by Role

| GP Role | Artifact Type | Character-held? |
|---------|---------------|-----------------|
| general | WEAPON | Yes (hereditary weapon) |
| prophet | RELIC | No (civ-owned, temple-bound) |
| merchant | ARTWORK | No (civ-owned, commissioned) |
| scientist | TREATISE | No (civ-owned) |
| exile | — | No artifact at promotion |
| hostage | — | No artifact at promotion |

### 4.7 Mule Artifact Types by Action

| Mule Role | Favored Action | Artifact Type | Name Pattern |
|-----------|----------------|---------------|--------------|
| general | WAR (conquest) | RELIC (war banner) | "The Banner of {Name}" |
| general | DEVELOP | TREATISE (military treatise) | "The Treatise of {Name}" |
| merchant | TRADE | TRADE_GOOD | "The {Adj} {Noun} of {Name}" |
| merchant | FUND_INSTABILITY | MANIFESTO | "The Manifesto of {Name}" |
| prophet | BUILD (temple) | RELIC | "The Sacred {Noun} of {Name}" |
| scientist | DEVELOP | TREATISE | "The {Adj} Codex of {Name}" |

Mule artifact creation fires only during the Mule's active window (first `MULE_ACTIVE_WINDOW` turns after promotion, currently 25), not during the fade period. The Mule GP is set as the character holder.

**One artifact per Mule lifetime.** The first matching action success during the active window creates the artifact. Subsequent successes do not create additional artifacts. Track via a `mule_artifact_created: bool` flag on `GreatPerson` (default False, set True on first creation). This prevents a warlike Mule from generating 5-10+ artifacts across a 25-turn window.

---

## 5. Lifecycle & Ownership Transitions

### 5.1 Conquest Transitions

When a region is conquered via `_resolve_war_action()`:

**Anchored artifacts** in the conquered region:
- Non-destructive conquest: `owner_civ` changes to conqueror. Artifact stays in place. History: "Claimed by {conqueror} after the fall of {region}, turn {t}."
- Destructive conquest: `status = DESTROYED`. History: "Destroyed during the sack of {region}, turn {t}."

**Definition of destructive conquest:** Conquest is destructive when the existing `scorched_earth_check()` in `infrastructure.py` fires (the defender's infrastructure is destroyed, probabilistic). Scorched earth is a defender-initiated action — the defender is destroying their own infrastructure to deny it to the attacker. Anchored artifacts in the region are destroyed alongside the infrastructure. Militant temple destruction (`destroy_temple_for_replacement()`) is a separate, faith-driven action and does **not** trigger artifact destruction — only scorched earth does.

**Portable civ-owned artifacts (no holder):**
- Transfer only on **capital capture or full civ absorption**. Ordinary non-capital region loss does not expose portable artifacts. This avoids the problem of a single border region conquest sweeping the entire portable collection.
- On capital capture: portable artifacts transfer to conqueror. History: "Captured by {conqueror} during the fall of {capital}, turn {t}."

**Character-held artifacts:**
- Stay with the holder regardless of conquest outcome. If the holder is exiled, the artifact goes with them. If the holder dies during conquest, revert to civ (see Section 5.2).

### 5.2 Holder Lifecycle

Checked in `tick_artifacts()` each turn:

- Scan all artifacts where `holder_name is not None`.
- For each, find the matching GP in the simulation. Match key: `(holder_name, holder_born_turn)`.
- If the GP is no longer active (`not gp.active`):
  - `holder_name = None`, `holder_born_turn = None`
  - Artifact reverts to the holder's **current** civ (`gp.civilization`) at time of reversion.
  - History: "Returned to {civ} after {gp.name}'s {gp.fate}, turn {t}."
  - If Mule artifact: emit `mule_artifact_relinquished` event.

**M51 enrichment:** Hereditary weapon transfer to dynasty successor wires here.

### 5.3 Civ Destruction

**With absorber (twilight absorption):** Apply conquest rules — absorber receives portable artifacts, anchored artifacts in absorbed regions change owner.

**Without absorber (zero regions, no absorber):**
- Character-held artifacts with a **living holder** (exile/hostage): stay `ACTIVE` with holder. Holder's artifact survives their origin civ's death.
- All other artifacts: `status = LOST`, `owner_civ = None`. History: "Lost when {civ} fell, turn {t}." Emit `artifact_lost` event.

### 5.4 Event Emission for Transitions

| Transition | Event emitted? | Rationale |
|------------|----------------|-----------|
| Artifact creation | Always | All creations are significant |
| Conquest capture (portable, capital) | Yes | War spoils are dramatic |
| Anchored artifact changes owner | No | Implicit in conquest narration |
| Anchored artifact destroyed | Yes | Destruction is always notable |
| Mule holder becomes inactive | Yes | Mule legacy moments matter |
| Non-Mule holder becomes inactive | No | Routine reversion |
| Artifact lost (civ destroyed) | Yes | "Lost to history" moments |

Only significant transitions emit events. Routine ownership changes (anchored artifact controller swap) do not compete for narration slots.

---

## 6. Mechanical Effects

### 6.1 Ongoing Prestige Contribution

Artifact prestige is an **ongoing per-turn source**, not a one-time grant. Each turn, `tick_artifacts()` computes per-civ artifact prestige and adds it through the accumulator:

```python
for civ_idx, civ in enumerate(world.civilizations):
    if len(civ.regions) == 0:
        continue
    artifact_prestige = sum(
        a.prestige_value for a in world.artifacts
        if a.owner_civ == civ.name and a.status == ArtifactStatus.ACTIVE
    )
    if artifact_prestige > 0:
        acc.add(civ_idx, civ, "prestige", artifact_prestige, "keep")
```

**Ordering and one-turn lag:** `tick_prestige()` runs in Phase 3 (line 523 of `simulation.py`), while `tick_artifacts()` runs at the end of Phase 10. This means artifact prestige from turn N does not contribute to the prestige-based trade bonus computed by `tick_prestige()` until turn N+1. This one-turn lag is **intentional** and matches the codebase convention (Gini one-turn lag in `AgentBridge._gini_by_civ`, conversion signal lag). Artifacts raise the prestige floor — a civ with many active artifacts has a higher baseline that decays more slowly toward zero.

When `acc is None` (aggregate mode, Phase 10), artifact prestige is applied directly: `civ.prestige += artifact_prestige`. This matches the standard `if acc is not None / else` pattern used throughout `phase_consequences()`.

**Prestige values by type (all `[CALIBRATE M53]`):**

| Type | Prestige Value | Rationale |
|------|----------------|-----------|
| MONUMENT | 4 | Permanent, visible, civilizational pride |
| RELIC | 3 | Sacred objects, high cultural weight |
| WEAPON | 2 | Military prestige |
| ARTWORK | 2 | Cultural refinement |
| TREATISE | 2 | Intellectual prestige |
| MANIFESTO | 1 | Political, divisive — less pure prestige |
| TRADE_GOOD | 1 | Luxury display, lowest tier |

### 6.2 Relic Conversion Bonus

Temple-anchored relics boost conversion rate in their region. Wired into the existing per-region conversion calculation in `religion.py`:

- Only applies when `owner_civ == region.controller` — a conquered relic in hostile hands does not boost conversion for the occupier.
- Non-stacking: one relic bonus per region. Multiple relics don't compound.
- `RELIC_CONVERSION_BONUS`: `[CALIBRATE M53]`, default 0.15 (15% multiplicative boost on base conversion rate).

### 6.3 No Other Modifier Channels

M52 does not add action weight modifiers, faction power modifiers, satisfaction terms, or any other mechanical effect. The 2.5x action weight cap (already strained by traditions × tech focus × factions × Mule) should not receive a fifth contributor until the cap mechanism is revised in M63.

---

## 7. Naming System

### 7.1 Canonical Names

Artifact names are deterministically generated at creation and remain immutable for the lifetime of the artifact. Names work in `--narrator off` mode and provide stable cross-references across narrative moments.

### 7.2 Name Generation

```python
def generate_artifact_name(
    artifact_type: ArtifactType,
    creator_name: str | None,
    origin_region: str,
    civ_values: list[str],
    seed: int,
) -> str:
```

Selects template, adjective, and noun deterministically from seed. Uses `origin_region` (birthplace) for `{place}`, not current location. Creator names use a possessive helper (`Ashara` → `Ashara's`).

### 7.3 Template Pools

Each artifact type has a set of name templates:

- **RELIC:** "The Sacred {adj} of {place}", "The {adj} Relic of {creator}", "The Holy {noun} of {place}"
- **WEAPON:** "The {noun} of {creator}", "{adj} {noun}", "The Blade of {place}"
- **MONUMENT:** "The {adj} {noun} of {place}", "The Great {noun} of {place}", "{creator}'s {noun}"
- **ARTWORK:** "The {adj} {noun}", "The {noun} of {place}", "{creator}'s {adj} {noun}"
- **TREATISE:** "The {noun} of {creator}", "The {adj} Codex", "The Letters of {creator}"
- **MANIFESTO:** "The {adj} Manifesto", "The Declarations of {creator}", "{creator}'s {noun}"
- **TRADE_GOOD:** "The {adj} {noun} of {place}", "{place} {noun}"

### 7.4 Vocabulary Pools with Cultural Flavor

Adjectives are drawn from the creating civ's dominant cultural value (first element of `civ.values`):

| Civ Value | Adjectives |
|-----------|------------|
| Honor | Iron, Crimson, Bloodforged, Unyielding |
| Trade | Golden, Gilded, Silver-wrought, Precious |
| Knowledge | Ancient, Illuminated, Sage, Inscribed |
| Tradition | Ancestral, Hallowed, Timeless, Venerable |
| Order | Sovereign, Imperial, Lawbound, Exalted |
| Cunning | Shadow, Veiled, Serpentine, Subtle |
| Piety | Sacred, Blessed, Radiant, Divine |
| Freedom / Liberty | Wild, Untamed, Windsworn, Bold |
| Strength / Self-reliance | Iron, Crimson, Bloodforged, Unyielding |
| Destiny | Sovereign, Imperial, Lawbound, Exalted |
| (default) | Great, Renowned, Storied, Fabled |

Values not explicitly listed (e.g., future additions) fall through to the default pool. `Strength` and `Self-reliance` map to the same pool as `Honor`; `Liberty` maps to `Freedom`; `Destiny` maps to `Order`.

Nouns are per-type:

| Type | Nouns |
|------|-------|
| WEAPON | Blade, Shield, Banner, Spear, Standard |
| RELIC | Chalice, Tome, Seal, Vessel, Shard |
| MONUMENT | Pillar, Arch, Colossus, Obelisk, Gate |
| ARTWORK | Tapestry, Mosaic, Fresco, Idol, Mask |
| TREATISE | Codex, Scrolls, Commentaries, Meditations |
| MANIFESTO | Manifesto, Declarations, Edicts, Theses |
| TRADE_GOOD | Silk, Jade, Amber, Ivory, Incense |

### 7.5 Collision Avoidance

After generation, check the candidate name against existing `world.artifacts`. On collision: try one or two deterministic re-rolls with a salted seed. If still colliding, append a numeral suffix ("II", "III"). Collisions should be rare given the combinatorial space.

---

## 8. Narrative Integration

### 8.1 Narrator Context

Artifact context is built as a separate `artifact_context_text` block during prompt assembly, alongside `agent_context_text`. It is **not** gated inside `build_agent_context_for_moment()` (which is restricted to moments with agent/economy events).

**Relevance selection (max 3 per moment):**

1. Character-held artifacts for GPs whose names appear in `moment.events[*].actors`
2. Anchored artifacts in regions referenced by `moment.named_events[*].region`
3. Civ-owned notable artifacts (Mule or high prestige) for civs appearing in moment actors — if under budget

**Rendering format (one line per artifact):**

```
ARTIFACTS:
- The Iron Banner of Tessara (weapon, held by General Kiran) — forged during the founding wars
- The Sacred Chalice of Ashara (relic, temple-bound in Ashara) — holy relic of the Ashkari faith
```

Name, type, holder/location status, origin snippet from `history[0]`.

### 8.2 Event Types

| Event type | Actors | When |
|------------|--------|------|
| `artifact_created` | [creator or civ, artifact name] | Any creation |
| `artifact_captured` | [capturing civ, losing civ, artifact name] | Portable artifact captured on capital fall |
| `artifact_lost` | [former owner civ, artifact name] | Civ destroyed without absorber |
| `artifact_destroyed` | [destroying civ, artifact name] | Anchored artifact in destructive conquest |
| `mule_artifact_relinquished` | [holder name, civ name, artifact name] | Mule holder becomes inactive |

Actors have civ/holder names first, artifact name last — matching existing scoring assumptions in `curator.py` where actors are typically civs or characters.

Events enter the normal curator pipeline without special scoring bonuses. Artifact events compete on the same terms as all other events. The curator's existing named-character scoring naturally boosts artifact events that involve GPs.

### 8.3 No Artifact-Specific Causal Patterns

M52 does not add entries to `CAUSAL_PATTERNS`. Artifact events participate in causal linking only through actor overlap and temporal proximity. Artifact-specific causal chains (e.g., `conquest → artifact_capture → diplomatic_tension`) are deferred to M53b validation.

### 8.4 Narrative Descriptions

```python
ARTIFACT_DESCRIPTIONS = {
    ArtifactType.RELIC: "a sacred relic",
    ArtifactType.WEAPON: "a legendary weapon",
    ArtifactType.MONUMENT: "a great monument",
    ArtifactType.ARTWORK: "a renowned work of art",
    ArtifactType.TREATISE: "a scholarly treatise",
    ArtifactType.MANIFESTO: "a political manifesto",
    ArtifactType.TRADE_GOOD: "a prized luxury",
}
```

---

## 9. Bundle & Analytics

### 9.1 Bundle Export

Artifacts are serialized into the bundle under a new top-level key `"artifacts"`:

```python
# In assemble_bundle():
"artifacts": [a.model_dump() for a in world.artifacts]
```

All artifacts (active, lost, destroyed) are included — the full history is the narrative value. This is an additive schema change; current bundle consumers tolerate additive keys.

### 9.2 Analytics Extractor

`extract_artifacts()` in `analytics.py`:

- Per-civ: artifact count, total prestige contribution, type distribution
- Global: creation rate per turn, loss/capture rate, cultural vs combat creation ratio
- Timeline: `artifacts_created_by_turn`, `artifacts_lost_by_turn`

Consumed by M53a calibration.

### 9.3 `--agents=off` Compatibility

Artifact creation from cultural events and temple construction works in aggregate mode. GP-driven creation (high-prestige promotions) works in aggregate mode because aggregate mode still creates GreatPersons.

Mule-driven creation only fires in agent/hybrid mode (Mules require the agent pool).

GP-driven creation (high-prestige threshold) has two code paths:
- **Agent/hybrid mode:** Intent emitted in `_process_promotions()` (agent_bridge.py).
- **Aggregate mode:** Intent emitted in `check_great_person_generation()` (great_persons.py) — a parallel hook is needed since `_process_promotions()` only runs in agent modes.

This is a **deliberate product boundary**: aggregate mode gets ambient and GP-driven artifacts; agent/hybrid mode additionally gets Mule artifacts.

---

## 10. File Changes

### New Files

| File | Contents |
|------|----------|
| `src/chronicler/artifacts.py` | `tick_artifacts()`, `generate_artifact_name()`, naming templates/vocabulary, `_prosperity_gate()`, `_get_relevant_artifacts()`, creation/transfer/lifecycle logic |

### Modified Files

| File | Changes |
|------|---------|
| `models.py` | `Artifact`, `ArtifactType`, `ArtifactStatus`, `ArtifactIntent` models. `WorldState.artifacts` field, `_artifact_intents` PrivateAttr. `GreatPerson.mule_artifact_created: bool = False` |
| `great_persons.py` | Intent emission in `check_great_person_generation()` for aggregate-mode GP artifacts (parallel to agent_bridge hook) |
| `simulation.py` | `tick_artifacts()` call in Phase 10 (end, before timeline write). Intent emission in `phase_cultural_milestones()` and `cultural_renaissance` handler |
| `infrastructure.py` | Intent emission in `tick_infrastructure()` on temple completion |
| `action_engine.py` | Intent emission in Mule action success path. Transfer intents in `_resolve_war_action()` on conquest |
| `agent_bridge.py` | Intent emission in `_process_promotions()` for high-prestige GP promotions |
| `narrative.py` | `artifact_context_text` in prompt assembly (separate from agent context). `ARTIFACT_DESCRIPTIONS` dict |
| `analytics.py` | `extract_artifacts()` extractor |
| `bundle.py` | `"artifacts"` key in `assemble_bundle()` output |

### No Rust Changes

Entirely Python-side. No simulation determinism impact on the Rust agent tick.

---

## 11. Calibration Constants

All `[CALIBRATE M53]`:

| Constant | Default | Location | Purpose |
|----------|---------|----------|---------|
| `CULTURAL_PRODUCTION_CHANCE` | 0.15 | `artifacts.py` | Per cultural_work/renaissance event |
| `GP_PRESTIGE_THRESHOLD` | 50 | `artifacts.py` | Min civ prestige for GP promotion artifact |
| `RELIC_CONVERSION_BONUS` | 0.15 | `artifacts.py` | Regional conversion rate boost |
| `PROSPERITY_STABILITY_THRESHOLD` | 70 | `artifacts.py` | Prosperity gate |
| `PROSPERITY_TREASURY_THRESHOLD` | 20 | `artifacts.py` | Prosperity gate |
| `MONUMENT_PRESTIGE` | 4 | `artifacts.py` | Per-turn prestige contribution |
| `RELIC_PRESTIGE` | 3 | `artifacts.py` | Per-turn prestige contribution |
| `WEAPON_PRESTIGE` | 2 | `artifacts.py` | Per-turn prestige contribution |
| `ARTWORK_PRESTIGE` | 2 | `artifacts.py` | Per-turn prestige contribution |
| `TREATISE_PRESTIGE` | 2 | `artifacts.py` | Per-turn prestige contribution |
| `MANIFESTO_PRESTIGE` | 1 | `artifacts.py` | Per-turn prestige contribution |
| `TRADE_GOOD_PRESTIGE` | 1 | `artifacts.py` | Per-turn prestige contribution |
| `HISTORY_CAP` | 10 | `artifacts.py` | Max history entries per artifact |

---

## 12. Deferred / Future Hooks

| Item | When | Notes |
|------|------|-------|
| Heir transfer of hereditary weapons | M51 enrichment | Wire at holder lifecycle check in `tick_artifacts()` |
| Artifact-specific causal patterns | M53b | Add `CAUSAL_PATTERNS` entries after observing event density |
| Relic faith-alignment gate | M53a | Gate relic conversion bonus on faith match, not just owner match |
| Artifact rediscovery | Post-M53 | Lost artifacts can be rediscovered — hook exists via status field |
| Action weight / faction modifiers | M63+ | Blocked until 2.5x cap mechanism is revised |
| Artifact trading between civs | Post-Phase 7 | Not in scope for M52 |
| Viewer integration | Phase 7.5 / M62 | Deferred to stable export contract |

---

## 13. Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Hybrid ownership (civ default, character for Mule/weapons) | Avoids GP `agent_id` instability. Keeps M52 independent of M51. Character holders only where the bearer is the narrative point. |
| 2 | Intent-based creation (detect inline, create centrally) | Triggers span Phase 2, 8, 10, and agent tick. Centralizes naming, prestige, history, and duplicate guards in one function. Mirrors M48 memory intent pattern. |
| 3 | Portability/anchoring model for conquest | Better than raw type-based transfer. Monuments stay, weapons move, relics can go either way. |
| 4 | Portable capture restricted to capital/full absorption | Without `storage_region`, any single region conquest would sweep all portable artifacts. Capital-only is historically resonant and avoids tracking per-artifact location for civ-owned portables. |
| 5 | Ongoing prestige source, not one-time grant | Transfers, loss, and conquest are all mechanically self-correcting. Lose the artifact, lose the prestige next turn. No reversal bookkeeping. |
| 6 | Cultural production via existing `cultural_work`/`cultural_renaissance` events | No new "golden age" system needed. Prosperity gate + probability on existing events. Faction biases type, not production. |
| 7 | B narrative (events for transitions, no causal patterns) | Artifact events compete normally. Causal patterns deferred to M53b after observing actual event density. |
| 8 | World-level registry, not per-civ lists | Anchored/lost/character-held/exile states don't map to per-civ ownership. Single source of truth. Transfers are field updates, not list surgery. |
| 9 | `owner_civ: str` not index | Matches codebase identity convention (`civ.name`, `region.controller`). Not coupled to list position. |
| 10 | GP artifact creation in aggregate mode is a deliberate product boundary | Aggregate mode GPs could create artifacts. M52 scopes GP-driven creation to all modes, Mule-driven to agent/hybrid only. |
| 11 | Holder reversion uses current civ | Not cached origin civ. If a GP changes allegiance, the artifact follows. |
| 12 | Live holder exemption on civ destruction | A Mule in exile keeps their artifact even if their origin civ is destroyed. The artifact is theirs, not the civ's. |
| 13 | One Mule artifact per lifetime | First matching action success creates the artifact. Prevents spam from frequently-warring Mules. Tracked via `mule_artifact_created` on GreatPerson. |
| 14 | One-turn prestige lag (intentional) | Artifact prestige added in Phase 10, consumed by `tick_prestige()` in Phase 3 next turn. Matches Gini lag pattern. |
| 15 | Declared wars only in prosperity gate | Proxy wars (`FUND_INSTABILITY`) do not block cultural production. Deliberate simplification — M53a calibration target. |
| 16 | Scorched earth = destructive conquest | Artifact destruction tied to existing `scorched_earth_check()`. Militant temple replacement does not destroy artifacts. |
| 17 | GP artifacts in aggregate mode via parallel hook | `check_great_person_generation()` gets its own intent emission, mirroring `_process_promotions()` in agent mode. |
