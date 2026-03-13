"""Chronicle compiler — assembles turn entries and era reflections into Markdown.

The final output reads like a mythic history: named ages, chapter breaks at
era reflections, and turn-level narrative woven into continuous prose.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChronicleEntry:
    turn: int
    text: str
    era: str | None = None


def compile_chronicle(
    world_name: str,
    entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    epilogue: str | None = None,
) -> str:
    """Compile all chronicle entries and era reflections into a Markdown document."""
    lines: list[str] = []
    lines.append(f"# Chronicle of {world_name}\n")
    lines.append("---\n")

    for entry in entries:
        # Insert era header if this turn marks an era boundary
        if entry.turn in era_reflections:
            lines.append("")
            lines.append(era_reflections[entry.turn])
            lines.append("")

        lines.append(entry.text)
        lines.append("")  # Blank line between entries

    if epilogue:
        lines.append("---\n")
        lines.append(f"*{epilogue}*\n")

    return "\n".join(lines)
