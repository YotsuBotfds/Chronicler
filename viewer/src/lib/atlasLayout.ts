/**
 * The atlas: node positions for the regions (fitted to the pins, or grouped
 * by controller when no region has a pin), the links drawn between them and
 * the civilizations' ranking. Pure functions, moved unchanged from
 * `components/phase75/AppShell.tsx`.
 */
import type { MapNode, RegionLike } from "../components/phase75/appShellTypes";
import { atlasPoint, type PinFrame } from "../components/phase75/appShellHelpers";
import type { CivilizationView } from "./civilizationViews";

export function computeAtlasLayout(
  regions: RegionLike[],
  controllers: Record<string, string | null>,
  frame: PinFrame,
): MapNode[] {
  if (regions.length === 0) {
    return [];
  }

  const hasPins = regions.some((region) => region.x !== null && region.y !== null);
  if (hasPins) {
    return regions.map((region) => ({
      region,
      controller: controllers[region.name],
      ...atlasPoint(region.x ?? frame.x0 + frame.sx / 2, region.y ?? frame.y0 + frame.sy / 2, frame),
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
        controller: controllers[region.name],
        x: groupCenterX + Math.cos(localAngle) * localRadius,
        y: groupCenterY + Math.sin(localAngle) * localRadius,
      });
    });
  });

  return nodes;
}

export function buildRegionConnections(nodes: MapNode[]): Array<{ source: MapNode; target: MapNode }> {
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

export function computeControllerCentroids(nodes: MapNode[]): Record<string, { x: number; y: number }> {
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

export function buildCampaignLinks(
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

export function dominantCivilization(civilizations: CivilizationView[]): CivilizationView | null {
  if (civilizations.length === 0) {
    return null;
  }

  return [...civilizations].sort((left, right) => {
    const leftTotal = left.population + left.military + left.economy + left.culture + left.stability;
    const rightTotal = right.population + right.military + right.economy + right.culture + right.stability;
    return rightTotal - leftTotal;
  })[0];
}

export function sortCivilizations(civilizations: CivilizationView[]): CivilizationView[] {
  return [...civilizations].sort((left, right) => {
    const leftScore = left.economy + left.culture + left.military + left.population + left.stability;
    const rightScore = right.economy + right.culture + right.military + right.population + right.stability;
    return rightScore - leftScore;
  });
}
