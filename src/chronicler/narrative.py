"""LLM narrative engine for chronicle generation.

Uses two LLMClient instances for historical compatibility:
- sim_client is retained for older call sites but does not decide simulation actions
- narrative_client produces chronicle prose

Domain threading (Caves of Qud technique): each civilization's thematic
keywords (domains) are woven into every narrative mention, creating the
perception of deep cultural coherence with minimal mechanical overhead.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Callable, Sequence

logger = logging.getLogger(__name__)

from chronicler import narration_context as nc
from chronicler import narration_provenance as npv
from chronicler.historical_context import AsOf, HistoricalRecord, HistoricalView, snapshot_as_of
from chronicler.llm import AnthropicClient, GeminiClient, LLMClient
from chronicler.models import (
    AgentContext,
    CausalChain,
    CausalLink,
    ChronicleEntry,
    Civilization,
    Event,
    NarrativeMoment,
    NarrativeRole,
    NamedEvent,
    SettlementSummary,
    ShockContext,
    TurnSnapshot,
    WorldState,
)


_SUMMARY_STATS = ("population", "military", "economy", "culture", "stability")
_STAT_THRESHOLD = 10

_MAX_ARC_SUMMARY_SENTENCES = 3


def _update_arc_summary(gp, new_sentence: str) -> None:
    """Append a sentence to gp.arc_summary, keeping max 3 sentences."""
    if gp.arc_summary:
        sentences = [s.strip() for s in gp.arc_summary.split(".") if s.strip()]
    else:
        sentences = []
    sentences.append(new_sentence.rstrip("."))
    if len(sentences) > _MAX_ARC_SUMMARY_SENTENCES:
        sentences = sentences[-_MAX_ARC_SUMMARY_SENTENCES:]
    gp.arc_summary = ". ".join(sentences) + "."


# ---------------------------------------------------------------------------
# M30: Agent context for narrator prompt
# ---------------------------------------------------------------------------

_MAX_NAMED_CHARACTERS = 6   # per prompt (token budget)
_MAX_MEMORIES = 3           # per character, the most intense

_DESPERATE_EVENTS = {"local_rebellion", "demographic_crisis"}
_RESTLESS_EVENTS = {"loyalty_cascade", "brain_drain", "occupation_shift"}

# ---------------------------------------------------------------------------
# M48: Memory descriptions for narration
# ---------------------------------------------------------------------------

MEMORY_DESCRIPTIONS = {
    # Agents remember any month below 0.6 food sufficiency: hunger, which a
    # famine is only when it lasts (ecology.FAMINE_SEVERE_TURNS).
    0: "hunger under the {civ}",
    1: "combat against the {civ}",
    2: "the fall of the {civ}",
    3: "persecution by the {civ}",
    4: "a migration from {civ} lands",
    5: "a time of prosperity",
    6: "victory over the {civ}",
    7: "a great achievement",
    8: "the birth of a child",
    9: "the death of kin",
    10: "a change of faith",
    11: "the fracture of the {civ}",
}

MEMORY_NARRATION_VIVID = 60   # [FROZEN M53 SOFT]
MEMORY_NARRATION_FADING = 30  # [FROZEN M53 SOFT]

# ---------------------------------------------------------------------------
# M49: Need descriptions for narration
# ---------------------------------------------------------------------------

NEED_DESCRIPTIONS = {
    "safety": "feels unsafe",
    "material": "wants for material comfort",
    "social": "is isolated",
    "spiritual": "is spiritually adrift",
    "autonomy": "chafes under foreign rule",
    "purpose": "lacks a sense of purpose",
}

# Thresholds must match agent.rs constants
_NEED_THRESHOLDS = {
    "safety": 0.3, "material": 0.3, "social": 0.35,
    "spiritual": 0.3, "autonomy": 0.35, "purpose": 0.35,
}


def render_needs(needs: dict) -> list[str]:
    """Render needs as narrator context lines.

    Returns lines like:
      "Needs: Safety satisfied, Material LOW (0.18), ..."
      "  - wants for material comfort"
    """
    if not needs:
        return []
    parts = []
    low_descriptions = []
    for name in ["safety", "material", "social", "spiritual", "autonomy", "purpose"]:
        val = needs.get(name, 0.5)
        threshold = _NEED_THRESHOLDS.get(name, 0.3)
        if val < threshold:
            parts.append(f"{name.title()} LOW ({val:.2f})")
            desc = NEED_DESCRIPTIONS.get(name)
            if desc:
                low_descriptions.append(f"  - {desc}")
        else:
            parts.append(f"{name.title()} satisfied")
    lines = [f"Needs: {', '.join(parts)}"]
    lines.extend(low_descriptions)
    return lines


def render_memory(mem: dict, civ_names: list, strength_observed: bool = True) -> str | None:
    """Render a memory slot as a natural language fragment.

    With ``strength_observed`` False the intensity is a later observation, a
    lower bound of the memory's strength at the moment (memories only fade):
    "vivid" is said only when the bound is vivid, "fading" never.
    """
    intensity = abs(mem.get("intensity", 0))
    if intensity < MEMORY_NARRATION_FADING:
        return None  # too weak to mention
    is_legacy = mem.get("is_legacy", False)
    template = MEMORY_DESCRIPTIONS.get(mem["event_type"], "an event")
    source = mem.get("source_civ", 0)
    civ_name = civ_names[source] if source < len(civ_names) else "unknown"
    descriptor = "vivid" if intensity >= MEMORY_NARRATION_VIVID else "fading"
    text = template.format(civ=civ_name)
    if is_legacy:
        text = f"an ancestral memory of {text}"
    if not strength_observed and descriptor != "vivid":
        return f"{text} (turn {mem['turn']})"
    return f"{text} (turn {mem['turn']}, {descriptor})"


def compute_population_mood(events: list[Event]) -> str:
    """Compute population mood from agent events. Worst wins."""
    agent_types = {e.event_type for e in events if e.source == "agent"}
    if agent_types & _DESPERATE_EVENTS:
        return "desperate"
    if agent_types & _RESTLESS_EVENTS:
        return "restless"
    return "content"


def _character_turn(char: dict, relationships: Sequence[dict]) -> int | None:
    """The latest turn a character's prompt lines date (birth, deeds,
    memories, bonds): later than the moment only if a later record leaked."""
    turns = [char.get("born_turn")]
    turns += [h.get("turn") for h in char.get("recent_history", [])]
    turns += [m.get("turn") for m in char.get("memories", []) or []]
    turns += [r.get("since_turn") for r in relationships
              if char["name"] in (r.get("character_a"), r.get("character_b"))]
    turns = [t for t in turns if isinstance(t, int)]
    return max(turns) if turns else None


def build_agent_context_block(ctx: AgentContext | None, sheet=None, refs: dict | None = None) -> str:
    """Build the agent context section for the narrator prompt.

    With ``sheet`` (``narration_provenance.FactSheet``) every fact line is
    registered and tagged; ``refs`` holds the fact ids the context itself
    does not carry (``mood``, ``displacement``, ``urban``, ``trade``: each
    ``(id, turn)``; ``settlements_turn``: the snapshot of the settlements;
    ``shocks``: one ``(id, turn)`` per active shock; ``agent_ids``: name ->
    agent id of characters named in relationships).
    """
    if ctx is None:
        return ""
    refs = refs or {}

    def tag(text: str, *facts) -> str:
        return sheet.line(text, facts) if sheet is not None else text

    char_ids: dict[str, tuple[str, int | None]] = {}
    if sheet is not None:
        for char in ctx.named_characters:
            fid = sheet.ids.character(char.get("agent_id"), char["name"], char.get("born_turn"))
            char_ids[char["name"]] = (fid, _character_turn(char, ctx.relationships))
        for name, agent_id in (refs.get("agent_ids") or {}).items():
            char_ids.setdefault(name, (sheet.ids.character(agent_id, name), None))

    lines = ["## Agent Context"]
    lines.append(tag(f"Population mood: {ctx.population_mood}", refs.get("mood")))
    if ctx.displacement_observed:
        lines.append(tag(f"Displacement: {int(ctx.displacement_fraction * 100)}% of population displaced",
                         refs.get("displacement")))
    if abs(ctx.urban_fraction_delta_20t) > 1e-6:
        lines.append(tag(f"Urbanization trend (20 turns): {ctx.urban_fraction_delta_20t * 100.0:+.1f}pp",
                         refs.get("urban")))
    if ctx.top_settlements:
        lines.append("Largest settlements:")
        snap_turn = refs.get("settlements_turn")
        for settlement in ctx.top_settlements:
            fact = ((sheet.ids.snapshot(snap_turn, "settlement", settlement.settlement_id), snap_turn - 1)
                    if sheet is not None and snap_turn is not None else None)
            lines.append(tag(
                f"- {settlement.name} ({settlement.region_name}, pop ~{settlement.population_estimate})", fact))
    lines.append("")

    if ctx.named_characters:
        lines.append("Named characters present:")
        for char in ctx.named_characters:
            origin = (f", originally {char.get('origin_civ')}"
                      if char.get("origin_civ") != char.get("civ") and char.get("origin_civ") else "")
            trait_str = f" [{char['trait']}]" if char.get("trait") else ""
            first = len(lines)
            lines.append(tag(
                f"- {char['role']} {char['name']}{trait_str} ({char['civ']}{origin}) [{char['status']}]:",
                char_ids.get(char["name"]))
            )
            # M45: Arc context
            arc_type = char.get("arc_type")
            arc_phase = char.get("arc_phase")
            if arc_type or arc_phase:
                arc_str = arc_type or ""
                if arc_phase:
                    arc_str = f"{arc_str} ({arc_phase})" if arc_str else arc_phase
                lines.append(f"  Arc: {arc_str}")
            if char.get("arc_summary"):
                lines.append(f"  Summary: {char['arc_summary']}")
            history_parts = []
            for h in char.get("recent_history", []):
                turn = h.get("turn")
                if turn is None:
                    history_parts.append(f"  {h['event']} in {h['region']}")
                else:
                    history_parts.append(f"  {h['event']} in {h['region']} (turn {turn})")
            if history_parts:
                lines.append(";".join(history_parts))
            if char.get("dynasty"):
                dynasty_line = f"  House of {char['dynasty']}"
                if char.get("dynasty_living", 0) == 1:
                    dynasty_line += " (last of their line)"
                elif char.get("dynasty_split"):
                    dynasty_line += " (dynasty divided)"
                else:
                    dynasty_line += f" ({char['dynasty_living']}/{char['dynasty_total']} living)"
                lines.append(dynasty_line)
            # M57a: Lineage house context (secondary dynasty from other parent)
            if char.get("lineage_house"):
                lines.append(f"  With lineage ties to the House of {char['lineage_house']}")
            # M48: Memory context
            if char.get("memories"):
                civ_names = char.get("_civ_names", [])
                observed = char.get("memory_strength_observed", True)
                strongest = sorted(char["memories"],
                                   key=lambda m: (-abs(m.get("intensity", 0)), -m.get("turn", 0)))
                rendered = [render_memory(m, civ_names, observed) for m in strongest]
                rendered = [r for r in rendered if r is not None][:_MAX_MEMORIES]
                if rendered:
                    lines.append("  Memories:")
                    for r in rendered:
                        lines.append(f"    - {r}")
            # M48: Mule context
            if char.get("mule") and char.get("status") == "active":
                overrides = char.get("utility_overrides", {})
                remaining = char.get("mule_remaining", 0)
                if remaining > 0 and overrides:
                    overrides_str = ", ".join(
                        f"{k} x{v}" for k, v in overrides.items()
                    )
                    lines.append(f"  [MULE] Active influence: {overrides_str}")
                    lines.append(f"    Window: {remaining} turns remaining")
            # M49: Needs context
            char_needs = char.get("needs")
            if char_needs:
                needs_lines = render_needs(char_needs)
                for line in needs_lines:
                    lines.append(line)
            if sheet is not None:  # the character's lines name what its fact names
                for line in lines[first + 1:]:
                    sheet.names_in(line)
        lines.append("")

    # M40: Render relationship context
    if ctx.relationships:
        lines.append("Character relationships:")
        for rel in ctx.relationships:
            pair = [char_ids.get(rel.get("character_a")), char_ids.get(rel.get("character_b"))]
            pair = [(fid, rel.get("since_turn")) for fid, _t in (p for p in pair if p)]
            if rel["type"] == "mentor":
                text = f"- {rel['character_b']} (apprentice of {rel['character_a']}, since turn {rel['since_turn']})"
            elif rel["type"] == "hostage":
                text = f"- {rel['character_b']} (hostage of {rel['character_a']})"
                pair = [(fid, None) for fid, _t in pair]
            else:
                text = f"- {rel['character_a']} and {rel['character_b']} ({rel['type']}, since turn {rel['since_turn']})"
            lines.append(tag(text, *pair))
        lines.append("")

    # M43b: Trade dependency and supply shock context
    if ctx.trade_dependent_regions:
        lines.append(tag(f"Trade-dependent regions: {', '.join(ctx.trade_dependent_regions)}", refs.get("trade")))
    if ctx.active_shocks:
        shock_facts = list(refs.get("shocks") or [])
        for k, shock in enumerate(ctx.active_shocks):
            lines.append(tag(
                f"Supply crisis in {shock.region}: {shock.category} "
                f"(severity {shock.severity:.1f}, "
                f"source: {shock.upstream_source or 'local'})",
                shock_facts[k] if k < len(shock_facts) else None,
            ))
    if ctx.trade_dependent_regions or ctx.active_shocks:
        lines.append("")

    lines.append("Guidelines:")
    lines.append("- Refer to named characters BY NAME — do not anonymize or rename them")
    lines.append("- Use their recent history for callbacks")
    lines.append("- Use population mood to set atmospheric tone")
    if ctx.displacement_observed and ctx.displacement_fraction > 0.10:
        lines.append("- Weave refugee/exile themes into the narrative")
    if ctx.relationships:
        lines.append("- Weave character relationships into the narrative — mentorships, rivalries, alliances")

    lines.append("")
    lines.append(
        "Character Continuity: When a named character has appeared in previous "
        "chronicle entries, maintain their name and identity. Do not re-introduce "
        "them or invent backstory that contradicts their listed history. "
        "The named characters list is authoritative."
    )

    return "\n".join(lines)


def build_agent_context_for_moment(
    moment: NarrativeMoment,
    great_persons: list,
    displacement_by_region: dict[int, float],
    dynasty_registry=None,       # M39: optional DynastyRegistry
    gp_by_agent_id: dict | None = None,  # M39: agent_id → GreatPerson
    social_edges: list[tuple] | None = None,      # M40
    dissolved_edges: list[tuple] | None = None,    # M40
    agent_name_map: dict[int, str] | None = None,  # M40
    hostage_data: list[dict] | None = None,        # M40
    civ_idx: int | None = None,                    # M41: which civ to pull gini for
    gini_by_civ: dict[int, float] | None = None,   # M41: per-civ Gini coefficients
    economy_result=None,  # M43b
    civ_names: list[str] | None = None,  # M48: for memory rendering
    world_turn: int = 0,  # M48: current turn for Mule window calculation
    history: Sequence[TurnSnapshot] | None = None,  # M56b: for urban delta
    current_snapshot: TurnSnapshot | None = None,  # M56b: for focal civ stats
    world: WorldState | None = None,  # M56b: for settlement enumeration
    view: HistoricalView | None = None,
) -> AgentContext | None:
    """Build AgentContext if the moment has agent-source or economy events.

    Everything comes from ``view`` (``historical_context``), what the record
    says after the moment's last turn: the characters born by then, their
    status, deeds, memories and bonds as of then, the snapshot of that turn,
    and the bridge's observations only when they describe it. ``view`` is
    then the only source and the per-value arguments are ignored (except
    ``gp_by_agent_id`` for dynasty lookups, ``civ_idx``, ``civ_names`` and
    ``world_turn``). Without a view (direct callers) one is built from the
    arguments, which the caller vouches describe the moment; the dated
    filters still apply, and ``current_snapshot`` is the snapshot read.
    """
    legacy = view is None
    if legacy:
        record = HistoricalRecord(
            history=history or (), great_persons=great_persons, world=world,
            events=list(moment.events), observed_through=None,
            gini_by_civ=gini_by_civ, displacement_by_region=displacement_by_region,
            economy_result=economy_result, social_edges=social_edges,
            dissolved_edges_by_turn=({moment.turn_range[0]: list(dissolved_edges)}
                                     if dissolved_edges else None),
            agent_name_map=agent_name_map, dynasty_registry=dynasty_registry,
        )
        view = record.view(AsOf.after(moment.turn_range[1]))
        snap = current_snapshot
    else:
        snap = view.snapshot
        history = view.record.history
        hostage_data = None
    economy_result = view.record.economy_result

    agent_events = [e for e in moment.events if e.source == "agent"]
    economy_events = [e for e in moment.events if e.source == "economy"]
    if not agent_events and not (economy_result is not None and economy_events):
        return None

    # Named characters of this moment: those its events name, and the active
    # characters of the civs its events involve, as of the moment's end.
    moment_actors = {actor for ev in moment.events for actor in ev.actors}
    moment_civs = moment_actors | {c for ev in moment.events for c in ev.civs}
    present = view.moment_characters(moment_actors, moment_civs)
    chars = []
    for c in present:
        char = {
            "name": c.name,
            "role": c.role.title(),
            "civ": c.civilization,
            "origin_civ": c.origin_civilization,
            "status": c.status,
            "born_turn": c.born_turn,
            "recent_history": [
                {"event": d.text, "region": d.region or "unknown", "turn": d.turn}
                for d in c.deeds[-3:]
            ],
        }
        # M50b: include agent_id for bond lookups
        if c.agent_id is not None:
            char["agent_id"] = c.agent_id
        # M39/M57a: dynasty and lineage house, members counted as of the moment
        if gp_by_agent_id is not None and c.agent_id:
            dynasty = view.dynasty(c, gp_by_agent_id)
            if dynasty:
                char.update(dynasty)
        # M45: Arc context
        if c.arc_type:
            char["arc_type"] = c.arc_type
        if c.arc_phase:
            char["arc_phase"] = c.arc_phase
        if c.arc_summary:
            char["arc_summary"] = c.arc_summary
        if c.trait:
            char["trait"] = c.trait
        # M48: Memory context (recorded by the moment's end)
        if c.memories:
            char["memories"] = [dict(m) for m in c.memories]
            char["_civ_names"] = civ_names or []
            if not c.memory_strength_observed:
                char["memory_strength_observed"] = False
        # M49: Needs context (observed values only)
        if c.active and c.needs:
            char["needs"] = dict(c.needs)
        # M48: Mule context
        if c.mule and c.active:
            from chronicler.action_engine import MULE_ACTIVE_WINDOW, MULE_FADE_TURNS
            char["mule"] = True
            char["utility_overrides"] = dict(c.utility_overrides)
            remaining = (c.born_turn + MULE_ACTIVE_WINDOW + MULE_FADE_TURNS) - world_turn
            char["mule_remaining"] = max(0, remaining)
        chars.append(char)

    mood = compute_population_mood(agent_events)
    displacement = view.displacement()

    # M40+M50b: relationships live at the moment's end, those dissolved
    # during the moment, and hostages held then.
    relationships = view.relationships(present, moment.turn_range,
                                       per_character_bonds=bool(gp_by_agent_id))
    char_names = {c["name"] for c in chars}
    if hostage_data:  # legacy callers list hostages themselves
        relationships = [r for r in relationships if r["type"] != "hostage"]
    for h in (hostage_data or []):
        if h.get("character_b") in char_names or h.get("character_a") in char_names:
            relationships.append(h)

    # M56b: Urbanization context — focal civ, urban delta, top settlements
    focal_civ = None
    if snap is not None:
        for ev in moment.events:
            for actor in ev.actors:
                if actor in snap.civ_stats:
                    focal_civ = actor
                    break
            if focal_civ is not None:
                break
        if focal_civ is None and snap.civ_stats:
            focal_civ = sorted(snap.civ_stats.keys())[0]

    # M41: Gini — the bridge's when it describes the moment, else the snapshot's.
    if legacy:
        gini = (gini_by_civ or {}).get(civ_idx) if civ_idx is not None else None
        if gini is None and snap is not None and focal_civ is not None:
            row = snap.civ_stats.get(focal_civ)
            gini = row.gini if row is not None else None
        gini = gini if gini is not None else 0.0
    else:
        gini = view.gini(civ_idx, focal_civ)

    urban_fraction_delta_20t = 0.0
    if history and snap is not None and focal_civ is not None:
        current_stats = snap.civ_stats.get(focal_civ)
        if current_stats is not None:
            current_frac = current_stats.urban_fraction
            past_turn = snap.turn - 20
            past_snapshot = next((s for s in history if s.turn == past_turn), None)
            if past_snapshot is not None and focal_civ in past_snapshot.civ_stats:
                urban_fraction_delta_20t = current_frac - past_snapshot.civ_stats[focal_civ].urban_fraction

    # Settlements from the snapshot of the moment (the world holds only the end).
    top_settlements: list[SettlementSummary] = []
    if focal_civ is not None:
        if not legacy:
            top_settlements = view.settlements(focal_civ)
        elif world is not None:
            top_settlements = _world_settlements(world, focal_civ)

    # Characters the moment's events name come first; cap for the token budget.
    chars.sort(key=lambda c: c["name"] not in moment_actors)
    ctx = AgentContext(
        named_characters=chars[:_MAX_NAMED_CHARACTERS],
        population_mood=mood,
        displacement_fraction=displacement if displacement is not None else 0.0,
        displacement_observed=displacement is not None,
        relationships=relationships,
        gini_coefficient=gini,
        urban_fraction_delta_20t=urban_fraction_delta_20t,
        top_settlements=top_settlements,
    )

    # M43b: trade dependency (observed) and the moment's own supply shocks
    if economy_result is not None:
        ctx.trade_dependent_regions = view.trade_dependent_regions() or []
        ctx.active_shocks = [
            ShockContext(
                region=ev.shock_region,
                category=ev.shock_category,
                severity=(ev.importance - 5) / 4.0,
                upstream_source=ev.actors[1] if len(ev.actors) > 1 else None,
            )
            for ev in moment.events
            if ev.event_type == "supply_shock" and ev.shock_region is not None and ev.shock_category is not None
        ]
    return ctx


def _world_settlements(world: WorldState, civ_name: str) -> list[SettlementSummary]:
    """The three largest active settlements of a civ in a world (current state)."""
    candidates: list[SettlementSummary] = []
    for region in world.regions:
        if region.controller != civ_name:
            continue
        for s in region.settlements:
            if s.status.value not in ("active", "dissolving"):
                continue
            candidates.append(
                SettlementSummary(
                    settlement_id=s.settlement_id,
                    name=s.name,
                    region_name=s.region_name,
                    population_estimate=s.population_estimate,
                    centroid_x=s.centroid_x,
                    centroid_y=s.centroid_y,
                    founding_turn=s.founding_turn,
                    status=s.status.value,
                )
            )
    candidates.sort(key=lambda ss: (-ss.population_estimate, ss.settlement_id))
    return candidates[:3]


def build_before_summary(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    prev_moment: NarrativeMoment | None,
) -> str:
    """Mechanical before-context from snapshot diffs.

    Compare prev_moment.anchor_turn (or turn 1 if None) to moment.anchor_turn.
    Report stat changes > 10, territory gains/losses. Return 3-5 bullet points.
    """
    _ref, _target, bullets = before_changes(history, moment, prev_moment)
    return "\n".join(f"- {text}" for _key, _attr, text in bullets) if bullets else ""


def before_changes(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    prev_moment: NarrativeMoment | None,
) -> tuple[int | None, int | None, list[tuple[tuple, str | None, str]]]:
    """The before-context's changes: the two snapshots' turns and, per
    bullet, what changed (``("civ", name)`` and a stat, or ``("region",
    name)``) and its text."""
    snap_by_turn: dict[int, TurnSnapshot] = {s.turn: s for s in history}
    if not snap_by_turn:
        return None, None, []

    # Reference turn: prev_moment's anchor, or the first available turn
    if prev_moment is not None:
        ref_turn = prev_moment.anchor_turn
    else:
        ref_turn = min(snap_by_turn.keys())

    target_turn = moment.anchor_turn

    # The snapshots labelled at (or the latest before) those turns: the
    # state before the anchor turn ran, never a later one (historical_context).
    target_snap = snapshot_as_of(history, AsOf.at_snapshot(target_turn))
    if target_snap is None:
        return None, None, []
    # A reference before the history starts reads from its first snapshot.
    ref_snap = (snapshot_as_of(history, AsOf.at_snapshot(ref_turn))
                or snap_by_turn[min(snap_by_turn)])
    if ref_snap.turn > target_snap.turn:
        return None, None, []

    bullets: list[tuple[tuple, str | None, str]] = []

    # Stat changes per civ
    all_civs = set(ref_snap.civ_stats.keys()) | set(target_snap.civ_stats.keys())
    for civ in sorted(all_civs):
        if civ not in ref_snap.civ_stats or civ not in target_snap.civ_stats:
            continue
        before = ref_snap.civ_stats[civ]
        after = target_snap.civ_stats[civ]
        for stat in _SUMMARY_STATS:
            old_val = getattr(before, stat)
            new_val = getattr(after, stat)
            delta = new_val - old_val
            if abs(delta) > _STAT_THRESHOLD:
                direction = "rose" if delta > 0 else "fell"
                bullets.append((("civ", civ), stat, f"{civ} {stat} {direction} from {old_val} to {new_val}"))

    # Territory gains/losses
    ref_regions = set(ref_snap.region_control.keys())
    target_regions = set(target_snap.region_control.keys())
    all_regions = ref_regions | target_regions
    for region in sorted(all_regions):
        ctrl_before = ref_snap.region_control.get(region)
        ctrl_after = target_snap.region_control.get(region)
        if ctrl_before != ctrl_after:
            if ctrl_after and ctrl_before:
                text = f"{ctrl_after} took {region} from {ctrl_before}"
            elif ctrl_after:
                text = f"{ctrl_after} claimed {region}"
            else:
                text = f"{ctrl_before} lost {region}"
            bullets.append((("region", region), None, text))

    # Cap at 5 bullets
    return ref_snap.turn, target_snap.turn, bullets[:5]


def build_after_summary(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    next_moment: NarrativeMoment | None,
) -> str:
    """Mechanical after-context for foreshadowing.

    Compare moment.anchor_turn to next_moment.anchor_turn (or final turn if None).
    Forward-looking: "will rise/fall to X".
    """
    _now, _later, bullets = after_changes(history, moment, next_moment)
    return "\n".join(f"- {text}" for _key, _attr, text in bullets) if bullets else ""


def after_changes(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    next_moment: NarrativeMoment | None,
) -> tuple[int | None, int | None, list[tuple[tuple, str | None, str]]]:
    """The after-context's changes, as :func:`before_changes`."""
    snap_by_turn: dict[int, TurnSnapshot] = {s.turn: s for s in history}
    if not snap_by_turn:
        return None, None, []

    current_turn = moment.anchor_turn

    # Reference turn: next_moment's anchor, or last available turn
    if next_moment is not None:
        ref_turn = next_moment.anchor_turn
    else:
        ref_turn = max(snap_by_turn.keys())

    current_snap = _closest_snap(snap_by_turn, current_turn)
    future_snap = _closest_snap(snap_by_turn, ref_turn)

    if current_snap is None or future_snap is None:
        return None, None, []

    bullets: list[tuple[tuple, str | None, str]] = []

    # Stat changes per civ (forward-looking language)
    all_civs = set(current_snap.civ_stats.keys()) | set(future_snap.civ_stats.keys())
    for civ in sorted(all_civs):
        if civ not in current_snap.civ_stats or civ not in future_snap.civ_stats:
            continue
        now = current_snap.civ_stats[civ]
        later = future_snap.civ_stats[civ]
        for stat in _SUMMARY_STATS:
            now_val = getattr(now, stat)
            later_val = getattr(later, stat)
            delta = later_val - now_val
            if abs(delta) > _STAT_THRESHOLD:
                direction = "will rise" if delta > 0 else "will fall"
                bullets.append((("civ", civ), stat, f"{civ} {stat} {direction} to {later_val}"))

    # Territory changes (forward-looking)
    current_regions = set(current_snap.region_control.keys())
    future_regions = set(future_snap.region_control.keys())
    all_regions = current_regions | future_regions
    for region in sorted(all_regions):
        ctrl_now = current_snap.region_control.get(region)
        ctrl_later = future_snap.region_control.get(region)
        if ctrl_now != ctrl_later:
            if ctrl_later and ctrl_now:
                text = f"{region} will pass from {ctrl_now} to {ctrl_later}"
            elif ctrl_later:
                text = f"{region} will be claimed by {ctrl_later}"
            else:
                text = f"{ctrl_now} will lose {region}"
            bullets.append((("region", region), None, text))

    # Cap at 5 bullets
    return current_snap.turn, future_snap.turn, bullets[:5]


