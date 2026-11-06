import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import v2 from "../../../__fixtures__/household_retail_v2_records.json";
import type { Bundle } from "../../../types";
import { HouseholdRetail } from "../HouseholdRetail";
import { snapOf } from "../../../lib/__tests__/householdRetailFixture";
afterEach(cleanup);

/* eslint-disable @typescript-eslint/no-explicit-any */
type Natural = { run: string; region_count: number; livelihoods: Record<string, any> };
const SNAPSHOTS = (v2 as unknown as { snapshots: Natural[] }).snapshots;
const CIVS = ["Ashkari Nomads", "Dorrathi Clans", "Kethani Empire", "Selurian Republic"];
function props(run: string, change?: (x: Record<string, any>) => void, history: unknown[] = []) {
  const s = SNAPSHOTS.find((n) => n.run === run)!;
  const x = structuredClone(s.livelihoods.household_retail);
  change?.(x);
  const regions = Array.from({ length: s.region_count }, (_, i) => ({ name: `Region ${i}` }));
  return { bundle: { world_state: { regions, civilizations: CIVS.map((name) => ({ name })) }, history } as unknown as Bundle,
    snapshot: snapOf(x), currentTurn: 1, onSelectRegion: vi.fn() };
}
const table = (name: string | RegExp) => within(screen.getByRole("table", { name }));
const note = (text: RegExp) => screen.getByText(text, { selector: "p" });
const lifetime = (label: RegExp) => table(/^Household retail to snapshot/).getByRole("row", { name: label });

