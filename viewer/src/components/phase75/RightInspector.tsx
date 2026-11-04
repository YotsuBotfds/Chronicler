/**
 * The shell's right rail: the selection details (region, civilization or
 * pinned event with its recorded causes, consequences and accounts), the
 * languages, metrics, network and session sections, and the batch
 * surface's run diagnostics. Presentation only: AppShell owns the
 * selection, the inspector sections' open state and every handler, and
 * resolves the selected records at the scrubbed turn; only a consequence
 * list's own "show all" toggle is local, keyed to its event.
 */
import { Suspense, useState } from "react";
import type {
  BatchReport, BatchRunSummary, Bundle, Event, LanguagesField, LobbyInit, TurnSnapshot, WorldState,
} from "../../types";
import { eventSnapshotTurn } from "../../lib/observedSystems";
import type { BatchState } from "../../hooks/useBatchConnection";
import { isFounded, type CivilizationEntry, type CivilizationView } from "../../lib/civilizationViews";
import { RegionSystemsDetail } from "../systems/RegionSystemsDetail";
import type { EventAccounts } from "../../lib/historiography";
import { InWorldAccounts } from "./InWorldAccounts";
import { LanguagesPanel } from "./lazyPanels";
import { PanelLoading } from "./PanelLoading";
import type { FamineSpan } from "../../lib/food";
import { eventKey, UNAVAILABLE } from "./appShellHelpers";
import type { AppSurface, RegionLike, SelectedEntity } from "./appShellTypes";
import type { HistoryEntity } from "../../lib/historyComparison";
// In the order AppShell imported them, which is their stylesheets' order.
import { RegionInvestigation } from "../RegionInvestigation";
import { CivilizationHistory } from "../CivilizationHistory";
import { MigrationEvidence } from "../MigrationEvidence";
import { DebtEvidence } from "../DebtEvidence";

