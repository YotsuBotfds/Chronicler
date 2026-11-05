import { Suspense, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import type {
  BatchReport,
  BatchRunSummary,
  Bundle,
  CheckpointStatus,
  Command,
  Event,
  LobbyInit,
  NewChronicleEntry,
  PauseContext,
  StartCommand,
  TurnSnapshot,
  WorldState,
} from "../../types";
import { isLegacyBundle } from "../../types";
import { isObservationEventType, observationEventKnown } from "../../lib/observedSystems";
import type { BatchConfig, FeatureSelection } from "../../types";
import { featurePayload } from "../../lib/featureCatalog";
import type { BatchState } from "../../hooks/useBatchConnection";
import { ERA_LABELS } from "../../lib/format";
import {
  buildCivilizationViews, isFounded, type CivilizationEntry, type CivilizationView,
} from "../../lib/civilizationViews";
import { snapshotPositionAt } from "../../lib/civRows";
import type { ArtifactIdentity } from "../../lib/artifactIdentity";
import { SavedWorldDetails } from "./SavedWorldDetails";
import { accountsForEvent, decodeAccounts } from "../../lib/historiography";
import {
  BatchCompare, BatchPanel, ChronicleSources, InterventionPanel, preloadPanels, RegionHistoryInspector,
  SystemsPanel,
} from "./lazyPanels";
import { SetupRail, type SetupState } from "./SetupRail";
import { PanelLoading } from "./PanelLoading";
import { foodCrisisSpans } from "../../lib/food";
import {
  availableMapLayers, buildMapLayer, defaultTechnique, practisedTechniquesBy, type MapLayerKey,
} from "../../lib/mapLayers";
import { eventByKey } from "../../lib/bundleIndex";
import {
  atlasPoint,
  buildEventFeed,
  buildTradeLinks,
  bundleWorldKind,
  eventKey,
  eventProvenance,
  percentToTurn,
  pinFrame,
  terrainAt,
  UNAVAILABLE,
  type PinFrame,
} from "./appShellHelpers";
import type { AppSurface, LiveTimelineControls, MapNode, OverlayKey, RegionLike, SelectedEntity } from "./appShellTypes";
import { MapViewport } from "./MapViewport";
// The lazy panels' styles stay in the entry stylesheet, in the cascade order
// they had when the panels were static imports (before the shell's own).
import "../region-history.css";
import "../systems/systems.css";
import "./app-shell.css";

import { WhereToLook } from "../WhereToLook";
import type { WhatIfControls, WhatIfPair } from "../../lib/whatIf";

import { TimelineRail } from "./TimelineRail";
import { InterestingPeriods } from "../InterestingPeriods";
import { TerritoryChanges } from "../TerritoryChanges";
import { HistoricalSearch } from "../HistoricalSearch";
import type { HistoricalSearchResult } from "../../lib/historicalSearch";
import { exactSnapshot, type HistoryEntity } from "../../lib/historyComparison";
// The inspector's civilization history styles keep their place in the entry
// stylesheet (before InstitutionHistory's), as when this file imported it.
import "../civilization-history.css";
import { InstitutionHistory } from "../InstitutionHistory";
import { RightInspector } from "./RightInspector";
import { InvestigationBookmarks } from "../InvestigationBookmarks";
import { InvestigationPacket } from "../InvestigationPacket";
import { useDialogFocus } from "../../hooks/useDialogFocus";
import { resolveInvestigationTarget, type InvestigationTarget } from "../../lib/investigationPacket";

// App.tsx and the shell's tests name the surfaces from here.
export type { AppSurface } from "./appShellTypes";

type LeftRailTab = "launch" | "status" | "chronicle" | "events" | "runs";

interface AppShellProps {
  surface: AppSurface;
  onSurfaceChange: (surface: AppSurface) => void;
  bundle: Bundle | null;
  artifactIdentity?: ArtifactIdentity | null;
  bundleLoading: boolean;
  error: string | null;
  liveNotice?: string | null;
  isLive: boolean;
  connected: boolean;
  serverState: "connecting" | "lobby" | "starting" | "running" | "completed";
  currentTurn: number;
  playing: boolean;
  speed: number;
  onSeek: (turn: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSetSpeed: (speed: number) => void;
  lobbyInit: LobbyInit | null;
  starting: boolean;
  onLaunch?: (params: Omit<StartCommand, "type">) => void;
  batchState?: BatchState;
  batchReport?: BatchReport | null;
  batchProgress?: { completed: number; total: number; currentSeed: number } | null;
  batchError?: string | null;
  onBatchStart?: (config: BatchConfig) => void;
  onBatchCancel?: () => void;
  onBatchReset?: () => void;
  onOpenBatchResult?: (path: string) => void;
  onOpenBundleFile: (file: File) => void;
  liveTimeline?: LiveTimelineControls;
  liveWhatIf?: WhatIfControls;
  livePaused?: boolean;
  livePauseContext?: PauseContext | null;
  liveSendCommand?: (cmd: Command) => void;
  liveForkedPath?: string | null;
  liveForkedHint?: string | null;
  liveCheckpointStatus?: CheckpointStatus | null;
  liveSaveCheckpoint?: () => void;
  liveReconnecting?: boolean;
}

interface ChronicleFeedItem {
  id: string;
  turn: number;
  title: string;
  body: string;
  eyebrow: string;
  accent: "gold" | "cyan" | "ember" | "stone";
  /** A narrated entry (its provenance lists the passage's sources). */
  entry?: NewChronicleEntry;
}

const FLOW_STEPS: { surface: AppSurface; label: string; index: string }[] = [
  { surface: "setup", label: "Setup", index: "01" },
  { surface: "progress", label: "Progress", index: "02" },
  { surface: "overview", label: "Overview", index: "03" },
  { surface: "character", label: "Character", index: "04" },
  { surface: "trade", label: "Trade", index: "05" },
  { surface: "campaign", label: "Campaign", index: "06" },
  { surface: "batch", label: "Batch Lab", index: "07" },
];

/** The timeline of a shell without a bundle (one array, so its index is built once). */
const NO_EVENTS: Event[] = [];

/**
 * The snapshot shown at `currentTurn`: the latest at or before it. Null
 * without history and before the first snapshot (a resumed run's history
 * starts late): a later snapshot never stands in, and the shell shows no
 * per-turn values there.
 */
function findCurrentSnapshot(bundle: Bundle | null, currentTurn: number): TurnSnapshot | null {
  if (!bundle) {
    return null;
  }
  const position = snapshotPositionAt(bundle.history, currentTurn);
  return position >= 0 ? bundle.history[position] : null;
}

function dominantCivilization(civilizations: CivilizationView[]): CivilizationView | null {
  if (civilizations.length === 0) {
    return null;
  }

  return [...civilizations].sort((left, right) => {
    const leftTotal = left.population + left.military + left.economy + left.culture + left.stability;
    const rightTotal = right.population + right.military + right.economy + right.culture + right.stability;
    return rightTotal - leftTotal;
  })[0];
}

function buildEraBands(history: TurnSnapshot[], maxTurn: number): { label: string; start: number; end: number }[] {
  if (history.length === 0) {
    const fallbackLabels = ["Founding", "Expansion", "Maturity", "Fracture", "Late Age"];
    const step = Math.max(1, Math.floor(maxTurn / fallbackLabels.length));
    return fallbackLabels.map((label, index) => ({
      label,
      start: Math.max(1, index * step + 1),
      end: index === fallbackLabels.length - 1 ? maxTurn : Math.min(maxTurn, (index + 1) * step),
    }));
  }

  const boundaries: { turn: number; label: string }[] = [];
  const seen = new Set<string>();
  for (const snapshot of history) {
    for (const civ of Object.values(snapshot.civ_stats)) {
      if (!seen.has(civ.tech_era)) {
        seen.add(civ.tech_era);
        boundaries.push({
          turn: snapshot.turn,
          label: ERA_LABELS[civ.tech_era as keyof typeof ERA_LABELS] ?? civ.tech_era,
        });
      }
    }
  }

  const ordered = boundaries.sort((left, right) => left.turn - right.turn);
  if (ordered.length === 0) {
    return [{ label: "Recorded Era", start: 1, end: maxTurn }];
  }

  return ordered.map((boundary, index) => ({
    label: boundary.label,
    start: boundary.turn,
    end: ordered[index + 1] ? ordered[index + 1].turn - 1 : maxTurn,
  }));
}

function buildNarratedSpans(chronicleEntries: Bundle["chronicle_entries"] | undefined): { start: number; end: number }[] {
  if (!chronicleEntries) {
    return [];
  }

  if (isLegacyBundle(chronicleEntries)) {
    return Object.keys(chronicleEntries)
      .map((turnString) => Number(turnString))
      .filter((turn) => !Number.isNaN(turn))
      .map((turn) => ({ start: turn, end: turn }))
      .sort((left, right) => left.start - right.start);
  }

  return chronicleEntries
    .map((entry) => ({
      start: entry.covers_turns[0],
      end: entry.covers_turns[1],
    }))
    .sort((left, right) => left.start - right.start);
}

function buildChronicleFeed(bundle: Bundle | null, currentTurn: number): ChronicleFeedItem[] {
  if (!bundle) {
    return [];
  }

  if (isLegacyBundle(bundle.chronicle_entries)) {
    const items: ChronicleFeedItem[] = [];
    for (const [turnString, reflection] of Object.entries(bundle.era_reflections)) {
      const turn = Number(turnString);
      if (!Number.isNaN(turn) && turn <= currentTurn) {
        items.push({
          id: `reflection-${turn}`,
          turn,
          title: `Reflection at Turn ${turn}`,
          body: reflection,
          eyebrow: "Era Reflection",
          accent: "gold",
        });
      }
    }

    for (const [turnString, narrative] of Object.entries(bundle.chronicle_entries)) {
      const turn = Number(turnString);
      if (!Number.isNaN(turn) && turn <= currentTurn) {
        items.push({
          id: `chronicle-${turn}`,
          turn,
          title: `Turn ${turn}`,
          body: narrative,
          eyebrow: "Chronicle",
          accent: "cyan",
        });
      }
    }

    return items.sort((left, right) => left.turn - right.turn).slice(-14);
  }

  // A curated entry narrates its moment through its last turn (the narrator
  // reads the record after it), so it appears once that turn has passed.
  const items = bundle.chronicle_entries
    .filter((entry) => entry.covers_turns[1] <= currentTurn)
    .map<ChronicleFeedItem>((entry, index) => ({
      id: `segment-${index}`,
      turn: entry.covers_turns[0],
      title: `Turns ${entry.covers_turns[0]}-${entry.covers_turns[1]}`,
      body: entry.narrative,
      eyebrow: entry.narrative_role,
      accent:
        entry.narrative_role === "climax"
          ? "ember"
          : entry.narrative_role === "resolution"
            ? "gold"
            : "cyan",
      entry,
    }));

  const reflections = Object.entries(bundle.era_reflections)
    .map(([turnString, text]) => ({
      id: `reflection-${turnString}`,
      turn: Number(turnString),
      title: `Reflection at Turn ${turnString}`,
      body: text,
      eyebrow: "Era Reflection",
      accent: "gold" as const,
    }))
    .filter((item) => !Number.isNaN(item.turn) && item.turn <= currentTurn);

  // A gap's summary counts every turn of the gap: shown once the gap has passed.
  const gaps = (bundle.gap_summaries ?? [])
    .filter((gap) => gap.turn_range[1] <= currentTurn)
    .map<ChronicleFeedItem>((gap, index) => ({
      id: `gap-${index}`,
      turn: gap.turn_range[0],
      title: `Mechanical window ${gap.turn_range[0]}-${gap.turn_range[1]}`,
      body: `${gap.event_count} events, ${gap.territory_changes} territorial shifts, dominant type ${gap.top_event_type}.`,
      eyebrow: "Mechanical Gap",
      accent: "stone",
    }));

  return [...items, ...reflections, ...gaps]
    .sort((left, right) => left.turn - right.turn)
    .slice(-14);
}

function buildRunSignalSummary(summary: BatchRunSummary | null): string {
  if (!summary) {
    return "Ranked run summaries appear here after a batch completes.";
  }
  if (summary.signal_flags.length === 0) {
    return "Balanced run with no standout anomaly signals.";
  }
  return summary.signal_flags.join(" · ");
}

function computeAtlasLayout(
  regions: RegionLike[],
  controllers: Record<string, string | null>,
  frame: PinFrame,
): MapNode[] {
  if (regions.length === 0) {
    return [];
  }

  const hasPins = regions.some((region) => region.x !== null && region.y !== null);
  if (hasPins) {
    return regions.map((region) => ({
      region,
      controller: controllers[region.name],
      ...atlasPoint(region.x ?? frame.x0 + frame.sx / 2, region.y ?? frame.y0 + frame.sy / 2, frame),
    }));
  }

  const grouped = new Map<string, RegionLike[]>();
  for (const region of regions) {
    const key = controllers[region.name] ?? "__uncontrolled__";
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key)?.push(region);
  }

  const groupKeys = [...grouped.keys()];
  const centerX = 500;
  const centerY = 310;
  const radiusX = 280;
  const radiusY = 180;
  const nodes: MapNode[] = [];

  groupKeys.forEach((groupKey, groupIndex) => {
    const groupRegions = grouped.get(groupKey) ?? [];
    const angle = (Math.PI * 2 * groupIndex) / Math.max(groupKeys.length, 1) - Math.PI / 2;
    const groupCenterX = centerX + Math.cos(angle) * radiusX;
    const groupCenterY = centerY + Math.sin(angle) * radiusY;
    const localRadius = Math.max(32, 26 + groupRegions.length * 6);

    groupRegions.forEach((region, regionIndex) => {
      const localAngle = (Math.PI * 2 * regionIndex) / Math.max(groupRegions.length, 1) - Math.PI / 2;
      nodes.push({
        region,
        controller: controllers[region.name],
        x: groupCenterX + Math.cos(localAngle) * localRadius,
        y: groupCenterY + Math.sin(localAngle) * localRadius,
      });
    });
  });

  return nodes;
}

function buildRegionConnections(nodes: MapNode[]): Array<{ source: MapNode; target: MapNode }> {
  const grouped = new Map<string, MapNode[]>();
  for (const node of nodes) {
    const key = node.controller ?? "__uncontrolled__";
    if (!grouped.has(key)) {
      grouped.set(key, []);
    }
    grouped.get(key)?.push(node);
  }

  const connections: Array<{ source: MapNode; target: MapNode }> = [];
  for (const group of grouped.values()) {
    for (let index = 1; index < group.length; index += 1) {
      connections.push({ source: group[index - 1], target: group[index] });
    }
  }
  return connections;
}

function computeControllerCentroids(nodes: MapNode[]): Record<string, { x: number; y: number }> {
  const grouped = new Map<string, MapNode[]>();
  for (const node of nodes) {
    if (!node.controller) {
      continue;
    }
    if (!grouped.has(node.controller)) {
      grouped.set(node.controller, []);
    }
    grouped.get(node.controller)?.push(node);
  }

  const centroids: Record<string, { x: number; y: number }> = {};
  for (const [controller, group] of grouped.entries()) {
    const totalX = group.reduce((sum, node) => sum + node.x, 0);
    const totalY = group.reduce((sum, node) => sum + node.y, 0);
    centroids[controller] = {
      x: totalX / group.length,
      y: totalY / group.length,
    };
  }
  return centroids;
}

function buildCampaignLinks(
  centroids: Record<string, { x: number; y: number }>,
  relationships: Record<string, Record<string, { disposition: string }>> | null,
  civNames: string[],
): Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; disposition: string }> {
  const links: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; disposition: string }> = [];
  const seen = new Set<string>();

  for (const civName of civNames) {
    const relationMap = relationships?.[civName] ?? {};
    for (const [other, relation] of Object.entries(relationMap)) {
      const key = [civName, other].sort().join("--");
      if (seen.has(key) || !centroids[civName] || !centroids[other]) {
        continue;
      }
      if (relation.disposition !== "hostile" && relation.disposition !== "suspicious") {
        continue;
      }
      seen.add(key);
      links.push({
        key,
        source: centroids[civName],
        target: centroids[other],
        disposition: relation.disposition,
      });
    }
  }

  return links;
}

