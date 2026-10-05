import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { SettlementInspector } from "../SettlementInspector";
import { settlementDemoHistory } from "./settlementHistory";
import "../../../index.css";
import "../app-shell.css";

export function SettlementInspectorDemo() {
  const [turn, setTurn] = useState(2);
  const [settlementId, setSettlementId] = useState<number | null>(7);
  const [open, setOpen] = useState(true);
  return <main className="phase75-shell">
    <div style={{ maxWidth: 760, margin: "0 auto", display: "grid", gap: 16 }}>
      <header className="phase75-panel phase75-inspector-header">
        <div className="phase75-overline">Chronicler · isolated visual fixture</div>
        <h1 style={{ fontFamily: "var(--phase75-serif)", fontSize: "1.6rem", margin: "8px 0" }}>Settlement history</h1>
        <p>Hand-authored six-turn fixture for V05/H28 QA. Production mounting remains gated by M61b.</p>
        <label className="phase75-field"><span>Requested turn</span><input aria-label="Requested turn" type="range" min={1} max={6} step={1}
          value={turn} onChange={(event) => setTurn(Number(event.target.value))} /></label>
        <div className="phase75-stat-row" style={{ marginTop: 12 }}>
          <button type="button" disabled={turn === 1} onClick={() => setTurn(turn - 1)}>Previous turn</button>
          <span>Turn {turn} / 6</span>
          <button type="button" disabled={turn === 6} onClick={() => setTurn(turn + 1)}>Next turn</button>
          {!open && <button type="button" onClick={() => setOpen(true)}>Open settlement inspector</button>}
        </div>
      </header>
      {open && <SettlementInspector history={settlementDemoHistory} requestedTurn={turn} settlementId={settlementId}
        onSelectSettlement={setSettlementId} onSeek={setTurn} onClose={() => setOpen(false)} />}
    </div>
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><SettlementInspectorDemo /></StrictMode>);
