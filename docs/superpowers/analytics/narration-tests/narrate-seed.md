# Chronicler Narration — Operator Prompt

Narrate a Chronicler simulation run for a given seed. You are narrating, not reviewing.

## Setup

1. Run the extraction script to generate windowed prompt files:

```bash
python scripts/narrate.py <SEED_DIR> --prompts-only
```

Where `<SEED_DIR>` is the path to a seed folder containing `chronicle_bundle.json` (e.g., `output/batch_gui/batch_1/seed_42`).

This produces `<SEED_DIR>/narration/window_N_prompt.md` files — one per narration window.

2. Read `window_1_prompt.md`. It contains the full narration instructions, world data, civilization snapshots, and curated event timeline.

3. Follow the instructions in that prompt exactly. Output ONLY the narration prose with `## Section Title` headers. No preamble, no metadata, no commentary.

4. After completing window 1, read `window_2_prompt.md` and narrate it. Continue sequentially through all windows.

5. After all windows are narrated, concatenate the outputs into a single `chronicle.md` in the seed directory:

```
# The Chronicle of {World Name}

*Seed {N} — {total_turns} Turns*

---

{window 1 narration}

---

{window 2 narration}

---

...
```

Save the final chronicle to `<SEED_DIR>/narration/chronicle.md`.

## Key Rules

- You are a classical historian. Past tense, third person, no game mechanics language.
- Each window's prompt contains all the style rules and data you need. Follow them.
- Maintain voice continuity across windows — the prologue in each window gives you the handoff state.
- Population convention: raw values below 10k, thousands at 10k+.
- No sermons in middle sections. Thematic reflections only in the final section or at civilization collapses.
- "The chronicle does not record..." works once per window maximum.
- Find internal tension in dominant civilizations — wealth with collapsing stability, merchant capture, cultural achievement masking decay.

## Example Invocation

```
Narrate seed 115. The seed folder is at output/batch_gui/batch_1/seed_115
```