function selectionDescription(
  surface: AppSurface,
  selection: SelectedEntity | null,
  summary: BatchRunSummary | null,
  currentTurn: number,
  eventRecorded = true,
): string {
  if (surface === "batch") {
    return buildRunSignalSummary(summary);
  }
  if (!selection) {
    return "Choose a region, civilization, or event to view its recorded details.";
  }
  if (selection.kind === "event") {
    // An event pinned at a later turn is not described before it happens.
    if (!eventRecorded || (selection.turn !== undefined && selection.turn > currentTurn)) {
      return `Pinned event not yet recorded at turn ${currentTurn}.`;
    }
    return `Pinned to ${selection.label} at turn ${selection.turn ?? "?"}.`;
  }
  return `${selection.kind === "region" ? "Region" : "Focus"} selected: ${selection.label}.`;
}

function totalTurnsFor(bundle: Bundle | null): number {
  return bundle?.metadata.total_turns ?? bundle?.history.length ?? 1;
}

function sortCivilizations(civilizations: CivilizationView[]): CivilizationView[] {
  return [...civilizations].sort((left, right) => {
    const leftScore = left.economy + left.culture + left.military + left.population + left.stability;
    const rightScore = right.economy + right.culture + right.military + right.population + right.stability;
    return rightScore - leftScore;
  });
}

