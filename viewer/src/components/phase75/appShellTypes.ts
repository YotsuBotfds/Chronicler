/**
 * Types shared by the shell (AppShell.tsx, which owns the state) and the
 * presentation components it renders from props. Type-only: this module adds
 * no code or styles to the build.
 */
import type { LiveInspectionControls } from "../LiveInspectionControls";

export type AppSurface =
  | "setup"
  | "progress"
  | "overview"
  | "character"
  | "trade"
  | "campaign"
  | "batch";

/** The live timeline's follow and lock controls (LiveInspectionControls' props). */
export type LiveTimelineControls = Parameters<typeof LiveInspectionControls>[0];

export type OverlayKey = "borders" | "settlements" | "chronicle" | "trade" | "campaign" | "fog" | "asabiya";

export interface SelectedEntity {
  kind: "civilization" | "region" | "event" | "run";
  id: string;
  label: string;
  turn?: number;
}

export interface RegionLike {
  name: string;
  terrain: string;
  x: number | null;
  y: number | null;
  resources?: string;
  carrying_capacity?: number;
}

export interface MapNode {
  region: RegionLike;
  controller: string | null | undefined;
  x: number;
  y: number;
}
