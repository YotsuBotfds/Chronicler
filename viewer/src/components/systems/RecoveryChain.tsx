import { useId, useMemo, useState } from "react";
import type { SystemPanelProps, StripRow } from "../../lib/systems";
import {
  budgetLimits, fullestChainRegion, CHAIN_PACKAGES, chainTotals, moreRowsLabel, type ChainPackage, type ChainTotals, farmLabourAway, LINKS, linkState, PACKAGE_INFO,
  readChainSnapshots, regionChain, type Cell, type ChainTurn, type ExpeditionValue, type LinkKey, type LinkState, type StoreValue,
  type WageRow,
} from "../../lib/recoveryChain";
import type { TimberStoreRecord } from "../../lib/timberSupply";
import { StripLegend, TurnStrip } from "./SystemParts";
import { requestEntityHistory } from "../../lib/entityHistoryNavigation";
import { entityKey,entityLabel,type EntityRef } from "../../lib/entityHistory";
import { words } from "./formatters";

const num = (value: number, digits = 2) =>
  (Math.abs(value) < 5e-7 ? 0 : value).toLocaleString(undefined, { maximumFractionDigits: digits });
/** Milli-units as coins (wealth units). */
const coins = (milli: number) => num(milli / 1000, 3);
const pct = (share: number) => `${num(100 * share, 1)}%`;
const ids = (people: number[]) => people.length ? people.join(", ") : "nobody";

const REASON: Record<string, string> = {
  no_timber: "no free timber", no_coins: "treasury short", no_labor: "not enough labour", no_envelope: "no repairs envelope",
  unqualified: "no qualified repairer (reduced rate)", no_people: "no farmer in the region (suspended)",
};
const REFUSAL: Record<string, string> = {
  no_forest: "no forest reachable", too_far: "no forest within the hop limit", forest_depleted: "every forest in range below the stock guard",
  forest_busy: "every healthy forest in range already being cut", no_crew: "nobody at home eligible",
  no_coins: "the treasury cannot pay the expedition",
};
const STATE_LABEL: Record<LinkState, string> = {
  off: "off", unknown: "unknown", none: "nothing recorded", active: "recorded", tradeoff: "tradeoff",
};
/** What a link's tradeoff state is (``linkState``). */
const TRADEOFF_LABEL: Partial<Record<LinkKey, string>> = {
  repair: "stalled", expedition: "need refused", forest: "forest stock drawn down", retail: "people priced out",
};
const COLOR = { active: "#3987e5", tradeoff: "#ec835a", unknown: "#8a8a86" } as const;
const TEXT = { active: "#ffffff", tradeoff: "#0b0b0b", unknown: "#0b0b0b" } as const;
const ROW_PAGE = 25;

/** Why a cell is not known, plainly. */
function missing(cell: Cell<unknown>, brief = false): string {
  if (cell.state === "off") return brief ? "off" : `Off: ${cell.reason}.`;
  if (cell.state === "malformed") return brief ? "unknown (rejected)" : `Unknown, rejected as malformed: ${cell.reason}.`;
  if (cell.state === "unknown") return brief ? "unknown" : `Unknown, not zero: ${cell.reason}.`;
  return "";
}

type Names = { region: (index: number) => string };

// ---------------------------------------------------------------- one link at one snapshot: what, then the tradeoff

function repairText(t: ChainTurn, brief: boolean): string {
  if (t.repair.state !== "known") return missing(t.repair, brief);
  const v = t.repair.value;
  const control = v.mode === "cost_only" ? " (cost-only control: condition never changes)" : "";
  const unmet = (v.unmet ?? []).map((u) => `${u.kind} below the threshold without a project (${words(u.reason)})`);
  if (!v.projects.length) return [brief ? "none" : "No repair project open in the region.", ...(brief ? [] : unmet)].join(" ");
  const receipts = new Map((v.receipts ?? []).map((r) => [r.pid, r]));
  return v.projects.map((p) => {
    const r = receipts.get(p.pid);
    const work = v.receipts === null ? "this turn's work unknown" : !r ? "no work this turn"
      : r.status === "stalled" ? `stalled: ${r.reasons.map((x) => REASON[x] ?? words(x)).join(", ")}`
        : `worked ${num(r.delivered)}${r.reasons.length ? ` (limited: ${r.reasons.map((x) => REASON[x] ?? words(x)).join(", ")})` : ""}`;
    const status = p.closedNow ? `, ${p.status} this turn` : "";
    if (brief) return `#${p.pid} ${p.kind}: ${work}${status}`;
    return `${p.kind === "granary" ? "Granary" : "Workshop"} project #${p.pid} (${p.cause}, opened turn ${p.opened_turn}): `
      + `${num(p.delivered)} of ${num(p.scope)} work done${status}; ${work}.`;
  }).join(brief ? "; " : " ") + (brief ? "" : control);
}