type LeftRailProps = {
  surface: AppSurface;
  leftRailTab: LeftRailTab;
  onTabChange: (tab: LeftRailTab) => void;
  chronicleFeed: ChronicleFeedItem[];
  eventFeed: Event[];
  onJumpToTurn: (turn: number) => void;
  onSelectEvent: (event: Event) => void;
  /** The bundle a passage's sources resolve against, and the scrubbed turn. */
  sourceBundle: Bundle | null;
  currentTurn: number;
  setupState: SetupState;
  onScenarioChange: (value: string) => void;
  onSeedChange: (value: string) => void;
  onTurnsChange: (value: number) => void;
  onCivsChange: (value: number) => void;
  onRegionsChange: (value: number) => void;
  onSimModelChange: (value: string) => void;
  onNarrativeModelChange: (value: string) => void;
  onCustomSimModelChange: (value: string) => void;
  onCustomNarrativeModelChange: (value: string) => void;
  onRandomSeed: () => void;
  onResumeBrowse: () => void;
  onResumeDrop: (file: File) => void;
  onClearResume: () => void;
  onFeaturesChange: (features: FeatureSelection) => void;
  onLaunch: () => void;
  batchState: BatchState;
  batchReport: BatchReport | null;
  batchProgress: { completed: number; total: number; currentSeed: number } | null;
  batchError: string | null;
  onBatchStart?: (config: BatchConfig) => void;
  onBatchCancel?: () => void;
  onBatchReset?: () => void;
  batchSummaries: BatchRunSummary[];
  batchSelectionPath: string | null;
  onSelectBatchRun: (path: string) => void;
  onOpenBatchResult?: (path: string) => void;
};

