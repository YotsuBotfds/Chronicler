/**
 * The shell's heavier panels, each in its own chunk (with Recharts in a
 * shared one): the systems tabs, the languages inspector, the region
 * history inspector, the Batch Lab panel and compare overlay, and the
 * live intervention panel. None is on the first screen (setup, before a
 * bundle). The shell starts loading them once it has painted
 * (`preloadPanels`), and again when a bundle starts loading, so they are
 * normally there before they are needed; until then a panel shows its
 * `PanelLoading` placeholder (PanelLoading.tsx).
 */
import { createElement, type ComponentProps } from "react";
import { preloadable } from "../../lib/preloadable";
import type { BatchCompare as BatchCompareType } from "../BatchCompare";
import type { BatchPanel as BatchPanelType } from "../BatchPanel";
import type { InterventionPanel as InterventionPanelType } from "../InterventionPanel";
import type { RegionHistoryInspector as RegionHistoryInspectorType } from "../RegionHistoryInspector";
import type { SystemsPanel as SystemsPanelType } from "../systems/SystemsPanel";
import type { LanguagesPanel as LanguagesPanelType } from "./LanguagesPanel";

/** What a panel whose chunk failed to load shows instead (no error boundary). */
function loadFailed(label: string) {
  return (message: string) => function PanelLoadFailed() {
    return createElement(
      "div",
      { className: "phase75-empty-state", role: "alert" },
      `Could not load the ${label} (${message}). Reload the viewer to try again.`,
    );
  };
}

export const SystemsPanel = preloadable<ComponentProps<typeof SystemsPanelType>>(
  () => import("../systems/SystemsPanel").then((module) => module.SystemsPanel),
  loadFailed("systems panel"),
  "SystemsPanel",
);

export const LanguagesPanel = preloadable<ComponentProps<typeof LanguagesPanelType>>(
  () => import("./LanguagesPanel").then((module) => module.LanguagesPanel),
  loadFailed("languages panel"),
  "LanguagesPanel",
);

export const RegionHistoryInspector = preloadable<ComponentProps<typeof RegionHistoryInspectorType>>(
  () => import("../RegionHistoryInspector").then((module) => module.RegionHistoryInspector),
  loadFailed("region history inspector"),
  "RegionHistoryInspector",
);

export const BatchPanel = preloadable<ComponentProps<typeof BatchPanelType>>(
  () => import("../BatchPanel").then((module) => module.BatchPanel),
  loadFailed("Batch Lab panel"),
  "BatchPanel",
);

export const BatchCompare = preloadable<ComponentProps<typeof BatchCompareType>>(
  () => import("../BatchCompare").then((module) => module.BatchCompare),
  loadFailed("batch comparison"),
  "BatchCompare",
);

export const InterventionPanel = preloadable<ComponentProps<typeof InterventionPanelType>>(
  () => import("../InterventionPanel").then((module) => module.InterventionPanel),
  loadFailed("intervention panel"),
  "InterventionPanel",
);

/** Start loading every lazy panel (once each); resolves when all render without suspending. */
export function preloadPanels(): Promise<unknown> {
  return Promise.all([SystemsPanel, LanguagesPanel, RegionHistoryInspector, BatchPanel, BatchCompare, InterventionPanel]
    .map((panel) => panel.preload()));
}