function needText(n: ExpeditionValue["need"]): string {
  if (n === null) return "Timber need unknown (the frame was not recorded).";
  if (n === "none") return "No timber need recorded for the region.";
  const head = `Needs ${num(n.want)} timber: ${num(n.free)} free, ${num(n.in_transit)} on the road, gap ${num(n.gap)}`;
  if (n.status === "refused") return `${head}; refused: ${REFUSAL[n.reason ?? ""] ?? words(n.reason)}.`;
  if (n.status === "launched") return `${head}; launched expedition #${n.eid}.`;
  if (n.status === "expedition") return `${head}; expedition #${n.eid} under way.`;
  return `${head}; supplied.`;
}

function expeditionText(t: ChainTurn, names: Names, brief: boolean): string {
  if (t.expedition.state !== "known") return missing(t.expedition, brief);
  const v = t.expedition.value;
  const receipts = new Map((v.receipts ?? []).map((r) => [r.eid, r]));
  const each = v.expeditions.map((e) => {
    const r = receipts.get(e.eid);
    const turn = v.receipts === null ? "this turn's work unknown" : !r ? (e.launched_turn === t.turn - 1 ? "launched this turn" : "no receipt this turn")
      : `crew of ${r.crew.length} ${r.stage}${r.cut > 0 ? `, cut ${num(r.cut)}` : ""}`;
    const end = e.status === "delivered" ? `delivered ${num(e.delivered)} of ${num(e.cut)} cut`
      : e.status === "returned" ? "came home with nothing to deliver" : e.status === "abandoned" ? `abandoned (${words(e.end_reason)})` : "";
    if (brief) return `#${e.eid} ${end || turn}`;
    return `Expedition #${e.eid} to ${names.region(e.forest)} (${e.hops} ${e.hops === 1 ? "hop" : "hops"}, launched turn ${e.launched_turn}; `
      + `crew ${ids(e.crew)} of ${e.launched_crew.length} launched): ${turn}${end ? `; ${end}` : ""}.`;
  });
  if (brief) {
    const n = v.need;
    const need = n !== null && n !== "none" && n.status === "refused" ? `refused: ${REFUSAL[n.reason ?? ""] ?? words(n.reason)}` : "";
    return [...each, need].filter(Boolean).join("; ") || (n === null ? "unknown" : "none");
  }
  return [needText(v.need), ...each, v.mode === "cost_only" ? "Cost-only control: nobody cuts." : ""].filter(Boolean).join(" ");
}

function forestText(t: ChainTurn, names: Names, brief: boolean): string {
  if (t.forest.state !== "known") return missing(t.forest, brief);
  const v = t.forest.value;
  if (v.slots === null) return brief ? "unknown" : "Unknown, not zero: this turn's expedition receipts were not recorded.";
  if (!v.slots.length) return brief ? "none" : "No expedition from the region was cutting.";
  return v.slots.map((s) => {
    const stock = s.stockBefore === null || s.stockAfter === null ? "stock unknown"
      : `stock ${num(s.stockBefore, 1)} → ${num(s.stockAfter, 1)} of ${s.capacity === null ? "unknown" : num(s.capacity, 1)}`;
    if (brief) return `#${s.eid} cut ${num(s.cut)} at ${names.region(s.forest)}: ${stock}`;
    const l3 = s.l3 ? `L3 account: opening ${num(s.l3.opening, 1)}, cleared ${num(s.l3.cleared)}, extraction ${num(s.l3.extraction)}, `
      + `regrowth ${num(s.l3.regrowth)}, stock ${num(s.l3.stock, 1)} of ${num(s.l3.capacity, 1)}`
      : `L3 account unknown: ${v.l3Missing ?? "the slot is not listed"}`;
    return `Expedition #${s.eid} cut ${num(s.cut)} at ${names.region(s.forest)}, slot ${s.slot}: ${stock}. ${l3}.`;
  }).join(brief ? "; " : " ");
}

