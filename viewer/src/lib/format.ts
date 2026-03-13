import type { TechEra } from "../types";

export const ERA_LABELS: Record<TechEra, string> = {
  tribal: "Tribal",
  bronze: "Bronze Age",
  iron: "Iron Age",
  classical: "Classical",
  medieval: "Medieval",
  renaissance: "Renaissance",
  industrial: "Industrial",
};

export const ERA_ORDER: TechEra[] = [
  "tribal",
  "bronze",
  "iron",
  "classical",
  "medieval",
  "renaissance",
  "industrial",
];

export function formatTurn(current: number, total: number): string {
  return `Turn ${current} / ${total}`;
}

export function formatScore(score: number | null | undefined): string {
  if (score == null) return "";
  return `Score: ${score.toFixed(1)}`;
}
