import type { Bundle } from "../types";
import { isRecord } from "./bundleValidation";

const SYSTEMS: Record<string, string> = {
  campaign: "Campaigns", governance: "Governance", contact: "Contact ledger", epidemics: "Epidemiology",
  finance: "Finance", diplomacy: "Diplomacy", techniques: "Techniques", maritime: "Maritime",
  gp_agendas: "Great-person agendas", nomads: "Nomads", cities: "Cities", agent_movements: "Movements",
  guilds: "Guilds", scholarship: "Scholarship", grain_reserves: "Public granaries", food: "Food and relief",
  health_care: "Health care", harvest_forecasts: "Harvest forecasts", ritual_gatherings: "Ritual gatherings",
  scientific_claims: "Scientific claims", transaction_receipts: "Transaction receipts",
  domestic_credit: "Domestic credit",
};
const STATE_SWITCHES = ["finance", "diplomacy", "techniques", "maritime", "gp_agendas", "nomads",
  "cities", "agent_movements", "guilds", "scholarship", "grain_reserves", "epidemics", "domestic_credit",
  "health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims", "transaction_receipts"];

export function savedWorldSummary(bundle: Bundle) {
  const world = bundle.world_state as unknown as Record<string, unknown>;
  const mode = Object.hasOwn(world, "agent_mode")
    ? world.agent_mode === null || world.agent_mode === "off" ? "Aggregate (agents off)"
      : typeof world.agent_mode === "string" ? world.agent_mode : "Unknown — not recorded"
    : "Unknown — not recorded";
  let first: number | null = null;
  let last: number | null = null;
  const recorded = new Set<string>();
  for (const snapshot of bundle.history) {
    first = first === null ? snapshot.turn : Math.min(first, snapshot.turn);
    last = last === null ? snapshot.turn : Math.max(last, snapshot.turn);
    const row = snapshot as unknown as Record<string, unknown>;
    for (const key of Object.keys(SYSTEMS)) {
      if (isRecord(row[key])) recorded.add(SYSTEMS[key]);
    }
    if (Object.values(snapshot.civ_stats).some((civ) => civ.governance)) recorded.add("Governance");
  }
  const enabled = STATE_SWITCHES.filter((key) => isRecord(world[key])).map((key) => SYSTEMS[key]);
  if (world.campaigns_enabled === true) enabled.push("Campaigns");
  if (world.mutual_aid_enabled === true) enabled.push("Mutual aid");
  if (isRecord(world.governance) && world.governance.enabled === true) enabled.push("Governance");
  if (isRecord(world.contact_ledger)) enabled.push("Contact ledger");
  if (world.community_anchoring === true) enabled.push("Community anchoring");
  if (world.capacity_aware_refugees === true) enabled.push("Capacity-aware refugees");
  return { mode, first, last, enabled, recorded: [...recorded], snapshots: bundle.history.length };
}
