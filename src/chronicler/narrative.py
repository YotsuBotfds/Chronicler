"""LLM narrative engine — action selection and chronicle generation.

Uses two LLMClient instances with role-based routing:
- sim_client (local model via LM Studio): action selection — high volume, free
- narrative_client (Claude API): chronicle prose — lower volume, higher quality

Domain threading (Caves of Qud technique): each civilization's thematic
keywords (domains) are woven into every narrative mention, creating the
perception of deep cultural coherence with minimal mechanical overhead.
"""
from __future__ import annotations

import time
from typing import Callable, Sequence

from chronicler.llm import LLMClient
from chronicler.models import (
    ActionType,
    AgentContext,
    CausalLink,
    ChronicleEntry,
    CivThematicContext,
    Civilization,
    Disposition,
    Event,
    GapSummary,
    NarrationContext,
    NarrativeMoment,
    NarrativeRole,
    NamedEvent,
    TurnSnapshot,
    WorldState,
)


_SUMMARY_STATS = ("population", "military", "economy", "culture", "stability")
_STAT_THRESHOLD = 10


# ---------------------------------------------------------------------------
# M30: Agent context for narrator prompt
# ---------------------------------------------------------------------------

_DESPERATE_EVENTS = {"local_rebellion", "demographic_crisis"}
_RESTLESS_EVENTS = {"loyalty_cascade", "brain_drain", "occupation_shift"}


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
    lines.append("")

    if ctx.named_characters:
        lines.append("Named characters present:")
        for char in ctx.named_characters:
            origin = (f", originally {char['origin_civ']}"
                      if char.get("origin_civ") != char.get("civ") else "")
            lines.append(
                f"- {char['role']} {char['name']} ({char['civ']}{origin}) [{char['status']}]:"
            )
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
        lines.append("")

    lines.append("Guidelines:")
    lines.append("- Refer to named characters BY NAME — do not anonymize or rename them")
    lines.append("- Use their recent history for callbacks")
    lines.append("- Use population mood to set atmospheric tone")
    if ctx.displacement_fraction > 0.10:
        lines.append("- Weave refugee/exile themes into the narrative")

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
) -> AgentContext | None:
    """Build AgentContext if the moment has agent-source events."""
    agent_events = [e for e in moment.events if e.source == "agent"]
    if not agent_events:
        return None

    # Named characters active in this moment
    chars = []
    for gp in great_persons:
        if not gp.active or gp.source != "agent":
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

        chars.append(char)

    mood = compute_population_mood(agent_events)

    # Average displacement across all tracked regions
    disp_values = list(displacement_by_region.values())
    avg_disp = sum(disp_values) / len(disp_values) if disp_values else 0.0

    return AgentContext(
        named_characters=chars[:10],  # cap for token budget
        population_mood=mood,
        displacement_fraction=avg_disp,
    )


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
    ) -> list[ChronicleEntry]:
        """Narrate all selected moments sequentially with full context.

        Sequential (LM Studio saturates GPU with one request).
        Per-moment fallback on LLM failure (mechanical summary, batch continues).
        Progress: on_progress(completed, total, eta_seconds).
        ETA from second call onward (first is warmup). Default: 30 tok/s.
        """
        entries: list[ChronicleEntry] = []
        total = len(moments)
        previous_prose: str | None = None
        start_time: float | None = None

        for idx, moment in enumerate(moments):
            # Build before/after summaries
            prev_moment = moments[idx - 1] if idx > 0 else None
            next_moment = moments[idx + 1] if idx < total - 1 else None

            before_summary = build_before_summary(history, moment, prev_moment)
            after_summary = build_after_summary(history, moment, next_moment)

            # Role instruction
            role_instruction = ROLE_INSTRUCTIONS.get(
                moment.narrative_role,
                ROLE_INSTRUCTIONS[NarrativeRole.RESOLUTION],
            )

            # Extract causes (causal links where effect is in this moment's turn range)
            causes: list[str] = []
            consequences: list[str] = []
            for link in moment.causal_links:
                if link.effect_turn >= moment.turn_range[0] and link.effect_turn <= moment.turn_range[1]:
                    causes.append(f"{link.pattern} (turn {link.cause_turn})")
                if link.cause_turn >= moment.turn_range[0] and link.cause_turn <= moment.turn_range[1]:
                    consequences.append(f"{link.pattern} (turn {link.effect_turn})")

            # Build event text
            event_text = ""
            for e in moment.events:
                event_text += f"\n- [{e.event_type}] {e.description} (actors: {', '.join(e.actors)}, importance: {e.importance}/10)"

            # Named events
            named_text = ""
            if moment.named_events:
                named_text = "\n\nHistorical landmarks in this period:\n"
                for ne in moment.named_events:
                    named_text += f"- {ne.name} (turn {ne.turn}): {ne.description}\n"

            # Causes and consequences context
            causal_text = ""
            if causes:
                causal_text += "\n\nCAUSES leading to this moment:\n"
                for c in causes:
                    causal_text += f"- {c}\n"
            if consequences:
                causal_text += "\n\nCONSEQUENCES flowing from this moment:\n"
                for c in consequences:
                    causal_text += f"- {c}\n"

            # Before/after context
            context_text = ""
            if before_summary:
                context_text += f"\n\nBEFORE this moment:\n{before_summary}"
            if after_summary:
                context_text += f"\n\nAFTER this moment (for foreshadowing):\n{after_summary}"

            # Previous prose for style continuity
            continuity_text = ""
            if previous_prose:
                # Include last 200 chars for continuity
                excerpt = previous_prose[-200:]
                continuity_text = f"\n\nPREVIOUS ENTRY (for style continuity):\n...{excerpt}"

            # Era-adaptive register
            snap = _closest_snap({s.turn: s for s in history}, moment.anchor_turn)
            dominant_era = get_dominant_era(moment, snap) if snap else "tribal"
            era_voice, era_style = ERA_REGISTER.get(dominant_era, ERA_REGISTER["tribal"])

            # Narrative style: scenario override takes precedence over era register
            style_text = ""
            if self.narrative_style:
                style_text = f"\n\nNARRATIVE STYLE: {self.narrative_style}"
            else:
                style_text = f"\n\nNARRATIVE REGISTER: {era_style}"

            # Build system prompt
            system = (
                f"{era_voice} "
                f"Do NOT include turn numbers or game mechanics in the prose. "
                f"ROLE: {role_instruction}"
            )

            # Build user prompt
            prompt = f"""NARRATIVE ROLE: {moment.narrative_role.value.upper()}
{role_instruction}

TURNS {moment.turn_range[0]}-{moment.turn_range[1]}:

EVENTS:{event_text}{named_text}{causal_text}{context_text}{continuity_text}{style_text}

Write 3-5 paragraphs of chronicle prose for this moment.
Respond only with the chronicle prose. No preamble, no markdown formatting."""

            # Call LLM with fallback
            try:
                narrative = self.narrative_client.complete(
                    prompt, max_tokens=1000, system=system
                )
            except Exception:
                # Mechanical fallback: join event descriptions
                descriptions = [
                    e.description for e in moment.events if e.description
                ]
                narrative = "; ".join(descriptions) if descriptions else "Events unfolded."

            previous_prose = narrative

            # Build ChronicleEntry
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
                    per_moment = elapsed / (completed - 1)  # exclude warmup
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
