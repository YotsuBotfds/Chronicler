"""Chronicle compiler — assembles turn entries and era reflections into Markdown.

The final output reads like a mythic history: named ages, chapter breaks at
era reflections, and turn-level narrative woven into continuous prose.
"""
from __future__ import annotations

from chronicler.models import ChronicleEntry, GapSummary


def compile_chronicle(
    world_name: str,
    entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    epilogue: str | None = None,
    gap_summaries: list[GapSummary] | None = None,
) -> str:
    """Compile all chronicle entries and era reflections into a Markdown document.

    Parameters
    ----------
    gap_summaries : list[GapSummary] | None
        If provided, one-liner summaries are inserted between narrated entries
        for any gap whose turn range falls between consecutive entries.
    """
    lines: list[str] = []
    lines.append(f"# Chronicle of {world_name}\n")
    lines.append("---\n")

    # Index gap summaries by start turn for efficient lookup
    gap_by_start: dict[int, GapSummary] = {}
    for gs in (gap_summaries or []):
        gap_by_start[gs.turn_range[0]] = gs

    prev_end: int | None = None
    for entry in entries:
        # Insert gap one-liners between narrated entries
        if prev_end is not None and gap_by_start:
            for gs_start, gs in sorted(gap_by_start.items()):
                if prev_end < gs_start <= entry.turn:
                    lines.append(
                        f"*Turns {gs.turn_range[0]}\u2013{gs.turn_range[1]}: "
                        f"{gs.event_count} events, dominated by {gs.top_event_type}.*"
                    )
                    lines.append("")

        # Insert era header if this turn marks an era boundary
        if entry.turn in era_reflections:
            lines.append("")
            lines.append(era_reflections[entry.turn])
            lines.append("")

        lines.append(entry.narrative)
        lines.append("")  # Blank line between entries

        prev_end = entry.covers_turns[1]

    if epilogue:
        lines.append("---\n")
        lines.append(f"*{epilogue}*\n")

    return "\n".join(lines)