def _closest_snap(
    snap_by_turn: dict[int, TurnSnapshot],
    target: int,
) -> TurnSnapshot | None:
    """Find the snapshot closest to target turn."""
    if not snap_by_turn:
        return None
    if target in snap_by_turn:
        return snap_by_turn[target]
    # Find nearest turn
    turns = sorted(snap_by_turn.keys())
    best = min(turns, key=lambda t: abs(t - target))
    return snap_by_turn[best]


ROLE_INSTRUCTIONS = {
    NarrativeRole.INCITING: "Introduce the tension. Something has changed that cannot be undone.",
    NarrativeRole.ESCALATION: "Build on what came before. The stakes are rising.",
    NarrativeRole.CLIMAX: "This is the turning point. Maximum consequence, maximum drama.",
    NarrativeRole.RESOLUTION: "The dust settles. Show what was won and what was lost.",
    NarrativeRole.CODA: "Look back on what happened. Reflect on the arc of this history.",
}

ERA_ORDER = ["tribal", "bronze", "iron", "classical", "medieval", "renaissance", "industrial", "information"]

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


def get_dominant_era(moment: NarrativeMoment, snapshot: TurnSnapshot) -> str:
    """Highest tech era among civs involved in this moment's events.

    The most advanced actor sets the 'recording technology' — if a Medieval
    civ is fighting a Tribal civ, the chronicle reads Medieval because the
    more literate society is the one whose records survive.

    Falls back to median era of all living civs if no actors found in snapshot.
    """
    actor_civs = set()
    for event in moment.events:
        for actor in event.actors:
            if actor in snapshot.civ_stats:
                actor_civs.add(actor)

    if not actor_civs:
        actor_civs = {name for name, cs in snapshot.civ_stats.items() if cs.alive}

    if not actor_civs:
        return "tribal"

    eras = [snapshot.civ_stats[name].tech_era for name in actor_civs
            if name in snapshot.civ_stats]
    if not eras:
        return "tribal"

    return max(eras, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 0)


