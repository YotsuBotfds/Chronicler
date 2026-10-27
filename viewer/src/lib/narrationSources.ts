/**
 * A chronicle passage's sources (docs/integration/narration-provenance.md):
 * each fact id of its provenance resolved to the bundle record it names,
 * with the turn to jump to. Only the lazily loaded sources panel reads this.
 */
import type { Bundle, Event, NewChronicleEntry, PassageProvenance } from "../types";

export interface PassageSource {
  id: string;
  /** event, landmark, account, character, artifact, state, change, window, observation, names, link, fact */
  kind: string;
  label: string;
  /** The record's turn (a snapshot's: the turn it stands after); null when undated. */
  turn: number | null;
  /** Given as retrospective (after the narrated moment, for foreshadowing). */
  retrospective: boolean;
  /** Cited by a sentence of the passage. */
  cited: boolean;
  /** The timeline event an `e<i>` id names (for the event inspector). */
  event?: Event;
}

export interface PassageSources {
  narrator: string;
  asOf: number;
  /** Cited facts first (in the passage's order), then the other facts given. */
  sources: PassageSource[];
  cited: number;
  given: number;
}

interface LoosePerson {
  name?: string;
  agent_id?: number | null;
}

interface LooseWorld {
  civilizations?: Array<{ name: string; great_persons?: LoosePerson[] }>;
  regions?: Array<{ name: string }>;
  retired_persons?: LoosePerson[];
  artifacts?: Array<{ artifact_id: number; name: string; origin_turn?: number }>;
}

const STATE_WORDS: Record<string, string> = {
  ruler: "ruler of", war: "war of", movement: "movement", reform: "reform", city: "city", guild: "guild",
  burghers: "burghers of", seat: "seat of learning", food: "food in", urban: "towns of", settlement: "settlement",
};

function entity(world: LooseWorld, key: string): string {
  const civ = /^c(\d+)$/.exec(key);
  if (civ) return world.civilizations?.[Number(civ[1])]?.name ?? key;
  const region = /^r(\d+)$/.exec(key);
  if (region) return world.regions?.[Number(region[1])]?.name ?? key;
  const named = /^[cr]:(.+)$/.exec(key);
  if (named) return named[1].replace(/_/g, " ");
  return key;
}

function personName(world: LooseWorld, agentId: number): string | null {
  for (const civ of world.civilizations ?? []) {
    const found = civ.great_persons?.find((gp) => gp.agent_id === agentId);
    if (found?.name) return found.name;
  }
  return world.retired_persons?.find((gp) => gp.agent_id === agentId)?.name ?? null;
}

function eventLabel(event: Event): string {
  const text = event.description || event.actors.join(", ");
  return `${event.event_type.replace(/_/g, " ")}: ${text}`;
}

