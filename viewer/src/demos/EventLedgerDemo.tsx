import { useState } from "react";
import { createRoot } from "react-dom/client";
import { GroupedEventLedger } from "../components/phase75/GroupedEventLedger";
import { eventLedgerFixture } from "./eventLedgerFixture";
import "../index.css";

export function EventLedgerDemo() {
  const [currentTurn, setCurrentTurn] = useState(4);
  const [open, setOpen] = useState(true);
  const [artifact, setArtifact] = useState(0);
  const [inspection, setInspection] = useState("Choose an original event to inspect its source position.");
  return <main className="phase75-shell">
    <div style={{ maxWidth: 980, margin: "0 auto" }}>
      <p className="phase75-overline">Chronicler · isolated visual fixture · V04 / H29</p>
      <h1 style={{ fontFamily: "var(--phase75-serif)" }}>The event record</h1>
      <p className="phase75-detail-copy">Synthetic QA only. 61 historical records and one future sentinel.
        This entry point does not mount AppShell or run the simulation.</p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBlock: 16 }}>
        <button className="phase75-ghost-button" onClick={() => {
          setCurrentTurn(currentTurn === 4 ? 3 : 4);
          setInspection("Choose an original event to inspect its source position.");
        }}>
          {currentTurn === 4 ? "Rewind to turn 3" : "Return to turn 4"}</button>
        <button className="phase75-ghost-button" onClick={() => setOpen(!open)}>{open ? "Close ledger" : "Open ledger"}</button>
        <button className="phase75-ghost-button" onClick={() => { setArtifact(value => value + 1); setInspection("Fixture reloaded."); }}>Reload fixture</button>
      </div>
      {open && <GroupedEventLedger key={artifact} events={eventLedgerFixture} currentTurn={currentTurn}
        civilizations={["Alpha", "Beta", "Nobody"]}
        onSelectEvent={(event, sourceIndex) => setInspection(`Original event #${sourceIndex + 1} · turn ${event.turn} · ${event.description}`)} />}
      <aside aria-label="Source inspection" className="phase75-mini-card" style={{ marginTop: 16 }}>{inspection}</aside>
    </div>
  </main>;
}

createRoot(document.getElementById("root")!).render(<EventLedgerDemo />);