def thread_domains(text: str, civ_name: str, civ_domains: dict[str, list[str]]) -> str:
    """Weave civilization domain keywords into narrative text.

    This is a post-processing hint — the real domain threading happens
    in the LLM prompt where we instruct it to reference domains.
    For non-LLM contexts (testing), returns text unchanged.
    """
    if civ_name not in civ_domains:
        return text
    return text


def build_chronicle_prompt(world: WorldState, events: list[Event]) -> str:
    """Backward-compatible wrapper — delegates to a no-flavor, no-style build."""
    return _build_chronicle_prompt_impl(world, events, event_flavor=None, narrative_style=None)


def _build_chronicle_prompt_impl(
    world: WorldState, events: list[Event],
    event_flavor: dict | None = None,
    narrative_style: str | None = None,
    sheet: npv.FactSheet | None = None,
) -> str:
    """Build the prompt for LLM chronicle narration.

    With ``sheet`` (``narration_provenance.FactSheet``) every fact line is
    registered and, when the sheet tags, tagged with its ids and the model
    asked to cite them: the world's state as observed after this turn
    (``o<T>.civ.c<i>``, ``o<T>.rival.c<i>``, ``o<T>.governance``), the
    turn's events and the landmarks.
    """
    turn = world.turn

    def tag(text: str, *facts) -> str:
        return sheet.line(text, facts) if sheet is not None else text

    def tag_block(text: str, *facts) -> str:
        """A fact of several lines: the tag on its first."""
        if sheet is None:
            return text
        head, sep, rest = text.partition("\n")
        sheet.names_in(rest)
        return sheet.line(head, facts) + sep + rest

    # Build civilization summaries
    civ_summaries = ""
    for i, civ in enumerate(world.civilizations):
        summary = f"{civ.name} (domains: {', '.join(civ.domains)}):"
        summary += f" Pop {civ.population}, Mil {civ.military}, Econ {civ.economy},"
        summary += f" Culture {civ.culture}, Stability {civ.stability},"
        summary += f" Treasury {civ.treasury}, Asabiya {civ.asabiya}"
        summary += f"\n  Leader: {civ.leader.name} ({civ.leader.trait})"
        summary += f"\n  Regions: {', '.join(civ.regions)}"
        civ_summaries += "\n" + tag_block(
            summary, (sheet.ids.observation(turn, "civ", ("civ", civ.name)), turn) if sheet is not None else None)

    # Build event list with flavor substitution
    event_text = ""
    for e in events:
        display_type = e.event_type
        display_desc = nc.event_text(e)
        if event_flavor and e.event_type in event_flavor:
            display_type = event_flavor[e.event_type].name
            display_desc = event_flavor[e.event_type].description
        event_text += "\n" + tag(
            f"- [{display_type}] {display_desc} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)",
            (sheet.ids.event(e), e.turn) if sheet is not None else None)

    # Named events context for historical callbacks
    named_context = ""
    if world.named_events:
        recent = world.named_events[-5:]
        named_context += "\n\nRecent historical landmarks:\n"
        for ne in recent:
            named_context += tag(f"- {ne.name} (turn {ne.turn}): {ne.description}",
                                 (sheet.ids.named(ne), ne.turn) if sheet is not None else None) + "\n"

        best_named = max(world.named_events, key=lambda ne: ne.importance)
        if best_named not in recent:
            named_context += "\n" + tag(
                f"Most significant event in all history: {best_named.name} (turn {best_named.turn})",
                (sheet.ids.named(best_named), best_named.turn) if sheet is not None else None) + "\n"

        named_context += "\nReference these landmarks when relevant — weave callbacks to past events.\n"

    # Rivalry context
    rivalries = []
    for civ in world.civilizations:
        if civ.leader.rival_leader:
            rivalries.append(tag(
                f"{civ.leader.name} of {civ.name} has a personal rivalry with {civ.leader.rival_leader} of {civ.leader.rival_civ}",
                (sheet.ids.observation(turn, "rival", ("civ", civ.name)), turn) if sheet is not None else None))
    rivalry_context = ""
    if rivalries:
        rivalry_context += "\n\nActive rivalries:\n"
        for r in rivalries:
            rivalry_context += f"- {r}\n"
        rivalry_context += "Weave these personal rivalries into the narrative when relevant.\n"

    # Phase 8 governance context (absent when the governance runtime is off)
    governance_context = ""
    if getattr(world, "governance", None) is not None:
        from chronicler.governance_runtime import governance_context_lines
        lines = governance_context_lines(world)
        if lines:
            gov = (sheet.ids.observation(turn, "governance"), turn) if sheet is not None else None
            lines = [tag(line, gov) for line in lines]
            governance_context = ("\n\nInstitutions, rulers and the strains of the age:\n" + "\n".join(lines)
                                  + "\nLet laws, a ruler's standing and vows, and rising or easing stress "
                                    "colour the narrative.\n")

    # Era-adaptive role line
    eras = [c.tech_era.value for c in world.civilizations if c.regions]
    dominant = max(eras, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 0) if eras else "tribal"
    era_voice, era_style = ERA_REGISTER.get(dominant, ERA_REGISTER["tribal"])
    role_line = f"{era_voice} You chronicle the world of {world.name}."
    if narrative_style:
        role_line += f"\n\nNARRATIVE STYLE: {narrative_style}"
    cite_rule = f"\n8. {npv.CITE_INSTRUCTION}" if sheet is not None and sheet.tags else ""

    return f"""{role_line}

TURN {world.turn}:

CIVILIZATIONS:{civ_summaries}

EVENTS THIS TURN:{event_text}{named_context}{rivalry_context}{governance_context}

Write a chronicle entry for this turn. Rules:
1. {narrative_style if narrative_style else era_style}
2. For each civilization mentioned, weave their cultural DOMAINS into the prose. A maritime culture's trade dispute involves harbors and currents; a mountain culture's crisis involves peaks and stone. This is critical for thematic coherence.
3. Focus on events with importance >= 5. Mention lower-importance events briefly or skip them.
4. Reference specific leader names, region names, and cultural values where relevant.
5. End with a sentence that hints at coming tension or change.
6. Do NOT include turn numbers or game mechanics in the prose.
7. Write 3-5 paragraphs.{cite_rule}

Respond only with the chronicle prose. No preamble, no markdown formatting, no meta-commentary."""


