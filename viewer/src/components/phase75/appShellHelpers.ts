export function turnToPercent(turn: number, maxTurn: number): number {
  if (maxTurn <= 1) {
    return 0;
  }
  return ((turn - 1) / (maxTurn - 1)) * 100;
}

export function percentToTurn(percent: number, maxTurn: number): number {
  if (maxTurn <= 1) {
    return 1;
  }
  const clampedPercent = Math.max(0, Math.min(1, percent));
  return Math.round(clampedPercent * (maxTurn - 1)) + 1;
}

type TradeRelationshipLike = {
  disposition?: string;
  trade_volume?: number;
};

export function buildTradeLinks(
  centroids: Record<string, { x: number; y: number }>,
  relationships: Record<string, Record<string, TradeRelationshipLike>> | null,
  civNames: string[],
  tradeRoutes: Array<[string, string]> | null = null,
): Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }> {
  const links: Array<{ key: string; source: { x: number; y: number }; target: { x: number; y: number }; strength: number }> = [];
  const seen = new Set<string>();

  if (tradeRoutes !== null) {
    for (const [civName, other] of tradeRoutes) {
      const key = [civName, other].sort().join("--");
      if (seen.has(key) || !centroids[civName] || !centroids[other]) {
        continue;
      }
      seen.add(key);
      links.push({
        key,
        source: centroids[civName],
        target: centroids[other],
        strength: 1.0,
      });
    }
    return links;
  }

  for (const civName of civNames) {
    const relationMap = relationships?.[civName] ?? {};
    for (const [other, relation] of Object.entries(relationMap)) {
      const key = [civName, other].sort().join("--");
      if (seen.has(key) || !centroids[civName] || !centroids[other]) {
        continue;
      }
      seen.add(key);
      const strength = (relation.trade_volume ?? 0) > 0
        ? (relation.trade_volume ?? 0)
        : relation.disposition === "friendly" || relation.disposition === "allied"
          ? 0.6
          : 0;
      if (strength <= 0) {
        continue;
      }
      links.push({
        key,
        source: centroids[civName],
        target: centroids[other],
        strength,
      });
    }
  }

  return links;
}