function storeText(t: ChainTurn, brief: boolean): string {
  if (t.store.state !== "known") return missing(t.store, brief);
  const v = t.store.value;
  if (v.store === null) return brief ? "unknown" : "Unknown, not zero: the timber frame of the source turn was not recorded.";
  if (v.store === "none") return brief ? "none" : "No timber store in the region.";
  const s = v.store;
  if (brief) return `${num(s.delivered)} in, ${num(s.held)} held, ${num(s.released)} released, ${num(s.closing)} left`;
  return `Store: ${num(s.opening)} at the start, ${num(s.delivered)} delivered, ${num(s.held)} held for repairs, `
    + `${num(s.returned)} returned, ${num(s.released)} released to the stockpile, ${num(s.closing)} left. ${storeSource(s, v.holders)}`;
}

/** Where the repairs' timber came from, as far as the records say. A delivery reaches the store in the expedition's
 * homecoming, after the turn's repairs have taken their timber, so a hold the store did not give came from the
 * region's other free timber. */
function storeSource(s: TimberStoreRecord, holders: StoreValue["holders"]): string {
  if (holders === null) return "Which project held timber this turn is unknown: the repair receipts were not recorded.";
  const list = holders.map((h) => `project #${h.pid} held ${num(h.held)} and used ${num(h.used)}`).join(", ");
  if (s.held <= 0) return holders.length === 0 ? "No project held timber."
    : `The store gave the repairs nothing this turn: ${list}, all from the region's other free timber `
      + "(a delivery reaches the store only after the turn's repairs have taken their timber).";
  if (holders.length === 0) return "No project in the region is recorded holding timber.";
  if (holders.length > 1) return `${list[0].toUpperCase()}${list.slice(1)}: several projects held timber, and the records do not say whose came from the store.`;
  const h = holders[0];
  const rest = h.held - s.held;
  return `Only project #${h.pid} held timber in the region this turn (${num(h.held)}, of which it used ${num(h.used)}), `
    + `so the store's ${num(s.held)} can only have gone to it${rest > 1e-6 ? `; its other ${num(rest)} came from the region's other free timber` : ""}. `
    + "The records still join the store to the repair by region only.";
}

function granaryText(t: ChainTurn, brief: boolean): string {
  if (t.granary.state !== "known") return missing(t.granary, brief);
  const v = t.granary.value;
  const asset = v.asset === null ? "condition unknown" : v.asset === "none" ? "no granary"
    : `condition ${num(v.asset.condition, 3)}${brief ? "" : ` (capacity ${num(v.asset.capacity, 1)})`}`;
  const project = v.project === "off" ? (brief ? "" : "repair projects off")
    : v.project === "unknown" ? "repair project unknown" : v.project === null ? (brief ? "" : "no granary repair project")
      : `project #${v.project.pid} ${pct(v.project.scope > 0 ? Math.min(1, v.project.delivered / v.project.scope) : 1)} done`
        + `${v.project.closedNow ? ` (${v.project.status})` : ""}`;
  const receipt = v.receipt ? `this turn ${num(v.receipt.condition_before, 3)} → ${num(v.receipt.condition_after, 3)}`
    : v.project !== null && typeof v.project === "object" && !v.receiptKnown ? "this turn's work unknown" : "";
  const parts = [asset, project, receipt].filter(Boolean);
  return brief ? parts.join("; ") : `${parts.join("; ")}.`.replace(/^./, (c) => c.toUpperCase());
}

function wageRow(r: WageRow, brief: boolean): string {
  const what = r.source === "pl3_granary" ? `granary crew of project #${r.pid}` : r.source === "rs2_workshop"
    ? `workshop crew of project #${r.pid}` : `woodcutters of expedition #${r.eid}`;
  const paid = r.unpaid ? (r.source === "pl3_granary" ? "unpaid control, no wage" : "unpaid this turn")
    : brief ? coins(r.wagesMilli) : `paid ${coins(r.wagesMilli)} coins`;
  return brief ? `${what} ${paid}` : `${what[0].toUpperCase()}${what.slice(1)} (${ids(r.people)}): ${paid}`;
}