def render_because(chain: CausalChain, told: set[str] | None = None) -> str:
    """One sentence that walks a recorded chain backwards from its effect.

    "Famine strikes X (turn 9), because Supply shock: food in X (turn 9),
    because X is occupied by Y (turn 6), because A goes to war with B (turn 0)."
    With ``told`` (ids already narrated) the walk stops at the first cause
    narrated before ("..., as told above") and adds the chain's ids to it.
    """
    return _because_parts(chain, told)[0]


def _because_parts(chain: CausalChain, told: set[str] | None = None) -> tuple[str, list]:
    """``render_because``'s sentence and the steps it names."""
    steps = list(chain.steps)
    if len(steps) < 2:
        return "", []
    effect, causes = steps[-1], list(reversed(steps[:-1]))
    parts = [f"{effect.description.strip().rstrip('.')} (turn {effect.turn})"]
    named = [effect]
    for step in causes:
        label = step.description.strip().rstrip(".")
        named.append(step)
        if told is not None and step.event_id and step.event_id in told:
            parts.append(f"because {label} (turn {step.turn}, as told above)")
            break
        parts.append(f"because {label} (turn {step.turn})")
    if told is not None:
        told.update(s.event_id for s in steps if s.event_id)
    return ", ".join(parts) + ".", named


