import { useId, useState } from "react";
import { GroupedEventLedger } from "../components/phase75/GroupedEventLedger";
import { SettlementInspector } from "../components/phase75/SettlementInspector";
import { combinedCivilizations, combinedEvents, combinedHistories, defaultSettlement,
  type ExampleCivilization } from "./combinedInspectionFixture";
import "./combined-inspection.css";

/** Isolated fixture composition. Ordinary viewer entry points never import it. */
export function CombinedInspectionDemo() {
  const id = useId();
  const [requestedTurn, setRequestedTurn] = useState(3);
  const [civilization, setCivilization] = useState<ExampleCivilization>("Alpha");
  const [settlementId, setSettlementId] = useState<number | null>(7);
  const [open, setOpen] = useState(true);
  const [artifact, setArtifact] = useState(0);
  return <main className="phase75-shell">
    <div className="combined-fixture">
      <header className="phase75-panel combined-header">
        <p className="phase75-overline">Chronicler · isolated experimental fixture · V04/H29 + V05/H28</p>
        <h1>Event ledger &amp; settlement history</h1>
        <p className="combined-notice">Synthetic / nonproduction preview. Production AppShell mounting remains gated by M61b; this fixture does not establish acceptance.</p>
        <p className="phase75-detail-copy">Hand-authored examples: 32 requested turns, 72 event records, and separate Alpha/Beta histories.
          Events match civilization actor names; they contain no settlement IDs. Settlement selection does not imply an event-to-settlement link.</p>
        <div className="combined-controls">
          <label htmlFor={`${id}-turn`}>Requested turn: <output>{requestedTurn}</output>
            <input id={`${id}-turn`} aria-label="Requested turn" type="range" min={1} max={32} step={1}
              value={requestedTurn} onChange={event => setRequestedTurn(Number(event.target.value))} />
          </label>
          <label htmlFor={`${id}-civilization`}>Example civilization
            <select id={`${id}-civilization`} value={civilization} onChange={event => {
              const next = event.target.value as ExampleCivilization;
              setCivilization(next); setSettlementId(defaultSettlement[next]);
            }}>{combinedCivilizations.map(name => <option key={name}>{name}</option>)}</select>
          </label>
        </div>
        <div className="combined-actions">
          <button className="phase75-ghost-button" type="button" aria-expanded={open} aria-controls={`${id}-panels`}
            onClick={() => setOpen(value => !value)}>{open ? "Close experimental panels" : "Open experimental panels"}</button>
          <button className="phase75-ghost-button" type="button" onClick={() => {
            setArtifact(value => value + 1); setRequestedTurn(3); setCivilization("Alpha"); setSettlementId(7); setOpen(true);
          }}>Reload synthetic fixture</button>
        </div>
        <p className="phase75-detail-copy">Explore turns 1/2/3/4/5/6 for absence, founding, stale data, a missing snapshot, dissolution, and missing fields.
          Select Upper Ferry at turn 25 to inspect a stale source-turn label and two pages of history.</p>
      </header>
      <div id={`${id}-panels`} className="combined-panels">
        {open && <>
          <GroupedEventLedger key={`ledger:${artifact}`} events={combinedEvents} currentTurn={requestedTurn}
            selectedCivilization={civilization} civilizations={combinedCivilizations} lockCivilization />
          <SettlementInspector key={`settlement:${artifact}:${civilization}`} history={combinedHistories[civilization]}
            requestedTurn={requestedTurn} settlementId={settlementId} onSelectSettlement={setSettlementId} onSeek={setRequestedTurn} />
        </>}
      </div>
    </div>
  </main>;
}
