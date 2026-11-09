/** Browser-session memory only: retain real inputs, never synthesize a scenario outcome. */
import { alignCompletedRuns, completedComparisonSummary, type CompletedRun } from "./completedRunComparison";
import type { WhatIfPair } from "./whatIf";

export const GALLERY_LIMIT = 6;
export interface ComparisonCase {
  id: number;
  title: string | null;
  left: CompletedRun;
  right: CompletedRun;
  turn: number;
  pair: WhatIfPair | null;
  summary: ReturnType<typeof completedComparisonSummary>;
}
let cases: readonly ComparisonCase[] = [];
let sequence = 0;
const listeners = new Set<() => void>();
function publish(next: readonly ComparisonCase[]) {
  cases = next;
  for (const listener of listeners) listener();
}
export const gallerySnapshot = () => cases;
export function subscribeGallery(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
const sameInput = (a: CompletedRun, b: CompletedRun) => a.bundle === b.bundle
  || !!a.identity?.sha256 && a.identity.sha256 === b.identity?.sha256;
export function keepComparison(left: CompletedRun, right: CompletedRun, turn: number, pair: WhatIfPair | null, title = ""): string {
  const duplicate = cases.find((row) => sameInput(row.left, left) && sameInput(row.right, right) && row.turn === turn);
  if (duplicate) return "This comparison and snapshot are already in the gallery.";
  if (cases.length >= GALLERY_LIMIT) return "Gallery is full. Remove a case before keeping another comparison.";
  const points = alignCompletedRuns(left.bundle, right.bundle);
  publish([...cases, { id: ++sequence, title: title.trim().slice(0, 120) || null, left, right, turn, pair,
    summary: completedComparisonSummary(left, right, points, turn) }]);
  return "Comparison kept for this browser session.";
}
export function removeComparison(id: number) { publish(cases.filter((row) => row.id !== id)); }
/** Test seam. */
export function clearComparisonGallery() { publish([]); }