def render_chain_line(chain: CausalChain) -> str:
    """Root-first arrow rendering for prompts: "[t0] a -> [t6] b -> [t9] c"."""
    return " -> ".join(
        f"[turn {s.turn}] {s.description.strip().rstrip('.')}" for s in chain.steps
    )


_MAX_PATTERN_LINKS = 6
_MAX_LANDMARKS = 5
# Placeholder names of the ideological movements ("Rise of Movement 0",
# "Schism of movement 3", "[movement_3] Schism between ...").
_PLACEHOLDER_NAME = re.compile(r"\bmovement[ _]\d+\b", re.IGNORECASE)
_PLACEHOLDER_TAG = re.compile(r"\[movement_\d+\]\s*", re.IGNORECASE)


def _listed_events(moment: NarrativeMoment, type_counts: dict[str, int] | None = None):
    """The moment's listed prompt lines, the unlisted events by type, and the
    listed events (each line's event and the repeats folded into it).
    ``type_counts`` (the run's count of each kind) weighs scarce kinds up."""
    chain_ids = [s.event_id for c in moment.causal_chains for s in c.steps if s.event_id]
    named_keys = [(ne.turn, frozenset(ne.actors)) for ne in moment.named_events]
    lines, omitted = nc.select_prompt_events(moment.events, chain_ids, named_keys,
                                             type_counts=type_counts)
    listed = [ev for line in lines for ev in line.events]
    return lines, omitted, listed


def _landmarks(named_events: Sequence[NamedEvent]) -> list[NamedEvent]:
    """At most ``_MAX_LANDMARKS`` named events: the most important, in turn order."""
    ranked = sorted(range(len(named_events)),
                    key=lambda i: (-named_events[i].importance, named_events[i].turn, i))
    keep = sorted(ranked[:_MAX_LANDMARKS])
    return [named_events[i] for i in keep]


_PLACEHOLDER_SUFFIX = re.compile(r"\s*\(movement[ _]\d+\)", re.IGNORECASE)


def _landmark_line(ne: NamedEvent) -> str:
    """``Name (turn T): description``. A placeholder id is cut from the name
    ("Universal Enlightenment (movement_1)"); a name that is only a
    placeholder ("Rise of Movement 0") is left out."""
    desc = _PLACEHOLDER_TAG.sub("", ne.description).strip().rstrip(".")
    name = _PLACEHOLDER_SUFFIX.sub("", ne.name).strip()
    if not name or _PLACEHOLDER_NAME.search(name):
        return f"(turn {ne.turn}): {desc}"
    return f"{name} (turn {ne.turn}): {desc}"


def _mechanical_sentence(line, faiths: dict[int, str] | None = None) -> str:
    text = nc.event_text(line.event, faiths)
    if line.folded:
        places = [p for p in nc.places_of(line.folded) if p != (line.event.region or line.event.shock_region)]
        if places:
            shown = places[:nc.MAX_FOLDED_PLACES]
            text += " (and in " + ", ".join(shown)
            if len(places) > len(shown):
                text += f" and {len(places) - len(shown)} other places"
            text += ")"
        else:
            text += f" ({len(line.folded)} more times)"
    return text[:1].upper() + text[1:] + "."


def _entry_for(moment: NarrativeMoment, narrative: str,
               accounts: list[str] | None = None, provenance: dict | None = None) -> ChronicleEntry:
    return ChronicleEntry(
        turn=moment.anchor_turn,
        covers_turns=moment.turn_range,
        events=list(moment.events),
        named_events=list(moment.named_events),
        narrative=narrative,
        importance=moment.score,
        narrative_role=moment.narrative_role,
        causal_links=list(moment.causal_links),
        causal_chains=list(moment.causal_chains),
        accounts=list(accounts or []),
        provenance=provenance,
    )


def mechanical_narrative(moment: NarrativeMoment, told: set[str] | None = None,
                         accounts=None, names=None, glossed: set | None = None,
                         type_counts: dict[str, int] | None = None,
                         faiths: dict[int, str] | None = None) -> str:
    """No-LLM chronicle text for a moment: its event descriptions, then the
    recorded causal chains behind them ("... because ..."), then, with an
    ``accounts`` index (``historiography.AccountIndex``), how the world's own
    chroniclers tell it ("In their own words: As the X chronicles tell it ..."),
    then, with a ``names`` index (``languages.NameIndex``), what the peoples
    call themselves and their lands ("In their own tongues: ...").
    The events are the ones a prompt lists (``narration_context``), each a
    sentence. :func:`compose_mechanical` gives the same text with the facts
    of each sentence."""
    return compose_mechanical(moment, told=told, accounts=accounts, names=names, glossed=glossed,
                              type_counts=type_counts, faiths=faiths).text


def _step_id(ids: npv.FactIds, step) -> str:
    return ids.event_by_id(step.event_id) or f"e:{npv.slug(f'{step.turn}:{step.event_type}')}"


def _step_text(ids: npv.FactIds, step, faiths: dict[int, str] | None) -> str:
    """A chain step's names-bearing text: its label, its place and its event's record."""
    ev = ids.timeline_event(step.event_id)
    parts = [step.description or "", step.region or ""]
    if ev is not None:
        parts.append(npv.event_fact_text(ev, faiths))
    return " | ".join(p for p in parts if p)