describe("household retail panel: rules version 2 evidence", () => {
  it("shows this turn's war events with their cause, actor and victim, and lifetime losses by cause", () => {
    render(<HouseholdRetail {...props("war3")} />);
    const rows = table("War losses of owned food at snapshot 3").getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["Region 1siege turnDorrathi Clans (besieger)Ashkari Nomads2.183",
      "Region 1occupation startDorrathi Clans (occupier)Ashkari Nomads2.474"]);
    expect(lifetime(/^War loss: conquest · siege · occupation/)).toHaveTextContent("0 · 4.636 · 2.474 (4)");
    expect(screen.queryByText(/conquest loss/)).toBeNull();
    // Version 2 keeps no requisition exemption: not applicable, never a recorded zero.
    expect(lifetime(/^Claims refused/)).toHaveTextContent("not applicable (rules version 2 applies sieges and occupations to owned food)");
    expect(note(/Retail rules version 2: each conquest, siege turn and occupation start reaches owned food once/)).toBeInTheDocument();
  });

  it("shows the record-only control's war exposure as events with nothing held", () => {
    render(<HouseholdRetail {...props("ro3")} />);
    const rows = table("War losses of owned food at snapshot 3").getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["Region 1siege turnDorrathi Clans (besieger)Ashkari Nomadsnone (nothing held)",
      "Region 1occupation startDorrathi Clans (occupier)Ashkari Nomadsnone (nothing held)"]);
    expect(screen.queryByRole("table", { name: /Household groups/ })).toBeNull();
  });

  it("shows household groups with recorded zeros as zeros and unknowns as Unknown with their reasons", () => {
    render(<HouseholdRetail {...props("pw7")} />);
    const groups = "Household groups at snapshot 35";
    const crew = table(groups).getByRole("row", { name: /^Crew members/ });
    expect(crew.textContent).toMatch(/^Crew members \(named on a paid or unpaid crew this turn\)Unknown0/);   // persons unknown (deaths), none priced out
    expect(crew).toHaveTextContent(/3\.941$/);                                                            // crew wages, exact
    expect(table(groups).getAllByRole("row")).toHaveLength(6);
    expect(note(/^Not attributable exactly: .*Region 11 persons: the Phase 2 roster lists 49, the tick provisioned 48/)).toBeInTheDocument();
    expect(screen.getByText(/Retail rules version 2/)).toBeInTheDocument();
  });

  it("says household groups are not recorded under rules version 1, and that a record without them is unknown", () => {
    render(<HouseholdRetail {...props("v1pw7")} />);
    expect(note(/^Household groups .* are recorded under retail rules version 2 only; this record is version 1/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /War losses/ })).toBeNull();
    expect(lifetime(/^Decay · storage overflow · conquest loss/)).toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...props("pw7", (x) => { for (const r of x.regions) delete r.cohorts; })} />);
    expect(note(/^This run recorded no household groups/)).toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...props("pw7", (x) => { x.regions.find((r: any) => r.region === 17).cohorts.groups.crew.persons += 1; })} />);
    expect(note(/^Household groups rejected as malformed: region 17: the groups' persons do not add up to the region's/)).toBeInTheDocument();
  });

  it("names the schedule boundary and its digest, and the storage-cap counter", () => {
    const p = props("sched7");
    render(<HouseholdRetail {...p} />);
    const sha = SNAPSHOTS.find((n) => n.run === "sched7")!.livelihoods.household_retail.schedule.sha256 as string;
    expect(note(new RegExp(`Pilot boundary: schedule: the regions of a frozen schedule .* \\(first-turn schedule, each region from its opening turn: approximate, it cannot replay a region its source closed; 14 regions, schedule sha256 ${sha.slice(0, 12)}\\); a region leaves only when it has no controller`)))
      .toBeInTheDocument();
    expect(lifetime(/^Grain above the storage cap, lost before granaries buy/)).toBeInTheDocument();
  });

  it("says an interval schedule enrolls each region only within its intervals, and that an interval's end closes it", () => {
    // Constructed (labelled): the fixture's first-turn schedule rewritten as exact intervals.
    render(<HouseholdRetail {...props("sched7", (x) => {
      x.schedule.turns = Object.fromEntries(Object.entries(x.schedule.turns as Record<string, number>)
        .map(([r, t], i) => [r, i === 0 ? [[t, t + 5], [t + 9, null]] : [[t, null]]]));
    })} />);
    expect(note(/\(exact intervals: each region only within its intervals; 14 regions, schedule sha256 [0-9a-f]{12}\); a region leaves when it has no controller or its schedule interval ends/))
      .toBeInTheDocument();
    expect(screen.queryByText(/first-turn schedule/)).toBeNull();
  });

  it("says when the rolling log kept fewer of this turn's war events than happened (constructed)", () => {
    // Constructed (labelled): the previous snapshot's counter says 3 war events happened this turn,
    // the log kept 2 rows.
    const war3 = SNAPSHOTS.find((n) => n.run === "war3")!.livelihoods.household_retail;
    const previous = structuredClone(war3);
    previous.source_turn = 1;
    previous.counters.war_events = war3.counters.war_events - 3;
    previous.regions = null; previous.money = null; previous.income = null; previous.sample = null; previous.sample_dropped = null;
    previous.log = previous.log.filter((r: any) => r.turn <= 1);
    render(<HouseholdRetail {...props("war3", undefined, [snapOf(previous)])} />);
    expect(note(/^3 war events in pilot regions this turn; the rolling log \(the last 64 records\) kept 2 rows/)).toBeInTheDocument();
    cleanup();
    // Without the previous record: a log that dropped records of this turn says so.
    render(<HouseholdRetail {...props("war3", (x) => { x.log = x.log.filter((r: any) => r.turn === 2); x.log_dropped = 5; })} />);
    expect(note(/^The rolling log \(the last 64 records\) dropped records of this turn/)).toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...props("war3")} />);
    expect(screen.queryByText(/rolling log/)).toBeNull();
  });

  it("shows the storage-cap counters as not recorded in records written before them", () => {
    const row = /^Grain above the storage cap, lost before granaries buy/;
    render(<HouseholdRetail {...props("pw7")} />);                       // A2R: no pro-rata commons share yet
    expect(lifetime(row)).toHaveTextContent("0 · not recorded (written before the pro-rata cut)");
    cleanup();
    render(<HouseholdRetail {...props("pw7", (x) => { delete x.opened_turn; })} />);   // A5: before the cut
    expect(lifetime(row)).toHaveTextContent("not recorded (written before the storage-cap cut)");
    cleanup();
    render(<HouseholdRetail {...props("pw7", (x) => {
      x.intervals = {}; x.counters.owned_grain_above_cap_milli = 1500; x.counters.commons_grain_above_cap_milli = 250;
    })} />);
    expect(lifetime(row)).toHaveTextContent(/1\.5 · 0\.25$/);
  });
});