function wagesText(t: ChainTurn, brief: boolean): string {
  if (t.wages.state !== "known") return missing(t.wages, brief);
  const v = t.wages.value;
  const parts: string[] = [];
  let total = 0;
  let complete = true;
  for (const [label, c] of [["PL3 granary crews", v.pl3], ["RS2 workshop crews", v.rs2], ["PL1 woodcutters", v.pl1]] as const) {
    if (c.state === "off") { if (!brief) parts.push(`${label}: off.`); continue; }
    if (c.state !== "known") { complete = false; parts.push(brief ? `${label}: unknown` : `${label}: ${missing(c)}`); continue; }
    total += c.value.rows.reduce((a, r) => a + r.wagesMilli, 0);
    const truncated = "truncated" in c.value && c.value.truncated ? " (the frame is at its row limit: possibly incomplete)" : "";
    if (truncated) complete = false;
    if (c.value.rows.length) parts.push(...c.value.rows.map((r) => wageRow(r, brief) + (brief ? "" : `.${truncated}`)));
    else if (!brief) parts.push(`${label}: none in the region.${truncated}`);
    if ("noCrew" in c.value) {
      for (const n of c.value.noCrew) parts.push(brief ? `project #${n.pid}: no crew formed`
        : `Granary project #${n.pid}: no crew formed (${n.planned > 0 ? "no free adult farmer" : "no work planned"}), so nobody was paid.`);
      if (!brief) for (const w of c.value.workshops) parts.push(`PL3 workshop crew of project #${w.pid} (${ids(w.people)}): `
        + `${num(w.farmTime)} farmer-turns from farming; its wages are on the RS2 receipt.`);
    }
  }
  if (brief) {
    if (!parts.length) return "none";
    // An unknown source leaves the total unknown: at least what the known receipts paid.
    const head = complete ? `${coins(total)} coins` : total > 0 ? `at least ${coins(total)} coins` : "unknown";
    return `${head} (${parts.join("; ")})`;
  }
  return `${parts.join(" ")} ${complete ? `Total paid in the region: ${coins(total)} coins.` : "The region's total is unknown: a source is not known."}`;
}

function retailText(t: ChainTurn, brief: boolean): string {
  if (t.retail.state !== "known") return missing(t.retail, brief);
  const v = t.retail.value;
  if (v.frame === null) return brief ? "not a pilot" : `Not a pilot region this turn (boundary ${words(v.boundary)}).`;
  const p = v.frame.provisioning;
  if (p === null && v.mode === "record_only") return brief ? "pilot (record-only control: provisions no one)"
    : `Pilot region since turn ${v.frame.opened_turn} (record-only control): the control provisions no one by design, so nobody buys or sells food here.`;
  if (p === null) return brief ? "pilot, not provisioned (unknown)"
    : `Pilot region since turn ${v.frame.opened_turn}; not provisioned this turn: purchases unknown, not zero.`;
  const bought = `${p.buying_households} households paid ${coins(p.paid_milli)} coins for ${num(p.sold_milli / 1000, 3)} food`
    + `${p.price_milli ? ` at ${coins(p.price_milli)} a ration` : ""}`;
  if (brief) return `pilot: ${p.persons} people, paid ${coins(p.paid_milli)} coins`;
  const matches = v.sampled === 0 ? "None of the person sample is in this region this turn."
    : v.matches.length === 0 ? `None of the ${v.sampled} people sampled here was paid in the region by this snapshot or is in a paid worker's household.`
      : `By id (ration and status only, not who paid; a worker counts from the snapshot of their first wage in the region): `
        + `${v.matches.map((m) => `${m.agentId}${m.who === "household" ? ` (household of ${m.worker})` : ""} `
        + `${words(m.status)} at ${num(m.ration, 3)} of ${num(m.fairShare, 3)}, paid since ${m.since}`).join("; ")}.`;
  return `Pilot region since turn ${v.frame.opened_turn} (${words(v.mode)}, boundary ${words(v.boundary)}): ${p.persons} people `
    + `(${p.children} children) in ${p.households} households provisioned; ${bought}. ${matches}`;
}

