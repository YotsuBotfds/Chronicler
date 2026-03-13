"""Memory streams and periodic reflections (Stanford Generative Agents pattern).

Each civilization maintains a MemoryStream of natural-language entries with
timestamps and importance scores. Every N turns, reflections consolidate
recent memories into higher-level era summaries that serve as chapter breaks
in the final chronicle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    turn: int
    text: str
    importance: int  # 1-10 scale
    entry_type: str = "event"  # "event" or "reflection"


class MemoryStream:
    """Running memory for a single civilization."""

    def __init__(self, civilization_name: str):
        self.civilization_name = civilization_name
        self.entries: list[MemoryEntry] = []
        self.reflections: list[MemoryEntry] = []

    def add(self, text: str, turn: int, importance: int = 5) -> None:
        self.entries.append(MemoryEntry(
            turn=turn, text=text, importance=importance, entry_type="event",
        ))

    def add_reflection(self, text: str, turn: int) -> None:
        entry = MemoryEntry(
            turn=turn, text=text, importance=10, entry_type="reflection",
        )
        self.reflections.append(entry)

    def get_recent(self, count: int = 10) -> list[MemoryEntry]:
        return self.entries[-count:]

    def get_important(self, min_importance: int = 5) -> list[MemoryEntry]:
        return [e for e in self.entries if e.importance >= min_importance]

    def get_context_window(self, recent_count: int = 10) -> list[MemoryEntry]:
        """Return recent entries + all reflections for LLM context."""
        recent = self.get_recent(recent_count)
        return list(self.reflections) + recent


def should_reflect(turn: int, interval: int = 10) -> bool:
    """Check whether it's time to generate a reflection."""
    return turn > 0 and turn % interval == 0


def build_reflection_prompt(
    stream: MemoryStream,
    era_start: int,
    era_end: int,
) -> str:
    """Build the prompt for LLM reflection generation."""
    era_entries = [e for e in stream.entries if era_start <= e.turn <= era_end]
    important = [e for e in era_entries if e.importance >= 5]
    all_entries = important or era_entries[-10:]  # Fallback to recent if no high-importance

    memory_text = "\n".join(
        f"- Turn {e.turn}: {e.text} (importance: {e.importance})"
        for e in all_entries
    )

    prev_reflections = "\n".join(
        f"- {r.text}" for r in stream.reflections
    ) or "None yet."

    return f"""You are a mythic historian reflecting on the history of {stream.civilization_name}.

PREVIOUS ERA SUMMARIES:
{prev_reflections}

EVENTS FROM TURNS {era_start}-{era_end}:
{memory_text}

Write a 2-3 sentence reflection summarizing this era for {stream.civilization_name}.
This should read like the name and description of a historical age — e.g.,
"The Age of Iron and Sorrow" followed by a concise characterization.
Focus on the most significant themes: expansion, decline, cultural flowering,
military conflict, or internal strife. Reference specific events where impactful.
This reflection will serve as a chapter heading in the final chronicle."""


def generate_reflection(
    stream: MemoryStream,
    era_start: int,
    era_end: int,
    client: Any,  # LLMClient — uses narrative client for quality
) -> str:
    """Generate an era-level reflection using the LLM.

    Accepts any LLMClient. In hybrid mode, this should be the narrative_client
    (Claude API) since era reflections benefit from high prose quality.
    """
    prompt = build_reflection_prompt(stream, era_start, era_end)
    text = client.complete(prompt, max_tokens=300)
    stream.add_reflection(text, turn=era_end)
    return text
