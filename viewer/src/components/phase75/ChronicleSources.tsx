import { useMemo, useState } from "react";
import type { Bundle, Event, NewChronicleEntry } from "../../types";
import { passageSources } from "../../lib/narrationSources";
import "./chronicle-sources.css";

export interface ChronicleSourcesProps {
  bundle: Bundle;
  entry: NewChronicleEntry;
  /** The scrubbed turn: facts dated after it are counted, not shown. */
  currentTurn: number;
  onJumpToTurn: (turn: number) => void;
  onSelectEvent?: (event: Event) => void;
}

/**
 * A chronicle passage's sources (its provenance, lib/narrationSources): the
 * facts its sentences cite, then, on request, every other fact its narrator
 * was given, each with a link to its turn (an event also opens in the
 * inspector). A fact dated after the scrubbed turn (a retrospective one,
 * given for foreshadowing) is shown once that turn has passed.
 */
export function ChronicleSources({ bundle, entry, currentTurn, onJumpToTurn, onSelectEvent }: ChronicleSourcesProps) {
  const data = useMemo(() => passageSources(bundle, entry), [bundle, entry]);
  const [showAll, setShowAll] = useState(false);
  if (!data) {
    return null;
  }
  const known = data.sources.filter((source) => source.turn === null || source.turn <= currentTurn);
  const later = data.sources.length - known.length;
  const cited = known.filter((source) => source.cited);
  const others = known.filter((source) => !source.cited);
  const shown = showAll || cited.length === 0 ? known : cited;
  const verb = data.narrator === "mechanical" ? "Built from" : "Cites";
  return (
    <div className="phase75-sources" aria-label="Passage sources">
      <div className="phase75-sources-summary">
        {verb} {data.cited} of the {data.given} facts given
        {data.narrator === "mechanical" ? " (mechanical narrator)" : ""}
        {later > 0 && ` · ${later} dated later, shown once their turn has passed`}
      </div>
      <ul className="phase75-sources-list">
        {shown.map((source) => (
          <li key={source.id} className={`phase75-source${source.cited ? " cited" : ""}`}>
            <button
              type="button"
              className="phase75-source-turn"
              disabled={source.turn === null}
              aria-label={source.turn === null ? `${source.id} (undated)` : `Turn ${source.turn}: ${source.label}`}
              onClick={() => {
                if (source.turn !== null) onJumpToTurn(source.turn);
                if (source.event && onSelectEvent) onSelectEvent(source.event);
              }}
            >
              {source.turn === null ? "—" : `T${source.turn}`}
            </button>
            <span className="phase75-source-kind">
              {source.kind}
              {source.retrospective ? " · later" : ""}
            </span>
            <span className="phase75-source-label">{source.label}</span>
          </li>
        ))}
      </ul>
      {cited.length > 0 && others.length > 0 && (
        <button type="button" className="phase75-sources-more" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Cited facts only" : `All ${known.length} facts given`}
        </button>
      )}
    </div>
  );
}
