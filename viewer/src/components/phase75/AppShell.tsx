import { useEffect, useEffectEvent, useRef, useState } from "react";
import type {
  BatchReport,
  BatchRunSummary,
  Bundle,
  Command,
  Event,
  LobbyInit,
  NamedEvent,
  PauseContext,
  StartCommand,
  TurnSnapshot,
  WorldState,
} from "../../types";
import { isLegacyBundle } from "../../types";
import type { BatchConfig } from "../../types";
import type { BatchState } from "../../hooks/useBatchConnection";
import { ERA_LABELS } from "../../lib/format";
import { DISPOSITION_COLORS, factionColor, UNCONTROLLED_COLOR } from "../../lib/colors";
import { BatchCompare } from "../BatchCompare";
import { BatchPanel } from "../BatchPanel";
import { InterventionPanel } from "../InterventionPanel";
import { buildTradeLinks, percentToTurn, turnToPercent } from "./appShellHelpers";
import "./app-shell.css";

export type AppSurface =
  | "setup"
  | "progress"
  | "overview"
  | "character"
  | "trade"
  | "campaign"
  | "batch";

type LeftRailTab = "launch" | "status" | "chronicle" | "events" | "runs";
type OverlayKey = "borders" | "settlements" | "chronicle" | "trade" | "campaign" | "fog" | "asabiya";

interface SelectedEntity {
  kind: "civilization" | "region" | "event" | "run";
  id: string;
  label: string;
  turn?: number;
}

interface AppShellProps {
  surface: AppSurface;
  onSurfaceChange: (surface: AppSurface) => void;
  bundle: Bundle | null;
  bundleLoading: boolean;
  error: string | null;
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
  livePaused?: boolean;
  livePauseContext?: PauseContext | null;
  liveSendCommand?: (cmd: Command) => void;
  liveForkedPath?: string | null;
  liveForkedHint?: string | null;
  liveReconnecting?: boolean;
}

interface CivilizationView {
  name: string;
  population: number;
  military: number;
  economy: number;
  culture: number;
  stability: number;
  treasury: number;
  asabiya: number;
  techEra: string;
  leaderName: string;
  leaderTrait: string;
  values: string[];
  goal: string;
  regions: string[];
  alive: boolean;
}

interface RegionLike {
  name: string;
  terrain: string;
  x: number | null;
  y: number | null;
  resources?: string;
  carrying_capacity?: number;
}

interface MapNode {
  region: RegionLike;
  controller: string | null;
  x: number;
  y: number;
}

