/**
 * Deterministic faction color from civilization name.
 * Hash the name to a hue, fixed saturation/lightness.
 */
function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash;
  }
  return Math.abs(hash);
}

export function factionColor(civName: string): string {
  const hue = hashString(civName) % 360;
  return `hsl(${hue}, 70%, 55%)`;
}

export function factionColorDark(civName: string): string {
  const hue = hashString(civName) % 360;
  return `hsl(${hue}, 70%, 35%)`;
}

export const DISPOSITION_COLORS: Record<string, string> = {
  hostile: "#ef4444",
  suspicious: "#eab308",
  neutral: "#6b7280",
  friendly: "#22c55e",
  allied: "#3b82f6",
};

export const UNCONTROLLED_COLOR = "#4b5563";
