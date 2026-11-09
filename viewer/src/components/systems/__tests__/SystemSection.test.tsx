import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { SystemSection } from "../SystemSection";
import { SystemTable } from "../SystemTable";
afterEach(cleanup);

describe("SystemSection", () => {
  it("renders the markup panels wrote by hand", () => {
    const { container } = render(<SystemSection label="Timber stock" title={<>Timber stock · snapshot {5}</>} note="Phase 2.">
      <p>Body</p>
    </SystemSection>);
    const { container: hand } = render(<section className="systems-section" aria-label="Timber stock">
      <h3>Timber stock · snapshot {5}</h3><p className="systems-note">Phase 2.</p><p>Body</p>
    </section>);
    expect(container.innerHTML).toBe(hand.innerHTML);
  });

  it("uses the label as heading and replaces the body with emptyText", () => {
    const { container } = render(<SystemSection label="Commons rules" note="ignored" emptyText="Not observed here."><p>Body</p></SystemSection>);
    expect(container.innerHTML).toBe(
      '<section class="systems-section" aria-label="Commons rules"><h3>Commons rules</h3><p class="systems-note">Not observed here.</p></section>');
  });
});

describe("SystemTable", () => {
  it("wraps a labelled systems table", () => {
    const { container } = render(<SystemTable label="Totals"><tbody><tr><td>1</td></tr></tbody></SystemTable>);
    expect(container.innerHTML).toBe(
      '<div class="systems-table-wrap"><table class="systems-table" aria-label="Totals"><tbody><tr><td>1</td></tr></tbody></table></div>');
    cleanup();
    const { container: extra } = render(<SystemTable label="Turns" className="recovery-chain-turns"><tbody /></SystemTable>);
    expect(extra.querySelector("table")?.className).toBe("systems-table recovery-chain-turns");
  });
});
