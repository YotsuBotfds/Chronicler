import type { Bundle, Event } from "../types";
import { eventKey, eventKeyCount } from "./bundleIndex";
import { exactSnapshot, readEntityTurn } from "./historyComparison";

export interface EvidenceEvent { event: Event; snapshotTurn: number; source: string; canPin: boolean }
export const PERIOD_TYPES: Record<string, "Disruption" | "Recovery / change"> = {
  drought: "Disruption", plague: "Disruption", earthquake: "Disruption", rebellion: "Disruption",
  secession: "Disruption", collapse: "Disruption", capital_loss: "Disruption", war_declared: "Disruption",
  battle: "Disruption", famine: "Disruption", dearth: "Disruption", federation_collapsed: "Disruption",
  restoration: "Recovery / change", cultural_renaissance: "Recovery / change",
  congress_peace: "Recovery / change", congress_ceasefire: "Recovery / change",
};
/** Completed snapshot T follows tick T-1. Exact duplicate reports count once;
 * colliding ids with different content remain separate, unpinnable evidence. */
export function recordedTimeline(bundle: Bundle, through: number): EvidenceEvent[] {
  if (!Number.isSafeInteger(through) || through < 1) return [];
  const seen = new Set<string>();
  return bundle.events_timeline.flatMap((event, index) => {
    if (!Number.isSafeInteger(event.turn) || event.turn < 0 || event.turn + 1 > through) return [];
    const identity = JSON.stringify([event.event_id, event.turn, event.event_type, event.actors,
      event.region, event.description, event.consequences, event.causes, event.episode, event.duration, event.driver]);
    if (seen.has(identity)) return [];
    seen.add(identity);
    return [{ event, snapshotTurn: event.turn + 1, source: `/events_timeline/${index}`,
      canPin: eventKeyCount(bundle.events_timeline, eventKey(event)) === 1 }];
  }).sort((a, b) => a.snapshotTurn - b.snapshotTurn);
}
export function regionInvestigation(bundle: Bundle, index: number, turn: number) {
  if (!Number.isSafeInteger(turn) || turn < 1 || !Number.isSafeInteger(index)) return null;
  const region = bundle.world_state.regions[index];
  if (!region) return null;
  const unique = bundle.world_state.regions.filter((row) => row.name === region.name).length === 1;
  const snapshot = exactSnapshot(bundle, turn);
  const reading = unique ? readEntityTurn(bundle, { kind: "region", name: region.name }, turn) : null;
  const hasOwner = unique && snapshot && Object.hasOwn(snapshot.region_control, region.name);
  const owner = hasOwner ? snapshot.region_control[region.name] : undefined;
  const ownerMatches = typeof owner === "string"
    ? bundle.world_state.civilizations.flatMap((civ, i) => civ.name === owner ? [i] : []) : [];
  const events = unique ? recordedTimeline(bundle, turn)
    .filter((row) => row.snapshotTurn >= Math.max(1, turn - 9) && row.event.region === region.name) : [];
  const named = unique ? bundle.named_events.flatMap((event, i) => event.region === region.name
    && Number.isSafeInteger(event.turn) && event.turn >= 0 && event.turn + 1 <= turn
    && event.turn + 1 >= Math.max(1, turn - 9)
    ? [{ event, snapshotTurn: event.turn + 1, source: `/named_events/${i}` }] : []) : [];
  return { index, name: region.name, unique, reading, owner,
    ownerIndex: ownerMatches.length === 1 ? ownerMatches[0] : null, events, named,
    from: Math.max(1, turn - 9), through: turn };
}
export interface InterestingPeriod { start: number; end: number; events: EvidenceEvent[]; categories: string[] }
export function interestingPeriods(bundle: Bundle, through: number): InterestingPeriod[] {
  const groups = new Map<number, InterestingPeriod>();
  for (const event of recordedTimeline(bundle, through)) {
    const category = Object.hasOwn(PERIOD_TYPES, event.event.event_type) ? PERIOD_TYPES[event.event.event_type] : undefined;
    if (!category) continue;
    const start = Math.floor((event.snapshotTurn - 1) / 5) * 5 + 1;
    const group = groups.get(start) ?? { start, end: Math.min(start + 4, through), events: [], categories: [] };
    group.events.push(event);
    if (!group.categories.includes(category)) group.categories.push(category);
    groups.set(start, group);
  }
  return [...groups.values()].filter((row) => row.events.length >= 2).sort((a, b) => b.start - a.start);
}
