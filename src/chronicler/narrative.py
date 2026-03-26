"""LLM narrative engine — action selection and chronicle generation.

Uses two LLMClient instances with role-based routing:
- sim_client (local model via LM Studio): action selection — high volume, free
- narrative_client (Claude API): chronicle prose — lower volume, higher quality

Domain threading (Caves of Qud technique): each civilization's thematic
keywords (domains) are woven into every narrative mention, creating the
perception of deep cultural coherence with minimal mechanical overhead.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Sequence

logger = logging.getLogger(__name__)

from chronicler.llm import AnthropicClient, GeminiClient, LLMClient
from chronicler.models import (
    ActionType,
    AgentContext,
    CausalLink,
    ChronicleEntry,
    Civilization,
    Disposition,
    Event,
    GapSummary,
    NarrationContext,
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

_DESPERATE_EVENTS = {"local_rebellion", "demographic_crisis"}
_RESTLESS_EVENTS = {"loyalty_cascade", "brain_drain", "occupation_shift"}

# ---------------------------------------------------------------------------
# M48: Memory descriptions for narration
# ---------------------------------------------------------------------------

MEMORY_DESCRIPTIONS = {
    0: "a great famine under the {civ}",
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
    "safety": 0.3, "material": 0.3, "social": 0.25,
    "spiritual": 0.3, "autonomy": 0.3, "purpose": 0.35,
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


def render_memory(mem: dict, civ_names: list) -> str | None:
    """Render a memory slot as a natural language fragment."""
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
    return f"{text} (turn {mem['turn']}, {descriptor})"


def compute_population_mood(events: list[Event]) -> str:
    """Compute population mood from agent events. Worst wins."""
    agent_types = {e.event_type for e in events if e.source == "agent"}
    if agent_types & _DESPERATE_EVENTS:
        return "desperate"
    if agent_types & _RESTLESS_EVENTS:
        return "restless"
    return "content"


def build_agent_context_block(ctx: AgentContext | None) -> str:
    """Build the agent context section for the narrator prompt."""
    if ctx is None:
        return ""

    lines = ["## Agent Context"]
    lines.append(f"Population mood: {ctx.population_mood}")
    lines.append(f"Displacement: {int(ctx.displacement_fraction * 100)}% of population displaced")
    if abs(ctx.urban_fraction_delta_20t) > 1e-6:
        lines.append(f"Urbanization trend (20 turns): {ctx.urban_fraction_delta_20t * 100.0:+.1f}pp")
    if ctx.top_settlements:
        lines.append("Largest settlements:")
        for settlement in ctx.top_settlements:
            lines.append(
                f"- {settlement.name} ({settlement.region_name}, pop ~{settlement.population_estimate})"
            )
    lines.append("")

    if ctx.named_characters:
        lines.append("Named characters present:")
        for char in ctx.named_characters:
            origin = (f", originally {char.get('origin_civ')}"
                      if char.get("origin_civ") != char.get("civ") and char.get("origin_civ") else "")
            trait_str = f" [{char['trait']}]" if char.get("trait") else ""
            lines.append(
                f"- {char['role']} {char['name']}{trait_str} ({char['civ']}{origin}) [{char['status']}]:"
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
                history_parts.append(f"  {h['event']} in {h['region']} (turn {h['turn']})")
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
            # M48: Memory context
            if char.get("memories"):
                civ_names = char.get("_civ_names", [])
                rendered = [render_memory(m, civ_names) for m in char["memories"]]
                rendered = [r for r in rendered if r is not None]
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
        lines.append("")

    # M40: Render relationship context
    if ctx.relationships:
        lines.append("Character relationships:")
        for rel in ctx.relationships:
            if rel["type"] == "mentor":
                lines.append(f"- {rel['character_b']} (apprentice of {rel['character_a']}, since turn {rel['since_turn']})")
            elif rel["type"] == "hostage":
                lines.append(f"- {rel['character_b']} (hostage of {rel['character_a']})")
            else:
                lines.append(f"- {rel['character_a']} and {rel['character_b']} ({rel['type']}, since turn {rel['since_turn']})")
        lines.append("")

    # M43b: Trade dependency and supply shock context
    if ctx.trade_dependent_regions:
        lines.append(f"Trade-dependent regions: {', '.join(ctx.trade_dependent_regions)}")
    if ctx.active_shocks:
        for shock in ctx.active_shocks:
            lines.append(
                f"Supply crisis in {shock.region}: {shock.category} "
                f"(severity {shock.severity:.1f}, "
                f"source: {shock.upstream_source or 'local'})"
            )
    if ctx.trade_dependent_regions or ctx.active_shocks:
        lines.append("")

    lines.append("Guidelines:")
    lines.append("- Refer to named characters BY NAME — do not anonymize or rename them")
    lines.append("- Use their recent history for callbacks")
    lines.append("- Use population mood to set atmospheric tone")
    if ctx.displacement_fraction > 0.10:
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
    region_names: dict[int, str],
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
) -> AgentContext | None:
    """Build AgentContext if the moment has agent-source or economy events."""
    agent_events = [e for e in moment.events if e.source == "agent"]
    economy_events = [e for e in moment.events if e.source == "economy"]
    if not agent_events and not (economy_result is not None and economy_events):
        return None

    # Named characters active in this moment
    moment_actors = {actor for ev in moment.events for actor in ev.actors}
    chars = []
    for gp in great_persons:
        if gp.source != "agent":
            continue
        if not gp.active and gp.name not in moment_actors:
            continue
        char = {
            "name": gp.name,
            "role": gp.role.title(),
            "civ": gp.civilization,
            "origin_civ": gp.origin_civilization,
            "status": ("exiled" if gp.fate == "exile"
                       else ("dead" if not gp.alive else "active")),
            "recent_history": [
                {"turn": 0, "event": d, "region": gp.region or "unknown"}
                for d in gp.deeds[-3:]
            ],
        }
        # M50b: include agent_id for bond lookups
        if gp.agent_id is not None:
            char["agent_id"] = gp.agent_id
        # M39: dynasty context
        if dynasty_registry is not None and gp_by_agent_id is not None and gp.agent_id:
            dynasty = dynasty_registry.get_dynasty_for(gp.agent_id, gp_by_agent_id)
            if dynasty is not None:
                living_count = sum(1 for m in dynasty.members if gp_by_agent_id[m].alive)
                char["dynasty"] = dynasty.founder_name
                char["dynasty_living"] = living_count
                char["dynasty_total"] = len(dynasty.members)
                if dynasty.split_detected:
                    char["dynasty_split"] = True

        # M45: Arc context
        if gp.arc_type:
            char["arc_type"] = gp.arc_type
        if gp.arc_phase:
            char["arc_phase"] = gp.arc_phase
        if gp.arc_summary:
            char["arc_summary"] = gp.arc_summary
        if gp.trait:
            char["trait"] = gp.trait

        # M48: Memory context
        if hasattr(gp, "memories") and gp.memories:
            char["memories"] = gp.memories
            char["_civ_names"] = civ_names or []

        # M49: Needs context
        if gp.active and hasattr(gp, "needs") and gp.needs:
            char["needs"] = gp.needs

        # M48: Mule context
        if getattr(gp, "mule", False) and gp.active:
            from chronicler.action_engine import MULE_ACTIVE_WINDOW, MULE_FADE_TURNS
            char["mule"] = True
            char["utility_overrides"] = getattr(gp, "utility_overrides", {})
            remaining = (gp.born_turn + MULE_ACTIVE_WINDOW + MULE_FADE_TURNS) - world_turn
            char["mule_remaining"] = max(0, remaining)

        chars.append(char)

    mood = compute_population_mood(agent_events)

    # Average displacement across all tracked regions
    disp_values = list(displacement_by_region.values())
    avg_disp = sum(disp_values) / len(disp_values) if disp_values else 0.0

    # M40+M50b: Merge relationship sources into AgentContext.relationships
    relationships: list[dict] = []
    rel_type_names = {
        0: "mentor", 1: "rival", 2: "marriage", 3: "exile_bond", 4: "co_religionist",
        5: "kin", 6: "friend", 7: "grudge",
    }
    name_map = agent_name_map or {}
    char_names = {c["name"] for c in chars}

    if gp_by_agent_id:
        # M50b path: use agent_bonds from Rust per-agent store
        for c in chars:
            aid = c.get("agent_id")
            gp = gp_by_agent_id.get(aid) if aid is not None else None
            if gp and gp.agent_bonds:
                for bond in gp.agent_bonds:
                    target_name = name_map.get(bond["target_id"])
                    if target_name is None:
                        continue  # Skip unnamed targets
                    sentiment = bond.get("sentiment", 0)
                    sent_desc = (
                        "deep" if abs(sentiment) > 80 else
                        "strong" if abs(sentiment) > 40 else
                        "mild" if abs(sentiment) > 0 else
                        "fading"
                    )
                    relationships.append({
                        "type": rel_type_names.get(bond["bond_type"], "unknown"),
                        "character_a": c["name"],
                        "character_b": target_name,
                        "sentiment": sent_desc,
                        "since_turn": bond.get("formed_turn", 0),
                    })
        # Also include dissolved edges from Rust-side dissolution events
        for edge in (dissolved_edges or []):
            agent_a, agent_b, rel_type, formed_turn = edge
            name_a = name_map.get(agent_a, "")
            name_b = name_map.get(agent_b, "")
            if name_a not in char_names and name_b not in char_names:
                continue
            relationships.append({
                "type": rel_type_names.get(rel_type, "unknown") + " (dissolved)",
                "character_a": name_a,
                "character_b": name_b,
                "since_turn": formed_turn,
            })
    else:
        # Legacy M40 path: use social_edges
        all_edges = list(social_edges or []) + list(dissolved_edges or [])
        for edge in all_edges:
            agent_a, agent_b, rel_type, formed_turn = edge
            name_a = name_map.get(agent_a, "")
            name_b = name_map.get(agent_b, "")
            if name_a not in char_names and name_b not in char_names:
                continue
            rel = {
                "type": rel_type_names.get(rel_type, "unknown"),
                "character_a": name_a,
                "character_b": name_b,
                "role_a": "mentor" if rel_type == 0 else None,
                "role_b": "apprentice" if rel_type == 0 else None,
                "since_turn": formed_turn,
            }
            relationships.append(rel)

    # Add hostage relationships
    for h in (hostage_data or []):
        if h.get("name") in char_names:
            relationships.append(h)

    # M41: Gini coefficient for wealth inequality context
    gini = (gini_by_civ or {}).get(civ_idx, 0.0) if civ_idx is not None else 0.0

    # M56b: Urbanization context — focal civ, urban delta, top settlements
    focal_civ = None
    if current_snapshot is not None:
        for ev in moment.events:
            for actor in ev.actors:
                if actor in current_snapshot.civ_stats:
                    focal_civ = actor
                    break
            if focal_civ is not None:
                break
        if focal_civ is None and current_snapshot.civ_stats:
            focal_civ = sorted(current_snapshot.civ_stats.keys())[0]

    urban_fraction_delta_20t = 0.0
    if history is not None and current_snapshot is not None and focal_civ is not None:
        current_stats = current_snapshot.civ_stats.get(focal_civ)
        if current_stats is not None:
            current_frac = current_stats.urban_fraction
            past_turn = current_snapshot.turn - 20
            past_snapshot = next((s for s in history if s.turn == past_turn), None)
            if past_snapshot is not None and focal_civ in past_snapshot.civ_stats:
                urban_fraction_delta_20t = current_frac - past_snapshot.civ_stats[focal_civ].urban_fraction

    top_settlements: list[SettlementSummary] = []
    if world is not None and focal_civ is not None:
        candidates: list[SettlementSummary] = []
        for region in world.regions:
            if region.controller != focal_civ:
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
        top_settlements = candidates[:3]

    ctx = AgentContext(
        named_characters=chars[:10],  # cap for token budget
        population_mood=mood,
        displacement_fraction=avg_disp,
        relationships=relationships,
        gini_coefficient=gini,
        urban_fraction_delta_20t=urban_fraction_delta_20t,
        top_settlements=top_settlements,
    )

    # M43b: Populate trade dependency and shock context
    if economy_result is not None:
        moment_civs = {ev.actors[0] for ev in moment.events if ev.actors}
        trade_dep = getattr(economy_result, 'trade_dependent', {})
        ctx.trade_dependent_regions = [
            rname for rname, dep in trade_dep.items()
            if dep
        ]
        ctx.active_shocks = [
            ShockContext(
                region=ev.shock_region,
                category=ev.shock_category,
                severity=(ev.importance - 5) / 4.0,
                upstream_source=ev.actors[1] if len(ev.actors) > 1 else None,
            )
            for ev in moment.events
            if ev.event_type == "supply_shock" and ev.shock_region is not None
        ]
    return ctx


def build_before_summary(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    prev_moment: NarrativeMoment | None,
) -> str:
    """Mechanical before-context from snapshot diffs.

    Compare prev_moment.anchor_turn (or turn 1 if None) to moment.anchor_turn.
    Report stat changes > 10, territory gains/losses. Return 3-5 bullet points.
    """
    snap_by_turn: dict[int, TurnSnapshot] = {s.turn: s for s in history}
    if not snap_by_turn:
        return ""

    # Reference turn: prev_moment's anchor, or the first available turn
    if prev_moment is not None:
        ref_turn = prev_moment.anchor_turn
    else:
        ref_turn = min(snap_by_turn.keys())

    target_turn = moment.anchor_turn

    # Find closest available snapshots
    ref_snap = _closest_snap(snap_by_turn, ref_turn)
    target_snap = _closest_snap(snap_by_turn, target_turn)

    if ref_snap is None or target_snap is None:
        return ""

    bullets: list[str] = []

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
                bullets.append(f"{civ} {stat} {direction} from {old_val} to {new_val}")

    # Territory gains/losses
    ref_regions = set(ref_snap.region_control.keys())
    target_regions = set(target_snap.region_control.keys())
    all_regions = ref_regions | target_regions
    for region in sorted(all_regions):
        ctrl_before = ref_snap.region_control.get(region)
        ctrl_after = target_snap.region_control.get(region)
        if ctrl_before != ctrl_after:
            if ctrl_after and ctrl_before:
                bullets.append(f"{ctrl_after} took {region} from {ctrl_before}")
            elif ctrl_after:
                bullets.append(f"{ctrl_after} claimed {region}")
            else:
                bullets.append(f"{ctrl_before} lost {region}")

    # Cap at 5 bullets
    bullets = bullets[:5]
    return "\n".join(f"- {b}" for b in bullets) if bullets else ""


def build_after_summary(
    history: Sequence[TurnSnapshot],
    moment: NarrativeMoment,
    next_moment: NarrativeMoment | None,
) -> str:
    """Mechanical after-context for foreshadowing.

    Compare moment.anchor_turn to next_moment.anchor_turn (or final turn if None).
    Forward-looking: "will rise/fall to X".
    """
    snap_by_turn: dict[int, TurnSnapshot] = {s.turn: s for s in history}
    if not snap_by_turn:
        return ""

    current_turn = moment.anchor_turn

    # Reference turn: next_moment's anchor, or last available turn
    if next_moment is not None:
        ref_turn = next_moment.anchor_turn
    else:
        ref_turn = max(snap_by_turn.keys())

    current_snap = _closest_snap(snap_by_turn, current_turn)
    future_snap = _closest_snap(snap_by_turn, ref_turn)

    if current_snap is None or future_snap is None:
        return ""

    bullets: list[str] = []

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
                bullets.append(f"{civ} {stat} {direction} to {later_val}")

    # Territory changes (forward-looking)
    current_regions = set(current_snap.region_control.keys())
    future_regions = set(future_snap.region_control.keys())
    all_regions = current_regions | future_regions
    for region in sorted(all_regions):
        ctrl_now = current_snap.region_control.get(region)
        ctrl_later = future_snap.region_control.get(region)
        if ctrl_now != ctrl_later:
            if ctrl_later and ctrl_now:
                bullets.append(f"{region} will pass from {ctrl_now} to {ctrl_later}")
            elif ctrl_later:
                bullets.append(f"{region} will be claimed by {ctrl_later}")
            else:
                bullets.append(f"{ctrl_now} will lose {region}")

    # Cap at 5 bullets
    bullets = bullets[:5]
    return "\n".join(f"- {b}" for b in bullets) if bullets else ""


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


def build_action_prompt(civ: Civilization, world: WorldState) -> str:
    """Build the prompt for LLM action selection."""
    # Summarize relationships
    rel_summary = ""
    if civ.name in world.relationships:
        for other_name, rel in world.relationships[civ.name].items():
            rel_summary += f"  - {other_name}: {rel.disposition.value}"
            if rel.grievances:
                rel_summary += f" (grievances: {', '.join(rel.grievances)})"
            if rel.treaties:
                rel_summary += f" (treaties: {', '.join(rel.treaties)})"
            rel_summary += "\n"

    # Summarize active conditions
    conditions = [
        c for c in world.active_conditions if civ.name in c.affected_civs
    ]
    cond_text = ", ".join(f"{c.condition_type} (severity {c.severity}, {c.duration} turns left)"
                          for c in conditions) or "None"

    return f"""You are the strategic advisor for {civ.name}.

