import { useEffect, useId, useMemo, useState } from "react";
import type { Bundle } from "../types";
import { buildHistoricalSearchIndex, searchHistoricalEntities, type HistoricalSearchKind, type HistoricalSearchResult } from "../lib/historicalSearch";
import "./historical-search.css";

export interface HistoricalSearchProps {
  bundle: Bundle;
  currentTurn: number;
  onInspect: (result: HistoricalSearchResult) => void;
  onViewRecordedTurn?: (result: HistoricalSearchResult) => void;
}
export function HistoricalSearch({ bundle, currentTurn, onInspect, onViewRecordedTurn }: HistoricalSearchProps) {
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [kind, setKind] = useState<HistoricalSearchKind | "all">("all");
  useEffect(() => { const timeout = setTimeout(() => setDebounced(query), 160); return () => clearTimeout(timeout); }, [query]);
  const index = useMemo(() => buildHistoricalSearchIndex(bundle, currentTurn), [bundle, currentTurn]);
  const results = useMemo(() => searchHistoricalEntities(index, debounced, kind), [index, debounced, kind]);
  return <section className="historical-search" aria-label="Historical entity search">
    <h2>Find in recorded history</h2>
    <p>Search names and dated aliases through selected turn {currentTurn}. Inspect keeps this turn selected.</p>
    <div className="historical-search-controls">
      <label htmlFor={inputId}>Name or dated alias<input id={inputId} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Region, civilization, institution, actor…" /></label>
      <label>Entity type<select value={kind} onChange={(event) => setKind(event.target.value as HistoricalSearchKind | "all")}>
        <option value="all">All types</option><option value="region">Regions</option><option value="civilization">Civilizations</option>
        <option value="institution">Institutions</option><option value="city">Cities</option><option value="actor">Named actor observations</option>
      </select></label>
    </div>
    <p role="status" aria-live="polite">{query !== debounced ? "Updating search…" : `Showing ${results.items.length} of ${results.total} matches through turn ${currentTurn}.`}</p>
    <ul className="historical-search-results">{results.items.map((item) => <li key={`${item.sourceRef}:${item.identity?.index ?? "observation"}`}>
      <h3>{item.name} <small>{item.kind}{item.identity ? ` · ${item.identity.namespace} ${item.identity.index}` : " · identity unresolved"}</small></h3>
      <p>{item.firstRecordedTurn === null ? "No dated historical observation." : `First recorded ${item.firstRecordedTurn}; last recorded ${item.lastRecordedTurn} (through ${currentTurn}).`}</p>
      <p>{item.status}</p>{item.ambiguity && <p className="historical-search-ambiguity">{item.ambiguity}</p>}
      <p>{item.aliases.length ? `Dated names: ${item.aliases.map((alias) => `${alias.name} (turn ${alias.turn})`).join("; ")}` : "Dated aliases unknown."}</p>
      <div className="historical-search-actions"><button type="button" onClick={() => onInspect(item)}>Inspect: {item.name}</button>
        {onViewRecordedTurn && item.turn !== null && item.turn !== currentTurn && <button type="button" onClick={() => onViewRecordedTurn(item)}>View recorded turn {item.turn}: {item.name}</button>}
      </div>
    </li>)}</ul>
    {results.total > results.items.length && <p>Narrow the name or entity type to see more matches. Results are limited to 30.</p>}
    {results.total === 0 && <p>No matching recorded names. Missing observations do not establish that an entity did not exist.</p>}
    <details><summary>Search coverage and identity</summary><ul>{index.coverage.map((line) => <li key={line}>{line}</li>)}</ul></details>
  </section>;
}