function remittanceText(t: ChainTurn, brief: boolean): string {
  if (t.remittances.state !== "known") return missing(t.remittances, brief);
  const v = t.remittances.value;
  const control = v.mode === "record_only" ? " (record-only control: nothing is sent)" : "";
  if (!v.row || v.row.inflow_milli === 0) return brief ? "none" : `Nothing came in this turn${control}.`;
  return brief ? `${coins(v.row.inflow_milli)} coins in` : `${coins(v.row.inflow_milli)} coins came in to ${v.row.recipients} recipients${control}.`;
}

/** The tradeoffs beside a link; an empty list when the link records none. */
function tradeoffs(t: ChainTurn, key: LinkKey, brief: boolean): string[] {
  const budget = budgetLimits(t).filter((b) => b.link === key).map((b) => `budget: ${b.text}`);
  const away = farmLabourAway(t);
  switch (key) {
    case "repair": return budget;
    case "expedition": {
      const out = [...budget];
      if (typeof away.pl1 === "number" && away.pl1 > 0) {
        const food = t.food.state !== "known" ? (brief ? "" : ` (the region's food: ${missing(t.food, true)})`)
          : t.food.value.sufficiency === null ? (brief ? "" : " (the region was not scarce for food allocation)")
            : ` (food sufficiency ${num(t.food.value.sufficiency, 3)})`;
        out.push(`farm labour away with the woodcutters: ${num(away.pl1)} farmer-turns${food}`);
      }
      return out;
    }
    case "forest": {
      if (t.forest.state !== "known" || !t.forest.value.slots) return [];
      return t.forest.value.slots.flatMap((s) => {
        if (s.stockBefore === null || s.stockAfter === null || !s.capacity) return [];
        const change = s.stockAfter - s.stockBefore;
        return [`forest at ${pct(s.stockAfter / s.capacity)} of capacity, ${change < 0 ? `drawn down ${num(-change, 3)}`
          : `up ${num(change, 3)} (regrowth outweighed the cut)`}`];
      });
    }
    case "wages": {
      const out = [...budget];
      if (typeof away.granary === "number" && away.granary > 0) out.push(`farm labour taken by PL3 granary crews: ${num(away.granary)} farmer-turns`);
      if (typeof away.workshop === "number" && away.workshop > 0) out.push(`farm labour taken by PL3 workshop crews: ${num(away.workshop)} farmer-turns`);
      if (away.granary === null && !brief) out.push("farm labour taken by PL3 crews: unknown");
      return out;
    }
    case "retail": {
      if (t.retail.state !== "known" || !t.retail.value.frame?.provisioning) return [];
      const p = t.retail.value.frame.provisioning;
      if (p.priced_out_persons === 0) return brief ? [] : ["nobody priced out"];
      return [`priced out: ${p.priced_out_persons} people (${p.priced_out_children} children) in ${p.priced_out_households} households`];
    }
    default: return [];
  }
}

function linkText(t: ChainTurn, key: LinkKey, names: Names, brief: boolean): string {
  switch (key) {
    case "repair": return repairText(t, brief);
    case "expedition": return expeditionText(t, names, brief);
    case "forest": return forestText(t, names, brief);
    case "store": return storeText(t, brief);
    case "granary": return granaryText(t, brief);
    case "wages": return wagesText(t, brief);
    case "retail": return retailText(t, brief);
    default: return remittanceText(t, brief);
  }
}

// ---------------------------------------------------------------- the view

/** "at least" a run total when some of its snapshots are unknown. */
const atLeast = (text: string, unknownSnapshots: number) => unknownSnapshots > 0 ? `at least ${text}` : text;

