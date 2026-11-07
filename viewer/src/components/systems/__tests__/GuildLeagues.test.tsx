import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { GuildLeagues } from "../GuildLeagues";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { empty, record } from "../../../lib/__tests__/guildLeaguesFixture";
afterEach(cleanup);

function props(livelihoods: Record<string, unknown> | null, history: unknown[] | null = null, turn = 120) {
  const snapshot = { turn, livelihoods: livelihoods === null ? null : { schema_version: 1, ...livelihoods } } as unknown as TurnSnapshot;
  return { bundle: { history: history ?? [snapshot], world_state: {
    regions: [{ name: "Gigur" }, { name: "Duyakhan" }, { name: "Sasa Coast" }, { name: "Vondor" }],
    civilizations: [{ name: "Ashkari" }, { name: "Selurian" }, { name: "Kethani" }, { name: "Vrashni" }] } } as unknown as Bundle,
    snapshot, currentTurn: turn, onSelectRegion: vi.fn() };
}
const row = (table: string, label: RegExp) => within(screen.getByRole("table", { name: table })).getByRole("row", { name: label });

it("shows leagues, their funds, claims on recorded losses and dissolutions", () => {
  render(<GuildLeagues {...props({ guild_leagues: record() })} />);
  expect(screen.getByRole("heading", { name: "Guild leagues · snapshot 120" })).toBeInTheDocument();
  expect(row("Guild leagues at snapshot 120", /^4 \(since 68\)/)).toHaveTextContent("Sasa Coast (city 15) (Selurian)");
  expect(row("Guild leagues at snapshot 120", /^4 \(since 68\)/)).toHaveTextContent("4.409");
  expect(row("League claims at snapshot 120", /levy share/)).toHaveTextContent("118:guild_levy:0");
  expect(screen.getByText(/League 1 dissolves: two members' realms went to war; 2.5 returned/)).toBeInTheDocument();
});

it("keeps disabled, absent, malformed, unobserved and recorded-zero readings distinct", () => {
  render(<GuildLeagues {...props({}, [{ turn: 1 }])} />);
  expect(screen.getByText(/off in this run/)).toBeInTheDocument();
  cleanup();
  const on = { turn: 2, livelihoods: { schema_version: 1, guild_leagues: record() } };
  render(<GuildLeagues {...props({}, [on])} />);
  expect(screen.getByText(/No guild-league record at snapshot 120: unknown, not zero/)).toBeInTheDocument();
  cleanup();
  render(<GuildLeagues {...props({ guild_leagues: record({ stage: "X" }) })} />);
  expect(screen.getByText(/rejected as malformed: unknown guild-leagues schema/)).toBeInTheDocument();
  cleanup();
  render(<GuildLeagues {...props({ guild_leagues: record({ frame: null }) })} />);
  expect(screen.getByText(/Simulation turn 119 was not observed/)).toBeInTheDocument();
  cleanup();
  render(<GuildLeagues {...props({ guild_leagues: record({ frame: empty }) })} />);
  expect(screen.getByText(/recorded zero; 0 candidate pairs, 3 links held/)).toBeInTheDocument();
});

it("the livelihoods tab mounts the panel on the run", () => {
  const extra = { onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectCivilization: vi.fn() };
  render(<LivelihoodsPanel {...{ ...props({ guild_leagues: record() }), ...extra }} />);
  expect(screen.getByRole("region", { name: "Guild leagues" })).toBeInTheDocument();
  expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
});
