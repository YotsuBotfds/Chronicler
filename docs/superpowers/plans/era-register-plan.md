# Era-Adaptive Narrative Register — Implementation Plan

> **Author:** Phoebe (architectural review) → Cici (implementation)
> **Scope:** ~40 lines in `src/chronicler/narrative.py`, no model changes, no new files
> **Depends on:** Nothing. Independent of all milestones. Land before Nemotron 3 120B test.
> **Risk:** Zero — prompt-only change, no simulation mutations, existing tests unaffected.

---

## Problem

The narrative prompts use a single fixed register ("literary historian looking back centuries later") regardless of era. A Tribal-era cattle raid and an Industrial-era banking crisis get the same voice. The implied narrator never evolves, which flattens the tonal arc across a 500-turn chronicle.

## Design

### Era Register Table

Map tech eras to a **source register** — the kind of historical document that would plausibly exist in that period. The voice shifts because the *implied narrator* shifts.

```python
ERA_REGISTER: dict[str, tuple[str, str]] = {
    # era_key: (system_voice, style_instruction)
    "tribal": (
        "You are a keeper of oral traditions, transcribing stories passed down through generations.",
        "Write as an oral tradition — rhythmic, mythic, using 'it is said that' and 'the elders remember'. "
        "Names carry weight. Nature is animate. Causation is fate or spirits, not policy.",
    ),
    "bronze": (
        "You are a temple scribe recording events on clay tablets for the gods and kings.",
        "Write as a temple chronicle — declarative, formal, focused on kings and omens. "
        "Events are divine will made manifest. Lists of deeds matter. Brevity is authority.",
    ),
    "iron": (
        "You are an archaic chronicler in the tradition of Herodotus — a traveler recording what you witnessed and were told.",
        "Write as an early historian — curious, discursive, citing named witnesses. "
        "Include asides about customs. Causation mixes human ambition with fortune.",
    ),
    "classical": (
        "You are a classical historian in the tradition of Thucydides or Sima Qian — analytical, precise, concerned with causes.",
        "Write as a classical history — measured prose, focus on institutional causes and consequences. "
        "Leaders are judged by their decisions. War is analyzed, not glorified.",
    ),
    "medieval": (
        "You are a monastic chronicler recording events for posterity in a scriptorium.",
        "Write as a medieval chronicle — annalistic, with moral commentary woven in. "
        "Events reflect cosmic justice or human folly. Traditions and legitimacy matter deeply.",
    ),
    "renaissance": (
        "You are a Renaissance court historian with access to diplomatic archives and personal correspondence.",
        "Write as a Renaissance history — sophisticated, aware of competing accounts. "
        "Note irony and paradox. Power is a craft. Culture and commerce rival the sword.",
    ),
    "industrial": (
        "You are a 19th-century diplomatic historian writing for an educated public.",
        "Write as a modern analytical history — institutional language, economic forces, "
        "structural causes. Reference demographics and resources. Leaders are products of systems.",
    ),
    "information": (
        "You are a contemporary historian writing a definitive account with full archival access.",
        "Write as a contemporary history — precise, data-aware, multi-perspectival. "
        "Acknowledge complexity. Soft power and information flow matter as much as armies.",
    ),
}
```

### Dominant Era Selection

For a narrated moment, compute the **dominant era** from the moment's actors:

```python
ERA_ORDER = ["tribal", "bronze", "iron", "classical", "medieval", "renaissance", "industrial", "information"]

def get_dominant_era(moment: NarrativeMoment, snapshot: TurnSnapshot) -> str:
    """Highest tech era among civs involved in this moment's events.

    The most advanced actor sets the 'recording technology' — if a Medieval
    civ is fighting a Tribal civ, the chronicle reads Medieval because the
    more literate society is the one whose records survive.

    Falls back to median era of all living civs if no actors found in snapshot.
    """
    # Collect actor civs from the moment's events
    actor_civs = set()
    for event in moment.events:
        for actor in event.actors:
            if actor in snapshot.civ_stats:
                actor_civs.add(actor)

    if not actor_civs:
        # Fallback: all living civs
        actor_civs = {name for name, cs in snapshot.civ_stats.items() if cs.alive}

    if not actor_civs:
        return "tribal"

    # Highest era among actors
    eras = [snapshot.civ_stats[name].tech_era for name in actor_civs
            if name in snapshot.civ_stats]
    if not eras:
        return "tribal"

    return max(eras, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 0)
```

**Why highest, not median:** The records that survive come from the more literate society. When Rome writes about Germanic tribes, the register is Classical, not Tribal. The higher civilization is the implied author.

### `narrative_style` Override

