import type { FC } from "react";
import { factionColor, UNCONTROLLED_COLOR } from "../lib/colors";

interface RegionData {
  name: string;
  terrain: string;
  x: number | null;
  y: number | null;
}

interface RegionMapProps {
  regions: RegionData[];
  controllers?: Record<string, string | null>;
  width?: number;
  height?: number;
}

const TERRAIN_COLORS: Record<string, string> = {
  plains: "#4ade80",
  forest: "#166534",
  mountain: "#78716c",
  desert: "#fbbf24",
  tundra: "#93c5fd",
  swamp: "#65a30d",
  coast: "#38bdf8",
  jungle: "#15803d",
  steppe: "#a3e635",
  wasteland: "#a8a29e",
};

function circleLayout(
  count: number,
  width: number,
  height: number,
): { x: number; y: number }[] {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });
}

export const RegionMap: FC<RegionMapProps> = ({
  regions,
  controllers,
  width = 400,
  height = 300,
}) => {
  if (regions.length === 0) {
    return <svg width={width} height={height} className="bg-gray-900 rounded" />;
  }

  const hasPins = regions.some((r) => r.x !== null && r.y !== null);
  const fallback = !hasPins ? circleLayout(regions.length, width, height) : null;

  return (
    <svg width={width} height={height} className="bg-gray-900 rounded">
      {regions.map((r, i) => {
        const px = r.x !== null ? r.x * width : fallback![i].x;
        const py = r.y !== null ? r.y * height : fallback![i].y;
        const ctrl = controllers?.[r.name];
        const fillColor = ctrl
          ? factionColor(ctrl)
          : controllers
            ? UNCONTROLLED_COLOR
            : TERRAIN_COLORS[r.terrain] ?? "#6b7280";

        return (
          <g key={r.name}>
            <circle
              cx={px}
              cy={py}
              r={12}
              fill={fillColor}
              stroke="#1f2937"
              strokeWidth={1.5}
              opacity={0.9}
            />
            <text
              x={px}
              y={py + 22}
              textAnchor="middle"
              className="fill-gray-400 text-[9px]"
            >
              {r.name.length > 14 ? r.name.slice(0, 14) + "\u2026" : r.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