export function AppShell({
  surface,
  onSurfaceChange,
  bundle,
  artifactIdentity,
  bundleLoading,
  error,
  liveNotice,
  isLive,
  connected,
  serverState,
  currentTurn,
  playing,
  speed,
  onSeek,
  onPlay,
  onPause,
  onSetSpeed,
  lobbyInit,
  starting,
  onLaunch,
  batchState = "idle",
  batchReport = null,
  batchProgress = null,
  batchError = null,
  onBatchStart,
  onBatchCancel,
  onBatchReset,
  onOpenBatchResult,
  onOpenBundleFile,
  liveTimeline,
  liveWhatIf,
  livePaused,
  livePauseContext,
  liveSendCommand,
  liveForkedPath,
  liveForkedHint,
  liveCheckpointStatus,
  liveSaveCheckpoint,
  liveReconnecting,
}: AppShellProps) {
  const scenarios = lobbyInit?.scenarios ?? [];
  const availableModels = lobbyInit?.models.length ? lobbyInit.models : [""];
  const primaryModel = availableModels[0] ?? "";
  const defaults = lobbyInit?.defaults ?? { turns: 500, civs: 4, regions: 16, seed: null };
  const openBundleRef = useRef<HTMLInputElement>(null);
  const resumeFileRef = useRef<HTMLInputElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const [leftRailTabSelection, setLeftRailTabSelection] = useState<LeftRailTab>("launch");
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity | null>(null);
  const [activeOverlays, setActiveOverlays] = useState<OverlayKey[]>(["borders", "settlements", "chronicle"]);
  const [mapLayerSelection, setMapLayerSelection] = useState<MapLayerKey>("control");
  const [techniqueSelection, setTechniqueSelection] = useState<string | null>(null);
  const [inspectorSections, setInspectorSections] = useState<Record<string, boolean>>({
    selection: true,
    languages: true,
    metrics: true,
    network: true,
    signals: true,
    batch: true,
  });
  const [showCompareOverlay, setShowCompareOverlay] = useState(false);
  const compareDialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(compareDialogRef, showCompareOverlay, () => setShowCompareOverlay(false));
  const [compareMode, setCompareMode] = useState<"runs" | "batch">("runs");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRequest, setHistoryRequest] = useState(0);
  const worldKey = bundle ? isLive ? `live:${bundle.metadata.seed}:${bundle.world_state.name}`
    : artifactIdentity?.sha256 ?? `${bundle.metadata.seed}:${bundle.metadata.generated_at}:${bundle.world_state.name}` : "";
  const [historyChoice, setHistoryChoice] = useState<{ world: string; entity: HistoryEntity } | null>(null);
  const historyFocus = historyChoice?.world === worldKey ? historyChoice.entity : null;
  const [territoryChoice, setTerritoryChoice] = useState<{ world: string; turn: number; from: number | null; civ: number | null } | null>(null);
  const [searchChoice, setSearchResult] = useState<{ world: string; result: HistoricalSearchResult } | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [bookmarkOpen, setBookmarkOpen] = useState(false);
  const [inspectedPause, setInspectedPause] = useState<string | null>(null);
  const pauseKey = `${worldKey}:${livePauseContext?.turn ?? "none"}`;
  const inspectingPausedWorld = !!livePaused && inspectedPause === pauseKey;
  const searchResult = searchChoice?.world === worldKey ? searchChoice.result : null;
  const searchEvidenceKnown = !!searchResult && (searchResult.turn === null || searchResult.turn <= currentTurn)
    && (searchResult.lastRecordedTurn === null || searchResult.lastRecordedTurn <= currentTurn);
  const [whatIfPair, setWhatIfPair] = useState<WhatIfPair | null>(null);
  const [batchSelectionPath, setBatchSelectionPath] = useState<string | null>(null);

  const [scenario, setScenario] = useState("");
  const [seed, setSeed] = useState("");
  const [turns, setTurns] = useState(defaults.turns);
  const [civs, setCivs] = useState(defaults.civs);
  const [regions, setRegions] = useState(defaults.regions);
  const [simModel, setSimModel] = useState(primaryModel);
  const [narrativeModel, setNarrativeModel] = useState(primaryModel);
  const [customSimModel, setCustomSimModel] = useState("");
  const [customNarrativeModel, setCustomNarrativeModel] = useState("");
  const [resumeState, setResumeState] = useState<WorldState | null>(null);
  const [resumeTurn, setResumeTurn] = useState<number | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [features, setFeatures] = useState<FeatureSelection>({});
  const syncSetupDefaults = useEffectEvent(() => {
    setTurns(defaults.turns);
    setCivs(defaults.civs);
    setRegions(defaults.regions);
    setSimModel(primaryModel);
    setNarrativeModel(primaryModel);
  });
  const syncOverlayPreset = useEffectEvent(() => {
    // The campaign surface opens on the war layer (when the bundle has it); the others on control.
    setMapLayerSelection(surface === "campaign" ? "wars" : "control");
    if (surface === "trade") {
      setActiveOverlays(["borders", "settlements", "trade"]);
    } else if (surface === "campaign") {
      setActiveOverlays(["borders", "campaign", "fog"]);
    } else if (surface === "character") {
      setActiveOverlays(["borders", "settlements", "asabiya"]);
    } else {
      setActiveOverlays(["borders", "settlements", "chronicle"]);
    }
  });

  const currentSnapshot = findCurrentSnapshot(bundle, currentTurn);
  // Every world civ at the snapshot; only those founded by then rank, show
  // chips and summaries and can be the default focus.
  const civilizationEntries = buildCivilizationViews(bundle, currentSnapshot);
  const civilizations = sortCivilizations(civilizationEntries.filter(isFounded));
  const leadCivilization = dominantCivilization(civilizations);
  const totalTurns = totalTurnsFor(bundle);
  // Whole-run timeline marks: built once per history and chronicle, not per scrubbed turn.
  const bundleHistory = bundle?.history;
  const eraBands = useMemo(() => buildEraBands(bundleHistory ?? [], totalTurns), [bundleHistory, totalTurns]);
  const chronicleEntries = bundle?.chronicle_entries;
  const narratedSpans = useMemo(() => buildNarratedSpans(chronicleEntries), [chronicleEntries]);
  const chronicleFeed = buildChronicleFeed(bundle, currentTurn);
  const selectedScenario = scenarios.find((entry) => entry.file === scenario) ?? null;
  const civsDisabled = resumeState !== null || (selectedScenario?.civs?.length ?? 0) > 0;
  const regionsDisabled = resumeState !== null || (selectedScenario?.regions?.length ?? 0) > 0;
  const previewRegions = resumeState
    ? resumeState.regions.map((region) => ({
      name: region.name,
      terrain: region.terrain,
      x: region.x,
      y: region.y,
      resources: region.resources,
      carrying_capacity: region.carrying_capacity,
    }))
    : selectedScenario?.regions.map((region) => ({
      ...region,
      resources: undefined,
      carrying_capacity: undefined,
    })) ?? [];
  const previewControllers = resumeState
    ? Object.fromEntries(resumeState.regions.map((region) => [region.name, region.controller]))
    : {};
  const previewCivilizations = resumeState
    ? resumeState.civilizations.map((civilization) => ({
      name: civilization.name,
      values: civilization.values ?? [],
    }))
    : selectedScenario?.civs ?? [];
  // The world state is the present only for a bundle without history (a
  // live session before its first turn); before the first snapshot of a
  // recorded history no controller is known.
  const worldIsPresent = !!bundle && bundle.history.length === 0;
  const mapSnapshot = bundle ? exactSnapshot(bundle, currentTurn) : null;
  const regionControllers = mapSnapshot?.region_control
    ?? (bundle
      ? (worldIsPresent
        ? Object.fromEntries(bundle.world_state.regions.map((region) => [region.name, region.controller]))
        : {})
      : previewControllers);
  const atlasRegions: RegionLike[] = bundle
    ? bundle.world_state.regions
    : previewRegions;
  // Fit the atlas to the region pins (and procedural sea zones, drawn on the sea layer).
  const seaZones = bundle?.world_state.geography?.sea_zones;
  const atlasFrame = useMemo(() => pinFrame([
    ...atlasRegions.filter((region) => region.x !== null && region.y !== null),
    ...(seaZones ?? []),
  ]), [atlasRegions, seaZones]);
  const atlasNodes = computeAtlasLayout(atlasRegions, regionControllers, atlasFrame);
  const mapLayers = useMemo(() => availableMapLayers(bundle), [bundle]);
  const mapLayer: MapLayerKey = bundle && mapLayers.includes(mapLayerSelection) ? mapLayerSelection : "control";
  const famine = useMemo(() => (bundle ? foodCrisisSpans(bundle.events_timeline) : []), [bundle]);
  const regionNames = useMemo(() => (bundle ? bundle.world_state.regions.map((region) => region.name) : []), [bundle]);
  // Techniques practised by the scrubbed turn (a later invention is not offered).
  const techniqueOptions = useMemo(
    () => (bundle ? practisedTechniquesBy(bundle.history, currentTurn) : []),
    [bundle, currentTurn],
  );
  const technique = techniqueSelection && techniqueOptions.includes(techniqueSelection)
    ? techniqueSelection
    : (mapLayer === "techniques" ? defaultTechnique(currentSnapshot, techniqueOptions) : null);
  const mapLayerView = bundle
    ? buildMapLayer(mapLayer, { bundle, snapshot: exactSnapshot(bundle, currentTurn), famine, technique,
      territoryFromTurn: territoryChoice?.world === worldKey && territoryChoice.turn === currentTurn ? territoryChoice.from ?? undefined : undefined,
      territoryCivilizationIndex: territoryChoice?.world === worldKey && territoryChoice.turn === currentTurn ? territoryChoice.civ
        : selectedEntity?.kind === "civilization" ? bundle.world_state.civilizations.findIndex((row) => row.name === selectedEntity.id) : null,
    })
    : null;
  const atlasConnections = buildRegionConnections(atlasNodes);
  const controllerCentroids = computeControllerCentroids(atlasNodes);
  const worldRelationships = worldIsPresent ? (bundle?.world_state.relationships ?? null) : null;
  const snapshotRelationships = currentSnapshot?.relationships ?? null;
  const tradeRelationships = snapshotRelationships ?? worldRelationships;
  const tradeLinks = buildTradeLinks(
    controllerCentroids,
    tradeRelationships,
    civilizations.map((civilization) => civilization.name),
    currentSnapshot?.trade_routes ?? null,
  );
  const campaignLinks = buildCampaignLinks(
    controllerCentroids,
    snapshotRelationships,
    civilizations.map((civilization) => civilization.name),
  );
  const observationSourceTurn = (currentSnapshot?.turn ?? currentTurn) - 1;
  const eventFeed = buildEventFeed(
    bundle?.events_timeline ?? NO_EVENTS,
    currentTurn,
    selectedEntity?.kind === "civilization" ? selectedEntity.id : null,
    observationSourceTurn,
  );
  const batchSummaries = batchReport?.run_summaries ?? [];
  const leftRailTab = surface === "setup"
    ? "launch"
    : surface === "progress"
      ? "status"
      : surface === "batch"
        ? "runs"
        : leftRailTabSelection === "chronicle" || leftRailTabSelection === "events"
          ? leftRailTabSelection
          : "chronicle";
  const effectiveBatchSelectionPath = batchSelectionPath ?? batchSummaries[0]?.bundle_path ?? null;
  const selectedBatchSummary = batchSummaries.find((summary) => summary.bundle_path === effectiveBatchSelectionPath)
    ?? batchSummaries[0]
    ?? null;
  const syncSelectedEntity = useEffectEvent(() => {
    if (!bundle) {
      setSelectedEntity((current) => (surface === "batch" ? current : null));
      return;
    }

    const selectedStillExists = selectedEntity?.kind === "region"
      ? bundle.world_state.regions.some((region) => region.name === selectedEntity.id)
      : selectedEntity?.kind === "civilization"
        ? civilizationEntries.some((civilization) => civilization.name === selectedEntity.id)
        : selectedEntity?.kind === "event"
          ? eventByKey(bundle.events_timeline, selectedEntity.id) !== null
          : true;

    if (!selectedStillExists) {
      if (leadCivilization) {
        setSelectedEntity({
          kind: "civilization",
          id: leadCivilization.name,
          label: leadCivilization.name,
        });
      } else if (bundle.world_state.regions[0]) {
        setSelectedEntity({
          kind: "region",
          id: bundle.world_state.regions[0].name,
          label: bundle.world_state.regions[0].name,
        });
      }
    }
  });

  // The lazy panels' chunks: fetched once the first screen has painted (when
  // the browser is idle), and at once when a bundle starts loading or arrives.
  useEffect(() => {
    const idle = typeof window.requestIdleCallback === "function";
    const handle = idle
      ? window.requestIdleCallback(() => void preloadPanels(), { timeout: 2000 })
      : window.setTimeout(() => void preloadPanels(), 200);
    return () => {
      if (idle) {
        window.cancelIdleCallback(handle);
      } else {
        window.clearTimeout(handle);
      }
    };
  }, []);

  useEffect(() => {
    if (bundle || bundleLoading) {
      void preloadPanels();
    }
  }, [bundle, bundleLoading]);

  useEffect(() => {
    syncSetupDefaults();
  }, [defaults.turns, defaults.civs, defaults.regions, primaryModel]);

  useEffect(() => {
    syncOverlayPreset();
  }, [surface]);

  useEffect(() => {
    syncSelectedEntity();
  }, [bundle, leadCivilization?.name, surface]);

  const headerWorldName = bundle?.world_state.name
    ?? resumeState?.name
    ?? selectedScenario?.world_name
    ?? selectedScenario?.name
    ?? "Chronicler Viewer";
  const headerScenario = bundle?.metadata.scenario_name
    ?? selectedScenario?.name
    ?? (bundle ? bundleWorldKind(bundle.world_state) : resumeState ? "Resumed world" : "Procedural setup");
  const headerSeed = bundle?.metadata.seed
    ?? resumeState?.seed
    ?? (seed === "" ? defaults.seed : Number(seed));
  const headerInterestingness = bundle?.metadata.interestingness_score ?? selectedBatchSummary?.interestingness_score ?? null;

  const handleResumeFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result as string);
        if (typeof parsed.turn !== "number" || !Array.isArray(parsed.civilizations)) {
          setResumeError("Invalid save file - missing required fields");
          return;
        }
        setResumeState(parsed as WorldState);
        setResumeTurn(parsed.turn);
        setResumeError(null);
      } catch {
        setResumeError("Invalid save file - not valid JSON");
      }
    };
    reader.readAsText(file);
  };

  const clearResume = () => {
    setResumeState(null);
    setResumeTurn(null);
    setResumeError(null);
    if (resumeFileRef.current) {
      resumeFileRef.current.value = "";
    }
  };

  const handleLaunch = () => {
    if (!onLaunch) {
      return;
    }

    const resolvedSimModel = simModel === "__custom__" ? customSimModel : simModel;
    const resolvedNarrativeModel = narrativeModel === "__custom__" ? customNarrativeModel : narrativeModel;
    const resolvedCivs = resumeState
      ? resumeState.civilizations.length
      : civsDisabled
        ? (selectedScenario?.civs?.length || defaults.civs)
        : civs;
    const resolvedRegions = resumeState
      ? resumeState.regions.length
      : regionsDisabled
        ? (selectedScenario?.regions?.length || defaults.regions)
        : regions;
    // Features apply to new worlds; nothing selected sends no field.
    const requested = resumeState ? undefined : featurePayload(features);
    onLaunch({
      scenario: resumeState ? null : (scenario || null),
      turns,
      seed: seed === "" ? null : Number(seed),
      civs: resolvedCivs,
      regions: resolvedRegions,
      sim_model: resolvedSimModel,
      narrative_model: resolvedNarrativeModel,
      narrator: "local",
      resume_state: resumeState,
      ...(requested ? { features: requested } : {}),
    });
  };

  const toggleOverlay = (overlay: OverlayKey) => {
    setActiveOverlays((current) => (
      current.includes(overlay)
        ? current.filter((entry) => entry !== overlay)
        : [...current, overlay]
    ));
  };

  const toggleInspectorSection = (section: string) => {
    setInspectorSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  };

  const handleTrackSeek = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!trackRef.current || !bundle) {
      return;
    }
    const rect = trackRef.current.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    onSeek(percentToTurn(percent, totalTurns));
  };

  const selectEvent = (event: Event) => {
    setSelectedEntity({
      kind: "event",
      id: eventKey(event),
      label: event.description,
      turn: event.turn,
    });
  };
  const selectHistoryEntity = (entity: HistoryEntity) => {
    setSelectedEntity({ kind: entity.kind, id: entity.name, label: entity.name });
    setHistoryChoice({ world: worldKey, entity });
  };
  const selectRegion = (name: string) => selectHistoryEntity({ kind: "region", name });
  const selectCivilization = (name: string) => selectHistoryEntity({ kind: "civilization", name });
  const inspectHistory = (entity: HistoryEntity) => { selectHistoryEntity(entity); setHistoryOpen(true); };
  const inspectSearch = (result: HistoricalSearchResult) => {
    setSearchResult({ world: worldKey, result });
    if (result.mapEntity) inspectHistory(result.mapEntity);
  };

  const selectedRegion = selectedEntity?.kind === "region"
    ? atlasRegions.find((region) => region.name === selectedEntity.id) ?? null
    : null;
  const selectedCivilization = selectedEntity?.kind === "civilization"
    ? civilizationEntries.find((civilization) => civilization.name === selectedEntity.id) ?? null
    : null;
  const selectedEvent = selectedEntity?.kind === "event"
    ? (bundle ? eventByKey(bundle.events_timeline, selectedEntity.id) : null)
    : null;
  const investigationTarget: InvestigationTarget | null = (() => {
    const focus = selectedEntity && (selectedEntity.kind === "region" || selectedEntity.kind === "civilization")
      ? { kind: selectedEntity.kind, name: selectedEntity.id } : historyFocus;
    if (!bundle || !focus) return null;
    const kind = focus.kind;
    const rows = kind === "region" ? bundle.world_state.regions : bundle.world_state.civilizations;
    const indices = rows.flatMap((row, index) => row.name === focus.name ? [index] : []);
    return indices.length === 1 ? { kind, index: indices[0], name: focus.name } : null;
  })();
  // An event pinned at a later turn stays selected while scrubbing back, but
  // is not shown before its turn; its consequences and accounts are those
  // recorded by the scrubbed turn (the event log's convention).
  const selectedEventRecorded = !!selectedEvent && selectedEvent.turn <= currentTurn
    && observationEventKnown(selectedEvent, observationSourceTurn);
  const selectedEventProvenance = eventProvenance(bundle?.events_timeline ?? NO_EVENTS, selectedEvent, currentTurn, observationSourceTurn);
  const historiography = bundle?.historiography;
  const accountRows = useMemo(
    () => (historiography ? decodeAccounts(historiography) : []),
    [historiography],
  );
  const selectedEventAccounts = selectedEventRecorded
    ? accountsForEvent(historiography, selectedEvent?.event_id, accountRows,
      isObservationEventType(selectedEvent?.event_type) ? observationSourceTurn : currentTurn)
    : null;
  // The region's terrain at the scrubbed turn (terrain transitions are dated events).
  const selectedRegionTerrain = selectedRegion
    ? (bundle && !worldIsPresent
      ? terrainAt(bundle.events_timeline, selectedRegion.name, selectedRegion.terrain, currentTurn)
      : selectedRegion.terrain)
    : null;
  // The pinned region or civ by index, for the languages panel's names.
  const languageSelection = useMemo(() => {
    if (!bundle?.languages || !selectedEntity) {
      return null;
    }
    if (selectedEntity.kind === "region") {
      const ref = bundle.world_state.regions.findIndex((region) => region.name === selectedEntity.id);
      return ref >= 0 ? { kind: "region" as const, ref } : null;
    }
    if (selectedEntity.kind === "civilization") {
      const ref = bundle.world_state.civilizations.findIndex((civ) => civ.name === selectedEntity.id);
      return ref >= 0 ? { kind: "civ" as const, ref } : null;
    }
    return null;
  }, [bundle, selectedEntity]);

  const viewerReady = bundle !== null;
  const canActivateSurface = (candidate: AppSurface): boolean => {
    if (candidate === "overview" || candidate === "character" || candidate === "trade" || candidate === "campaign") {
      return viewerReady;
    }
    if (candidate === "progress") {
      return serverState === "starting";
    }
    return true;
  };

  return (
    <div className="phase75-shell">
      <input
        ref={openBundleRef}
        type="file"
        aria-label="Open saved world file"
        accept=".json,.ckpt,.checkpoint"
        className="phase75-hidden-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onOpenBundleFile(file);
          }
          event.target.value = "";
        }}
      />

      <TopHeader
        surface={surface}
        worldName={headerWorldName}
        scenarioName={headerScenario}
        seed={headerSeed}
        interestingness={headerInterestingness}
        currentTurn={viewerReady ? currentTurn : null}
        totalTurns={viewerReady ? totalTurns : null}
        connected={connected}
        liveReconnecting={liveReconnecting}
        serverState={serverState}
        viewerReady={viewerReady}
        onOpenBundle={() => openBundleRef.current?.click()}
        onCompare={() => { setWhatIfPair(null); setCompareMode("runs"); setShowCompareOverlay(true); }}
      />

      {error && <div className="phase75-error-banner saved-world-message" role="alert">
        {error}{bundle && <p>The loaded world is still available. Choose another file with Open Existing.</p>}
      </div>}
      {bundle && <SavedWorldDetails bundle={bundle} identity={artifactIdentity} />}
      {bundleLoading && <div className="saved-world-loading" role="status">Reading saved world…</div>}
      {liveNotice && <div className="saved-world-loading" role="status">{liveNotice}</div>}
      {inspectingPausedWorld && <div className="interesting-periods" role="status">
        <p>Simulation paused at turn {livePauseContext?.turn}. Inspecting history does not advance the original world.</p>
        <button type="button" onClick={() => setInspectedPause(null)}>Return to run controls</button>
      </div>}
      <details className="interesting-periods" open={bookmarkOpen} onToggle={(event) => setBookmarkOpen(event.currentTarget.open)}>
        <summary>Bookmarks and investigation export</summary>
        {bookmarkOpen && <>
          <InvestigationBookmarks artifactIdentity={artifactIdentity ?? null} currentTurn={currentTurn}
            target={investigationTarget} panel={historyOpen ? "history" : "conditions"} onRestore={(bookmark) => {
              if (!bundle || artifactIdentity?.sha256 !== bookmark.world.sha256) return "Open the matching source file first. Your current world is kept.";
              const error = resolveInvestigationTarget(bundle, bookmark.target, bookmark.turn);
              if (error) return error;
              onSeek(bookmark.turn);
              selectHistoryEntity({ kind: bookmark.target.kind, name: bookmark.target.name });
              setHistoryOpen(bookmark.panel === "history");
              onSurfaceChange("overview");
            }} />
          {bundle && <InvestigationPacket bundle={bundle} identity={artifactIdentity ?? null}
            target={investigationTarget} turn={currentTurn} />}
        </>}
      </details>

      <ModeTabs
        current={surface}
        onSelect={(candidate) => {
          if (canActivateSurface(candidate)) {
            onSurfaceChange(candidate);
          }
        }}
        canActivateSurface={canActivateSurface}
      />

      <TimelineRail
        surface={surface}
        flowSteps={FLOW_STEPS}
        currentTurn={currentTurn}
        totalTurns={totalTurns}
        bundle={bundle}
        eraBands={eraBands}
        narratedSpans={narratedSpans}
        namedEvents={bundle?.named_events ?? []}
        trackRef={trackRef}
        onTrackSeek={handleTrackSeek}
        playing={playing}
        speed={speed}
        onPlay={onPlay}
        onPause={onPause}
        onSetSpeed={onSetSpeed}
        liveTimeline={liveTimeline}
        onSeek={onSeek}
      />

      {bundle && surface !== "setup" && surface !== "progress" && surface !== "batch" && <>
        <details className="interesting-periods" open={searchOpen} onToggle={(event) => setSearchOpen(event.currentTarget.open)}>
          <summary>Search recorded entities</summary>
          {searchOpen && <HistoricalSearch bundle={bundle} currentTurn={currentTurn} onInspect={inspectSearch}
            onViewRecordedTurn={(result) => { inspectSearch(result); if (result.turn !== null) onSeek(result.turn); }} />}
        </details>
        {searchResult && <details className="interesting-periods" open>
          <summary>Selected search evidence{searchEvidenceKnown ? `: ${searchResult.name}` : ""}</summary>
          {searchEvidenceKnown ? <><p>{searchResult.status} · {searchResult.sourceRef}</p>
            {searchResult.ambiguity && <p>{searchResult.ambiguity}</p>}
            <InstitutionHistory bundle={bundle} currentTurn={currentTurn} selection={searchResult}
              onSelectEvent={selectEvent} onInspectRelated={inspectHistory} onViewRecordedTurn={onSeek} /></> : <p>The selected search record lies beyond this turn. Search again to inspect the observations available here.</p>}
          <button type="button" onClick={() => setSearchResult(null)}>Close search evidence</button>
        </details>}
        <InterestingPeriods bundle={bundle} currentTurn={currentTurn} onSeek={onSeek} onEvent={selectEvent} />
      </>}
      <ValidationRibbon
        visible={surface === "campaign"}
        bundle={bundle}
        batchReport={batchReport}
        selectedCivilization={selectedCivilization}
        civilizations={civilizations}
      />

      {bundle && surface !== "setup" && surface !== "progress" && surface !== "batch" && <WhereToLook
        bundle={bundle} currentTurn={currentTurn} onInspectEntity={(entity) => {
          inspectHistory(entity);
          setHistoryRequest((value) => value + 1);
        }} />}
      {bundle && surface !== "setup" && surface !== "progress" && surface !== "batch" && (
        <details open={historyOpen} className="region-history-disclosure" onToggle={(event) => setHistoryOpen(event.currentTarget.open)}>
          <summary>Compare turns and inspect history</summary>
          {historyOpen && <Suspense fallback={<PanelLoading label="the region history inspector" />}>
            <RegionHistoryInspector
              key={`${worldKey}:${historyRequest}`}
              bundle={bundle}
              artifactIdentity={artifactIdentity}
              selectedRegion={historyFocus?.kind === "region" ? historyFocus.name : selectedRegion?.name}
              selectedCivilization={historyFocus?.kind === "civilization" ? historyFocus.name : selectedCivilization?.name}
              currentTurn={currentTurn}
              onSeek={onSeek}
              onSelectEvent={selectEvent}
              onSelectEntity={selectHistoryEntity}
            />
          </Suspense>}
        </details>
      )}

      {bundle && mapLayer === "territory" && <TerritoryChanges bundle={bundle} currentTurn={currentTurn}
        selectedRegion={selectedRegion?.name} selectedCivilization={selectedCivilization?.name}
        onInspectEntity={inspectHistory} onSeek={onSeek}
        onComparisonChange={(from, civ) => setTerritoryChoice({ world: worldKey, turn: currentTurn, from, civ })} />}
      <div className="phase75-workspace">
        <LeftRail
          surface={surface}
          leftRailTab={leftRailTab}
          onTabChange={setLeftRailTabSelection}
          chronicleFeed={chronicleFeed}
          eventFeed={eventFeed}
          onJumpToTurn={(turn) => onSeek(turn)}
          onSelectEvent={selectEvent}
          sourceBundle={bundle}
          currentTurn={currentTurn}
          setupState={{
            scenario,
            scenarios,
            seed,
            turns,
            civs,
            regions,
            simModel,
            narrativeModel,
            models: availableModels,
            customSimModel,
            customNarrativeModel,
            starting,
            error,
            resumeState,
            resumeTurn,
            resumeError,
            civsDisabled,
            regionsDisabled,
            lobbyReady: !!lobbyInit,
            featureCatalog: lobbyInit?.feature_catalog,
            features,
          }}
          onFeaturesChange={setFeatures}
          onScenarioChange={setScenario}
          onSeedChange={setSeed}
          onTurnsChange={setTurns}
          onCivsChange={setCivs}
          onRegionsChange={setRegions}
          onSimModelChange={setSimModel}
          onNarrativeModelChange={setNarrativeModel}
          onCustomSimModelChange={setCustomSimModel}
          onCustomNarrativeModelChange={setCustomNarrativeModel}
          onRandomSeed={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
          onResumeBrowse={() => resumeFileRef.current?.click()}
          onResumeDrop={handleResumeFile}
          onClearResume={clearResume}
          onLaunch={handleLaunch}
          batchState={batchState}
          batchReport={batchReport}
          batchProgress={batchProgress}
          batchError={batchError}
          onBatchStart={onBatchStart}
          onBatchCancel={onBatchCancel}
          onBatchReset={onBatchReset}
          batchSummaries={batchSummaries}
          batchSelectionPath={effectiveBatchSelectionPath}
          onSelectBatchRun={setBatchSelectionPath}
          onOpenBatchResult={onOpenBatchResult}
        />

        <MapViewport
          surface={surface}
          atlasNodes={atlasNodes}
          atlasConnections={atlasConnections}
          controllerCentroids={controllerCentroids}
          activeOverlays={activeOverlays}
          onToggleOverlay={toggleOverlay}
          mapLayers={mapLayers}
          mapLayer={mapLayer}
          onMapLayerChange={setMapLayerSelection}
          mapLayerView={mapLayerView}
          toAtlas={(x, y) => atlasPoint(x, y, atlasFrame)}
          techniqueOptions={techniqueOptions}
          technique={technique}
          onTechniqueChange={setTechniqueSelection}
          civilizations={civilizations}
          tradeLinks={tradeLinks}
          campaignLinks={campaignLinks}
          selectedEntity={selectedEntity}
          onSelectEntity={(entity) => {
            if (entity && (entity.kind === "region" || entity.kind === "civilization")) selectHistoryEntity({ kind: entity.kind, name: entity.id });
            else setSelectedEntity(entity);
          }}
          namedEvents={bundle?.named_events ?? []}
          selectedScenario={selectedScenario?.name ?? null}
          resumeState={resumeState}
          batchSummary={selectedBatchSummary}
          currentTurn={currentTurn}
          totalTurns={totalTurns}
          bundleLoading={bundleLoading}
          viewerReady={viewerReady}
          batchState={batchState}
          batchProgress={batchProgress}
        />

        <RightInspector
          surface={surface}
          selection={selectedEntity}
          selectedRegion={selectedRegion}
          selectedCivilization={selectedCivilization}
          selectedEvent={selectedEvent}
          selectedEventRecorded={selectedEventRecorded}
          selectedEventProvenance={selectedEventProvenance}
          selectedEventAccounts={selectedEventAccounts}
          onSelectEvent={selectEvent}
          onSeek={onSeek}
          onSelectRegion={selectRegion}
          onSelectCivilization={selectCivilization}
          civilizationNames={civilizationEntries.map((civilization) => civilization.name)}
          selectedRegionTerrain={selectedRegionTerrain}
          languages={bundle?.languages}
          languagesBundle={bundle}
          languageSelection={languageSelection}
          currentTurn={currentTurn}
          selectedBatchSummary={selectedBatchSummary}
          civilizations={civilizations}
          previewCivilizations={previewCivilizations}
          selectedScenario={selectedScenario}
          resumeState={resumeState}
          description={selectionDescription(surface, selectedEntity, selectedBatchSummary, currentTurn,
            !isObservationEventType(selectedEvent?.event_type) || selectedEventRecorded)}
          inspectorSections={inspectorSections}
          onToggleSection={toggleInspectorSection}
          batchReport={batchReport}
          batchState={batchState}
          batchProgress={batchProgress}
          onOpenBatchResult={onOpenBatchResult}
          onShowCompare={() => { setWhatIfPair(null); setCompareMode("batch"); setShowCompareOverlay(true); }}
          viewerReady={viewerReady}
          liveState={{
            isLive,
            connected,
            serverState,
            livePaused: livePaused ?? false,
          }}
          investigationBundle={bundle}
          onOpenHistory={inspectHistory}
          currentSnapshot={currentSnapshot}
          famine={famine}
          regionNames={regionNames}
        />
      </div>

      {bundle && surface !== "setup" && surface !== "progress" && surface !== "batch" && (
        <Suspense fallback={<PanelLoading label="the simulation systems" className="phase75-panel systems-loading" />}>
          <SystemsPanel
            key={`${bundle.metadata.seed}:${bundle.metadata.generated_at}:${bundle.world_state.name}`}
            bundle={bundle}
            surface={surface}
            snapshot={currentSnapshot}
            currentTurn={currentTurn}
            onSeek={onSeek}
            onSelectEvent={selectEvent}
            onSelectRegion={selectRegion}
            onSelectCivilization={selectCivilization}
            selectedRegion={selectedRegion?.name ?? null}
            selectedCivilization={selectedCivilization?.name ?? null}
          />
        </Suspense>
      )}

      <input
        ref={resumeFileRef}
        type="file"
        accept=".json"
        className="phase75-hidden-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            handleResumeFile(file);
          }
        }}
      />

      {showCompareOverlay && (
        <div className="phase75-modal-backdrop" onClick={() => setShowCompareOverlay(false)}>
          <div ref={compareDialogRef} tabIndex={-1} className="phase75-modal-card" role="dialog" aria-modal="true" aria-label="Compare saved runs and reports" onClick={(event) => event.stopPropagation()}>
            <div className="phase75-modal-header">
              <div>
                <div className="phase75-overline">Compare saved outputs</div>
                <h2>Compare runs or batch reports</h2>
              </div>
              <button className="phase75-ghost-button" onClick={() => setShowCompareOverlay(false)}>
                Close
              </button>
            </div>
            <div className="phase75-modal-content">
              <Suspense fallback={<PanelLoading label="the report comparison" />}>
                <BatchCompare initialPair={whatIfPair} initialRight={batchReport} initialMode={compareMode}
                  initialBundle={!isLive || serverState === "completed" ? bundle : null}
                  initialIdentity={!isLive ? artifactIdentity : null} />
              </Suspense>
            </div>
          </div>
        </div>
      )}

      {!showCompareOverlay && livePaused && livePauseContext && liveSendCommand && (
        <Suspense fallback={<PanelLoading label="the intervention panel" className="phase75-panel" />}>
          <InterventionPanel
            pauseContext={livePauseContext}
            sendCommand={liveSendCommand}
            forkedPath={liveForkedPath}
            forkedHint={liveForkedHint}
            onSaveCheckpoint={liveSaveCheckpoint}
            checkpointStatus={liveCheckpointStatus}
            whatIf={liveWhatIf}
            onCompareWhatIf={(pair) => { setWhatIfPair(pair); setCompareMode("runs"); setShowCompareOverlay(true); }}
            onInspectWorld={() => {
              setInspectedPause(pauseKey);
              window.requestAnimationFrame(() => document.getElementById("world-investigation-map")?.focus());
            }}
            inspectionHidden={inspectingPausedWorld}
          />
        </Suspense>
      )}
    </div>
  );
}

