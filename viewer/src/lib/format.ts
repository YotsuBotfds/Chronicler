import type { TechEra } from "../types";

export const ERA_LABELS: Record<TechEra, string> = {
  tribal: "Tribal",
  bronze: "Bronze Age",
  iron: "Iron Age",
  classical: "Classical",
  medieval: "Medieval",
  renaissance: "Renaissance",
  industrial: "Industrial",
  information: "Information",
};

export const ERA_ORDER: TechEra[] = [
  "tribal",
  "bronze",
  "iron",
  "classical",
  "medieval",
  "renaissance",
  "industrial",
  "information",
];
