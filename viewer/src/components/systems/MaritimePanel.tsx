import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import {
  BLOCKADE_COLOR, CONTESTED_COLOR, eventsOfTypes, formatShare, humanize, recordedSpan, SYSTEM_EVENT_TYPES,
  zoneControllers, zonePorts, zoneRows, type SystemPanelProps,
} from "../../lib/systems";
import { StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

const COUNTERS: Array<[string, string]> = [
  ["fleets_commissioned", "Fleets commissioned"],
  ["naval_battles", "Naval battles"],
  ["blockades", "Blockades"],
  ["blockade_turns", "Blockade turns"],
  ["piracy_losses", "Cargo lost to pirates"],
  ["landings", "Landings"],
  ["colonies", "Colonies"],
  ["crossings", "Sea crossings"],
];

export function MaritimePanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const rows = useMemo(() => zoneRows(history, factionColor), [history]);
  const regionNames = useMemo(() => bundle.world_state.regions.map((region) => region.name), [bundle.world_state.regions]);
  const ports = useMemo(() => zonePorts(bundle.world_state.maritime?.zones, regionNames), [bundle.world_state.maritime, regionNames]);
  const { first, end } = recordedSpan(history);
  const maritime = snapshot?.maritime;
  const at = snapshot?.turn ?? currentTurn;
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.maritime, currentTurn);
  const hasSea = history.some((snap) => (snap.maritime?.zones.length ?? 0) > 0);
  const controllers = useMemo(() => zoneControllers(history), [history]);

  if (!hasSea) {
    return (
      <div className="systems-panel-body" aria-label="Maritime">
        <div className="phase75-empty-state">
          The maritime layer is on, but this world has no sea zones: template worlds need connected coastal regions,
          and procedural worlds take Geography 2.0&apos;s seas. No fleet, blockade or piracy can occur.
        </div>
      </div>
    );
  }

  return (
    <div className="systems-panel-body" aria-label="Maritime">
      {maritime ? (
        <div className="systems-tiles">
          <StatTile label="Fleets" value={maritime.fleets.length} detail={`turn ${at}`} />
          <StatTile label="Ships" value={maritime.fleets.reduce((sum, fleet) => sum + fleet.ships, 0)} />
          <StatTile label="Controlled zones"
            value={`${maritime.zones.filter((zone) => zone.status === "controlled").length} / ${maritime.zones.length}`} />
          <StatTile label="Contested zones" value={maritime.zones.filter((zone) => zone.status === "contested").length} />
          <StatTile label="Blockades" value={maritime.blockades.length} detail={`${maritime.blocked_lanes} lanes closed`} />
        </div>
      ) : (
        <div className="phase75-empty-state">No maritime record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Sea-zone control</h3>
        <p className="systems-note">
          A bar is a zone controlled by one civilization (its colour) or contested; uncontested turns are blank; the
          red line under a row marks a blockade. The map&apos;s Sea layer draws the zones and their ports.
        </p>
        <StripLegend items={[
          ...controllers.map((civ) => ({ label: civ, color: factionColor(civ) })),
          { label: "contested", color: CONTESTED_COLOR },
          { label: "blockade", color: BLOCKADE_COLOR, mark: true },
        ]} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Sea-zone control and blockades over time"
          emptyText="No zone was ever controlled or contested."
          onSeek={onSeek}
        />
      </section>

      <div className="systems-columns">
        <div className="systems-stack">
          {maritime && (
            <section className="systems-section">
              <h3>Sea zones at turn {at}</h3>
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Sea zones at turn ${at}`}>
                  <thead>
                    <tr><th>Zone</th><th>Status</th><th>Ships</th><th>Pirates</th><th>Sea trade</th><th>Piracy</th><th>Ports</th></tr>
                  </thead>
                  <tbody>
                    {maritime.zones.map((zone) => (
                      <tr key={zone.zone}>
                        <td>{zone.zone}</td>
                        <td>
                          {zone.status === "controlled" && zone.controller ? (
                            <button type="button" className="systems-link" onClick={() => onSelectCivilization(zone.controller as string)}>
                              <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(zone.controller) }} />
                              {" "}{zone.controller}
                            </button>
                          ) : zone.status}
                        </td>
                        <td>
                          {Object.keys(zone.ships).length === 0 ? "None"
                            : Object.entries(zone.ships).map(([civ, ships]) => `${civ} ${ships}`).join(" · ")}
                        </td>
                        <td>{formatShare(zone.pirates)}</td>
                        <td>{zone.sea_trade.toFixed(2)}</td>
                        <td>{zone.piracy.toFixed(2)}</td>
                        <td className="systems-ports">
                          {(ports.get(zone.zone) ?? []).map((port, index) => (
                            <span key={port}>
                              {index > 0 && ", "}
                              <button type="button" className="systems-link" onClick={() => onSelectRegion(port)}>{port}</button>
                            </span>
                          ))}
                          {(ports.get(zone.zone)?.length ?? 0) === 0 && <span className="systems-muted">Not recorded</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {maritime && (
            <section className="systems-section">
              <h3>Fleets and blockades at turn {at}</h3>
              {maritime.fleets.length === 0 ? (
                <div className="phase75-empty-state">No fleet at sea at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Fleets at turn ${at}`}>
                    <thead><tr><th>Fleet</th><th>Civilization</th><th>Zone</th><th>Ships</th><th>Mission</th></tr></thead>
                    <tbody>
                      {maritime.fleets.map((fleet) => (
                        <tr key={fleet.id}>
                          <td>{fleet.name}</td>
                          <td>
                            {fleet.civ ? (
                              <button type="button" className="systems-link" onClick={() => onSelectCivilization(fleet.civ as string)}>
                                <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(fleet.civ) }} /> {fleet.civ}
                              </button>
                            ) : "Not recorded"}
                          </td>
                          <td>{fleet.zone}</td>
                          <td>{fleet.ships}</td>
                          <td>{humanize(fleet.mission)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {maritime.blockades.length === 0 ? (
                <div className="phase75-empty-state">No blockade at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Blockades at turn ${at}`}>
                    <thead><tr><th>Zone</th><th>Blockader</th><th>Target</th><th>Since</th></tr></thead>
                    <tbody>
                      {maritime.blockades.map((blockade) => (
                        <tr key={`${blockade.zone}-${blockade.target}`}>
                          <td>{blockade.zone}</td>
                          <td>{blockade.blockader ?? "Not recorded"}</td>
                          <td>{blockade.target ?? "Not recorded"}</td>
                          <td>T{blockade.since}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="systems-counters" aria-label={`Maritime totals by turn ${at}`}>
                {COUNTERS.map(([key, label]) => (
                  <div key={key} className="phase75-stat-row">
                    <span>{label}</span>
                    <strong>{Number(maritime.counters[key] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <section className="systems-section">
          <h3>Naval events</h3>
          <SystemEventList
            events={events}
            label="Maritime events"
            emptyText={`No naval event by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