interface ChronicleFeedItem {
  id: string;
  turn: number;
  title: string;
  body: string;
  eyebrow: string;
  accent: "gold" | "cyan" | "ember" | "stone";
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

const SPEED_OPTIONS = [1, 2, 5, 10];

function findCurrentSnapshot(bundle: Bundle | null, currentTurn: number): TurnSnapshot | null {
  if (!bundle || bundle.history.length === 0) {
    return null;
  }

  let latest = bundle.history[0];
  for (const snapshot of bundle.history) {
    if (snapshot.turn > currentTurn) {
      break;
    }
    latest = snapshot;
  }
  return latest ?? bundle.history[bundle.history.length - 1];
}

function buildCivilizationViews(bundle: Bundle | null, snapshot: TurnSnapshot | null): CivilizationView[] {
  if (!bundle) {
    return [];
  }

  return bundle.world_state.civilizations.map((civilization) => {
    const snap = snapshot?.civ_stats[civilization.name];
    return {
      name: civilization.name,
      population: snap?.population ?? civilization.population,
      military: snap?.military ?? civilization.military,
      economy: snap?.economy ?? civilization.economy,
      culture: snap?.culture ?? civilization.culture,
      stability: snap?.stability ?? civilization.stability,
      treasury: snap?.treasury ?? civilization.treasury,
      asabiya: snap?.asabiya ?? civilization.asabiya,
      techEra: snap?.tech_era ?? civilization.tech_era,
      leaderName: snap?.leader_name ?? civilization.leader.name,
      leaderTrait: snap?.trait ?? civilization.leader.trait,
      values: civilization.values,
      goal: civilization.goal,
      regions: snap?.regions ?? civilization.regions,
      alive: snap?.alive ?? civilization.regions.length > 0,
    };
  });
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

function buildNarratedSpans(bundle: Bundle | null): { start: number; end: number }[] {
  if (!bundle) {
    return [];
  }

  if (isLegacyBundle(bundle.chronicle_entries)) {
    return Object.keys(bundle.chronicle_entries)
      .map((turnString) => Number(turnString))
      .filter((turn) => !Number.isNaN(turn))
      .map((turn) => ({ start: turn, end: turn }))
      .sort((left, right) => left.start - right.start);
  }

  return bundle.chronicle_entries
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

  const items = bundle.chronicle_entries
    .filter((entry) => entry.covers_turns[0] <= currentTurn)
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

  const gaps = (bundle.gap_summaries ?? [])
    .filter((gap) => gap.turn_range[0] <= currentTurn)
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

function buildEventFeed(
  events: Event[],
  currentTurn: number,
  selectedEntity: SelectedEntity | null,
): Event[] {
  const visible = events
    .filter((event) => event.turn <= currentTurn)
    .sort((left, right) => right.turn - left.turn);

  if (selectedEntity?.kind !== "civilization") {
    return visible.slice(0, 24);
  }

  const focused = visible.filter((event) => event.actors.includes(selectedEntity.id));
  if (focused.length >= 8) {
    return focused.slice(0, 24);
  }

  const merged = [...focused];
  for (const event of visible) {
    if (merged.length >= 24) {
      break;
    }
    if (!merged.includes(event)) {
      merged.push(event);
    }
  }
  return merged;
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

function computeAtlasLayout(regions: RegionLike[], controllers: Record<string, string | null>): MapNode[] {
  if (regions.length === 0) {
    return [];
  }

  const hasPins = regions.some((region) => region.x !== null && region.y !== null);
  if (hasPins) {
    return regions.map((region) => ({
      region,
      controller: controllers[region.name] ?? null,
      x: 90 + (region.x ?? 0.5) * 820,
      y: 80 + (region.y ?? 0.5) * 480,
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
        controller: controllers[region.name] ?? null,
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
): string {
  if (surface === "batch") {
    return buildRunSignalSummary(summary);
  }
  if (!selection) {
    return "Map selection drives inspector context across Overview, Character, Trade, and Campaign.";
  }
  if (selection.kind === "event") {
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
  setupState: {
    scenario: string;
    scenarios: LobbyInit["scenarios"];
    seed: string;
    turns: number;
    civs: number;
    regions: number;
    simModel: string;
    narrativeModel: string;
    models: string[];
    customSimModel: string;
    customNarrativeModel: string;
    starting: boolean;
    error: string | null;
    resumeState: WorldState | null;
    resumeTurn: number | null;
    resumeError: string | null;
    civsDisabled: boolean;
    regionsDisabled: boolean;
    lobbyReady: boolean;
  };
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
  bundleLoading,
  error,
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
  livePaused,
  livePauseContext,
  liveSendCommand,
  liveForkedPath,
  liveForkedHint,
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
  const [inspectorSections, setInspectorSections] = useState<Record<string, boolean>>({
    selection: true,
    metrics: true,
    network: true,
    signals: true,
    batch: true,
  });
  const [showCompareOverlay, setShowCompareOverlay] = useState(false);
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
  const syncSetupDefaults = useEffectEvent(() => {
    setTurns(defaults.turns);
    setCivs(defaults.civs);
    setRegions(defaults.regions);
    setSimModel(primaryModel);
    setNarrativeModel(primaryModel);
  });
  const syncOverlayPreset = useEffectEvent(() => {
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
  const civilizations = sortCivilizations(buildCivilizationViews(bundle, currentSnapshot));
  const leadCivilization = dominantCivilization(civilizations);
  const totalTurns = totalTurnsFor(bundle);
  const eraBands = buildEraBands(bundle?.history ?? [], totalTurns);
  const narratedSpans = buildNarratedSpans(bundle);
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
  const regionControllers = currentSnapshot?.region_control
    ?? (bundle
      ? Object.fromEntries(bundle.world_state.regions.map((region) => [region.name, region.controller]))
      : previewControllers);
  const atlasRegions: RegionLike[] = bundle
    ? bundle.world_state.regions
    : previewRegions;
  const atlasNodes = computeAtlasLayout(atlasRegions, regionControllers);
  const atlasConnections = buildRegionConnections(atlasNodes);
  const controllerCentroids = computeControllerCentroids(atlasNodes);
  const worldRelationships = bundle?.world_state.relationships ?? null;
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
  const eventFeed = buildEventFeed(bundle?.events_timeline ?? [], currentTurn, selectedEntity);
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
        ? civilizations.some((civilization) => civilization.name === selectedEntity.id)
        : selectedEntity?.kind === "event"
          ? bundle.events_timeline.some((event) => `${event.turn}-${event.event_type}` === selectedEntity.id)
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
    ?? (resumeState ? "Resumed world" : "Procedural setup");
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

  const selectedRegion = selectedEntity?.kind === "region"
    ? atlasRegions.find((region) => region.name === selectedEntity.id) ?? null
    : null;
  const selectedCivilization = selectedEntity?.kind === "civilization"
    ? civilizations.find((civilization) => civilization.name === selectedEntity.id) ?? null
    : null;
  const selectedEvent = selectedEntity?.kind === "event"
    ? (bundle?.events_timeline.find((event) => `${event.turn}-${event.event_type}` === selectedEntity.id) ?? null)
    : null;

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
        accept=".json"
        className="phase75-hidden-input"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) {
            onOpenBundleFile(file);
          }
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
      />

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
      />

      <ValidationRibbon
        visible={surface === "campaign"}
        bundle={bundle}
        batchReport={batchReport}
        selectedCivilization={selectedCivilization}
        civilizations={civilizations}
      />

      <div className="phase75-workspace">
        <LeftRail
          surface={surface}
          leftRailTab={leftRailTab}
          onTabChange={setLeftRailTabSelection}
          chronicleFeed={chronicleFeed}
          eventFeed={eventFeed}
          onJumpToTurn={(turn) => onSeek(turn)}
          onSelectEvent={(event) => {
            setSelectedEntity({
              kind: "event",
              id: `${event.turn}-${event.event_type}`,
              label: event.description,
              turn: event.turn,
            });
            onSeek(event.turn);
          }}
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
          }}
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
          civilizations={civilizations}
          tradeLinks={tradeLinks}
          campaignLinks={campaignLinks}
          selectedEntity={selectedEntity}
          onSelectEntity={setSelectedEntity}
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
          selectedBatchSummary={selectedBatchSummary}
          civilizations={civilizations}
          previewCivilizations={previewCivilizations}
          selectedScenario={selectedScenario}
          resumeState={resumeState}
          description={selectionDescription(surface, selectedEntity, selectedBatchSummary)}
          inspectorSections={inspectorSections}
          onToggleSection={toggleInspectorSection}
          batchReport={batchReport}
          batchState={batchState}
          batchProgress={batchProgress}
          onOpenBatchResult={onOpenBatchResult}
          onShowCompare={() => setShowCompareOverlay(true)}
          viewerReady={viewerReady}
          liveState={{
            isLive,
            connected,
            serverState,
            livePaused: livePaused ?? false,
          }}
        />
      </div>

      {error && surface !== "setup" && surface !== "batch" && (
        <div className="phase75-error-banner">{error}</div>
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
          <div className="phase75-modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="phase75-modal-header">
              <div>
                <div className="phase75-overline">Batch Compare</div>
                <h2>Ranked report comparison workspace</h2>
              </div>
              <button className="phase75-ghost-button" onClick={() => setShowCompareOverlay(false)}>
                Close
              </button>
            </div>
            <div className="phase75-modal-content">
              <BatchCompare initialRight={batchReport} />
            </div>
          </div>
        </div>
      )}

      {livePaused && livePauseContext && liveSendCommand && (
        <InterventionPanel
          pauseContext={livePauseContext}
          sendCommand={liveSendCommand}
          forkedPath={liveForkedPath}
          forkedHint={liveForkedHint}
        />
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
          <div className="phase75-overline">Chronicler Phase 7.5 Shell</div>
          <div className="phase75-brand-title">{worldName}</div>
          <div className="phase75-brand-subtitle">
            {scenarioName ?? "Procedural workspace"}
          </div>
        </div>
      </div>

      <div className="phase75-header-meta">
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">State</span>
          <span className="phase75-meta-value">{surface}</span>
        </div>
        <div className="phase75-meta-cluster">
          <span className="phase75-meta-label">Turn</span>
          <span className="phase75-meta-value">
            {viewerReady && currentTurn !== null && totalTurns !== null ? `${currentTurn} / ${totalTurns}` : "Front door"}
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
        <button className="phase75-primary-button phase75-open-bundle" onClick={onOpenBundle}>
          Open Existing
        </button>
      </div>
    </header>
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

function TimelineRail({
  surface,
  flowSteps,
  currentTurn,
  totalTurns,
  bundle,
  eraBands,
  narratedSpans,
  namedEvents,
  trackRef,
  onTrackSeek,
  playing,
  speed,
  onPlay,
  onPause,
  onSetSpeed,
}: {
  surface: AppSurface;
  flowSteps: { surface: AppSurface; label: string; index: string }[];
  currentTurn: number;
  totalTurns: number;
  bundle: Bundle | null;
  eraBands: { label: string; start: number; end: number }[];
  narratedSpans: { start: number; end: number }[];
  namedEvents: NamedEvent[];
  trackRef: React.RefObject<HTMLDivElement | null>;
  onTrackSeek: (event: React.MouseEvent<HTMLDivElement>) => void;
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onSetSpeed: (speed: number) => void;
}) {
  const visibleMarkers = [...namedEvents]
    .sort((left, right) => right.importance - left.importance)
    .slice(0, 8);

  return (
    <section className="phase75-timeline-rail">
      <div className="phase75-flow-ladder">
        {flowSteps.map((step) => (
          <div key={step.surface} className={`phase75-flow-step${surface === step.surface ? " active" : ""}`}>
            <span className="phase75-flow-index">{step.index}</span>
            <span className="phase75-flow-name">{step.label}</span>
          </div>
        ))}
      </div>

      <div className="phase75-track-shell">
        <div className="phase75-track-header">
          <div>
            <div className="phase75-overline">Timeline Rail</div>
            <h2>
              {bundle ? "Archive timeline, event markers, and narrated spans" : "Product flow, launch state, and handoff context"}
            </h2>
          </div>

          <div className="phase75-track-actions">
            <button className="phase75-ghost-button" onClick={playing ? onPause : onPlay} disabled={!bundle}>
              {playing ? "Pause" : "Play"}
            </button>
            <select
              className="phase75-speed-select"
              value={speed}
              onChange={(event) => onSetSpeed(Number(event.target.value))}
              disabled={!bundle}
            >
              {SPEED_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}x
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          ref={trackRef}
          className={`phase75-turn-track${bundle ? " interactive" : ""}`}
          onClick={onTrackSeek}
        >
          {eraBands.map((band) => (
            <div
              key={`${band.label}-${band.start}`}
              className="phase75-era-band"
              style={{
                left: `${turnToPercent(band.start, totalTurns)}%`,
                width: `${Math.max(2, turnToPercent(band.end, totalTurns) - turnToPercent(band.start, totalTurns))}%`,
              }}
            >
              <span>{band.label}</span>
            </div>
          ))}

          {narratedSpans.map((span, index) => (
            <div
              key={`span-${index}`}
              className="phase75-narrated-span"
              style={{
                left: `${turnToPercent(span.start, totalTurns)}%`,
                width: `${Math.max(1.6, turnToPercent(span.end, totalTurns) - turnToPercent(span.start, totalTurns) + 1.5)}%`,
              }}
            />
          ))}

          {visibleMarkers.map((marker) => (
            <button
              key={`${marker.turn}-${marker.name}`}
              type="button"
              className="phase75-track-marker"
              style={{ left: `${turnToPercent(marker.turn, totalTurns)}%` }}
              title={marker.name}
            />
          ))}

          {bundle ? (
            <div className="phase75-playhead" style={{ left: `${turnToPercent(currentTurn, totalTurns)}%` }}>
              <div className="phase75-playhead-line" />
              <div className="phase75-playhead-label">T{currentTurn}</div>
            </div>
          ) : (
            <div className="phase75-frontdoor-callout">
              One shell now carries setup, run handoff, overview, diagnostics, and batch review.
            </div>
          )}
        </div>
      </div>
    </section>
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
  selectedCivilization: CivilizationView | null;
  civilizations: CivilizationView[];
}) {
  if (!visible) {
    return null;
  }

  const anomalies = batchReport?.anomalies.length ?? 0;
  const lateEraCount = civilizations.filter((civilization) => civilization.techEra === "industrial" || civilization.techEra === "information").length;
  const focusValue = selectedCivilization ? selectedCivilization.stability.toFixed(1) : "none";

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
      status: selectedCivilization && selectedCivilization.stability <= 1 ? "warn" : "pass",
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

function LeftRail({
  surface,
  leftRailTab,
  onTabChange,
  chronicleFeed,
  eventFeed,
  onJumpToTurn,
  onSelectEvent,
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
              ? "Launch Surface"
              : surface === "progress"
                ? "Progress Handoff"
                : surface === "batch"
                  ? "Batch Lab"
                  : leftRailTab === "events"
                    ? "Event context"
                    : "Chronicle context"}
          </div>
          <h3>
            {surface === "batch"
              ? "Interestingness-ranked runs and compare affordances"
              : surface === "setup"
                ? "Single-run configuration wired into the shell"
                : surface === "progress"
                  ? "Run state, launch confirmation, and handoff"
                  : leftRailTab === "events"
                    ? "Event identity stays anchored on the left rail"
                    : "Chronicle identity stays anchored on the left rail"}
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
              The shell stays intact through world generation so the handoff into Overview feels like the same product, not a route jump.
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
                  Ranked results now feed directly into the viewer shell. Open any run below to land in Overview without leaving the app family.
                </p>
              </div>

              <div className="phase75-run-list">
                {batchSummaries.length === 0 && (
                  <div className="phase75-empty-state">
                    This report predates ranked run summaries. Generate a new batch to unlock direct-open viewer flow.
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
            <BatchPanel
              batchState={batchState}
              report={batchReport}
              progress={batchProgress}
              error={batchError}
              runDefaults={batchRunDefaults}
              onStart={onBatchStart}
              onCancel={onBatchCancel}
              onReset={onBatchReset}
            />
          ) : (
            <div className="phase75-empty-state">
              Batch execution needs the live viewer bridge. You can still open existing bundles from the header and use compare mode once a report is available.
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
                onClick={() => {
                  onJumpToTurn(event.turn);
                  onSelectEvent(event);
                }}
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

function SetupRail({
  state,
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
  onLaunch,
}: {
  state: LeftRailProps["setupState"];
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
  onLaunch: () => void;
}) {
  return (
    <div className="phase75-form-stack">
      <label className="phase75-field">
        <span>Scenario</span>
        <select
          value={state.scenario}
          onChange={(event) => onScenarioChange(event.target.value)}
          disabled={!state.lobbyReady || !!state.resumeState}
        >
          <option value="">Procedural</option>
          {state.scenarios.map((scenario) => (
            <option key={scenario.file} value={scenario.file}>
              {scenario.name}
            </option>
          ))}
        </select>
      </label>

      <div className="phase75-field">
        <span>Seed</span>
        <div className="phase75-inline-field">
          <input
            type="number"
            value={state.seed}
            placeholder="Random"
            onChange={(event) => onSeedChange(event.target.value)}
            disabled={!state.lobbyReady}
          />
          <button type="button" className="phase75-ghost-button" onClick={onRandomSeed} disabled={!state.lobbyReady}>
            Randomize
          </button>
        </div>
      </div>

      <div className="phase75-two-up">
        <label className="phase75-field">
          <span>Turns</span>
          <input
            type="number"
            min={1}
            value={state.turns}
            onChange={(event) => onTurnsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady}
          />
        </label>
        <label className="phase75-field">
          <span>Civilizations</span>
          <input
            type="number"
            min={1}
            value={state.civs}
            onChange={(event) => onCivsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady || state.civsDisabled}
          />
        </label>
      </div>

      <div className="phase75-two-up">
        <label className="phase75-field">
          <span>Regions</span>
          <input
            type="number"
            min={1}
            value={state.regions}
            onChange={(event) => onRegionsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady || state.regionsDisabled}
          />
        </label>
        <label className="phase75-field">
          <span>Sim Model</span>
          <select value={state.simModel} onChange={(event) => onSimModelChange(event.target.value)} disabled={!state.lobbyReady}>
            {state.models.map((model) => (
              <option key={model} value={model}>
                {model || "(Default)"}
              </option>
            ))}
            <option value="__custom__">Custom...</option>
          </select>
        </label>
      </div>

      {state.simModel === "__custom__" && (
        <label className="phase75-field">
          <span>Custom Sim Endpoint</span>
          <input
            type="text"
            value={state.customSimModel}
            onChange={(event) => onCustomSimModelChange(event.target.value)}
          />
        </label>
      )}

      <label className="phase75-field">
        <span>Narrative Model</span>
        <select value={state.narrativeModel} onChange={(event) => onNarrativeModelChange(event.target.value)} disabled={!state.lobbyReady}>
          {state.models.map((model) => (
            <option key={model} value={model}>
              {model || "(Default)"}
            </option>
          ))}
          <option value="__custom__">Custom...</option>
        </select>
      </label>

      {state.narrativeModel === "__custom__" && (
        <label className="phase75-field">
          <span>Custom Narrative Endpoint</span>
          <input
            type="text"
            value={state.customNarrativeModel}
            onChange={(event) => onCustomNarrativeModelChange(event.target.value)}
          />
        </label>
      )}

      <div className="phase75-field">
        <span>Resume / Fork</span>
        {state.resumeState ? (
          <div className="phase75-resume-pill">
            <span>Resuming from turn {state.resumeTurn}</span>
            <button type="button" className="phase75-ghost-button" onClick={onClearResume}>
              Clear
            </button>
          </div>
        ) : (
          <div
            className="phase75-dropzone"
            onClick={onResumeBrowse}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const file = event.dataTransfer.files[0];
              if (file) {
                onResumeDrop(file);
              }
            }}
          >
            Drop `state.json` or click to browse
          </div>
        )}
        {state.resumeError && <div className="phase75-inline-error">{state.resumeError}</div>}
      </div>

      {!state.lobbyReady && (
        <div className="phase75-empty-state">
          Setup controls activate when the viewer is launched with a live WebSocket bridge. Until then, this shell still supports opening existing bundles from the header.
        </div>
      )}

      {state.error && <div className="phase75-inline-error">{state.error}</div>}

      <button
        type="button"
        className="phase75-primary-button"
        onClick={onLaunch}
        disabled={!state.lobbyReady || state.starting || state.turns <= 0}
      >
        {state.starting ? "Preparing World..." : "Run World"}
      </button>
    </div>
  );
}

function MapViewport({
  surface,
  atlasNodes,
  atlasConnections,
  controllerCentroids,
  activeOverlays,
  onToggleOverlay,
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
  civilizations: CivilizationView[];
  tradeLinks: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }>;
  campaignLinks: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; disposition: string }>;
  selectedEntity: SelectedEntity | null;
  onSelectEntity: (selection: SelectedEntity | null) => void;
  namedEvents: NamedEvent[];
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
  const highlightedEventRegions = new Set(
    namedEvents
      .filter((event) => event.region)
      .slice(0, 8)
      .map((event) => event.region as string),
  );

  return (
    <section className="phase75-map-column">
      <div className="phase75-viewport-toolbar phase75-panel">
        <div>
          <div className="phase75-overline">
            {surface === "setup"
              ? "Setup Surface"
              : surface === "progress"
                ? "Progress Surface"
                : surface === "batch"
                  ? "Batch Surface"
                  : "Map Workspace"}
          </div>
          <h2>
            {surface === "setup"
              ? "Map-first launch workflow inside the same shell"
              : surface === "progress"
                ? "Run handoff stays inside the map-first frame"
                : surface === "batch"
                  ? "Ranked runs feed back into the viewer without a separate page"
                  : "Overview remains the anchor shell for all analysis modes"}
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
              ? "The center canvas stays visually dominant even during world generation and handoff."
              : surface === "batch"
                ? (batchSummary
                  ? `${batchSummary.major_event_count} major events · ${batchSummary.signal_flags.join(" · ") || "steady signal profile"}`
                  : "Run a batch to populate ranked previews and direct-open results.")
                : "Map selection, overlays, and inspector behavior stay consistent across shell modes."}
          </p>
        </div>

        <div className="phase75-map-surface">
          <div className="phase75-map-texture" />
          <svg className="phase75-atlas" viewBox="0 0 1000 640" aria-label="Chronicler atlas workspace">
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
              const fill = node.controller ? factionColor(node.controller) : UNCONTROLLED_COLOR;
              const radius = 16 + (node.region.carrying_capacity ?? 2) * 2;
              return (
                <g key={node.region.name}>
                  <circle
                    className={`phase75-region-node${isSelected ? " selected" : ""}`}
                    cx={node.x}
                    cy={node.y}
                    r={radius}
                    fill={fill}
                    onClick={() => onSelectEntity({
                      kind: "region",
                      id: node.region.name,
                      label: node.region.name,
                    })}
                  />
                  {activeOverlays.includes("settlements") && (
                    <text className="phase75-region-label" x={node.x} y={node.y + radius + 14}>
                      {node.region.name}
                    </text>
                  )}
                  {activeOverlays.includes("chronicle") && highlightedEventRegions.has(node.region.name) && (
                    <circle className="phase75-event-marker" cx={node.x + radius - 2} cy={node.y - radius + 2} r={7} />
                  )}
                </g>
              );
            })}

            {activeOverlays.includes("fog") && (
              <path className="phase75-fog-mask" d="M 664 112 L 962 164 L 962 612 L 612 612 L 566 288 Z" />
            )}
          </svg>

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
                ? "Setup and Batch Lab now live inside the same shell family as the archive viewer."
                : "Open an existing bundle or launch a live run to populate the map with archive data."}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function RightInspector({
  surface,
  selection,
  selectedRegion,
  selectedCivilization,
  selectedEvent,
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
}: {
  surface: AppSurface;
  selection: SelectedEntity | null;
  selectedRegion: RegionLike | null;
  selectedCivilization: CivilizationView | null;
  selectedEvent: Event | null;
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
}) {
  return (
    <aside className="phase75-right-rail phase75-panel">
      <div className="phase75-inspector-header">
        <div className="phase75-overline">Right Inspector</div>
        <h3>
          {surface === "setup"
            ? "Launch details"
            : surface === "batch"
              ? "Batch diagnostics"
              : viewerReady
                ? "Selection details"
                : "Awaiting viewer data"}
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
                  <strong>{selectedRegion.terrain}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Resources</span>
                  <strong>{selectedRegion.resources ?? "Unknown"}</strong>
                </div>
              </>
            )}

            {selectedCivilization && (
              <>
                <div className="phase75-stat-row">
                  <span>Civilization</span>
                  <strong>{selectedCivilization.name}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Leader</span>
                  <strong>{selectedCivilization.leaderName}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Era</span>
                  <strong>{selectedCivilization.techEra}</strong>
                </div>
                <div className="phase75-stat-row">
                  <span>Values</span>
                  <strong>{selectedCivilization.values.join(", ") || "None recorded"}</strong>
                </div>
              </>
            )}

            {selectedEvent && (
              <>
                <div className="phase75-stat-row">
                  <span>Event</span>
                  <strong>{selectedEvent.event_type}</strong>
                </div>
                <p className="phase75-detail-copy">{selectedEvent.description}</p>
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
            Trade and campaign diagnostics plug into the same inspector shell without spawning a bespoke layout.
          </div>
        )}
      </InspectorSection>

      <InspectorSection
        title="Shell Signals"
        open={inspectorSections.signals}
        onToggle={() => onToggleSection("signals")}
      >
        <div className="phase75-stat-row">
          <span>Viewer state</span>
          <strong>{liveState.serverState}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>Connected</span>
          <strong>{liveState.connected ? "Yes" : "No"}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>Paused</span>
          <strong>{liveState.livePaused ? "Yes" : "No"}</strong>
        </div>
        <div className="phase75-stat-row">
          <span>Mode cohesion</span>
          <strong>{viewerReady ? "Unified shell" : "Front door active"}</strong>
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