CURRENT STATE:
- Population: {civ.population} ({len(civ.regions)} region{'s' if len(civ.regions) != 1 else ''})
- Military: {civ.military}/100
- Economy: {civ.economy}/100
- Culture: {civ.culture}/100
- Stability: {civ.stability}/100
- Tech Era: {civ.tech_era.value}
- Treasury: {civ.treasury}
- Asabiya (solidarity): {civ.asabiya}
- Controlled regions: {', '.join(civ.regions) or 'None'}
- Cultural domains: {', '.join(civ.domains)}
- Values: {', '.join(civ.values)}
- Leader: {civ.leader.name} ({civ.leader.trait})
- Goal: {civ.goal}

RELATIONSHIPS:
{rel_summary or '  None'}

ACTIVE CONDITIONS: {cond_text}

Choose exactly ONE action from: EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR, BUILD, EMBARGO, MOVE_CAPITAL, FUND_INSTABILITY, EXPLORE, INVEST_CULTURE

Consider: your goal, your stats, your relationships, active threats, and available resources.
You must respond with exactly one word. Do not explain your reasoning.
Respond with ONLY the action name (one word, all caps). Nothing else."""


def build_chronicle_prompt(world: WorldState, events: list[Event]) -> str:
    """Backward-compatible wrapper — delegates to a no-flavor, no-style build."""
    return _build_chronicle_prompt_impl(world, events, event_flavor=None, narrative_style=None)


def _build_chronicle_prompt_impl(
    world: WorldState, events: list[Event],
    event_flavor: dict | None = None,
    narrative_style: str | None = None,
) -> str:
    """Build the prompt for LLM chronicle narration."""
    # Build civilization summaries
    civ_summaries = ""
    for civ in world.civilizations:
        civ_summaries += f"\n{civ.name} (domains: {', '.join(civ.domains)}):"
        civ_summaries += f" Pop {civ.population}, Mil {civ.military}, Econ {civ.economy},"
        civ_summaries += f" Culture {civ.culture}, Stability {civ.stability},"
        civ_summaries += f" Treasury {civ.treasury}, Asabiya {civ.asabiya}"
        civ_summaries += f"\n  Leader: {civ.leader.name} ({civ.leader.trait})"
        civ_summaries += f"\n  Regions: {', '.join(civ.regions)}"

    # Build event list with flavor substitution
    event_text = ""
    for e in events:
        display_type = e.event_type
        display_desc = e.description
        if event_flavor and e.event_type in event_flavor:
            display_type = event_flavor[e.event_type].name
            display_desc = event_flavor[e.event_type].description
        event_text += f"\n- [{display_type}] {display_desc} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)"

    # Named events context for historical callbacks
    named_context = ""
    if world.named_events:
        recent = world.named_events[-5:]
        named_context += "\n\nRecent historical landmarks:\n"
        for ne in recent:
            named_context += f"- {ne.name} (turn {ne.turn}): {ne.description}\n"

        best_named = max(world.named_events, key=lambda ne: ne.importance)
        if best_named not in recent:
            named_context += f"\nMost significant event in all history: {best_named.name} (turn {best_named.turn})\n"

        named_context += "\nReference these landmarks when relevant — weave callbacks to past events.\n"

    # Rivalry context
    rivalries = []
    for civ in world.civilizations:
        if civ.leader.rival_leader:
            rivalries.append(f"{civ.leader.name} of {civ.name} has a personal rivalry with {civ.leader.rival_leader} of {civ.leader.rival_civ}")
    rivalry_context = ""
    if rivalries:
        rivalry_context += "\n\nActive rivalries:\n"
        for r in rivalries:
            rivalry_context += f"- {r}\n"
        rivalry_context += "Weave these personal rivalries into the narrative when relevant.\n"

    # Era-adaptive role line
    eras = [c.tech_era.value for c in world.civilizations if c.regions]
    dominant = max(eras, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 0) if eras else "tribal"
    era_voice, era_style = ERA_REGISTER.get(dominant, ERA_REGISTER["tribal"])
    role_line = f"{era_voice} You chronicle the world of {world.name}."
    if narrative_style:
        role_line += f"\n\nNARRATIVE STYLE: {narrative_style}"

    return f"""{role_line}

