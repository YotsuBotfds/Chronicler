/**
 * The shell's map column: the region list, overlay chips, the map layer bar,
 * the atlas (regions, links, layer marks and legend) and the civilization
 * chips. Presentation only: AppShell owns the selection, overlays, layer and
 * technique choices and computes the atlas nodes, links and layer view.
 */
import type { BatchRunSummary, Bundle, WorldState } from "../../types";
import type { BatchState } from "../../hooks/useBatchConnection";
import type { CivilizationView } from "../../lib/civilizationViews";
import { DISPOSITION_COLORS, factionColor, UNCONTROLLED_COLOR } from "../../lib/colors";
import {
  MAP_LAYER_LABELS, NO_DATA_FILL, NO_DATA_OPACITY, type MapLayerKey, type MapLayerView,
} from "../../lib/mapLayers";
import { techniqueLabel } from "../../lib/systems";
import { regionNodeRadius } from "./appShellHelpers";
import type { AppSurface, MapNode, OverlayKey, SelectedEntity } from "./appShellTypes";
import { MapLayerLegend, MapLayerMarks } from "./MapLayerMarks";

export function MapViewport({
  surface,
  atlasNodes,
  atlasConnections,
  controllerCentroids,
  activeOverlays,
  onToggleOverlay,
  mapLayers = ["control"],
  mapLayer = "control",
  onMapLayerChange,
  mapLayerView = null,
  toAtlas,
  techniqueOptions = [],
  technique = null,
  onTechniqueChange,
  civilizations,
  tradeLinks,
  campaignLinks,
  selectedEntity,
  onSelectEntity,
  namedEvents,
  selectedScenario,
  resumeState,
  batchSummary,
  currentTurn,
  totalTurns,
  bundleLoading,
  viewerReady,
  batchState,
  batchProgress,
}: {
  surface: AppSurface;
  atlasNodes: MapNode[];
  atlasConnections: Array<{ source: MapNode; target: MapNode }>;
  controllerCentroids: Record<string, { x: number; y: number }>;
  activeOverlays: OverlayKey[];
  onToggleOverlay: (overlay: OverlayKey) => void;
  mapLayers?: MapLayerKey[];
  mapLayer?: MapLayerKey;
  onMapLayerChange?: (layer: MapLayerKey) => void;
  mapLayerView?: MapLayerView | null;
  toAtlas?: (x: number, y: number) => { x: number; y: number };
  techniqueOptions?: string[];
  technique?: string | null;
  onTechniqueChange?: (technique: string) => void;
  civilizations: CivilizationView[];
  tradeLinks: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }>;
  campaignLinks: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; disposition: string }>;
  selectedEntity: SelectedEntity | null;
  onSelectEntity: (selection: SelectedEntity | null) => void;
  namedEvents: Bundle["named_events"];
  selectedScenario: string | null;
  resumeState: WorldState | null;
  batchSummary: BatchRunSummary | null;
  currentTurn: number;
  totalTurns: number;
  bundleLoading: boolean;
  viewerReady: boolean;
  batchState: BatchState;
  batchProgress: { completed: number; total: number; currentSeed: number } | null;
}) {
  const maxCapacity = Math.max(0, ...atlasNodes.map((node) => node.region.carrying_capacity ?? 0));
  const nodeRadius = (node: MapNode) => regionNodeRadius(node.region.carrying_capacity, maxCapacity, atlasNodes.length);
  const placedNodes = mapLayerView
    ? atlasNodes.map((node) => ({ name: node.region.name, x: node.x, y: node.y, r: nodeRadius(node) }))
    : [];
  const layerFill = (node: MapNode): { fill: string; opacity: number } => {
    const control = node.controller === undefined ? NO_DATA_FILL : node.controller === null ? UNCONTROLLED_COLOR : factionColor(node.controller);
    if (!mapLayerView) {
      return { fill: control, opacity: node.controller === undefined ? NO_DATA_OPACITY : 1 };
    }
    const fill = mapLayerView.fills.get(node.region.name);
    if (fill) {
      return { fill, opacity: mapLayerView.opacity.get(node.region.name) ?? 1 };
    }
    return mapLayerView.dimControl ? { fill: control, opacity: 0.32 } : { fill: NO_DATA_FILL, opacity: NO_DATA_OPACITY };
  };
  // Named events recorded by the scrubbed turn (a later landmark is not marked).
  const highlightedEventRegions = new Set(
    namedEvents
      .filter((event) => event.region && event.turn <= currentTurn)
      .slice(0, 8)
      .map((event) => event.region as string),
  );

  return (
    <section className="phase75-map-column" id="world-investigation-map" tabIndex={-1} aria-label="World map investigation">
      {viewerReady && <div className="phase75-region-navigation phase75-panel">
        <label>Inspect a region<select aria-label="Inspect a region" value={selectedEntity?.kind === "region" ? selectedEntity.id : ""}
          onChange={(event) => onSelectEntity({ kind: "region", id: event.target.value, label: event.target.value })}>
          <option value="" disabled>Choose a region</option>
          {atlasNodes.map((node, index) => <option key={index} value={node.region.name}>{node.region.name}</option>)}
        </select></label>
        <button type="button" onClick={() => { const details = document.getElementById("selected-world-details"); details?.focus(); details?.scrollIntoView({ block: "start" }); }}>View selection details</button>
        <p>Use the list to select small map markers. Selection and historical turn are kept when moving between map and details.</p>
        {mapLayer === "control" && <p>Ownership at this exact turn: dim gray is unknown; solid gray is explicitly uncontrolled. Named owners use their civilization colors.</p>}
      </div>}
      <div className="phase75-viewport-toolbar phase75-panel">
        <div>
          <div className="phase75-overline">
            {surface === "setup"
              ? "World preview"
              : surface === "progress"
                ? "Starting run"
                : surface === "batch"
                  ? "Run preview"
                  : "World map"}
          </div>
          <h2>
            {surface === "setup"
              ? "Choose a scenario or generate a world"
              : surface === "progress"
                ? "Preparing your world"
                : surface === "batch"
                  ? "Select a run to preview"
                  : "Explore the world at the selected turn"}
          </h2>
        </div>

        <div className="phase75-overlay-chips">
          {(["borders", "settlements", "chronicle", "trade", "campaign", "fog", "asabiya"] as OverlayKey[]).map((overlay) => (
            <button
              key={overlay}
              type="button"
              className={`phase75-layer-chip${activeOverlays.includes(overlay) ? " active" : ""}`}
              onClick={() => onToggleOverlay(overlay)}
              disabled={surface === "setup" && (overlay === "trade" || overlay === "campaign" || overlay === "fog")}
            >
              {overlay}
            </button>
          ))}
        </div>
      </div>

      {viewerReady && mapLayers.length > 1 && onMapLayerChange && (
        <div className="phase75-layer-bar phase75-panel">
          <span className="phase75-overline">Map layer</span>
          <div className="phase75-overlay-chips" role="radiogroup" aria-label="Map layer">
            {mapLayers.map((key) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={mapLayer === key}
                className={`phase75-layer-chip${mapLayer === key ? " active" : ""}`}
                onClick={() => onMapLayerChange(key)}
              >
                {MAP_LAYER_LABELS[key]}
              </button>
            ))}
          </div>
          {mapLayer === "techniques" && techniqueOptions.length > 0 && onTechniqueChange && (
            <label className="phase75-layer-select">
              <span>Technique</span>
              <select value={technique ?? ""} onChange={(event) => onTechniqueChange(event.target.value)}>
                {techniqueOptions.map((key) => (
                  <option key={key} value={key}>{techniqueLabel(key)}</option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}

      <div className="phase75-map-stage phase75-panel">
        <div className="phase75-map-overlay-copy">
          <div className="phase75-overline">
            {surface === "batch" && batchSummary ? `Rank #${batchSummary.rank} preview` : surface}
          </div>
          <h3>
            {surface === "setup"
              ? selectedScenario ?? (resumeState ? "Resumed world preview" : "Procedural world preview")
              : surface === "batch"
                ? (batchSummary?.dominant_faction || "Batch preview")
                : viewerReady
                  ? `Turn ${currentTurn} of ${totalTurns}`
                  : "Awaiting archive data"}
          </h3>
          <p>
            {surface === "progress"
              ? "Waiting for the first recorded turn."
              : surface === "batch"
                ? (batchSummary
                  ? `${batchSummary.major_event_count} major events · ${batchSummary.signal_flags.join(" · ") || "steady signal profile"}`
                  : "Run a batch to compare worlds and inspect individual results.")
                : "Select a region or civilization to inspect it at this turn."}
          </p>
        </div>

        <div className="phase75-map-surface">
          <div className="phase75-map-texture" />
          <svg className="phase75-atlas" viewBox="0 0 1000 640" aria-label="World map">
            <g className="phase75-contours">
              <path d="M 30 122 C 210 48 418 84 642 112 S 926 142 972 116" />
              <path d="M 36 202 C 200 142 398 150 624 188 S 902 234 968 198" />
              <path d="M 42 294 C 220 238 426 244 618 286 S 866 336 962 310" />
              <path d="M 46 392 C 212 346 404 354 612 396 S 858 448 952 426" />
              <path d="M 64 502 C 236 466 418 472 602 514 S 844 566 936 538" />
            </g>

            {activeOverlays.includes("trade") && tradeLinks.map((link) => (
              <line
                key={link.key}
                className="phase75-trade-link"
                x1={link.source.x}
                y1={link.source.y}
                x2={link.target.x}
                y2={link.target.y}
                strokeWidth={2 + Math.min(link.strength, 1.4) * 2}
              />
            ))}

            {activeOverlays.includes("campaign") && campaignLinks.map((link) => (
              <line
                key={link.key}
                className="phase75-campaign-link"
                x1={link.source.x}
                y1={link.source.y}
                x2={link.target.x}
                y2={link.target.y}
                stroke={DISPOSITION_COLORS[link.disposition] ?? "#a34c4c"}
              />
            ))}

            {activeOverlays.includes("asabiya") && civilizations.map((civilization) => {
              const centroid = controllerCentroids[civilization.name];
              if (!centroid) {
                return null;
              }
              return (
                <circle
                  key={`asabiya-${civilization.name}`}
                  className="phase75-asabiya-ring"
                  cx={centroid.x}
                  cy={centroid.y}
                  r={46 + civilization.asabiya * 48}
                  stroke={factionColor(civilization.name)}
                />
              );
            })}

            {activeOverlays.includes("borders") && atlasConnections.map((connection) => (
              <line
                key={`${connection.source.region.name}-${connection.target.region.name}`}
                className="phase75-region-connection"
                x1={connection.source.x}
                y1={connection.source.y}
                x2={connection.target.x}
                y2={connection.target.y}
              />
            ))}

            {atlasNodes.map((node) => {
              const isSelected = selectedEntity?.kind === "region" && selectedEntity.id === node.region.name;
              const { fill, opacity } = layerFill(node);
              const radius = nodeRadius(node);
              return (
                <g key={node.region.name}>
                  <circle
                    className={`phase75-region-node${isSelected ? " selected" : ""}`}
                    cx={node.x}
                    cy={node.y}
                    r={radius}
                    fill={fill}
                    fillOpacity={opacity === 1 ? undefined : opacity}
                    role="button" tabIndex={0} aria-label={`Inspect region ${node.region.name}`}
                    onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelectEntity({ kind: "region", id: node.region.name, label: node.region.name }); } }}
                    onClick={() => onSelectEntity({
                      kind: "region",
                      id: node.region.name,
                      label: node.region.name,
                    })}
                  >
                    <title>{mapLayerView ? mapLayerView.titles.get(node.region.name) ?? node.region.name
                      : `${node.region.name} · ${node.controller === undefined ? "Ownership unknown" : node.controller === null ? "Uncontrolled" : `Owner: ${node.controller}`} at T${currentTurn}`}</title>
                  </circle>
                  {activeOverlays.includes("settlements") && (
                    <text className="phase75-region-label" x={node.x} y={node.y + radius + 14}>
                      {node.region.name}
                    </text>
                  )}
                  {/* Named-event markers would read as a data layer's marks, so a layer hides them. */}
                  {activeOverlays.includes("chronicle") && !mapLayerView && highlightedEventRegions.has(node.region.name) && (
                    <circle className="phase75-event-marker" cx={node.x + radius - 2} cy={node.y - radius + 2} r={7} />
                  )}
                </g>
              );
            })}

            {mapLayerView && toAtlas && <MapLayerMarks view={mapLayerView} nodes={placedNodes} toAtlas={toAtlas} />}

            {/* The fog mask is decorative; it never covers a data layer. */}
            {activeOverlays.includes("fog") && !mapLayerView && (
              <path className="phase75-fog-mask" d="M 664 112 L 962 164 L 962 612 L 612 612 L 566 288 Z" />
            )}
          </svg>

          {mapLayerView && <MapLayerLegend items={mapLayerView.legend} note={mapLayerView.note} />}

          {bundleLoading && (
            <div className="phase75-map-loading">Loading bundle...</div>
          )}

          {surface === "batch" && batchState === "running" && batchProgress && (
            <div className="phase75-map-progress-card">
              <div className="phase75-overline">Batch in flight</div>
              <strong>Seed {batchProgress.currentSeed}</strong>
              <span>{batchProgress.completed} / {batchProgress.total} complete</span>
              <div className="phase75-progress-bar">
                <div
                  className="phase75-progress-fill"
                  style={{ width: `${(batchProgress.completed / Math.max(batchProgress.total, 1)) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="phase75-map-footer">
          <div className="phase75-civ-chip-row">
            {civilizations.map((civilization) => (
              <button
                key={civilization.name}
                type="button"
                className={`phase75-civ-chip${selectedEntity?.kind === "civilization" && selectedEntity.id === civilization.name ? " active" : ""}`}
                onClick={() => onSelectEntity({
                  kind: "civilization",
                  id: civilization.name,
                  label: civilization.name,
                })}
              >
                <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civilization.name) }} />
                {civilization.name}
              </button>
            ))}
          </div>

          {!viewerReady && (
            <div className="phase75-map-note">
              {surface === "setup"
                ? "Choose run settings, then select Run World to begin."
                : "Choose Open Existing to explore a saved run, or start a live session."}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
