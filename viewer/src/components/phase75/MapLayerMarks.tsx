import type { LegendItem, MapLayerView } from "../../lib/mapLayers";

export interface PlacedNode {
  name: string;
  x: number;
  y: number;
  r: number;
}

type Point = { x: number; y: number };

const ARROW = 7;

function curve(from: PlacedNode, to: PlacedNode, arrow: boolean): string | null {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (length < 1) {
    return null;
  }
  const ux = dx / length;
  const uy = dy / length;
  // Bend to the right of travel, so A->B and B->A stay apart.
  const bend = Math.min(40, length * 0.14);
  const control = { x: (from.x + to.x) / 2 - uy * bend, y: (from.y + to.y) / 2 + ux * bend };
  const start = { x: from.x + ux * from.r, y: from.y + uy * from.r };
  const trim = to.r + (arrow ? ARROW * 0.6 : 0);
  const end = { x: to.x - ux * trim, y: to.y - uy * trim };
  return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} Q ${control.x.toFixed(1)} ${control.y.toFixed(1)} ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

function burst(center: Point, size: number): string {
  const points: string[] = [];
  for (let index = 0; index < 16; index += 1) {
    const angle = (Math.PI * 2 * index) / 16 - Math.PI / 2;
    const radius = index % 2 === 0 ? size : size * 0.45;
    points.push(`${(center.x + Math.cos(angle) * radius).toFixed(1)},${(center.y + Math.sin(angle) * radius).toFixed(1)}`);
  }
  return points.join(" ");
}

function diamond(center: Point, size: number): string {
  return `${center.x},${center.y - size} ${center.x + size},${center.y} ${center.x},${center.y + size} ${center.x - size},${center.y}`;
}

/**
 * Marks of one thematic map layer, drawn over the region nodes: outlines,
 * flows with arrowheads, markers beside their region and sea-zone hubs with
 * spokes to their ports. Every mark carries its own hover text.
 */
export function MapLayerMarks({
  view,
  nodes,
  toAtlas,
}: {
  view: MapLayerView;
  nodes: PlacedNode[];
  /** Map coordinates (the regions' pin space) to atlas viewBox coordinates. */
  toAtlas: (x: number, y: number) => Point;
}) {
  const byName = new Map(nodes.map((node) => [node.name, node]));
  const colors = [...new Set(view.flows.map((flow) => flow.color))];
  const markerId = (color: string) => `layer-arrow-${view.key}-${colors.indexOf(color)}`;
  const perRegion = new Map<string, number>();

  return (
    <g className="phase75-layer-marks" aria-label={`${view.key} layer`}>
      <defs>
        {colors.map((color) => (
          <marker
            key={color}
            id={markerId(color)}
            viewBox="0 0 10 10"
            refX="5"
            refY="5"
            markerWidth={ARROW}
            markerHeight={ARROW}
            markerUnits="userSpaceOnUse"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
          </marker>
        ))}
      </defs>

      {[...view.outlines.entries()].map(([name, color]) => {
        const node = byName.get(name);
        return node ? (
          <circle key={`outline-${name}`} className="phase75-layer-outline" cx={node.x} cy={node.y} r={node.r + 4} stroke={color} />
        ) : null;
      })}

      {view.hubs.map((hub) => {
        const ports = hub.ports.map((name) => byName.get(name)).filter((node): node is PlacedNode => !!node);
        let center: Point | null = hub.x !== null && hub.y !== null ? toAtlas(hub.x, hub.y) : null;
        if (!center && ports.length > 0) {
          center = {
            x: ports.reduce((sum, node) => sum + node.x, 0) / ports.length,
            y: ports.reduce((sum, node) => sum + node.y, 0) / ports.length + 26,
          };
        }
        if (!center) {
          return null;
        }
        const hubCenter = center;
        return (
          <g key={`hub-${hub.id}`} className="phase75-sea-hub">
            {ports.map((port) => (
              <line key={port.name} className="phase75-sea-spoke" x1={hubCenter.x} y1={hubCenter.y} x2={port.x} y2={port.y} />
            ))}
            <polygon points={diamond(hubCenter, 11)} fill={hub.fill} stroke={hub.ring ?? "rgba(240, 239, 236, 0.7)"}
              strokeWidth={hub.ring ? 3.5 : 1.2}>
              <title>{hub.title}</title>
            </polygon>
            {hub.label && <text className="phase75-sea-label" x={hubCenter.x} y={hubCenter.y - 15}>{hub.label}</text>}
          </g>
        );
      })}

      {view.flows.map((flow, index) => {
        const from = byName.get(flow.from);
        const to = byName.get(flow.to);
        const d = from && to ? curve(from, to, !flow.dashed) : null;
        return d ? (
          <path
            key={`flow-${index}-${flow.from}-${flow.to}`}
            className={`phase75-layer-flow${flow.dashed ? " dashed" : ""}`}
            d={d}
            stroke={flow.color}
            strokeWidth={flow.width}
            markerEnd={flow.dashed ? undefined : `url(#${markerId(flow.color)})`}
          >
            <title>{flow.title}</title>
          </path>
        ) : null;
      })}

      {view.markers.map((marker, index) => {
        const node = byName.get(marker.region);
        if (!node) {
          return null;
        }
        const slot = perRegion.get(marker.region) ?? 0;
        perRegion.set(marker.region, slot + 1);
        const angle = -Math.PI / 4 + slot * (Math.PI / 3.2);
        const center = { x: node.x + Math.cos(angle) * node.r, y: node.y + Math.sin(angle) * node.r };
        return marker.shape === "burst" ? (
          <polygon key={`marker-${index}`} className="phase75-layer-marker" points={burst(center, marker.size)} fill={marker.color}>
            <title>{marker.title}</title>
          </polygon>
        ) : (
          <circle key={`marker-${index}`} className="phase75-layer-marker" cx={center.x} cy={center.y} r={marker.size} fill={marker.color}>
            <title>{marker.title}</title>
          </circle>
        );
      })}
    </g>
  );
}

export function MapLayerLegend({ items, note }: { items: LegendItem[]; note: string }) {
  return (
    <div className="phase75-layer-legend" aria-label="Map layer legend">
      <p>{note}</p>
      {items.length > 0 && (
        <div className="phase75-layer-legend-items">
          {items.map((item) => (
            <span key={`${item.kind}-${item.label}`} className="phase75-layer-legend-item">
              <span className={`phase75-layer-key ${item.kind}`} style={item.kind === "ring" || item.kind === "line"
                ? { borderColor: item.color } : { backgroundColor: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
