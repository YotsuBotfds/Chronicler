import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { transactionFixture } from "../../../__fixtures__/transactionHistory";
import type { Bundle } from "../../../types";
import { Transactions } from "../Transactions";

afterEach(cleanup);
function props(name: Parameters<typeof transactionFixture>[0] = "hybrid-public", index = 0) {
  const history = transactionFixture(name);
  return { bundle: { history, world_state: { transaction_receipts: { rows: ["future"], public_purchases: { buyer_paid: 999 } } } } as unknown as Bundle,
    snapshot: history[index], currentTurn: history[index].turn,
    onSeek: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn(), onSelectEvent: vi.fn() };
}

describe("recorded Transactions inspector", () => {
  it("shows actual public-only foreign payment legs despite absent native substrate", () => {
    const p = props("public-foreign"); render(<Transactions {...p} />);
    expect(screen.getByText(/No usable native mobility frame at snapshot 31/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Public purchases at snapshot 31" });
    const cells = within(table).getAllByRole("cell");
    expect(cells[4]).toHaveTextContent("8 / 7.6 / 0.4");
    expect(cells[5]).toHaveTextContent("1"); expect(cells[6]).toHaveTextContent("1"); expect(cells[7]).toHaveTextContent("0");
    fireEvent.click(within(table).getByRole("button", { name: "Verdant Plains" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Verdant Plains");
    expect(within(table).getByText(/Buyer projected treasury: 200 → 199; foreign seller: 0 → 1/)).toBeInTheDocument();
    expect(p.onSelectEvent).not.toHaveBeenCalled();
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it.each(["public-own-market", "public-same-realm"] as const)("shows domestic producer sink without a private cash credit: %s", (name) => {
    render(<Transactions {...props(name)} />);
    const cells = within(screen.getByRole("table", { name: "Public purchases at snapshot 31" })).getAllByRole("cell");
    expect(cells[5]).toHaveTextContent("1"); expect(cells[6]).toHaveTextContent("0"); expect(cells[7]).toHaveTextContent("1");
    expect(screen.getByText(/A producer sink is not credited to a private merchant account/)).toBeInTheDocument();
  });

  it("keeps actual shared stock and virtual shadow rows distinct", () => {
    const view = render(<Transactions {...props("native-shadow")} />);
    expect(within(screen.getByRole("table", { name: "Native transactions at snapshot 1" })).getAllByText("Virtual shadow cargo").length).toBeGreaterThan(0);
    expect(screen.queryByText("Observed zero public purchases in this completed phase.")).not.toBeInTheDocument();
    view.rerender(<Transactions {...props()} />);
    const table = screen.getByRole("table", { name: "Native transactions at snapshot 1" });
    expect(within(table).getAllByText("Shared regional stock")).toHaveLength(2);
    expect(within(table).getAllByText("timber (slot 3)")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Mobility cargo basis"), { target: { value: "virtual_shadow" } });
    expect(screen.queryByRole("table", { name: "Native transactions at snapshot 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Public purchases at snapshot 1" })).toBeInTheDocument();
  });

  it("withholds only the future domain, without hiding the independently dated public frame", () => {
    const p = props(); p.snapshot.transaction_receipts!.rows[0].source_turn = 8;
    const view = render(<Transactions {...p} />);
    expect(screen.queryByRole("table", { name: "Native transactions at snapshot 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Public purchases at snapshot 1" })).toBeInTheDocument();
    const q = props(); q.snapshot.transaction_receipts!.public_purchases!.rows[0].source_turn = 8;
    view.rerender(<Transactions {...q} />);
    expect(screen.getByRole("table", { name: "Native transactions at snapshot 1" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Public purchases at snapshot 1" })).not.toBeInTheDocument();
  });

  it("does not leave an invisible operation filter active after scrubbing to an earlier phase", () => {
    const p = props("hybrid-public", 1);
    const view = render(<Transactions {...p} />);
    fireEvent.change(screen.getByLabelText("Mobility operation"), { target: { value: "departed" } });
    expect(screen.getByLabelText("Mobility operation")).toHaveValue("departed");
    view.rerender(<Transactions {...p} snapshot={p.bundle.history[0]} currentTurn={1} />);
    expect(screen.getByLabelText("Mobility operation")).toHaveValue("all");
    expect(within(screen.getByRole("table", { name: "Native transactions at snapshot 1" })).getAllByText("reserved")).toHaveLength(1);
  });

  it("labels capped retained rows and incomplete duplicate detection without claiming complete totals", () => {
    const p = props(), frame = p.snapshot.transaction_receipts!;
    frame.complete = false; frame.dropped_rows = 3; frame.rows[0].voyage_id = null;
    Object.assign(frame.public_purchases!, { complete: false, dropped_rows: 2, retained_key_duplicates: 1, duplicate_detection_complete: false });
    render(<Transactions {...p} />);
    expect(screen.getByText(/duplicate scan incomplete; count is not a total/)).toBeInTheDocument();
    expect(screen.getByText(/no complete purchase total is inferred/)).toBeInTheDocument();
    expect(screen.getByText("Voyage identity unknown")).toBeInTheDocument();
  });

  it("keeps history as of the selected snapshot and navigates by its saved turn", () => {
    const p = props("hybrid-public", 2); render(<Transactions {...p} />);
    const table = screen.getByRole("table", { name: "Transaction frame history through snapshot 3" });
    expect(within(table).queryByRole("button", { name: "4" })).not.toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "2" }));
    expect(p.onSeek).toHaveBeenCalledWith(2);
  });

  it("distinguishes observed zero, unavailable, missing old fields and a never-recorded system", () => {
    const p = props(); Object.assign(p.snapshot.transaction_receipts!.public_purchases!, { rows: [], observed_purchases: 0 });
    const view = render(<Transactions {...p} />);
    expect(screen.getByText("Observed zero public purchases in this completed phase.")).toBeInTheDocument();
    delete p.snapshot.transaction_receipts!.public_purchases;
    view.rerender(<Transactions {...p} />);
    expect(screen.getByText(/No usable public-purchase frame/)).toBeInTheDocument();
    delete p.snapshot.transaction_receipts;
    view.rerender(<Transactions {...p} />);
    expect(screen.getByText(/No usable native mobility frame/)).toBeInTheDocument();
    p.bundle.history = [p.snapshot]; view.rerender(<Transactions {...p} />);
    expect(view.container).toBeEmptyDOMElement();
  });
});
