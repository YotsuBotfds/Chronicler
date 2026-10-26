"""Memory streams and periodic reflections (Stanford Generative Agents pattern).

Each civilization maintains a MemoryStream of natural-language entries with
timestamps and importance scores. Every N turns, reflections consolidate
recent memories into higher-level era summaries that serve as chapter breaks
in the final chronicle.
"""
from __future__ import annotations

import json
import re
# Keep field available to existing memory module callers.
from dataclasses import dataclass, field
from pathlib import Path
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

    def save(self, path: Path) -> None:
        """Persist memory stream to a JSON file."""
        parent = path.parent
        try:
            parent_is_dir = parent.is_dir()
        except OSError:
            parent_is_dir = False
        if not parent_is_dir:
            parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.json_text())

    def json_text(self) -> str:
        """``json.dumps(data, indent=2)`` of the stream (what ``save`` writes).

        Streams only grow and are saved every few turns, so each entry's
        encoding is kept and reused while the entry (the same object, with
        the very same field objects) is still at its place in the list;
        the text is assembled as the indenting encoder lays it out.
        """
        return (
            '{\n  "civilization_name": ' + json.dumps(self.civilization_name)
            + ',\n  "entries": ' + self._list_text("entries", self.entries)
            + ',\n  "reflections": ' + self._list_text("reflections", self.reflections)
            + "\n}"
        )

    def _list_text(self, kind: str, items: list[MemoryEntry]) -> str:
        if not items:
            return "[]"
        caches = self.__dict__.setdefault("_encoded", {})
        cache = caches.setdefault(kind, [])
        del cache[len(items):]
        texts = []
        for i, e in enumerate(items):
            turn, text, importance, entry_type = e.turn, e.text, e.importance, e.entry_type
            if i < len(cache):
                c = cache[i]
                # The same entry holding the very same field objects.
                if c[0] is e and c[1] is turn and c[2] is text and c[3] is importance and c[4] is entry_type:
                    texts.append(c[5])
                    continue
            # A nested object of a list in the top-level object: its lines sit
            # four spaces deeper than a top-level dump of the entry.
            encoded = json.dumps(
                {"turn": turn, "text": text, "importance": importance, "entry_type": entry_type},
                indent=2,
            ).replace("\n", "\n    ")
            row = (e, turn, text, importance, entry_type, encoded)
            if i < len(cache):
                cache[i] = row
            else:
                cache.append(row)
            texts.append(encoded)
        return "[\n    " + ",\n    ".join(texts) + "\n  ]"

    @classmethod
    def load(cls, path: Path) -> MemoryStream:
        """Load a memory stream from a JSON file."""
        data = json.loads(path.read_text())
        stream = cls(civilization_name=data["civilization_name"])
        stream.entries = [
            MemoryEntry(turn=e["turn"], text=e["text"], importance=e["importance"], entry_type=e["entry_type"])
            for e in data["entries"]
        ]
        stream.reflections = [
            MemoryEntry(turn=r["turn"], text=r["text"], importance=r["importance"], entry_type=r["entry_type"])
            for r in data["reflections"]
        ]
        return stream


def sanitize_civ_name(name: str) -> str:
    """Sanitize a civilization name for use in filenames."""
    name = name.lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]", "", name)


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
