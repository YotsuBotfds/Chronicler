import { useEffect, useRef, useMemo, useState } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { Region, TurnSnapshot } from "../types";
import { factionColor, DISPOSITION_COLORS, UNCONTROLLED_COLOR } from "../lib/colors";

interface TerritoryMapProps {
  regions: Region[];
  history: TurnSnapshot[];
  currentTurn: number;
  showRelationships: boolean;
  onToggleRelationships: () => void;
}

interface MapNode extends SimulationNodeDatum {
  id: string;
  region: Region;
  controller: string | null;
  pinned: boolean;
}

interface MapLink extends SimulationLinkDatum<MapNode> {
  id: string;
}

/**
 * Group regions in a circle by initial controller.
 * Regions with the same controller at turn 0 are adjacent in the circle.
 */
function circleLayout(
  regions: Region[],
  initialControl: Record<string, string | null>,
  width: number,
  height: number,
): Map<string, { x: number; y: number }> {
  const groups: Map<string | null, string[]> = new Map();
  for (const r of regions) {
    const ctrl = initialControl[r.name] ?? null;
    if (!groups.has(ctrl)) groups.set(ctrl, []);
    groups.get(ctrl)!.push(r.name);
  }

  const ordered: string[] = [];
  for (const [ctrl, names] of groups) {
    if (ctrl !== null) ordered.push(...names);
  }
  const uncontrolled = groups.get(null) ?? [];
  ordered.push(...uncontrolled);

  const positions = new Map<string, { x: number; y: number }>();
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  ordered.forEach((name, i) => {
    const angle = (2 * Math.PI * i) / ordered.length - Math.PI / 2;
    positions.set(name, {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    });
  });

  return positions;
}

function buildEdges(
  regions: Region[],
  _history: TurnSnapshot[],
  initialControl: Record<string, string | null>,
): { source: string; target: string }[] {
  const hasPins = regions.some((r) => r.x !== null && r.y !== null);
  const edges: { source: string; target: string }[] = [];
  const seen = new Set<string>();

  if (hasPins) {
    for (let i = 0; i < regions.length; i++) {
      for (let j = i + 1; j < regions.length; j++) {
        const a = regions[i];
        const b = regions[j];
        if (a.x == null || a.y == null || b.x == null || b.y == null) continue;
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist <= 0.25) {
          edges.push({ source: a.name, target: b.name });
        }
      }
    }
  } else {
    const groups: Map<string, string[]> = new Map();
    for (const r of regions) {
      const ctrl = initialControl[r.name] ?? "__none__";
      if (!groups.has(ctrl)) groups.set(ctrl, []);
      groups.get(ctrl)!.push(r.name);
    }
    // Intra-faction edges: connect all regions within the same faction
    for (const names of groups.values()) {
      for (let i = 0; i < names.length; i++) {
        for (let j = i + 1; j < names.length; j++) {
          const key = [names[i], names[j]].sort().join("--");
          if (!seen.has(key)) {
            seen.add(key);
            edges.push({ source: names[i], target: names[j] });
          }
        }
      }
    }
    // Cross-faction boundary edges: connect one region from each faction pair
    // so the map reads as a connected world rather than isolated islands
    const groupKeys = [...groups.keys()];
    for (let i = 0; i < groupKeys.length; i++) {
      for (let j = i + 1; j < groupKeys.length; j++) {
        const a = groups.get(groupKeys[i])![0];
        const b = groups.get(groupKeys[j])![0];
        const key = [a, b].sort().join("--");
        if (!seen.has(key)) {
          seen.add(key);
          edges.push({ source: a, target: b });
        }
      }
    }
  }
  return edges;
}