function TopHeader({
  surface,
  worldName,
  scenarioName,
  seed,
  interestingness,
  currentTurn,
  totalTurns,
  connected,
  liveReconnecting,
  serverState,
  viewerReady,
  onOpenBundle,
  onCompare,
}: {
  surface: AppSurface;
  worldName: string;
  scenarioName: string | null;
  seed: number | null;
  interestingness: number | null;
  currentTurn: number | null;
  totalTurns: number | null;
  connected: boolean;
  liveReconnecting?: boolean;
  serverState: "connecting" | "lobby" | "starting" | "running" | "completed";
  viewerReady: boolean;
  onOpenBundle: () => void;
  onCompare: () => void;
}) {
  const statusLabel = liveReconnecting
    ? "Reconnecting"
    : connected
      ? "Live"
      : serverState === "completed"
        ? "Archive"
        : "Offline";

  return (
    <header className="phase75-topbar">
      <div className="phase75-brand-block">
        <div className="phase75-brand-mark">C</div>
        <div>
          <div className="phase75-overline">Chronicler</div>
          <div className="phase75-brand-title">{worldName}</div>
          <div className="phase75-brand-subtitle">
            {scenarioName ?? "World history"}
          </div>
        </div>
      </div>

      <div className="phase75-header-meta">
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">View</span>
          <span className="phase75-meta-value">{surface}</span>
        </div>
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">Turn</span>
          <span className="phase75-meta-value">
            {viewerReady && currentTurn !== null && totalTurns !== null ? `${currentTurn} / ${totalTurns}` : "No run loaded"}
          </span>
        </div>
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">Seed</span>
          <span className="phase75-meta-value">{seed ?? "?"}</span>
        </div>
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">Interestingness</span>
          <span className="phase75-meta-value">
            {interestingness == null ? "Pending" : interestingness.toFixed(1)}
          </span>
        </div>
        <div className="phase75-status-badge">{statusLabel}</div>
        <button type="button" className="phase75-ghost-button" onClick={onCompare}>Compare saved runs</button>
        <button className="phase75-primary-button phase75-open-bundle" onClick={onOpenBundle}>
          Open Existing
        </button>
      </div>
    </header>
  );
}