TURN {world.turn}:

CIVILIZATIONS:{civ_summaries}

EVENTS THIS TURN:{event_text}{named_context}{rivalry_context}

Write a chronicle entry for this turn. Rules:
1. {narrative_style if narrative_style else era_style}
2. For each civilization mentioned, weave their cultural DOMAINS into the prose. A maritime culture's trade dispute involves harbors and currents; a mountain culture's crisis involves peaks and stone. This is critical for thematic coherence.
3. Focus on events with importance >= 5. Mention lower-importance events briefly or skip them.
4. Reference specific leader names, region names, and cultural values where relevant.
5. End with a sentence that hints at coming tension or change.
6. Do NOT include turn numbers or game mechanics in the prose.
7. Write 3-5 paragraphs.

Respond only with the chronicle prose. No preamble, no markdown formatting, no meta-commentary."""


class NarrativeEngine:
    """LLM-powered action selection and chronicle generation.

    Accepts two separate LLMClient instances: one for simulation calls
    (action selection — high volume, can be local) and one for narrative
    calls (chronicle prose — lower volume, benefits from higher quality).
    """

    def __init__(self, sim_client: LLMClient, narrative_client: LLMClient,
                 event_flavor: dict | None = None,
                 narrative_style: str | None = None):
        self.sim_client = sim_client
        self.narrative_client = narrative_client
        self.event_flavor = event_flavor
        self.narrative_style = narrative_style

    def _is_api_client(self) -> bool:
        """Check if narrative_client is an API backend (not local)."""
        return isinstance(self.narrative_client, (AnthropicClient, GeminiClient))

    def _supports_batch(self) -> bool:
        """Check if narrative_client supports batch_complete()."""
        return isinstance(self.narrative_client, AnthropicClient)

    def select_action(self, civ: Civilization, world: WorldState) -> ActionType:
        """Ask the LLM to choose an action for a civilization.

        Routes to sim_client (local model) for cost efficiency.
        Falls back to DEVELOP on any LLM error.
        """
        prompt = build_action_prompt(civ, world)
        try:
            text = self.sim_client.complete(prompt, max_tokens=10).upper()
        except Exception:
            return ActionType.DEVELOP

        # Parse response — must be exactly one valid action
        try:
            return ActionType(text.lower())
        except ValueError:
            # Fuzzy match
            for action in ActionType:
                if action.value.upper() in text:
                    return action
            return ActionType.DEVELOP  # Safe default

    def generate_chronicle(self, world: WorldState, events: list[Event]) -> str:
        """Generate a chronicle entry for the current turn.

        Routes to narrative_client for prose quality.
        Falls back to a mechanical summary on any LLM error.
        """
        prompt = _build_chronicle_prompt_impl(world, events,
                                              event_flavor=self.event_flavor,
                                              narrative_style=self.narrative_style)
        try:
            return self.narrative_client.complete(prompt, max_tokens=1000)
        except Exception:
            # Fallback: mechanical summary so the run doesn't crash
            summaries = "; ".join(e.description for e in events if e.description)
            return f"Turn {world.turn}: {summaries or 'Events unfolded.'}"

    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        gap_summaries: list[GapSummary],
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
        # M45: Arc summary follow-up (API mode only)
        gp_by_name: dict | None = None,
        # M52: World state for artifact context in prompts
        world=None,
    ) -> list[ChronicleEntry]:
        """Narrate all selected moments.

        Uses Anthropic Batch API when available (50% cheaper, parallel).
        Falls back to sequential for local/Gemini clients.
        Per-moment fallback on LLM failure (mechanical summary, batch continues).
        Progress: on_progress(completed, total, eta_seconds).
        """
        # M52: Store world for artifact context
        self._world = world

        # Build prompts and context for all moments up front
        prepared = self._prepare_narration_prompts(
            moments, history, great_persons, social_edges,
            dissolved_edges_by_turn, agent_name_map, gini_by_civ,
            economy_result,
        )

        # Batch API path — Anthropic only
        if self._supports_batch():
            return self._narrate_batch_api(
                moments, prepared, on_progress,
            )

        # Sequential path — local / Gemini / fallback
        return self._narrate_sequential(
            moments, prepared, on_progress, gp_by_name,
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
    ) -> list[dict]:
        """Build prompt/system pairs for each moment. Returns list of dicts
        with keys: prompt, system, agent_ctx."""
        snap_map = {s.turn: s for s in history}
        total = len(moments)
        result = []

        # M50b: Build gp_by_agent_id for bond-source narration
        gp_by_agent_id: dict | None = None
        if great_persons:
            gp_by_agent_id = {}
            for gp in great_persons:
                if gp.agent_id is not None:
                    gp_by_agent_id[gp.agent_id] = gp

        for idx, moment in enumerate(moments):
            prev_moment = moments[idx - 1] if idx > 0 else None
            next_moment = moments[idx + 1] if idx < total - 1 else None

            before_summary = build_before_summary(history, moment, prev_moment)
            after_summary = build_after_summary(history, moment, next_moment)

            role_instruction = ROLE_INSTRUCTIONS.get(
                moment.narrative_role,
                ROLE_INSTRUCTIONS[NarrativeRole.RESOLUTION],
            )

            causes: list[str] = []
            consequences: list[str] = []
            for link in moment.causal_links:
                if link.effect_turn >= moment.turn_range[0] and link.effect_turn <= moment.turn_range[1]:
                    causes.append(f"{link.pattern} (turn {link.cause_turn})")
                if link.cause_turn >= moment.turn_range[0] and link.cause_turn <= moment.turn_range[1]:
                    consequences.append(f"{link.pattern} (turn {link.effect_turn})")

            event_text = ""
            for e in moment.events:
                event_text += f"\n- [{e.event_type}] {e.description} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)"

            named_text = ""
            if moment.named_events:
                named_text = "\n\nHistorical landmarks in this period:\n"
                for ne in moment.named_events:
                    named_text += f"- {ne.name} (turn {ne.turn}): {ne.description}\n"

            causal_text = ""
            if causes:
                causal_text += "\n\nCAUSES leading to this moment:\n"
                for c in causes:
                    causal_text += f"- {c}\n"
            if consequences:
                causal_text += "\n\nCONSEQUENCES flowing from this moment:\n"
                for c in consequences:
                    causal_text += f"- {c}\n"

            context_text = ""
            if before_summary:
                context_text += f"\n\nBEFORE this moment:\n{before_summary}"
            if after_summary:
                context_text += f"\n\nAFTER this moment (for foreshadowing):\n{after_summary}"

            # M40: Build agent context with relationships
            agent_context_text = ""
            agent_ctx = None
            if great_persons is not None:
                hostage_data = []
                for gp in great_persons:
                    if gp.is_hostage and gp.captured_by:
                        hostage_data.append({
                            "type": "hostage",
                            "character_a": gp.captured_by,
                            "character_b": gp.name,
                            "role_a": "captor",
                            "role_b": "captive",
                            "since_turn": gp.born_turn,
                        })

                moment_dissolved: list[tuple] = []
                if dissolved_edges_by_turn:
                    for t in range(moment.turn_range[0], moment.turn_range[1] + 1):
                        moment_dissolved.extend(dissolved_edges_by_turn.get(t, []))

                snap = _closest_snap(snap_map, moment.anchor_turn)
                agent_ctx = build_agent_context_for_moment(
                    moment, great_persons, {}, {},
                    gp_by_agent_id=gp_by_agent_id,
                    social_edges=social_edges,
                    dissolved_edges=moment_dissolved if moment_dissolved else None,
                    agent_name_map=agent_name_map,
                    hostage_data=hostage_data,
                    gini_by_civ=gini_by_civ,
                    economy_result=economy_result,
                    history=history,
                    current_snapshot=snap,
                    world=getattr(self, "_world", None),
                )
                if agent_ctx is not None:
                    agent_context_text = "\n\n" + build_agent_context_block(agent_ctx)

            # M52: Artifact context
            artifact_context_text = ""
            if hasattr(self, '_world') and self._world is not None:
                from chronicler.artifacts import _get_relevant_artifacts, render_artifact_context
                relevant_artifacts = _get_relevant_artifacts(self._world, moment)
                artifact_context_text = render_artifact_context(relevant_artifacts)
                if artifact_context_text:
                    artifact_context_text = "\n\n" + artifact_context_text

            snap = _closest_snap(snap_map, moment.anchor_turn)
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

            prompt = f"""NARRATIVE ROLE: {moment.narrative_role.value.upper()}
{role_instruction}