def compose_mechanical(moment: NarrativeMoment, sheet: npv.FactSheet | None = None,
                       told: set[str] | None = None, accounts=None, names=None,
                       glossed: set | None = None, noted: set[str] | None = None,
                       type_counts: dict[str, int] | None = None,
                       faiths: dict[int, str] | None = None) -> npv.Composer:
    """:func:`mechanical_narrative` as a ``narration_provenance.Composer``:
    the text and, per sentence, the facts it was built from (registered in
    ``sheet``: the records' dates and the names they mention). ``noted``
    carries the archive losses already told across a chronicle."""
    a, b = moment.turn_range
    if sheet is None:
        sheet = npv.FactSheet(npv.FactIds(timeline=list(moment.events)), None, b, tags=False)
    ids = sheet.ids
    comp = npv.Composer(sheet)
    lines, _omitted, listed = _listed_events(moment, type_counts)
    if lines:
        for line in lines:
            comp.add(_mechanical_sentence(line, faiths),
                     [(ids.event(ev), ev.turn, npv.event_fact_text(ev, faiths)) for ev in line.events])
    else:
        comp.add("Events unfolded.", [(ids.window(a, b), b, "")])
    sep = "\n\n"
    for chain in moment.causal_chains:
        text, steps = _because_parts(chain, told)
        if not text:
            continue
        comp.add(text, [(_step_id(ids, s), s.turn, _step_text(ids, s, faiths)) for s in steps], sep=sep)
        sep = " "
    if accounts:
        for k, (text, row) in enumerate(accounts.passage_parts(listed, noted=noted)):
            comp.add(text, [(ids.account(row), accounts.row_turn(row), accounts.fact_text(row))],
                     sep="\n\n" if k == 0 else " ")
            comp.accounts.append(row["account_id"])
    if names:
        for k, (text, kind, ref, record) in enumerate(names.passage_parts(listed, b, glossed)):
            comp.add(text, [(ids.names_entity(kind, ref), b, record)], sep="\n\n" if k == 0 else " ")
    return comp


def _add_link_line(lines: list[list], text: str, turn: int, j: int) -> None:
    """A type-pair link's prompt line ``[text, turn, [link indices]]``; links
    that read the same share it."""
    for row in lines:
        if row[0] == text:
            row[2].append(j)
            return
    lines.append([text, turn, [j]])


