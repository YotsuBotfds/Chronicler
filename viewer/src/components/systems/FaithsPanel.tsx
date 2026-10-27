import { useMemo, useState } from "react";
import {
  faithEvents, faithLabel, faithsKnownAt, faithTable, holdsSlotAt, slotSharers, successorInSlot,
} from "../../lib/faiths";
import type { FaithRecord } from "../../types";
import type { SystemPanelProps } from "../../lib/systems";
import { StatTile, SystemEventList } from "./SystemParts";

/**
 * The run's faiths by permanent identity (docs/integration/permanent-faiths.md):
 * each church once, with its founding, the faith it broke from, the native
 * slot it holds or held, and the later church that took a vanished faith's
 * slot. As known at the scrubbed turn.
 */
export function FaithsPanel({ bundle, currentTurn, onSelectEvent, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const table = useMemo(() => faithTable(bundle), [bundle]);
  const civs = bundle.world_state.civilizations;
  const regions = bundle.world_state.regions;
  const movements = bundle.world_state.agent_movements?.movements ?? [];
  const known = faithsKnownAt(table, currentTurn);
  const holding = known.filter((id) => holdsSlotAt(table.faiths[id], currentTurn));
  const vanished = known.length - holding.length;
  const reused = new Set(known.filter((id) => slotSharers(table, id, currentTurn).length > 0)
    .map((id) => table.faiths[id].slot)).size;
  const unresolved = table.faiths.filter((rec) => rec.legacy === "unresolved").length;
  const [chosen, setChosen] = useState<number | null>(null);
  const selected = chosen != null && known.includes(chosen) ? chosen : null;
  const selectedLabel = selected != null ? faithLabel(table, selected) : null;
  const events = selected != null ? faithEvents(bundle, table, selected, currentTurn) : [];

  const origin = (rec: FaithRecord) => {
    const civ = civs[rec.civ]?.name ?? null;
    if (rec.origin === "founding") {
      return civ ? (
        <>founding faith of <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>{civ}</button></>
      ) : "founding faith";
    }
    const region = rec.region != null ? regions[rec.region]?.name ?? null : null;
    const where = region ? (
      <> in <button type="button" className="systems-link" onClick={() => onSelectRegion(region)}>{region}</button></>
    ) : null;
    if (rec.origin === "sect") {
      const movement = rec.movement != null ? movements[rec.movement]?.name ?? null : null;
      return <>sect{movement ? ` of ${movement}` : ""}{rec.leader ? `, led by ${rec.leader}` : ""}{where}</>;
    }
    if (rec.origin === "schism") {
      return <>schism{civ ? ` in ${civ}` : ""}{where}</>;
    }
    return "founding not recorded";
  };

  const status = (id: number) => {
    const rec = table.faiths[id];
    if (holdsSlotAt(rec, currentTurn)) {
      return `holds slot ${rec.slot}`;
    }
    const next = successorInSlot(table, id, currentTurn);
    const label = next != null ? faithLabel(table, next) : null;
    return `vanished; slot ${rec.slot} passed${label ? ` to the ${label}` : ""} at turn ${rec.released_turn}`;
  };

  return (
    <div className="systems-panel-body" aria-label="Faiths">
      <div className="systems-tiles">
        <StatTile label="Faiths founded" value={known.length} detail={`by turn ${currentTurn}`} />
        <StatTile label="Holding a slot" value={holding.length} />
        <StatTile label="Vanished" value={vanished} detail="their slot taken by a later church" />
        <StatTile label="Slots reused" value={reused} />
      </div>

      <section className="systems-section">
        <h3>Faiths by turn {currentTurn}</h3>
        <p className="systems-note">
          Each church once, by its permanent identity: its name and founding turn. The agent runtime counts
          believers by a native slot (16 at most); once a faith has no believer and nothing names it, a new sect
          can take its slot, and the two stay distinct here.
          {table.legacy && (
            <>
              {" "}This bundle predates permanent faith ids: identities were rebuilt from its final registry and
              its schism records{unresolved ? `; ${unresolved} could not be fully traced (an older record naming
              their slot may mean an earlier faith)` : ""}.
            </>
          )}
        </p>
        {known.length === 0 ? (
          <div className="phase75-empty-state">No faith is recorded by turn {currentTurn}.</div>
        ) : (
          <div className="systems-table-wrap">
            <table className="systems-table" aria-label={`Faiths by turn ${currentTurn}`}>
              <thead>
                <tr><th>Faith</th><th>Founded</th><th>Origin</th><th>Broke from</th><th>Slot</th><th>Status</th></tr>
              </thead>
              <tbody>
                {known.map((id) => {
                  const rec = table.faiths[id];
                  const parent = rec.parent != null ? faithLabel(table, rec.parent) : null;
                  const shared = slotSharers(table, id, currentTurn).length > 0;
                  return (
                    <tr key={id} aria-current={id === selected ? "true" : undefined}>
                      <td>
                        <button type="button" className="systems-link" onClick={() => setChosen(id)}>{rec.name}</button>
                        {rec.legacy === "unresolved" ? " (not fully traced)" : ""}
                      </td>
                      <td>{rec.founded_turn ?? "?"}</td>
                      <td>{origin(rec)}</td>
                      <td>{parent ?? "-"}</td>
                      <td>{shared ? `${rec.slot} (shared)` : rec.slot}</td>
                      <td>{status(id)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected != null && selectedLabel && (
        <section className="systems-section" aria-label={`History of the ${selectedLabel}`}>
          <h3>{selectedLabel}</h3>
          {slotSharers(table, selected, currentTurn).length > 0 && (
            <p className="systems-note">
              Slot {table.faiths[selected].slot} by turn {currentTurn} also named:{" "}
              {slotSharers(table, selected, currentTurn).map((id) => faithLabel(table, id)).join("; ")}.
            </p>
          )}
          <SystemEventList
            events={events}
            label={`Recorded moments of the ${selectedLabel}`}
            emptyText={`No recorded schism, reformation or temple of the ${selectedLabel} by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      )}
    </div>
  );
}