TURNS {moment.turn_range[0]}-{moment.turn_range[1]}:

EVENTS:{event_text}{named_text}{causal_text}{context_text}{agent_context_text}{artifact_context_text}{style_text}

Write 3-5 paragraphs of chronicle prose for this moment.
Respond only with the chronicle prose. No preamble, no markdown formatting."""

            result.append({
                "prompt": prompt,
                "system": system,
                "agent_ctx": agent_ctx,
            })

        return result

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
        for idx, (moment, narrative) in enumerate(zip(moments, results)):
            if narrative is None:
                descriptions = [e.description for e in moment.events if e.description]
                narrative = "; ".join(descriptions) if descriptions else "Events unfolded."

            entries.append(ChronicleEntry(
                turn=moment.anchor_turn,
                covers_turns=moment.turn_range,
                events=list(moment.events),
                named_events=list(moment.named_events),
                narrative=narrative,
                importance=moment.score,
                narrative_role=moment.narrative_role,
                causal_links=list(moment.causal_links),
            ))

            if on_progress is not None:
                on_progress(idx + 1, len(moments), None)

        return entries

    def _narrate_sequential(
        self,
        moments: list[NarrativeMoment],
        prepared: list[dict],
        on_progress: Callable[[int, int, float | None], None] | None = None,
        gp_by_name: dict | None = None,
    ) -> list[ChronicleEntry]:
        """Narrate moments sequentially — for local and Gemini clients."""
        entries: list[ChronicleEntry] = []
        total = len(moments)
        previous_prose: str | None = None
        start_time: float | None = None
        _first_failure = True

        for idx, (moment, prep) in enumerate(zip(moments, prepared)):
            prompt = prep["prompt"]
            system = prep["system"]
            agent_ctx = prep["agent_ctx"]

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
                if _first_failure:
                    logger.warning("Narration failed (falling back to mechanical summary): %s", exc)
                    _first_failure = False
                descriptions = [
                    e.description for e in moment.events if e.description
                ]
                narrative = "; ".join(descriptions) if descriptions else "Events unfolded."

            previous_prose = narrative

            # M45: Arc summary follow-up (API mode only)
            if (agent_ctx is not None
                    and self._is_api_client()
                    and gp_by_name):
                known_names = {c["name"] for c in agent_ctx.named_characters}
                for ev in moment.events:
                    for actor in ev.actors:
                        if actor in gp_by_name:
                            known_names.add(actor)
                matched = [n for n in known_names if n in narrative]
                if matched:
                    try:
                        summary_prompt = (
                            "Based on the following passage, write exactly one sentence "
                            "summarizing each named character's role. "
                            "Only reference events described in the passage.\n\n"
                            f"Characters: {', '.join(matched)}\n"
                            f"Passage: {narrative}\n\n"
                            "Respond as:\n"
                            + "\n".join(f"{n}: [sentence]" for n in matched)
                        )
                        summary_response = self.narrative_client.complete(summary_prompt)
                        for name in matched:
                            prefix = f"{name}: "
                            for line in summary_response.split("\n"):
                                if line.startswith(prefix):
                                    sentence = line[len(prefix):].strip()
                                    if sentence and name in gp_by_name:
                                        _update_arc_summary(gp_by_name[name], sentence)
                                    break
                    except Exception:
                        logger.warning(
                            "Arc summary follow-up failed for moment %d, skipping",
                            moment.anchor_turn,
                        )

            entry = ChronicleEntry(
                turn=moment.anchor_turn,
                covers_turns=moment.turn_range,
                events=list(moment.events),
                named_events=list(moment.named_events),
                narrative=narrative,
                importance=moment.score,
                narrative_role=moment.narrative_role,
                causal_links=list(moment.causal_links),
            )
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

        return entries

    def action_selector(self, civ: Civilization, world: WorldState) -> ActionType:
        """Adapter method matching the ActionSelector callback signature."""
        return self.select_action(civ, world)

    def narrator(self, world: WorldState, events: list[Event]) -> str:
        """Adapter method matching the Narrator callback signature."""
        return self.generate_chronicle(world, events)
