import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { AttributionRecords } from "../AttributionRecords";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { empty, record } from "../../../lib/__tests__/attributionRecordsFixture";
afterEach(cleanup);

function props(livelihoods: Record<string, unknown> | null, history: unknown[] | null = null, turn = 10) {
  const snapshot = { turn, livelihoods: livelihoods === null ? null : { schema_version: 1, ...livelihoods } } as unknown as TurnSnapshot;
  return { bundle: { history: history ?? [snapshot], world_state: { regions: [{ name: "Oldmere" }, { name: "Ashford Vale" },
    { name: "Dun" }], civilizations: [{ name: "Ashkari" }, { name: "Selurian" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const row = (table: string, label: RegExp) => within(screen.getByRole("table", { name: table })).getByRole("row", { name: label });

it("shows deaths by cause with their actors, seizures, burdens and identity reuse", () => {
  render(<AttributionRecords {...props({ attribution_records: record() })} />);
  expect(screen.getByRole("heading", { name: "Attribution records · snapshot 10" })).toBeInTheDocument();
  expect(screen.getByText(/combat 4, attrition 0, war drain 0, natural 2/)).toBeInTheDocument();
  expect(screen.getByText(/no note was dropped \(every army's counter closes\)/)).toBeInTheDocument();
  expect(screen.getByText(/moved nothing \(not in the table\): Occupation plunder 2/)).toBeInTheDocument();
  expect(row("Soldiers' deaths at snapshot 10", /battle \(field\)/)).toHaveTextContent("Selurian");
  expect(row("Soldiers' deaths at snapshot 10", /natural death while enlisted/)).toHaveTextContent("no actor (at war with Selurian)");
  expect(row("Granary seizures at snapshot 10", /Dun/)).toHaveTextContent("the granary books still name Selurian");
  expect(row("Burdens at snapshot 10", /Occupation plunder/)).toHaveTextContent("minted (credited, taken from no one)");
  expect(row("Burdens at snapshot 10", /City dues to the lord \(own realm\)/)).toHaveTextContent("1.25 treasury");
  expect(screen.getByText(/Selurian \(index 1\): restored/)).toBeInTheDocument();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings distinct", () => {
  render(<AttributionRecords {...props({}, [{ turn: 1 }])} />);
  expect(screen.getByText(/off in this run/)).toBeInTheDocument();
  cleanup();
  const on = { turn: 2, livelihoods: { schema_version: 1, attribution_records: record() } };
  render(<AttributionRecords {...props({}, [on])} />);
  expect(screen.getByText(/No attribution record at snapshot 10: unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<AttributionRecords {...props({ attribution_records: record({ stage: "X" }) })} />);
  expect(screen.getByText(/rejected as malformed: unknown attribution-records schema/)).toBeInTheDocument();
  cleanup();
  render(<AttributionRecords {...props({ attribution_records: record({ frame: null }) })} />);
  expect(screen.getByText(/Simulation turn 9 was not observed.*unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<AttributionRecords {...props({ attribution_records: record({ frame: empty }) })} />);
  expect(screen.getByText(/Nothing was attributed this turn.*granaries are off: seizures unknown, not zero.*recorded zero/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the records on the run, also where a snapshot lacks them", () => {
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...{ ...props({ attribution_records: record() }), ...extra }} />);
  expect(screen.getByRole("region", { name: "Attribution records" })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
  cleanup();
  const on = { turn: 2, livelihoods: { schema_version: 1, attribution_records: record() } };
  render(<LivelihoodsPanel {...{ ...props({ food_allocation: null }, [on]), ...extra }} />);
  expect(screen.getByText(/No attribution record at snapshot 10/)).toBeInTheDocument();
});
