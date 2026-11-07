import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { ReformServices } from "../ReformServices";
import { empty, record } from "../../../lib/__tests__/reformServicesFixture";
afterEach(cleanup);

function props(livelihoods: Record<string, unknown> | null, history: unknown[] | null = null, turn = 86) {
  const snapshot = { turn, livelihoods: livelihoods === null ? null : { schema_version: 1, ...livelihoods } } as unknown as TurnSnapshot;
  return { bundle: { history: history ?? [snapshot], world_state: {
    regions: [{ name: "Crystalfen" }, { name: "Sapphire Coast" }, { name: "Stormbreak" }, { name: "Verdant Plains" }],
    civilizations: [{ name: "Vrashni" }, { name: "Ashkari" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const row = (table: string, label: RegExp) => within(screen.getByRole("table", { name: table })).getByRole("row", { name: label });

it("shows funds, purchases paid by id and bounded deliveries by region", () => {
  render(<ReformServices {...props({ reform_services: record() })} />);
  expect(screen.getByRole("heading", { name: "Poor relief services · snapshot 86" })).toBeInTheDocument();
  expect(row("Relief funds at snapshot 86", /Ashkari/)).toHaveTextContent("7.561");
  expect(row("Relief purchases at snapshot 86", /Verdant Plains/)).toHaveTextContent("0.484");
  expect(row("Relief deliveries at snapshot 86", /Verdant Plains/)).toHaveTextContent("at most 1.752 (no lower bound: gross outbound food is unobserved)");
  expect(screen.getByText(/Historical lower estimates are not established delivery evidence/)).toBeInTheDocument();
  expect(row("Relief deliveries at snapshot 86", /Stormbreak/)).toHaveTextContent("at most 0.004 (no lower bound");
  expect(screen.getByText(/Recipients are not named/)).toBeInTheDocument();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings distinct", () => {
  render(<ReformServices {...props({}, [{ turn: 1 }])} />);
  expect(screen.getByText(/off in this run/)).toBeInTheDocument();
  cleanup();
  const on = { turn: 2, livelihoods: { schema_version: 1, reform_services: record() } };
  render(<ReformServices {...props({}, [on])} />);
  expect(screen.getByText(/No poor-relief services record at snapshot 86: unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<ReformServices {...props({ reform_services: record({ stage: "X" }) })} />);
  expect(screen.getByText(/rejected as malformed: unknown relief-services schema/)).toBeInTheDocument();
  cleanup();
  render(<ReformServices {...props({ reform_services: record({ frame: null }) })} />);
  expect(screen.getByText(/Simulation turn 85 was not observed.*unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<ReformServices {...props({ reform_services: record({ frame: empty }) })} />);
  expect(screen.getByText(/Nothing moved this turn.*recorded zero/)).toBeInTheDocument();
  cleanup();
  render(<ReformServices {...props({ reform_services: record({ mode: "cost_only", frame: empty }) })} />);
  expect(screen.getByText(/The cost-only control/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the panel on the run, also where a snapshot lacks it", () => {
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...{ ...props({ reform_services: record() }), ...extra }} />);
  expect(screen.getByRole("region", { name: "Poor relief services" })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
  cleanup();
  const on = { turn: 2, livelihoods: { schema_version: 1, reform_services: record() } };
  render(<LivelihoodsPanel {...{ ...props({ food_allocation: null }, [on]), ...extra }} />);
  expect(screen.getByText(/No poor-relief services record at snapshot 86/)).toBeInTheDocument();
});