/** Only already-resolved provenance enters this list; selecting a link never seeks. */
function RecordedEventLinks({ events, kind, onSelectEvent }: {
  events: Event[];
  kind: "causes" | "consequences";
  onSelectEvent: (event: Event) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const limit = kind === "consequences" && !expanded ? 3 : events.length;
  return <div className="phase75-event-links" aria-label={`Recorded ${kind}`}>
    <span>{kind === "causes" ? "Because" : "Led to"} · {events.length} {events.length === 1 ? "event" : "events"}</span>
    {events.slice(0, limit).map((event) => <button key={eventKey(event)} type="button"
      className="phase75-inspector-link" onClick={() => onSelectEvent(event)}>
      T{event.turn} {event.description || event.event_type.replace(/_/g, " ")}
    </button>)}
    {kind === "consequences" && events.length > 3 && <button type="button" className="phase75-ghost-button"
      aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {expanded ? "Show fewer consequences" : `Show all ${events.length} recorded consequences`}
    </button>}
  </div>;
}

export function RightInspector({
  surface,
  selection,
  selectedRegion,
  selectedCivilization,
  selectedEvent,
  selectedEventRecorded = true,
  selectedEventProvenance,
  selectedEventAccounts = null,
  onSelectEvent,
  onSeek,
  onSelectRegion,
  onSelectCivilization,
  civilizationNames,
  selectedRegionTerrain,
  languages,
  languagesBundle = null,
  languageSelection = null,
  currentTurn = 0,
  selectedBatchSummary,
  civilizations,
  previewCivilizations,
  selectedScenario,
  resumeState,
  description,
  inspectorSections,
  onToggleSection,
  batchReport,
  batchState,
  batchProgress,
  onOpenBatchResult,
  onShowCompare,
  viewerReady,
  liveState,
  currentSnapshot = null,
  famine = [],
  regionNames = [],
  investigationBundle = null,
  onOpenHistory,
}: {
  surface: AppSurface;
  selection: SelectedEntity | null;
  selectedRegion: RegionLike | null;
  selectedCivilization: CivilizationEntry | null;
  selectedEvent: Event | null;
  /** False when the pinned event is dated after the scrubbed turn. */
  selectedEventRecorded?: boolean;
  selectedEventProvenance?: { causes: Event[]; effects: Event[] };
  selectedEventAccounts?: EventAccounts | null;
  onSelectEvent: (event: Event) => void;
  onSeek: (turn: number) => void;
  onSelectRegion: (name: string) => void;
  onSelectCivilization: (name: string) => void;
  civilizationNames: string[];
  /** The selected region's terrain at the scrubbed turn (null: unreadable record). */
  selectedRegionTerrain?: string | null;
  languages?: LanguagesField;
  /** The bundle whose faith table names the languages' faith words (lib/faiths). */
  languagesBundle?: Bundle | null;
  languageSelection?: { kind: "region" | "civ"; ref: number } | null;
  currentTurn?: number;
  selectedBatchSummary: BatchRunSummary | null;
  civilizations: CivilizationView[];
  previewCivilizations: Array<{ name: string; values: string[] }>;
  selectedScenario: LobbyInit["scenarios"][number] | null;
  resumeState: WorldState | null;
  description: string;
  inspectorSections: Record<string, boolean>;
  onToggleSection: (section: string) => void;
  batchReport: BatchReport | null;
  batchState: BatchState;
  batchProgress: { completed: number; total: number; currentSeed: number } | null;
  onOpenBatchResult?: (path: string) => void;
  onShowCompare: () => void;
  viewerReady: boolean;
  liveState: {
    isLive: boolean;
    connected: boolean;
    serverState: "connecting" | "lobby" | "starting" | "running" | "completed";
    livePaused: boolean;
  };
  currentSnapshot?: TurnSnapshot | null;
  famine?: FamineSpan[];
  regionNames?: string[];
  investigationBundle?: Bundle | null;
  onOpenHistory?: (entity: HistoryEntity) => void;
}) {
  return (
    <aside className="phase75-right-rail phase75-panel" id="selected-world-details" tabIndex={-1} aria-label="Selection details">
      {viewerReady && <button type="button" className="phase75-back-to-map" onClick={() => { const map = document.getElementById("world-investigation-map"); map?.focus(); map?.scrollIntoView({ block: "start" }); }}>Back to map</button>}
      <div className="phase75-inspector-header">
        <div className="phase75-overline">Details</div>
        <h3>
          {surface === "setup"
            ? "Launch details"
            : surface === "batch"
              ? "Batch diagnostics"
              : viewerReady
                ? "Selection details"
                : "Open a run to view details"}
        </h3>
        <p>{description}</p>
      </div>

      <InspectorSection
        title={surface === "batch" ? "Selected Run" : "Selection"}
        open={inspectorSections.selection}
        onToggle={() => onToggleSection("selection")}
      >
        {surface === "setup" && (
          <>
            <div className="phase75-stat-row">
              <span>Scenario</span>
              <strong>{selectedScenario?.name ?? (resumeState ? "Resumed state" : "Procedural world")}</strong>
            </div>
            <div className="phase75-stat-row">
              <span>World</span>
              <strong>{selectedScenario?.world_name ?? resumeState?.name ?? "Generated at launch"}</strong>
            </div>
            <div className="phase75-stat-row">
              <span>Civilizations</span>
              <strong>{previewCivilizations.length || resumeState?.civilizations.length || "Variable"}</strong>
            </div>
          </>
        )}

        {surface === "batch" && (
          selectedBatchSummary ? (
            <>
              <div className="phase75-stat-row">
                <span>Seed</span>
                <strong>{selectedBatchSummary.seed ?? "?"}</strong>
              </div>
              <div className="phase75-stat-row">
                <span>Interestingness</span>
                <strong>{selectedBatchSummary.interestingness_score?.toFixed(1) ?? "Pending"}</strong>
              </div>
              <div className="phase75-stat-row">
                <span>Dominant faction</span>
                <strong>{selectedBatchSummary.dominant_faction || "Unsettled"}</strong>
              </div>
              <div className="phase75-stat-row">
                <span>Signals</span>
                <strong>{selectedBatchSummary.signal_flags.join(" · ") || "steady"}</strong>
              </div>
              {onOpenBatchResult && (
                <button
                  type="button"
                  className="phase75-primary-button"
                  onClick={() => onOpenBatchResult(selectedBatchSummary.bundle_path)}
                >
                  Open In Viewer
                </button>
              )}
            </>
          ) : (
            <div className="phase75-empty-state">
              {batchState === "running"
                ? `Batch running${batchProgress ? `: ${batchProgress.completed}/${batchProgress.total}` : ""}.`
                : "Batch results will populate here once ranked summaries are available."}
            </div>
          )
        )}

        {surface !== "setup" && surface !== "batch" && (
          <>
            {selectedRegion && (
              <>
                <div className="phase75-stat-row">
                  <span>Region</span>
                  <strong>{selectedRegion.name}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Terrain</span>
                  <strong>{selectedRegionTerrain === undefined ? selectedRegion.terrain : (selectedRegionTerrain ?? UNAVAILABLE)}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Resources</span>
                  <strong>{selectedRegion.resources ?? "Unknown"}</strong>
                </div>
                {investigationBundle && <>
                  <RegionInvestigation bundle={investigationBundle}
                    regionIndex={investigationBundle.world_state.regions.findIndex((row) => row.name === selectedRegion.name)}
                    currentTurn={currentTurn} onHistory={() => onOpenHistory?.({ kind: "region", name: selectedRegion.name })}
                    onCivilization={(name) => onOpenHistory?.({ kind: "civilization", name })} onEvent={onSelectEvent} />
                  <MigrationEvidence bundle={investigationBundle} currentTurn={currentTurn}
                    selectedRegionIndex={investigationBundle.world_state.regions.findIndex((row) => row.name === selectedRegion.name)}
                    onInspectRegion={(_, name) => onSelectRegion(name)} />
                </>}
                <RegionSystemsDetail
                  snapshot={currentSnapshot}
                  region={selectedRegion.name}
                  famine={famine}
                  regionNames={regionNames}
                />
              </>
            )}

            {selectedCivilization && (
              <>
                {investigationBundle && <CivilizationHistory bundle={investigationBundle} currentTurn={currentTurn}
                  civilizationIndex={investigationBundle.world_state.civilizations.findIndex((row) => row.name === selectedCivilization.name)}
                  onSeek={onSeek} onInspectEvent={onSelectEvent} onInspectRegion={(_, name) => onSelectRegion(name)} />}
                {investigationBundle && <DebtEvidence bundle={investigationBundle} currentTurn={currentTurn}
                  civilizationIndex={investigationBundle.world_state.civilizations.findIndex((row) => row.name === selectedCivilization.name)}
                  onInspectEvent={onSelectEvent} onViewRecordedTurn={onSeek} />}
                <div className="phase75-stat-row">
                  <span>Civilization</span>
                  <strong>{selectedCivilization.name}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Status</span>
                  <strong>{selectedCivilization.status}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Leader</span>
                  <strong>{isFounded(selectedCivilization) ? selectedCivilization.leaderName : UNAVAILABLE}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Era</span>
                  <strong>{isFounded(selectedCivilization) ? selectedCivilization.techEra : UNAVAILABLE}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Values</span>
                  <strong>{selectedCivilization.values.join(", ") || "None recorded"}</strong>
                </div>
              </>
            )}

            {selectedEvent && !selectedEventRecorded && (
              // Pinned at a later turn: not recorded yet at the scrubbed turn.
              <>
                <div className="phase75-stat-row">
                  <span>Event</span>
                  <strong>{UNAVAILABLE}</strong>
                </div>
                <p className="phase75-detail-copy">Not yet recorded at turn {currentTurn}.</p>
              </>
            )}

            {selectedEvent && selectedEventRecorded && (
              <>
                <div className="phase75-stat-row">
                  <span>Event</span>
                  <strong>{selectedEvent.event_type}</strong>
                </div>
                <p className="phase75-detail-copy">{selectedEvent.description}</p>
                <button type="button" className="phase75-ghost-button"
                  onClick={() => onSeek(eventSnapshotTurn(selectedEvent))}>Go to recorded turn</button>
                {selectedEvent.actors.length > 0 && <div className="phase75-event-links" aria-label="Recorded actors">
                  <span>Actors</span>
                  {selectedEvent.actors.map((actor, index) => civilizationNames.includes(actor)
                    ? <button key={`${index}:${actor}`} type="button" className="phase75-inspector-link"
                      onClick={() => onSelectCivilization(actor)}>{actor}</button>
                    : regionNames.includes(actor)
                      ? <button key={`${index}:${actor}`} type="button" className="phase75-inspector-link"
                        onClick={() => onSelectRegion(actor)}>{actor}</button>
                      : <span key={`${index}:${actor}`}>{actor}</span>)}
                </div>}
                {selectedEvent.region && regionNames.includes(selectedEvent.region) && <div className="phase75-event-links">
                  <span>Recorded region</span>
                  <button type="button" className="phase75-inspector-link"
                    onClick={() => onSelectRegion(selectedEvent.region!)}>{selectedEvent.region}</button>
                </div>}
                {selectedEventProvenance && selectedEventProvenance.causes.length > 0 && (
                  <RecordedEventLinks key={`causes:${eventKey(selectedEvent)}`} kind="causes"
                    events={selectedEventProvenance.causes} onSelectEvent={onSelectEvent} />
                )}
                {selectedEventProvenance && selectedEventProvenance.effects.length > 0 && (
                  <RecordedEventLinks key={`consequences:${eventKey(selectedEvent)}`} kind="consequences"
                    events={selectedEventProvenance.effects} onSelectEvent={onSelectEvent} />
                )}
                <InWorldAccounts accounts={selectedEventAccounts} />
              </>
            )}

            {!selectedRegion && !selectedCivilization && !selectedEvent && (
              <div className="phase75-empty-state">
                {selection ? selection.label : "Select a region, civ, or event to pin details here."}
              </div>
            )}
          </>
        )}
      </InspectorSection>

      {languages && surface !== "setup" && surface !== "batch" && (
        <InspectorSection
          title="Languages"
          open={inspectorSections.languages}
          onToggle={() => onToggleSection("languages")}
        >
          <Suspense fallback={<PanelLoading label="the languages" />}>
            <LanguagesPanel field={languages} turn={currentTurn} selected={languageSelection} bundle={languagesBundle} />
          </Suspense>
        </InspectorSection>
      )}

      <InspectorSection
        title={surface === "batch" ? "Report Health" : "Metrics"}
        open={inspectorSections.metrics}
        onToggle={() => onToggleSection("metrics")}
      >
        {surface === "batch" ? (
          <>
            <div className="phase75-stat-row">
              <span>Runs</span>
              <strong>{batchReport?.metadata.runs ?? 0}</strong>
            </div>
            <div className="phase75-stat-row">
              <span>Anomalies</span>
              <strong>{batchReport?.anomalies.length ?? 0}</strong>
            </div>
            <div className="phase75-stat-row">
              <span>Compare</span>
              <button type="button" className="phase75-ghost-button" onClick={onShowCompare}>
                Open Overlay
              </button>
            </div>
          </>
        ) : selectedCivilization && !isFounded(selectedCivilization) ? (
          // No history row yet: no values to show (not the end-of-run ones).
          <>
            {["Economy", "Culture", "Military", "Stability", "Treasury"].map((label) => (
              <div key={label} className="phase75-stat-row">
                <span>{label}</span>
                <strong>{UNAVAILABLE}</strong>
              </div>
            ))}
          </>
        ) : selectedCivilization ? (
          <>
            <MetricBar label="Economy" value={selectedCivilization.economy} scale={12} />
            <MetricBar label="Culture" value={selectedCivilization.culture} scale={12} />
            <MetricBar label="Military" value={selectedCivilization.military} scale={12} />
            <MetricBar label="Stability" value={selectedCivilization.stability} scale={12} />
            <MetricBar label="Treasury" value={selectedCivilization.treasury} scale={24} />
          </>
        ) : (
          civilizations.slice(0, 4).map((civilization) => (
            <div key={civilization.name} className="phase75-mini-card">
              <strong>{civilization.name}</strong>
              <span>
                Econ {civilization.economy} · Mil {civilization.military} · Era {civilization.techEra}
              </span>
            </div>
          ))
        )}
      </InspectorSection>

      <InspectorSection
        title={surface === "campaign" ? "Campaign Signals" : surface === "trade" ? "Trade Signals" : "Network"}
        open={inspectorSections.network}
        onToggle={() => onToggleSection("network")}
      >
        {surface === "trade" && civilizations.slice(0, 4).map((civilization) => (
          <div key={civilization.name} className="phase75-mini-card">
            <strong>{civilization.name}</strong>
            <span>Treasury {civilization.treasury} · Asabiya {(civilization.asabiya * 100).toFixed(0)}%</span>
          </div>
        ))}

        {surface === "campaign" && civilizations.slice(0, 4).map((civilization) => (
          <div key={civilization.name} className="phase75-mini-card">
            <strong>{civilization.name}</strong>
            <span>Military {civilization.military} · Stability {civilization.stability}</span>
          </div>
        ))}

        {surface !== "trade" && surface !== "campaign" && (
          <div className="phase75-empty-state">
            Choose Trade or Campaign to view civilization summaries for this turn.
          </div>
        )}
      </InspectorSection>

      <InspectorSection
        title="Session status"
        open={inspectorSections.signals}
        onToggle={() => onToggleSection("signals")}
      >
        <div className="phase75-stat-row">
          <span>Run status</span>
          <strong>{liveState.serverState}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>Live connection</span>
          <strong>{liveState.connected ? "Yes" : "No"}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>Run paused</span>
          <strong>{liveState.livePaused ? "Yes" : "No"}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>History</span>
          <strong>{viewerReady ? "Loaded" : "No run loaded"}</strong>
        </div>
      </InspectorSection>
    </aside>
  );
}

function InspectorSection({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="phase75-inspector-section">
      <button type="button" className="phase75-section-toggle" onClick={onToggle}>
        <span>{title}</span>
        <span>{open ? "−" : "+"}</span>
      </button>
      {open && <div className="phase75-section-body">{children}</div>}
    </section>
  );
}

function MetricBar({ label, value, scale }: { label: string; value: number; scale: number }) {
  const width = Math.max(8, Math.min(100, (value / Math.max(scale, 1)) * 100));
  return (
    <div className="phase75-metric-bar">
      <div className="phase75-stat-row">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="phase75-metric-track">
        <div className="phase75-metric-fill" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