/** The region's run in one sentence: each total over known snapshots, "at least" where some are unknown. */
function summary(t: ChainTotals, on: Record<ChainPackage, boolean>, links: ReadonlyArray<{ key: LinkKey; title: string }>): string {
  const u = t.unknown;
  const parts: string[] = [];
  if (on.repair_projects) parts.push(`repair projects stalled on ${atLeast(`${t.stalls} project-snapshots`, u.repair)} `
    + `(${t.stallsNoTimber} for want of timber)`);
  if (on.timber_supply) parts.push(`${t.expeditions.length} expeditions from the region${t.expeditions.length ? ` (#${t.expeditions.join(", #")})` : ""}, `
    + `${atLeast(num(t.delivered), t.deliveredUnknown)} timber delivered home`);
  const sources = [["PL1 woodcutters", on.timber_supply, t.farmAway.pl1], ["PL3 granary crews", on.recovery_crews, t.farmAway.granary],
    ["PL3 workshop crews", on.recovery_crews, t.farmAway.workshop]] as const;
  if (sources.some(([, isOn]) => isOn)) {
    const total = sources.reduce((a, [, isOn, v]) => a + (isOn ? v : 0), 0);
    parts.push(`${atLeast(num(total), t.farmAwayUnknown)} farmer-turns taken from farming (`
      + `${sources.map(([label, isOn, v]) => `${label} ${isOn ? num(v) : "off"}`).join(", ")})`);
  }
  if (t.conditionFirst !== null) parts.push(`granary condition ${num(t.conditionFirst, 3)} → ${num(t.conditionLast ?? 0, 3)}`);
  const w = t.wagesMilli;
  parts.push(links.some((l) => l.key === "wages")
    ? `wages ${atLeast(`${coins(w.pl3 + w.rs2 + w.pl1)} coins`, u.wages)} to ${t.paidPeople} people paid by id`
      + ` (PL3 granary crews ${on.recovery_crews ? coins(w.pl3) : "off"}, RS2 workshop crews ${on.repair_projects ? coins(w.rs2) : "off"},`
      + ` PL1 woodcutters ${on.timber_supply ? coins(w.pl1) : "off"})`
    : "no wages recorded (every wage source is off)");
  if (on.household_retail) parts.push(`households paid ${atLeast(`${coins(t.purchasesMilli)} coins`, u.retail)} for food on `
    + `${t.purchaseSnapshots} snapshots, with people priced out on ${t.pricedOutSnapshots}`);
  if (on.remittances) parts.push(`${atLeast(`${coins(t.remittanceMilli)} coins`, u.remittances)} of remittances in`);
  const unknownLinks = links.filter((l) => u[l.key] > 0);
  return `${parts.join("; ")}.${unknownLinks.length ? ` Totals count known snapshots only; unknown at, wholly or in part: `
    + `${unknownLinks.map((l) => `${l.title} ${u[l.key]}`).join(", ")}.` : ""}`;
}

/** A link's strip: runs of the same state over consecutive turns (a gap in the history ends a run). */
function stripSegments(turns: readonly ChainTurn[], key: LinkKey): StripRow["segments"] {
  const out: Array<StripRow["segments"][number] & { state: keyof typeof COLOR }> = [];
  for (const t of turns) {
    const s = linkState(t, key);
    if (s !== "active" && s !== "tradeoff" && s !== "unknown") continue;
    const last = out[out.length - 1];
    if (last && last.state === s && last.end === t.turn) last.end = t.turn + 1;
    else out.push({ state: s, start: t.turn, end: t.turn + 1, color: COLOR[s], textColor: TEXT[s], label: "" });
  }
  return out.map(({ state, ...seg }) => ({ ...seg,
    label: `${state === "tradeoff" ? TRADEOFF_LABEL[key] ?? STATE_LABEL[state] : STATE_LABEL[state]}, ${seg.end - seg.start === 1 ? `snapshot ${seg.start}` : `snapshots ${seg.start}-${seg.end - 1}`}` }));
}

/**
 * One region's recovery chain over the run, composed from the packages' own
 * readers (lib/recoveryChain). Off packages say off, unknown frames say
 * unknown, and each link says whether it is joined by id or only by region.
 */
export function RecoveryChain({ bundle, snapshot, currentTurn, onSeek, onSelectRegion, selectedRegion }: SystemPanelProps) {
  const regions = useMemo(() => bundle.world_state.regions ?? [], [bundle]);
  const read = useMemo(() => readChainSnapshots(bundle), [bundle]);
  const fullest = useMemo(() => fullestChainRegion(read.snapshots, regions.length), [read, regions.length]);
  const [chosen, setChosen] = useState<number | null>(null);
  const [everySnapshot, setEverySnapshot] = useState(false);
  const [limit, setLimit] = useState(ROW_PAGE);
  const id = useId();
  const fromMap = selectedRegion ? regions.findIndex((r) => r.name === selectedRegion) : -1;
  const region = chosen !== null && chosen < regions.length ? chosen : fromMap >= 0 ? fromMap : fullest;
  const turns = useMemo(() => regionChain(read.snapshots, region), [read, region]);
  const totals = useMemo(() => chainTotals(turns), [turns]);
  const names: Names = { region: (index) => regions[index]?.name ?? `Region ${index}` };
  const name = names.region(region);
  const at = snapshot?.turn ?? currentTurn;
  const now = turns.find((t) => t.turn === at) ?? null;
  const named=new Map<string,EntityRef>();
  const remember=(kind:EntityRef["kind"],id:number)=>{const entity={kind,id};named.set(entityKey(entity),entity);};
  remember("region",region);
  if(now?.repair.state==="known")now.repair.value.projects.forEach(p=>remember("project",p.pid));
  if(now?.expedition.state==="known")now.expedition.value.expeditions.forEach(e=>remember("expedition",e.eid));
  if(now?.wages.state==="known")for(const cell of [now.wages.value.pl3,now.wages.value.rs2,now.wages.value.pl1])if(cell.state==="known")cell.value.rows.forEach(row=>row.people.forEach(id=>remember("person",id)));
  if(now?.retail.state==="known")now.retail.value.matches.forEach(p=>{remember("person",p.agentId);remember("household",p.household);});
  const links = useMemo(() => LINKS.filter((l) => turns.some((t) => linkState(t, l.key) !== "off")), [turns]);
  const offLinks = LINKS.filter((l) => !links.includes(l));
  const on = CHAIN_PACKAGES.filter((k) => read.on[k]);
  const off = CHAIN_PACKAGES.filter((k) => !read.on[k]);

  const strip: StripRow[] = useMemo(() => links.map((l) => ({ id: l.key, label: l.title,
    segments: stripSegments(turns, l.key) })), [links, turns]);

  // The turn table is the strip's text form: every snapshot the strip draws (recorded, tradeoff or unknown) is listed.
  const shown = turns.filter((t) => everySnapshot || t.turn === at
    || links.some((l) => ["active", "tradeoff", "unknown"].includes(linkState(t, l.key))));
  const hidden = turns.length - shown.length;
  const first = turns[0]?.turn;
  const last = turns[turns.length - 1]?.turn;

  return <section className="systems-section" aria-label="Recovery chain">
    <h3>Recovery chain · snapshot {at}</h3>
    <p className="systems-note">Simulation turn {at - 1}. One region&apos;s chain of productive recovery: a repair project needs timber,
      the region sends a paid woodcutting crew, the timber reaches the repair, named workers are paid and the region&apos;s households
      buy food, with the tradeoffs beside each link (farm labour away, the forest drawn down, budgets short, people priced out). Each
      link is read from its own record; &quot;Joined by&quot; says whether the records join it to the chain by stable id or only by
      region. Unknown is never shown as zero. Money in coins, timber in goods, labour in farmer-turns.</p>
    <p className="systems-note">On in this run: {on.map((k) => PACKAGE_INFO[k].label).join(", ") || "none"}.
      {off.length ? ` Off: ${off.map((k) => `${PACKAGE_INFO[k].label} (${PACKAGE_INFO[k].flag})`).join(", ")}.` : " Nothing in the chain is off."}</p>
    <div className="phase75-field recovery-chain-field">
      <label htmlFor={`${id}-region`}>Region</label>
      <select id={`${id}-region`} value={region} onChange={(event) => { setChosen(Number(event.target.value)); setLimit(ROW_PAGE); }}>
        {regions.map((r, index) => <option key={index} value={index}>{r.name}{index === fullest ? " (fullest chain)" : ""}</option>)}
      </select>
    </div>
    <details><summary>Linked histories of identities recorded in this chain</summary><div className="systems-inline-list">{[...named.values()].map(entity=><button type="button" className="systems-link" key={entityKey(entity)} onClick={()=>requestEntityHistory(entity,at)}>History: {entityLabel(entity)}</button>)}</div><p className="systems-note">Each identity link opens saved observations. Regional co-occurrence is not an individual causal history.</p></details>
    <p className="systems-note">
      <button type="button" className="systems-link" onClick={() => onSelectRegion(name)}>{name}</button>
      {turns.length ? ` over snapshots ${first}-${last}: ${summary(totals, read.on, links)}` : " no snapshots are recorded."}
    </p>
    {now === null
      ? <p className="systems-note">No snapshot of this run is dated {at}; the chain at this turn is unknown.</p>
      // Explicit roles: at phone width the rows are restyled as blocks, which can drop the table's native semantics.
      : <div className="systems-table-wrap"><table role="table" className="systems-table recovery-chain-now" aria-label={`Recovery chain in ${name} at snapshot ${at}`}>
        <thead role="rowgroup"><tr role="row"><th role="columnheader">Link</th><th role="columnheader">At snapshot {at}</th>
          <th role="columnheader">Joined by</th><th role="columnheader">Tradeoff</th></tr></thead>
        <tbody role="rowgroup">{LINKS.map((l) => {
          const trade = tradeoffs(now, l.key, false);
          return <tr role="row" key={l.key} data-link={l.key}>
            <th role="rowheader" scope="row">{l.title}</th>
            <td role="cell" data-label={`At snapshot ${at}`}>{linkText(now, l.key, names, false)}</td>
            <td role="cell" data-label="Joined by">{l.join === "id" ? "Stable id" : "Region only"}: {l.joined.replace(/^by (id|region only): /, "")}</td>
            <td role="cell" data-label="Tradeoff">{trade.length ? trade.join("; ") : "—"}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    {links.length > 0 && <>
      <TurnStrip rows={strip} firstTurn={first ?? 0} endTurn={(last ?? 0) + 1} currentTurn={at}
        label={`Recovery chain in ${name} over snapshots`} emptyText="Nothing recorded." onSeek={onSeek} />
      <StripLegend items={[{ label: "Recorded", color: COLOR.active }, { label: "Stall, refusal, priced out or forest drawn down", color: COLOR.tradeoff },
        { label: "Unknown", color: COLOR.unknown }]} />
      <p className="systems-note">The strip is drawn from the table below, which is its text form.
        {offLinks.length ? ` Links off in this run are left out: ${offLinks.map((l) => l.title).join(", ")}.` : ""}</p>
    </>}
    <label className="systems-inline-list"><input type="checkbox" checked={everySnapshot}
      onChange={(event) => { setEverySnapshot(event.target.checked); setLimit(ROW_PAGE); }} /> Show every snapshot</label>
    <p className="systems-note">{everySnapshot ? `All ${turns.length} snapshots are listed.`
      : `${shown.length} of ${turns.length} snapshots are listed: those where a link recorded something or is unknown, and the current one. ${hidden} where every link recorded nothing are hidden.`}</p>
    <div className="systems-table-wrap"><table className="systems-table recovery-chain-turns" aria-label={`Recovery chain in ${name} over snapshots`}>
      <thead><tr><th>Snapshot</th>{links.map((l) => <th key={l.key}>{l.title}</th>)}<th>Tradeoffs</th></tr></thead>
      <tbody>{shown.slice(0, limit).map((t) => {
        const trade = links.flatMap((l) => tradeoffs(t, l.key, true));
        return <tr key={t.turn} aria-current={t.turn === at ? "true" : undefined}>
          <th scope="row"><button type="button" className="systems-link" onClick={() => onSeek(t.turn)}
            aria-label={`Seek to snapshot ${t.turn}`}>{t.turn}</button></th>
          {links.map((l) => <td key={l.key}>{linkText(t, l.key, names, true)}</td>)}
          <td>{trade.length ? trade.join("; ") : "—"}</td>
        </tr>;
      })}</tbody>
    </table></div>
    {shown.length > limit && <button type="button" className="phase75-ghost-button systems-more" onClick={() => setLimit(limit + ROW_PAGE)}>
      {moreRowsLabel(shown.length - limit, ROW_PAGE)}</button>}
  </section>;
}