function LeftRail({
  surface,
  leftRailTab,
  onTabChange,
  chronicleFeed,
  eventFeed,
  onJumpToTurn,
  onSelectEvent,
  sourceBundle,
  currentTurn,
  setupState,
  onScenarioChange,
  onSeedChange,
  onTurnsChange,
  onCivsChange,
  onRegionsChange,
  onSimModelChange,
  onNarrativeModelChange,
  onCustomSimModelChange,
  onCustomNarrativeModelChange,
  onRandomSeed,
  onResumeBrowse,
  onResumeDrop,
  onClearResume,
  onFeaturesChange,
  onLaunch,
  batchState,
  batchReport,
  batchProgress,
  batchError,
  onBatchStart,
  onBatchCancel,
  onBatchReset,
  batchSummaries,
  batchSelectionPath,
  onSelectBatchRun,
  onOpenBatchResult,
}: LeftRailProps) {
  // The chronicle card whose sources are open (one at a time).
  const [openSources, setOpenSources] = useState<string | null>(null);
  const selectedScenario = setupState.scenarios.find((entry) => entry.file === setupState.scenario) ?? null;
  const railTabs = surface === "setup"
    ? [{ key: "launch", label: "Launch" }]
    : surface === "progress"
      ? [{ key: "status", label: "Run Log" }]
      : surface === "batch"
        ? [{ key: "runs", label: "Ranked Runs" }]
        : [
          { key: "chronicle", label: "Chronicle" },
          { key: "events", label: "Event Log" },
        ];
  const batchRunDefaults: Partial<BatchConfig> = {
    turns: setupState.turns,
    civs: setupState.resumeState
      ? setupState.resumeState.civilizations.length
      : setupState.civsDisabled
        ? (selectedScenario?.civs?.length || setupState.civs)
        : setupState.civs,
    regions: setupState.resumeState
      ? setupState.resumeState.regions.length
      : setupState.regionsDisabled
        ? (selectedScenario?.regions?.length || setupState.regions)
        : setupState.regions,
    scenario: setupState.resumeState ? null : (setupState.scenario || null),
    sim_model: setupState.simModel === "__custom__" ? setupState.customSimModel : setupState.simModel,
    narrative_model: setupState.narrativeModel === "__custom__"
      ? setupState.customNarrativeModel
      : setupState.narrativeModel,
    narrator: "local",
  };

  return (
    <aside className="phase75-left-rail phase75-panel">
      <div className="phase75-rail-tabs">
        {railTabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`phase75-rail-tab${leftRailTab === tab.key ? " active" : ""}`}
            onClick={() => onTabChange(tab.key as LeftRailTab)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="phase75-rail-toolbar">
        <div>
          <div className="phase75-overline">
            {surface === "setup"
              ? "New run"
              : surface === "progress"
                ? "Starting run"
                : surface === "batch"
                  ? "Batch Lab"
                  : leftRailTab === "events"
                    ? "Event context"
                    : "Chronicle context"}
          </div>
          <h3>
            {surface === "batch"
              ? "Explore and compare recorded runs"
              : surface === "setup"
                ? "Choose how your world begins"
                : surface === "progress"
                  ? "Preparing your world"
                  : leftRailTab === "events"
                    ? "Select an event to inspect its recorded details"
                    : "Read the chronicle through the selected turn"}
          </h3>
        </div>
      </div>

      <div className="phase75-rail-content">
        {surface === "setup" && (
          <SetupRail
            state={setupState}
            onScenarioChange={onScenarioChange}
            onSeedChange={onSeedChange}
            onTurnsChange={onTurnsChange}
            onCivsChange={onCivsChange}
            onRegionsChange={onRegionsChange}
            onSimModelChange={onSimModelChange}
            onNarrativeModelChange={onNarrativeModelChange}
            onCustomSimModelChange={onCustomSimModelChange}
            onCustomNarrativeModelChange={onCustomNarrativeModelChange}
            onRandomSeed={onRandomSeed}
            onResumeBrowse={onResumeBrowse}
            onResumeDrop={onResumeDrop}
            onClearResume={onClearResume}
            onFeaturesChange={onFeaturesChange}
            onLaunch={onLaunch}
          />
        )}

        {surface === "progress" && (
          <div className="phase75-progress-list">
            <div className="phase75-progress-line">
              <span>Connection</span>
              <strong>{setupState.lobbyReady ? "Viewer linked" : "Waiting for lobby"}</strong>
            </div>
            <div className="phase75-progress-line">
              <span>Scenario</span>
              <strong>{setupState.resumeState ? "Resume / fork" : (setupState.scenario || "Procedural world")}</strong>
            </div>
            <div className="phase75-progress-line">
              <span>Turns</span>
              <strong>{setupState.turns}</strong>
            </div>
            <div className="phase75-progress-line">
              <span>Narration</span>
              <strong>{setupState.narrativeModel || "Default"}</strong>
            </div>
            <div className="phase75-progress-note">
              The map and history become available as the run progresses.
            </div>
          </div>
        )}

        {surface === "batch" && (
          batchState === "complete" && batchReport ? (
            <div className="phase75-batch-results">
              <div className="phase75-batch-summary-card">
                <div className="phase75-overline">Report Summary</div>
                <h4>
                  {batchReport.metadata.runs} runs · seeds {batchReport.metadata.seed_range[0]}-{batchReport.metadata.seed_range[1]}
                </h4>
                <p>
                  Select a run to preview its results, then open it to explore its history.
                </p>
              </div>

              <div className="phase75-run-list">
                {batchSummaries.length === 0 && (
                  <div className="phase75-empty-state">
                    This report has no ranked run summaries. Generate a new batch to open individual runs here.
                  </div>
                )}

                {batchSummaries.map((summary) => (
                  <button
                    key={summary.bundle_path}
                    type="button"
                    className={`phase75-run-row${batchSelectionPath === summary.bundle_path ? " active" : ""}`}
                    onClick={() => onSelectBatchRun(summary.bundle_path)}
                  >
                    <div className="phase75-run-rank">#{summary.rank}</div>
                    <div className="phase75-run-body">
                      <div className="phase75-run-line">
                        <strong>Seed {summary.seed ?? "?"}</strong>
                        <span>{summary.interestingness_score == null ? "Pending" : summary.interestingness_score.toFixed(1)}</span>
                      </div>
                      <div className="phase75-run-meta">
                        {summary.dominant_faction || "Unsettled"} · {summary.major_event_count} major events · {summary.signal_flags.join(" · ") || "steady"}
                      </div>
                    </div>
                    <span className="phase75-run-open">
                      {onOpenBatchResult ? "Open" : "Preview"}
                    </span>
                  </button>
                ))}
              </div>

              {batchSelectionPath && onOpenBatchResult && (
                <button
                  type="button"
                  className="phase75-primary-button phase75-run-open-button"
                  onClick={() => onOpenBatchResult(batchSelectionPath)}
                >
                  Open Selected Result
                </button>
              )}
            </div>
          ) : onBatchStart && onBatchCancel && onBatchReset ? (
            <Suspense fallback={<PanelLoading label="the Batch Lab" />}>
              <BatchPanel
                batchState={batchState}
                report={batchReport}
                progress={batchProgress}
                error={batchError}
                runDefaults={batchRunDefaults}
                featureCatalog={setupState.featureCatalog}
                onStart={onBatchStart}
                onCancel={onBatchCancel}
                onReset={onBatchReset}
              />
            </Suspense>
          ) : (
            <div className="phase75-empty-state">
              Start a live session to run a batch. You can open saved runs from the header and compare results when a report is available.
            </div>
          )
        )}

        {surface !== "setup" && surface !== "progress" && surface !== "batch" && leftRailTab === "chronicle" && (
          <div className="phase75-feed">
            {chronicleFeed.length === 0 && (
              <div className="phase75-empty-state">Chronicle segments will appear here once the bundle has narrated material.</div>
            )}
            {chronicleFeed.map((item) => (
              <article key={item.id} className={`phase75-feed-card ${item.accent}`}>
                <div className="phase75-feed-eyebrow">{item.eyebrow}</div>
                <h4>{item.title}</h4>
                <p>{item.body}</p>
                {item.entry?.provenance && sourceBundle && (
                  <>
                    <button
                      type="button"
                      className="phase75-link-button phase75-sources-toggle"
                      aria-expanded={openSources === item.id}
                      onClick={() => setOpenSources(openSources === item.id ? null : item.id)}
                    >
                      Sources ({item.entry.provenance.facts.length})
                    </button>
                    {openSources === item.id && (
                      <Suspense fallback={<PanelLoading label="the passage's sources" />}>
                        <ChronicleSources
                          bundle={sourceBundle} entry={item.entry} currentTurn={currentTurn}
                          onJumpToTurn={onJumpToTurn} onSelectEvent={onSelectEvent}
                        />
                      </Suspense>
                    )}
                  </>
                )}
              </article>
            ))}
          </div>
        )}

        {surface !== "setup" && surface !== "progress" && surface !== "batch" && leftRailTab === "events" && (
          <div className="phase75-feed">
            {eventFeed.length === 0 && (
              <div className="phase75-empty-state">No visible events for this slice yet.</div>
            )}
            {eventFeed.map((event) => (
              <button
                key={`${event.turn}-${event.event_type}-${event.description}`}
                type="button"
                className="phase75-event-row"
                onClick={() => onSelectEvent(event)}
              >
                <div className="phase75-event-turn">T{event.turn}</div>
                <div className="phase75-event-copy">
                  <strong>{event.event_type}</strong>
                  <span>{event.description}</span>
                </div>
                <div className="phase75-event-importance">{event.importance}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}

function ModeTabs({
  current,
  onSelect,
  canActivateSurface,
}: {
  current: AppSurface;
  onSelect: (surface: AppSurface) => void;
  canActivateSurface: (surface: AppSurface) => boolean;
}) {
  return (
    <nav className="phase75-mode-tabs">
      {FLOW_STEPS.map((step) => (
        <button
          key={step.surface}
          type="button"
          className={`phase75-mode-tab${current === step.surface ? " active" : ""}`}
          disabled={!canActivateSurface(step.surface)}
          onClick={() => onSelect(step.surface)}
        >
          {step.label}
        </button>
      ))}
    </nav>
  );
}

function ValidationRibbon({
  visible,
  bundle,
  batchReport,
  selectedCivilization,
  civilizations,
}: {
  visible: boolean;
  bundle: Bundle | null;
  batchReport: BatchReport | null;
  selectedCivilization: CivilizationEntry | null;
  civilizations: CivilizationView[];
}) {
  if (!visible) {
    return null;
  }
  const focus = selectedCivilization && isFounded(selectedCivilization) ? selectedCivilization : null;

  const anomalies = batchReport?.anomalies.length ?? 0;
  const lateEraCount = civilizations.filter((civilization) => civilization.techEra === "industrial" || civilization.techEra === "information").length;
  const focusValue = focus ? focus.stability.toFixed(1) : selectedCivilization ? UNAVAILABLE : "none";

  const checks = [
    {
      label: "Interestingness",
      status: bundle?.metadata.interestingness_score && bundle.metadata.interestingness_score >= 20 ? "pass" : "warn",
      value: bundle?.metadata.interestingness_score?.toFixed(1) ?? "pending",
    },
    {
      label: "Anomalies",
      status: anomalies === 0 ? "pass" : "warn",
      value: String(anomalies),
    },
    {
      label: "Late Era",
      status: lateEraCount > 0 ? "pass" : "warn",
      value: String(lateEraCount),
    },
    {
      label: "Focus Stability",
      status: focus && focus.stability <= 1 ? "warn" : "pass",
      value: focusValue,
    },
  ];

  return (
    <div className="phase75-validation-ribbon">
      {checks.map((check) => (
        <div key={check.label} className={`phase75-validation-pill ${check.status}`}>
          <span>{check.label}</span>
          <strong>{check.value}</strong>
        </div>
      ))}
    </div>
  );
}
