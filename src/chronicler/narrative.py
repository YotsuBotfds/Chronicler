"""LLM narrative engine — action selection and chronicle generation.

Uses two LLMClient instances with role-based routing:
- sim_client (local model via LM Studio): action selection — high volume, free
- narrative_client (Claude API): chronicle prose — lower volume, higher quality

Domain threading (Caves of Qud technique): each civilization's thematic
keywords (domains) are woven into every narrative mention, creating the
perception of deep cultural coherence with minimal mechanical overhead.
"""
from __future__ import annotations

from chronicler.llm import LLMClient
from chronicler.models import (
    ActionType,
    Civilization,
    Disposition,
    Event,
    NamedEvent,
    WorldState,
)


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
- Population: {civ.population}/10
- Military: {civ.military}/10
- Economy: {civ.economy}/10
- Culture: {civ.culture}/10
- Stability: {civ.stability}/10
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

Choose exactly ONE action from: EXPAND, DEVELOP, TRADE, DIPLOMACY, WAR

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

    # Role line and narrative style
    role_line = f"You are a historian chronicling the world of {world.name}."
    if narrative_style:
        role_line += f"\n\nNARRATIVE STYLE: {narrative_style}"

    return f"""{role_line}

TURN {world.turn}:

CIVILIZATIONS:{civ_summaries}

EVENTS THIS TURN:{event_text}{named_context}{rivalry_context}

Write a chronicle entry for this turn. Rules:
1. Write in the style of a history — evocative, literary, as if written by a scholar looking back on these events centuries later.
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

    def action_selector(self, civ: Civilization, world: WorldState) -> ActionType:
        """Adapter method matching the ActionSelector callback signature."""
        return self.select_action(civ, world)

    def narrator(self, world: WorldState, events: list[Event]) -> str:
        """Adapter method matching the Narrator callback signature."""
        return self.generate_chronicle(world, events)
