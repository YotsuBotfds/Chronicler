import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import { eventsOfTypes, formatShare, SYSTEM_EVENT_TYPES, type SeriesRow, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, SystemEventList } from "./SystemParts";

const PAIR_SERIES = ["contact pairs", "trade partners"];
const PAIR_COLORS: Record<string, string> = { "contact pairs": "#7ebec3", "trade partners": "#c98500" };

/** Who is in touch with whom, and who depends on whom for trade (the contact ledger). */
export function ContactPanel({
  bundle, snapshot, currentTurn, onSelectEvent, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const pairs = useMemo<SeriesRow[]>(() => history.map((snap) => ({
    turn: snap.turn,
    "contact pairs": snap.contact ? snap.contact.contact_pairs : null,
    "trade partners": snap.contact ? snap.contact.trade_pairs : null,
  })), [history]);
  const contact = snapshot?.contact;
  const at = snapshot?.turn ?? currentTurn;
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.contact, currentTurn);

  const civButton = (civ: string) => (
    <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>
      <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
    </button>
  );

  return (
    <div className="systems-panel-body" aria-label="Contact">
      {contact ? (
        <div className="systems-tiles">
          <StatTile label="Civilizations in contact" value={contact.contact_pairs} detail={`pairs at turn ${at}`} />
          <StatTile label="Trade partners" value={contact.trade_pairs} detail="pairs" />
          <StatTile label="Region links" value={contact.edges} detail="with any flow" />
          <StatTile label="People moving" value={(contact.inflow.people ?? 0).toFixed(0)} detail="this turn" />
        </div>
      ) : (
        <div className="phase75-empty-state">No contact ledger record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Contact and trade between civilizations</h3>
        <CivLineChart
          data={pairs}
          civs={PAIR_SERIES}
          color={(name) => PAIR_COLORS[name]}
          currentTurn={currentTurn}
          label="Pairs of living civilizations in contact, and trading"
          step
        />
      </section>

      <div className="systems-columns">
        {contact && (
          <section className="systems-section">
            <h3>Largest trade partnerships at turn {at}</h3>
            {contact.top_trade_pairs.length === 0 ? (
              <div className="phase75-empty-state">No two living civilizations trade at turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Trade partnerships at turn ${at}`}>
                  <thead><tr><th>Civilization</th><th>Partner</th><th>Trade flow</th><th>Its share of A&apos;s trade</th><th>Of B&apos;s</th></tr></thead>
                  <tbody>
                    {contact.top_trade_pairs.map((pair) => (
                      <tr key={`${pair.a}-${pair.b}`}>
                        <td>{civButton(pair.a)}</td>
                        <td>{civButton(pair.b)}</td>
                        <td>{pair.trade.toFixed(1)}</td>
                        <td>{formatShare(pair.dependence_ab, 0)}</td>
                        <td>{formatShare(pair.dependence_ba, 0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="systems-note">
              Shares say how much of each side&apos;s recorded trade runs through this partner: a high share is a
              dependence an embargo or war would hurt.
            </p>
          </section>
        )}

        <section className="systems-section">
          <h3>Embargoes and first contacts</h3>
          <SystemEventList
            events={events}
            label="Contact events"
            emptyText={`No embargo or first contact by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