export function TerritoryMap({
  regions,
  history,
  currentTurn,
  showRelationships,
  onToggleRelationships,
}: TerritoryMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [nodes, setNodes] = useState<MapNode[]>([]);
  const [links, setLinks] = useState<MapLink[]>([]);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  const WIDTH = 500;
  const HEIGHT = 400;

  const currentSnapshot = history.find((s) => s.turn === currentTurn);
  const initialControl = useMemo(() => {
    if (history.length === 0) return {} as Record<string, string | null>;
    return history[0].region_control;
  }, [history]);

  useEffect(() => {
    const hasPins = regions.some((r) => r.x !== null && r.y !== null);
    const circlePos = !hasPins
      ? circleLayout(regions, initialControl, WIDTH, HEIGHT)
      : null;

    const newNodes: MapNode[] = regions.map((r) => {
      let x: number, y: number, pinned: boolean;
      if (r.x !== null && r.y !== null) {
        x = r.x * WIDTH;
        y = r.y * HEIGHT;
        pinned = true;
      } else if (circlePos) {
        const pos = circlePos.get(r.name)!;
        x = pos.x;
        y = pos.y;
        pinned = true;
      } else {
        x = WIDTH / 2;
        y = HEIGHT / 2;
        pinned = false;
      }
      return {
        id: r.name,
        region: r,
        controller: initialControl[r.name] ?? r.controller,
        x,
        y,
        fx: pinned ? x : undefined,
        fy: pinned ? y : undefined,
        pinned,
      };
    });

    const edgeData = buildEdges(regions, history, initialControl);
    const newLinks: MapLink[] = edgeData.map((e) => ({
      id: `${e.source}--${e.target}`,
      source: e.source,
      target: e.target,
    }));

    if (!hasPins && !circlePos) {
      const sim = forceSimulation<MapNode>(newNodes)
        .force("link", forceLink<MapNode, MapLink>(newLinks).id((d) => d.id).distance(80))
        .force("charge", forceManyBody().strength(-200))
        .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
        .force("collide", forceCollide(30))
        .stop();

      for (let i = 0; i < 300; i++) sim.tick();
    }

    setNodes([...newNodes]);
    setLinks(newLinks);
  }, [regions, history, initialControl]);

  useEffect(() => {
    if (!currentSnapshot) return;
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        controller: currentSnapshot.region_control[n.id] ?? null,
      })),
    );
  }, [currentSnapshot]);

  const nodeMap = useMemo(() => {
    const m = new Map<string, MapNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  const relationshipEdges = useMemo(() => {
    if (!showRelationships || !currentSnapshot) return [];
    const edges: { source: string; target: string; disposition: string }[] = [];
    const seen = new Set<string>();
    for (const [civA, inner] of Object.entries(currentSnapshot.relationships)) {
      for (const [civB, rel] of Object.entries(inner)) {
        const key = [civA, civB].sort().join("--");
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push({ source: civA, target: civB, disposition: rel.disposition });
      }
    }
    return edges;
  }, [showRelationships, currentSnapshot]);

  const factionCentroids = useMemo(() => {
    const centroids: Record<string, { x: number; y: number }> = {};
    const groups: Record<string, MapNode[]> = {};
    for (const n of nodes) {
      const ctrl = n.controller ?? "__none__";
      if (!groups[ctrl]) groups[ctrl] = [];
      groups[ctrl].push(n);
    }
    for (const [ctrl, ns] of Object.entries(groups)) {
      const cx = ns.reduce((s, n) => s + (n.x ?? 0), 0) / ns.length;
      const cy = ns.reduce((s, n) => s + (n.y ?? 0), 0) / ns.length;
      centroids[ctrl] = { x: cx, y: cy };
    }
    return centroids;
  }, [nodes]);

  return (
    <div className="relative">
      <button
        onClick={onToggleRelationships}
        className={`absolute top-2 right-2 z-10 text-xs px-2 py-1 rounded ${
          showRelationships ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"
        }`}
      >
        {showRelationships ? "Diplomacy" : "Adjacency"}
      </button>
      <svg ref={svgRef} width={WIDTH} height={HEIGHT} className="bg-gray-900 rounded">
        {/* Adjacency edges */}
        {!showRelationships &&
          links.map((link) => {
            const s = nodeMap.get(typeof link.source === "string" ? link.source : (link.source as MapNode).id);
            const t = nodeMap.get(typeof link.target === "string" ? link.target : (link.target as MapNode).id);
            if (!s || !t) return null;
            return (
              <line
                key={link.id}
                x1={s.x ?? 0}
                y1={s.y ?? 0}
                x2={t.x ?? 0}
                y2={t.y ?? 0}
                stroke="#374151"
                strokeWidth={1}
              />
            );
          })}

        {/* Relationship edges */}
        {showRelationships &&
          relationshipEdges.map((e) => {
            const s = factionCentroids[e.source];
            const t = factionCentroids[e.target];
            if (!s || !t) return null;
            return (
              <line
                key={`rel-${e.source}-${e.target}`}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={DISPOSITION_COLORS[e.disposition] ?? "#6b7280"}
                strokeWidth={2}
                opacity={0.7}
              />
            );
          })}

        {/* Region nodes */}
        {nodes.map((n) => {
          const size = 8 + n.region.carrying_capacity * 2;
          const color = n.controller
            ? factionColor(n.controller)
            : UNCONTROLLED_COLOR;

          return (
            <g key={n.id}>
              <circle
                cx={n.x ?? 0}
                cy={n.y ?? 0}
                r={size}
                fill={color}
                stroke="#1f2937"
                strokeWidth={1.5}
                className="cursor-pointer"
                onClick={(e) => {
                  const controlChanges: string[] = [];
                  let lastCtrl: string | null | undefined = undefined;
                  for (const snap of history) {
                    const ctrl = snap.region_control[n.id] ?? null;
                    if (ctrl !== lastCtrl) {
                      controlChanges.push(`Turn ${snap.turn}: ${ctrl ?? "Uncontrolled"}`);
                      lastCtrl = ctrl;
                    }
                  }
                  const historyText = controlChanges.length > 0
                    ? `\nHistory:\n${controlChanges.join("\n")}`
                    : "";
                  setTooltip(
                    tooltip?.text.startsWith(n.region.name) ? null : {
                      x: e.clientX,
                      y: e.clientY,
                      text: `${n.region.name}\n${n.region.terrain} · ${n.region.resources}\nCap: ${n.region.carrying_capacity}\nCtrl: ${n.controller ?? "None"}${historyText}`,
                    },
                  );
                }}
              />
              <text
                x={n.x ?? 0}
                y={(n.y ?? 0) + size + 12}
                textAnchor="middle"
                className="fill-gray-400 text-[9px]"
              >
                {n.region.name.length > 12
                  ? n.region.name.slice(0, 12) + "\u2026"
                  : n.region.name}
              </text>
            </g>
          );
        })}
      </svg>

      {tooltip && (
        <div
          className="fixed z-50 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-xs text-gray-200 whitespace-pre-line pointer-events-none"
          style={{ left: tooltip.x + 12, top: tooltip.y - 10 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