If `self.narrative_style` is set (scenario-level override, e.g. Dead Miles' vehicle world voice), it **takes precedence** over era register. The era register is the default, not a mandate. This is already handled by the existing `style_text` block in the prompt — era register just replaces the generic baseline that `style_text` overrides.

---

## Files to Modify

### `src/chronicler/narrative.py` — All changes here

**1. Add `ERA_REGISTER` dict and `ERA_ORDER` list** (after `ROLE_INSTRUCTIONS`, ~line 192)

~25 lines. The table above.

**2. Add `get_dominant_era()` function** (~line 195, after the table)

~15 lines. The function above.

**3. Modify `narrate_batch()` system prompt** (line 476-481)

Current:
```python
system = (
    f"You are a literary historian writing a chronicle. "
    f"Write evocative prose as if looking back centuries later. "
    f"Do NOT include turn numbers or game mechanics in the prose. "
    f"ROLE: {role_instruction}"
)
```

New:
```python
# Get snapshot for this moment
snap = _closest_snap({s.turn: s for s in history}, moment.anchor_turn)
dominant_era = get_dominant_era(moment, snap) if snap else "tribal"
era_voice, era_style = ERA_REGISTER.get(dominant_era, ERA_REGISTER["tribal"])

system = (
    f"{era_voice} "
    f"Do NOT include turn numbers or game mechanics in the prose. "
    f"ROLE: {role_instruction}"
)
```

And inject `era_style` into the user prompt (only when `self.narrative_style` is not set):

```python
# Replace the generic style_text block
if self.narrative_style:
    style_text = f"\n\nNARRATIVE STYLE: {self.narrative_style}"
else:
    style_text = f"\n\nNARRATIVE REGISTER: {era_style}"
```

**4. Modify legacy `_build_chronicle_prompt_impl()` system role** (line 313)

Current:
```python
role_line = f"You are a historian chronicling the world of {world.name}."
```

New — compute dominant era from living civs on `world`:
```python
eras = [c.tech_era.value for c in world.civilizations if c.regions]
dominant = max(eras, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 0) if eras else "tribal"
era_voice, era_style = ERA_REGISTER.get(dominant, ERA_REGISTER["tribal"])
role_line = f"{era_voice} You chronicle the world of {world.name}."
```

And inject era style into the rules block (rule 1 replacement) when no `narrative_style` override:
```python
# Rule 1 currently: "Write in the style of a history — evocative, literary..."
# Replace with era-appropriate instruction when no scenario override
if narrative_style:
    rule_1 = f"1. {narrative_style}"
else:
    rule_1 = f"1. {era_style}"
```

---

## What Does NOT Change

- `build_action_prompt()` — action selection prompt stays mechanical, no era flavor needed
- `build_before_summary()` / `build_after_summary()` — these are mechanical diffs, not prose
- `NarrativeMoment`, `ChronicleEntry`, `NarrationContext` — no model changes
- `ROLE_INSTRUCTIONS` — narrative role (inciting/climax/etc.) is orthogonal to era register
- Domain threading rule — still applies at all eras
- Test suite — no behavioral change to simulation; narrative output changes are cosmetic

---

## Interaction with Nemotron 3 120B Test

This change is specifically valuable for the local model test because:

1. **Smaller models benefit more from explicit style guidance.** Claude can infer register from context. A 10B-active MoE model needs the instruction spelled out.
2. **Era-adaptive prompts give the model a clearer voice target** — "write as a temple scribe" is more actionable than "write as a literary historian" for a model with limited stylistic range.
3. **Multi-era runs will show whether Nemotron can actually shift register** — good diagnostic for model capability. If it can't, we know the model's ceiling.

---

## Verification

After implementation:
1. Run a 100-turn, 4-civ simulation with `--simulate-only`, then narrate with Nemotron
2. Check that early entries (Tribal/Bronze era) use mythic/oral register
3. Check that late entries (if civs advance) shift to analytical/institutional register
4. Confirm `narrative_style` override still works (run Dead Miles scenario, verify vehicle-world voice)
5. Existing test suite passes (986+ tests)

---

## Line Estimate

| Change | Lines |
|--------|-------|
| `ERA_REGISTER` dict | ~25 |
| `ERA_ORDER` list | 1 |
| `get_dominant_era()` function | ~15 |
| `narrate_batch()` system prompt modification | ~6 |
| `narrate_batch()` style_text modification | ~4 |
| `_build_chronicle_prompt_impl()` role_line modification | ~4 |
| `_build_chronicle_prompt_impl()` rule 1 modification | ~4 |
| **Total** | **~59 lines** |
