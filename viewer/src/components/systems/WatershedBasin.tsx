import type { Region, TurnSnapshot } from "../../types";
import type { WatershedRecord } from "../../watershedTypes";
import { watershedOutflow } from "../../lib/watershed";

/** Static geography, dated controllers and flows; no final-state ownership. */
export function WatershedBasin({ regions, snapshot, record, onSelectRegion }: {
  regions: Region[]; snapshot: TurnSnapshot | null; record: WatershedRecord;
  onSelectRegion: (name: string) => void;
}) {
  const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
  const coords = regions.every((r) => finite(r.x) && finite(r.y));
  const outflow = watershedOutflow(record);
  const control = snapshot?.region_control ?? {};
  const edges = record.graph.down.flatMap((down, source) => down < 0 ? [] : [{ source, down }]);
  const cross = (source: number, down: number) => {
    const a = control[regions[source].name], b = control[regions[down].name];
    return a == null || b == null ? null : a !== b;
  };
  const xs = regions.map((r) => r.x ?? 0), ys = regions.map((r) => r.y ?? 0);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  const spanX = Math.max(1e-9, Math.max(...xs) - minX), spanY = Math.max(1e-9, Math.max(...ys) - minY);
  const x = (i: number) => 15 + 270 * (xs[i] - minX) / spanX;
  const y = (i: number) => 15 + 170 * (ys[i] - minY) / spanY;
  return <details><summary>Drainage map and cross-border flows</summary>
    <p className="systems-note">Arrows follow the saved drainage graph. Dashed arrows cross a known border at snapshot {snapshot?.turn}; unknown controllers are listed as unknown. Flow is water routed this turn, not an estimate of harm or a causal attribution.</p>
    {coords ? <svg viewBox="0 0 300 200" role="img" aria-label="Drainage basin map" style={{ width: "100%", maxHeight: 360 }}>
      <defs><marker id="watershed-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
      {edges.map(({ source, down }) => <line key={source} x1={x(source)} y1={y(source)} x2={x(down)} y2={y(down)}
        stroke="currentColor" strokeWidth="0.8" strokeDasharray={cross(source, down) ? "3 2" : undefined}
        markerEnd="url(#watershed-arrow)"><title>{regions[source].name} → {regions[down].name}</title></line>)}
      {regions.map((r, i) => <circle key={r.name} cx={x(i)} cy={y(i)} r="3" fill="currentColor"
        role="button" tabIndex={0} aria-label={`Inspect basin region ${r.name}`} onClick={() => onSelectRegion(r.name)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectRegion(r.name); } }}><title>{r.name}</title></circle>)}
    </svg> : <p className="systems-note">Map coordinates were not recorded; the drainage links remain readable below.</p>}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Basin links at snapshot ${snapshot?.turn}`}>
      <thead><tr><th>Upstream</th><th>Downstream</th><th>Border</th><th>Water passed</th></tr></thead>
      <tbody>{edges.map(({ source, down }) => <tr key={source}>
        <td><button className="systems-link" onClick={() => onSelectRegion(regions[source].name)}>{regions[source].name}</button></td>
        <td><button className="systems-link" onClick={() => onSelectRegion(regions[down].name)}>{regions[down].name}</button></td>
        <td>{cross(source, down) === null ? "Unknown" : cross(source, down) ? "Cross-border" : "Within realm"}</td>
        <td>{outflow === null ? "Unknown" : outflow[source].toFixed(3)}</td>
      </tr>)}</tbody></table></div>
  </details>;
}