class NarrativeEngine:
    """LLM-powered chronicle generation.

    `sim_client` is retained for backward-compatible construction, but
    simulation actions are selected deterministically by `ActionEngine`.
    """

    def __init__(self, sim_client: LLMClient, narrative_client: LLMClient,
                 event_flavor: dict | None = None,
                 narrative_style: str | None = None,
                 citations: bool = True):
        self.sim_client = sim_client
        self.narrative_client = narrative_client
        self.event_flavor = event_flavor
        self.narrative_style = narrative_style
        # Curated prompts tag each fact line with its id and ask the model to
        # cite them (narration_provenance); False keeps the untagged prompts.
        # The facts each passage was given are recorded either way.
        self.citations = citations

    def _faiths(self) -> dict[int, str] | None:
        """Faith id -> name from the world's belief registry (None without a world)."""
        world = getattr(self, "_world", None)
        registry = getattr(world, "belief_registry", None) if world is not None else None
        return {b.faith_id: b.name for b in registry} if registry else None

    def _type_counts(self) -> dict[str, int] | None:
        """The run's count of each event kind (set by the last prompt build)."""
        timeline = getattr(self, "_timeline", None)
        return timeline.type_counts if timeline is not None else None

    def _supports_batch(self) -> bool:
        """Check if narrative_client supports batch_complete()."""
        return isinstance(self.narrative_client, AnthropicClient)

    def generate_chronicle(self, world: WorldState, events: list[Event]) -> str:
        """Generate a chronicle entry for the current turn.

        Routes to narrative_client for prose quality.
        Falls back to a mechanical summary on any LLM error.
        The entry's provenance (the facts the prompt gave, the model's
        citations, removed from the returned prose; or the fallback's exact
        facts) waits in :meth:`take_turn_provenance`.
        """
        sheet = self._turn_sheet(world)
        prompt = _build_chronicle_prompt_impl(world, events,
                                              event_flavor=self.event_flavor,
                                              narrative_style=self.narrative_style,
                                              sheet=sheet)
        try:
            text = self.narrative_client.complete(prompt, max_tokens=1000)
        except Exception:
            # Fallback: mechanical summary so the run doesn't crash
            comp = npv.Composer(npv.FactSheet(sheet.ids, sheet.universe, world.turn, tags=False))
            lead = f"Turn {world.turn}: "
            for k, e in enumerate(events):
                comp.add((lead if k == 0 else "") + nc.event_text(e),
                         [(sheet.ids.event(e), e.turn, npv.event_fact_text(e))], sep="; ")
            if not events:
                comp.add(lead + "Events unfolded.", [(sheet.ids.window(world.turn, world.turn), world.turn, "")])
            self._turn_provenance = comp.export()
            return comp.text
        if not isinstance(text, str):
            self._turn_provenance = None
            return text
        clean, spans = npv.parse_citations(text)
        self._turn_provenance = sheet.export("llm", spans)
        return clean

    def take_turn_provenance(self) -> dict | None:
        """The provenance of the last per-turn entry (once; None when the
        engine did not narrate since)."""
        provenance = getattr(self, "_turn_provenance", None)
        self._turn_provenance = None
        return provenance

    def _turn_sheet(self, world: WorldState) -> npv.FactSheet:
        """A per-turn prompt's fact sheet, over the run's timeline so far."""
        ids = getattr(self, "_turn_ids", None)
        if ids is None:
            ids = self._turn_ids = npv.FactIds()
        ids.sync(world.events_timeline, world.named_events)
        ids.sync_world(world)
        key = (tuple(c.name for c in world.civilizations), tuple(r.name for r in world.regions),
               tuple(b.name for b in (getattr(world, "belief_registry", None) or [])),
               tuple(c.leader.name for c in world.civilizations),
               tuple(gp.name for c in world.civilizations for gp in c.great_persons),
               len(getattr(world, "retired_persons", None) or []))
        cached = getattr(self, "_turn_universe", None)
        if cached is None or cached[0] != key:
            cached = self._turn_universe = (key, npv.EntityUniverse.from_world(world))
        return npv.FactSheet(ids, cached[1], world.turn, tags=bool(getattr(self, "citations", True)))

    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        on_progress: Callable[[int, int, float | None], None] | None = None,
        # M40: Optional agent context data
        great_persons: list | None = None,
        social_edges: list[tuple] | None = None,
        dissolved_edges_by_turn: dict[int, list[tuple]] | None = None,
        agent_name_map: dict[int, str] | None = None,
        # M41: per-civ Gini coefficients for wealth inequality narration
        gini_by_civ: dict[int, float] | None = None,
        # M43b: Economy result for trade dependency and shock narration
        economy_result=None,
        # M52: World state for artifact context in prompts
        world=None,
        # Displacement fractions by region index (from agent bridge)
        displacement_by_region: dict[int, float] | None = None,
        # M39: Dynasty registry for lineage narration
        dynasty_registry=None,
        # In-world accounts (historiography.AccountIndex); None = not used
        historiography=None,
        # In-world names (languages.NameIndex); None = not used
        languages=None,
        # Completed turn the bridge values and final character fields
        # describe; "auto" = the world's last completed turn (historical_context)
        observed_through: int | None | str = "auto",
        # The run's event timeline and named events, the lists fact ids index
        # (narration_provenance); default: the world's
        timeline: Sequence[Event] | None = None,
        named_events: Sequence[NamedEvent] | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate all selected moments.

        Uses Anthropic Batch API when available (50% cheaper, parallel).
        Falls back to sequential for local/Gemini clients.
        Per-moment fallback on LLM failure (mechanical summary, batch continues).
        Progress: on_progress(completed, total, eta_seconds).
        With ``historiography`` the prompts gain an IN-WORLD ACCOUNTS block and
        the mechanical chronicle an "In their own words" passage; entries list
        the account ids they drew on. With ``languages`` the prompts gain an
        IN-WORLD NAMES block and the mechanical chronicle an "In their own
        tongues" gloss.

        Each moment's prompt reads the record as of the end of its last turn
        (``historical_context.AsOf.after``): characters born by then, their
        deeds, memories, bonds and status then, and the bridge values and
        final character fields only when ``observed_through`` is that turn.

        Every entry records its provenance (``ChronicleEntry.provenance``,
        ``narration_provenance``): the facts its narrator was given, by id,
        and the facts each sentence cites (the mechanical narrator's exactly,
        an LLM's from the bracketed ids the prompt asks for, which are
        removed from the prose).
        """
        # M52: Store world for artifact context
        self._world = world
        self._accounts = historiography if historiography else None
        self._names = languages if languages else None
        self._timeline_events = list(timeline) if timeline is not None else None
        self._named_list = list(named_events) if named_events is not None else None

        # Build prompts and context for all moments up front
        prepared = self._prepare_narration_prompts(
            moments, history, great_persons, social_edges,
            dissolved_edges_by_turn, agent_name_map, gini_by_civ,
            economy_result, displacement_by_region=displacement_by_region,
            dynasty_registry=dynasty_registry, observed_through=observed_through,
        )

        # No-LLM narrator: render moments mechanically (with their chains).
        if getattr(self.narrative_client, "mechanical", False) is True:
            return self._narrate_mechanical(moments, on_progress)

        # Batch API path — Anthropic only
        if self._supports_batch():
            return self._narrate_batch_api(
                moments, prepared, on_progress,
            )

        # Sequential path — local / Gemini / fallback
        return self._narrate_sequential(
            moments, prepared, on_progress,
        )

    def _prepare_narration_prompts(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        great_persons: list | None = None,
        social_edges: list[tuple] | None = None,
        dissolved_edges_by_turn: dict[int, list[tuple]] | None = None,
        agent_name_map: dict[int, str] | None = None,
        gini_by_civ: dict[int, float] | None = None,
        economy_result=None,
        displacement_by_region: dict[int, float] | None = None,
        dynasty_registry=None,
        observed_through: int | None | str = "auto",
    ) -> list[dict]:
        """Build prompt/system pairs for each moment. Returns list of dicts
        with keys: prompt, system, agent_ctx.

        One ``HistoricalRecord`` holds the run's record; each moment reads
        its view after the moment's last turn."""
        total = len(moments)
        result = []
        world_obj = getattr(self, "_world", None)
        recorded = list(getattr(self, "_timeline_events", None)
                        or getattr(world_obj, "events_timeline", None) or [])
        if not recorded:
            recorded = sorted((e for m in moments for e in m.events), key=lambda e: e.turn)
        timeline = nc.TimelineView(recorded)
        self._timeline = timeline
        type_counts = timeline.type_counts
        faiths = self._faiths()

        # Fact ids index the timeline and named events the bundle holds
        # (narration_provenance); names are those of the world and its history.
        named_list = list(getattr(self, "_named_list", None) or getattr(world_obj, "named_events", None) or [])
        if not named_list:  # direct callers: the moments' own, in order
            seen: set[int] = set()
            for m in moments:
                for ne in m.named_events:
                    if id(ne) not in seen:
                        seen.add(id(ne))
                        named_list.append(ne)
        ids = npv.FactIds(recorded, named_list, world_obj, getattr(self, "_names", None))
        universe = npv.EntityUniverse.from_world(world_obj, history)
        self._fact_ids = ids
        self._universe = universe
        cite = bool(getattr(self, "citations", True))

        # M50b: Build gp_by_agent_id for bond-source narration
        gp_by_agent_id: dict | None = None
        if great_persons:
            gp_by_agent_id = {}
            for gp in great_persons:
                if gp.agent_id is not None:
                    gp_by_agent_id[gp.agent_id] = gp

        record = HistoricalRecord(
            history=history, events=recorded, great_persons=great_persons or (), world=world_obj,
            observed_through=observed_through, gini_by_civ=gini_by_civ,
            displacement_by_region=displacement_by_region, economy_result=economy_result,
            social_edges=social_edges, dissolved_edges_by_turn=dissolved_edges_by_turn,
            agent_name_map=agent_name_map, dynasty_registry=dynasty_registry,
            accounts=getattr(self, "_accounts", None),
        )
        # The mechanical chronicle and the fallbacks read the same views.
        self._record = record

        for idx, moment in enumerate(moments):
            view = record.view(AsOf.after(moment.turn_range[1]))
            prev_moment = moments[idx - 1] if idx > 0 else None
            next_moment = moments[idx + 1] if idx < total - 1 else None
            start, end = moment.turn_range
            # Every fact line is registered (its id, date and the names it
            # mentions) and, with citations on, tagged "[id, ...]".
            sheet = npv.FactSheet(ids, universe, end, tags=cite)

            role_instruction = ROLE_INSTRUCTIONS.get(
                moment.narrative_role,
                ROLE_INSTRUCTIONS[NarrativeRole.RESOLUTION],
            )

            # Type-pair links are listed only for events without recorded
            # provenance (old saves and bundles); recorded links reach the
            # prompt as the causal chains and the later consequences below.
            causes: list[list] = []        # [text, turn, [link indices]]
            consequences: list[list] = []
            for j, link in enumerate(moment.causal_links):
                if link.provenance == "recorded":
                    continue
                line = f"{link.pattern} (turn {{turn}})"
                if start <= link.effect_turn <= end:
                    _add_link_line(causes, line.format(turn=link.cause_turn), link.cause_turn, j)
                if start <= link.cause_turn <= end:
                    _add_link_line(consequences, line.format(turn=link.effect_turn), link.effect_turn, j)

            lines, omitted, listed = _listed_events(moment, type_counts)
            event_text = ""
            for line in lines:
                facts = [(ids.event(ev), ev.turn) for ev in line.events]
                spark = nc.news_spark(line.event, timeline)
                if spark is not None:
                    facts.append((ids.event(spark), spark.turn))
                event_text += "\n" + sheet.line(nc.render_prompt_line(line, faiths, timeline), facts,
                                                shown=[facts[0][0]])
            if omitted:
                event_text += "\n" + sheet.line(nc.render_omitted(omitted), [(ids.window(start, end), end)])

            named_text = ""
            if moment.named_events:
                named_text = "\n\nHistorical landmarks in this period:\n"
                for ne in _landmarks(moment.named_events):
                    named_text += sheet.line(f"- {_landmark_line(ne)}", [(ids.named(ne), ne.turn)]) + "\n"

            causal_text = ""
            if moment.causal_chains:
                causal_text += ("\n\nCAUSAL CHAINS recorded by the simulation (root cause first; "
                                "say why these events happened, \"because ...\"):\n")
                for chain in moment.causal_chains:
                    causal_text += sheet.line(f"- {render_chain_line(chain)}",
                                              [(_step_id(ids, s), s.turn) for s in chain.steps]) + "\n"
            later = timeline.consequences(moment.events, end)
            if later:
                causal_text += "\n\nLATER CONSEQUENCES recorded by the simulation (after these turns):\n"
                for ev in later:
                    causal_text += sheet.line(f"- [turn {ev.turn}] {nc.event_text(ev, faiths)}",
                                              [(ids.event(ev), ev.turn)], retro=True) + "\n"
            if causes:
                causal_text += "\n\nCAUSES leading to this moment:\n"
                for text, turn, js in causes[:_MAX_PATTERN_LINKS]:
                    causal_text += sheet.line(f"- {text}", [(ids.link(j), turn) for j in js]) + "\n"
            if consequences:
                causal_text += "\n\nCONSEQUENCES flowing from this moment:\n"
                for text, turn, js in consequences[:_MAX_PATTERN_LINKS]:
                    causal_text += sheet.line(f"- {text}", [(ids.link(j), turn) for j in js],
                                              retro=turn > end) + "\n"

            # The snapshot of turn T + 1 holds the state after turn T.
            snap = view.snapshot
            state_lines = []
            if snap is not None:
                for keys, text in nc.standing_state_facts(snap, listed, getattr(self, "_world", None),
                                                          timeline, at_turn=end):
                    state_lines.append(sheet.line(
                        text, [(ids.snapshot(snap.turn, kind, key), snap.turn - 1) for kind, key in keys]))
            causal_text += nc.render_standing_state(state_lines, end)

            account_ids: list[str] = []
            # The accounts as of the moment's end: losses dated after it are not told.
            accounts_index = view.accounts
            if accounts_index:
                accounts_text, account_ids = accounts_index.prompt_block(listed, sheet=sheet)
                causal_text += accounts_text
            names_index = getattr(self, "_names", None)
            if names_index:
                causal_text += names_index.prompt_block(listed, end, sheet=sheet)

            ref_turn, target_turn, before = before_changes(history, moment, prev_moment)
            before_summary = "\n".join(
                sheet.line(f"- {text}", [(ids.change(ref_turn, target_turn, key, attr), target_turn - 1)])
                for key, attr, text in before)
            now_turn, later_turn, after = after_changes(history, moment, next_moment)
            after_summary = "\n".join(
                sheet.line(f"- {text}", [(ids.change(now_turn, later_turn, key, attr), later_turn - 1)],
                           retro=True)
                for key, attr, text in after)

            context_text = ""
            if before_summary:
                context_text += f"\n\nBEFORE this moment:\n{before_summary}"
            if after_summary:
                context_text += f"\n\nAFTER this moment (for foreshadowing):\n{after_summary}"

            focal_civ_name = None
            if snap is not None:
                for ev in moment.events:
                    for actor in ev.actors:
                        if actor in snap.civ_stats:
                            focal_civ_name = actor
                            break
                    if focal_civ_name is not None:
                        break
                if focal_civ_name is None and snap.civ_stats:
                    focal_civ_name = sorted(snap.civ_stats.keys())[0]

            civ_idx = None
            civ_names = None
            world_obj = getattr(self, "_world", None)
            if world_obj is not None:
                civ_names = [c.name for c in world_obj.civilizations]
                if focal_civ_name is not None:
                    civ_idx = next(
                        (i for i, civ in enumerate(world_obj.civilizations) if civ.name == focal_civ_name),
                        None,
                    )

            # M40: Build agent context with relationships
            agent_context_text = ""
            agent_ctx = None
            if great_persons is not None:
                agent_ctx = build_agent_context_for_moment(
                    moment, great_persons, {},
                    gp_by_agent_id=gp_by_agent_id,
                    civ_idx=civ_idx,
                    civ_names=civ_names,
                    world_turn=moment.anchor_turn,
                    view=view,
                )
                if agent_ctx is not None:
                    refs = self._agent_context_refs(moment, view, snap, focal_civ_name, agent_ctx)
                    agent_context_text = "\n\n" + build_agent_context_block(agent_ctx, sheet=sheet, refs=refs)

            # M52: Artifact context
            artifact_context_text = ""
            if world_obj is not None:
                from chronicler.artifacts import render_artifact_context
                artifact_context_text = render_artifact_context(view.artifacts(moment), sheet=sheet)
                if artifact_context_text:
                    artifact_context_text = "\n\n" + artifact_context_text

            dominant_era = get_dominant_era(moment, snap) if snap else "tribal"
            era_voice, era_style = ERA_REGISTER.get(dominant_era, ERA_REGISTER["tribal"])

            style_text = ""
            if self.narrative_style:
                style_text = f"\n\nNARRATIVE STYLE: {self.narrative_style}"
            else:
                style_text = f"\n\nNARRATIVE REGISTER: {era_style}"

            system = (
                f"{era_voice} "
                f"Do NOT include turn numbers or game mechanics in the prose. "
                f"ROLE: {role_instruction}"
            )
            cite_text = ""
            if cite:
                system += " Cite the facts you use only by their bracketed ids, as the prompt asks."
                cite_text = f"\n{npv.CITE_INSTRUCTION}"

            prompt = f"""NARRATIVE ROLE: {moment.narrative_role.value.upper()}
{role_instruction}

TURNS {moment.turn_range[0]}-{moment.turn_range[1]}:

EVENTS:{event_text}{named_text}{causal_text}{context_text}{agent_context_text}{artifact_context_text}{style_text}

Write 3-5 paragraphs of chronicle prose for this moment.{cite_text}
Respond only with the chronicle prose. No preamble, no markdown formatting."""

            prepared = {
                "prompt": prompt,
                "system": system,
                "agent_ctx": agent_ctx,
                "shown_event_ids": [e.event_id for e in listed],
                # What this prompt gives the narrator (narration_provenance.FactSheet).
                "sheet": sheet,
            }
            if account_ids:
                prepared["account_ids"] = account_ids
            result.append(prepared)

        return result

    def _moment_accounts(self, moment: NarrativeMoment):
        """The in-world accounts as of the moment's last turn (None when not used).

        The prompts' record (``_prepare_narration_prompts``) when it holds
        this index, so every path reads the same view.
        """
        accounts = getattr(self, "_accounts", None)
        if not accounts:
            return None
        as_of = AsOf.after(moment.turn_range[1])
        record = getattr(self, "_record", None)
        if record is not None and record.accounts is accounts:
            return record.view(as_of).accounts
        return accounts.as_of(as_of)

    def _agent_context_refs(self, moment: NarrativeMoment, view: HistoricalView,
                            snap: TurnSnapshot | None, focal_civ: str | None,
                            ctx: AgentContext) -> dict:
        """Fact ids of the agent context's lines that the context does not
        carry (``build_agent_context_block``'s ``refs``)."""
        ids = self._fact_ids
        start, end = moment.turn_range
        observed = view.record.observed_through
        obs_turn = observed if observed is not None else end
        refs: dict = {
            "mood": (ids.window(start, end, "mood"), end),
            "displacement": (ids.observation(obs_turn, "displacement"), obs_turn),
            "trade": (ids.observation(obs_turn, "trade_dependency"), obs_turn),
        }
        if snap is not None:
            refs["settlements_turn"] = snap.turn
            if focal_civ is not None:
                refs["urban"] = (ids.snapshot(snap.turn, "urban", ("civ", focal_civ)), snap.turn - 1)
        refs["shocks"] = [(ids.event(ev), ev.turn) for ev in moment.events
                          if ev.event_type == "supply_shock" and ev.shock_region is not None
                          and ev.shock_category is not None]
        by_name = {name: aid for aid, name in view.record.agent_name_map.items()}
        refs["agent_ids"] = {n: by_name[n] for rel in ctx.relationships
                             for n in (rel.get("character_a"), rel.get("character_b")) if n in by_name}
        return refs

    def _mechanical_sheet(self, moment: NarrativeMoment) -> npv.FactSheet:
        """The facts the mechanical narrator builds a moment's sentences from."""
        ids = getattr(self, "_fact_ids", None) or npv.FactIds(timeline=list(moment.events))
        return npv.FactSheet(ids, getattr(self, "_universe", None), moment.turn_range[1], tags=False)

    def _mechanical_entry(self, moment: NarrativeMoment, **kwargs) -> ChronicleEntry:
        """A moment rendered mechanically, with its exact provenance."""
        comp = compose_mechanical(moment, self._mechanical_sheet(moment),
                                  accounts=self._moment_accounts(moment),
                                  type_counts=self._type_counts(), faiths=self._faiths(), **kwargs)
        return _entry_for(moment, comp.text, comp.accounts, comp.export())

    def _llm_entry(self, moment: NarrativeMoment, prep: dict, text: str) -> ChronicleEntry:
        """A moment as the LLM told it: its bracketed citations parsed and
        removed from the prose, the facts its prompt gave recorded."""
        narrative, spans = npv.parse_citations(text)
        sheet = prep.get("sheet")
        provenance = sheet.export("llm", spans) if sheet is not None else None
        return _entry_for(moment, narrative, prep.get("account_ids", []), provenance)

    def _narrate_mechanical(
        self,
        moments: list[NarrativeMoment],
        on_progress: Callable[[int, int, float | None], None] | None = None,
    ) -> list[ChronicleEntry]:
        entries: list[ChronicleEntry] = []
        told: set[str] = set()  # chain steps already narrated, in chronicle order
        names = getattr(self, "_names", None)
        noted: set[str] = set()  # archive losses already told, in chronicle order
        glossed: set = set()  # entities whose names were glossed, in chronicle order
        for idx, moment in enumerate(moments):
            entries.append(self._mechanical_entry(moment, told=told, names=names, glossed=glossed,
                                                  noted=noted))
            if on_progress is not None:
                on_progress(idx + 1, len(moments), None)
        return entries

    def _narrate_batch_api(
        self,
        moments: list[NarrativeMoment],
        prepared: list[dict],
        on_progress: Callable[[int, int, float | None], None] | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate via Anthropic Batch API — all prompts submitted at once."""
        requests = [
            {"prompt": p["prompt"], "system": p["system"], "max_tokens": 1000}
            for p in prepared
        ]

        results = self.narrative_client.batch_complete(requests)

        entries: list[ChronicleEntry] = []
        names = getattr(self, "_names", None)
        for idx, (moment, narrative) in enumerate(zip(moments, results)):
            if narrative is None:
                entries.append(self._mechanical_entry(moment, names=names))
            else:
                entries.append(self._llm_entry(moment, prepared[idx], narrative))

            if on_progress is not None:
                on_progress(idx + 1, len(moments), None)

        return entries

    def _narrate_sequential(
        self,
        moments: list[NarrativeMoment],
        prepared: list[dict],
        on_progress: Callable[[int, int, float | None], None] | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate moments sequentially — for local and Gemini clients."""
        entries: list[ChronicleEntry] = []
        total = len(moments)
        previous_prose: str | None = None
        start_time: float | None = None
        _first_failure = True
        _failure_count = 0

        for idx, (moment, prep) in enumerate(zip(moments, prepared)):
            prompt = prep["prompt"]
            system = prep["system"]

            # Inject previous prose for style continuity (sequential only)
            if previous_prose:
                excerpt = previous_prose[-200:]
                prompt += f"\n\nPREVIOUS ENTRY (for style continuity):\n...{excerpt}"

            # Call LLM with fallback
            try:
                narrative = self.narrative_client.complete(
                    prompt, max_tokens=1000, system=system
                )
            except Exception as exc:
                _failure_count += 1
                if _first_failure:
                    logger.warning("Narration failed (falling back to mechanical summary): %s", exc)
                    _first_failure = False
                entry = self._mechanical_entry(moment, names=getattr(self, "_names", None))
            else:
                entry = self._llm_entry(moment, prep, narrative)

            previous_prose = entry.narrative
            entries.append(entry)

            # Progress callback with ETA
            completed = idx + 1
            if completed == 1:
                start_time = time.monotonic()
                eta = None
            else:
                elapsed = time.monotonic() - (start_time or time.monotonic())
                if elapsed > 0 and completed > 1:
                    per_moment = elapsed / (completed - 1)
                    remaining = total - completed
                    eta = per_moment * remaining
                else:
                    eta = None

            if on_progress is not None:
                on_progress(completed, total, eta)

        if _failure_count > 0:
            logger.warning("Narration: %d/%d moments fell back to mechanical summary", _failure_count, total)

        return entries

    def narrator(self, world: WorldState, events: list[Event]) -> str:
        """Adapter method matching the Narrator callback signature."""
        return self.generate_chronicle(world, events)