/** One fact id as the bundle names it (`turn` is the provenance's own date when the record gives none). */
export function resolveFact(bundle: Bundle, entry: NewChronicleEntry, id: string, turn: number | null):
  Omit<PassageSource, "retrospective" | "cited"> {
  const world = bundle.world_state as unknown as LooseWorld;
  let m = /^e(\d+)$/.exec(id);
  if (m) {
    const event = bundle.events_timeline[Number(m[1])];
    return event ? { id, kind: "event", label: eventLabel(event), turn: event.turn, event }
      : { id, kind: "event", label: "an event this bundle does not hold", turn };
  }
  m = /^n(\d+)$/.exec(id);
  if (m) {
    const named = bundle.named_events[Number(m[1])];
    return named ? { id, kind: "landmark", label: `${named.name}: ${named.description}`, turn: named.turn }
      : { id, kind: "landmark", label: "a landmark this bundle does not hold", turn };
  }
  m = /^((?:court|temple|seat):\d+)\/e(\d+)$/.exec(id);
  if (m) {
    const chronicler = bundle.historiography?.chroniclers.find((c) => c.id === m![1]);
    const event = bundle.events_timeline[Number(m[2])];
    const who = chronicler?.name ?? m[1];
    return { id, kind: "account", label: event ? `${who} on ${eventLabel(event)}` : who, turn: turn ?? event?.turn ?? null, event };
  }
  m = /^p(\d+)$/.exec(id);
  if (m) {
    return { id, kind: "character", label: personName(world, Number(m[1])) ?? `character ${m[1]}`, turn };
  }
  m = /^art(\d+)$/.exec(id);
  if (m) {
    const artifact = world.artifacts?.find((a) => a.artifact_id === Number(m![1]));
    return { id, kind: "artifact", label: artifact?.name ?? `artifact ${m[1]}`, turn: artifact?.origin_turn ?? turn };
  }
  m = /^s(\d+)\.(\w+)(?:\.(.+))?$/.exec(id);
  if (m) {
    const word = STATE_WORDS[m[2]] ?? m[2];
    const key = m[3] ? m[3].split("-").map((part) => entity(world, part)).join(" and ") : "";
    return { id, kind: "state", label: `State after turn ${Number(m[1]) - 1}: ${word} ${key}`.trim(), turn: Number(m[1]) - 1 };
  }
  m = /^d(\d+)-(\d+)\.([^.]+)(?:\.(\w+))?$/.exec(id);
  if (m) {
    const what = m[4] ? `${entity(world, m[3])} ${m[4]}` : `control of ${entity(world, m[3])}`;
    return {
      id, kind: "change", label: `Change of ${what}, turns ${Number(m[1]) - 1} to ${Number(m[2]) - 1}`,
      turn: Number(m[2]) - 1,
    };
  }
  m = /^w(\d+)-(\d+)(?:\.(\w+))?$/.exec(id);
  if (m) {
    const what = m[3] === "mood" ? "The people's mood" : "Other events";
    return { id, kind: "window", label: `${what} in turns ${m[1]}-${m[2]}`, turn: Number(m[2]) };
  }
  m = /^o(\d+)\.(.+)$/.exec(id);
  if (m) {
    const parts = m[2].split(".");
    const key = parts[1] ? ` of ${entity(world, parts[1])}` : "";
    return { id, kind: "observation", label: `${parts[0].replace(/_/g, " ")}${key} after turn ${m[1]}`, turn: Number(m[1]) };
  }
  m = /^L\.([crsfp])(\d+)$/.exec(id);
  if (m) {
    const target = m[1] === "c" || m[1] === "r" ? entity(world, `${m[1]}${m[2]}`) : `${m[1]}${m[2]}`;
    return { id, kind: "names", label: `In-world names of ${target}`, turn };
  }
  m = /^k(\d+)$/.exec(id);
  if (m) {
    const link = entry.causal_links[Number(m[1])];
    return { id, kind: "link", label: link ? link.pattern : id, turn };
  }
  return { id, kind: "fact", label: id, turn };
}

/** A passage's sources, or null when the entry has no provenance. */
export function passageSources(bundle: Bundle, entry: NewChronicleEntry): PassageSources | null {
  const provenance: PassageProvenance | undefined = entry.provenance;
  if (!provenance) return null;
  const given = new Map<string, { turn: number | null; retrospective: boolean }>();
  for (const row of provenance.facts) {
    if (typeof row === "string") {
      given.set(row, { turn: provenance.as_of, retrospective: false });  // dated the passage's own turn
    } else {
      given.set(row[0], { turn: row[1], retrospective: row[2] === "r" });
    }
  }
  const citedIds: string[] = [];
  for (const [, , ids] of provenance.spans) {
    for (const id of ids) {
      if (!citedIds.includes(id)) citedIds.push(id);
    }
  }
  const order = [...citedIds, ...[...given.keys()].filter((id) => !citedIds.includes(id))];
  const sources = order.map((id) => {
    const info = given.get(id);
    return {
      ...resolveFact(bundle, entry, id, info?.turn ?? null),
      retrospective: info?.retrospective ?? false,
      cited: citedIds.includes(id),
    };
  });
  return {
    narrator: provenance.narrator,
    asOf: provenance.as_of,
    sources,
    cited: citedIds.length,
    given: given.size,
  };
}
