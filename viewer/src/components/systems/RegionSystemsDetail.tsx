import type { TurnSnapshot } from "../../types";
import { crisesAtSnapshot, sufficiencyByRegion, type FamineSpan } from "../../lib/food";
import {
  formatShare, pathogenColor, pathogenLabel, regionOutbreaks, regionPractice, techniqueLabel,
} from "../../lib/systems";

const PRACTICE_LIMIT = 6;

/**
 * Per-region food, war, epidemic and technique state at the scrubbed
 * snapshot, for the shell's region inspector. Each block renders only when
 * the bundle carries that system (food: the food field or recorded famines).
 */
export function RegionSystemsDetail({
  snapshot,
  region,
  famine = [],
  regionNames = [],
}: {
  snapshot: TurnSnapshot | null;
  region: string;
  /** Food-crisis spans of the run, famine and dearth (`lib/food.foodCrisisSpans`). */
  famine?: FamineSpan[];
  /** Region names in world order, to read the food field by index. */
  regionNames?: string[];
}) {
  const epidemics = snapshot?.epidemics;
  const techniques = snapshot?.techniques;
  const campaign = snapshot?.campaign;
  const turn = snapshot?.turn ?? 0;
  const span = crisesAtSnapshot(famine.filter((entry) => entry.region === region), turn)[0] ?? null;
  const sufficiency = snapshot?.food ? sufficiencyByRegion(snapshot, regionNames).get(region) : undefined;
  const showFood = !!snapshot?.food || famine.length > 0;
  if (!epidemics && !techniques && !campaign && !showFood) {
    return null;
  }
  const controller = snapshot?.region_control?.[region] ?? null;
  const outbreaks = regionOutbreaks(snapshot, region);
  const practice = regionPractice(snapshot, region);
  const armies = campaign?.armies.filter((army) => army.region === region) ?? [];
  const occupation = campaign?.occupations.find((entry) => entry.region === region) ?? null;

  return (
    <div className="systems-region-detail" aria-label={`Systems in ${region}`}>
      {showFood && (
        <div className="systems-region-block" aria-label={`Food in ${region}`}>
          <div className="phase75-overline">Food · turn {turn}</div>
          {snapshot?.food && (
            <div className="phase75-stat-row">
              <span>Food ÷ need</span>
              <strong>{sufficiency === undefined ? "Not observed" : sufficiency.toFixed(2)}</strong>
            </div>
          )}
          <div className="phase75-stat-row">
            <span>{span?.kind === "dearth" ? "Dearth" : "Famine"}</span>
            <strong>{span ? `Since turn ${span.start}` : "None"}</strong>
          </div>
        </div>
      )}
      {campaign && (armies.length > 0 || occupation) && (
        <div className="systems-region-block" aria-label={`War in ${region}`}>
          <div className="phase75-overline">War · turn {turn}</div>
          {occupation && (
            <div className="phase75-stat-row">
              <span>Occupied by</span>
              <strong>{occupation.occupier} since turn {occupation.since_turn}</strong>
            </div>
          )}
          {armies.map((army) => (
            <div key={army.id} className="phase75-mini-card">
              <strong>{army.name}</strong>
              <span>{army.soldiers} soldiers · {army.phase.replace(/_/g, " ")}{army.objective && army.objective !== region ? ` toward ${army.objective}` : ""}</span>
            </div>
          ))}
        </div>
      )}
      {epidemics && (
        <div className="systems-region-block" aria-label={`Epidemics in ${region}`}>
          <div className="phase75-overline">Epidemics · turn {turn}</div>
          {outbreaks.length === 0 ? (
            <div className="phase75-stat-row"><span>Outbreaks</span><strong>None reportable</strong></div>
          ) : outbreaks.map((outbreak) => (
            <div key={outbreak.pathogen} className="phase75-mini-card">
              <strong>
                <span className="phase75-civ-swatch" style={{ backgroundColor: pathogenColor(outbreak.pathogen) }} />
                {" "}{pathogenLabel(outbreak.pathogen)}{outbreak.virgin ? " (virgin soil)" : ""}
              </strong>
              <span>
                Prevalence {formatShare(outbreak.prevalence, 2)} · immune {formatShare(outbreak.immune)} · {outbreak.cases.toFixed(1)} new
                cases · {outbreak.deaths} death{outbreak.deaths === 1 ? "" : "s"}
              </span>
            </div>
          ))}
          {controller && (
            <div className="phase75-stat-row">
              <span>Quarantine</span>
              <strong>{epidemics.quarantine.includes(controller) ? `${controller} has closed its borders` : "Borders open"}</strong>
            </div>
          )}
        </div>
      )}
      {techniques && (
        <div className="systems-region-block" aria-label={`Techniques in ${region}`}>
          <div className="phase75-overline">Techniques · turn {turn}</div>
          {practice === null ? (
            <div className="phase75-stat-row"><span>Practice</span><strong>Not exported in this bundle</strong></div>
          ) : practice.length === 0 ? (
            <div className="phase75-stat-row"><span>Practice</span><strong>None recorded</strong></div>
          ) : (
            <>
              {practice.slice(0, PRACTICE_LIMIT).map(([key, level]) => (
                <div key={key} className="phase75-metric-bar">
                  <div className="phase75-stat-row">
                    <span>{techniqueLabel(key)}</span>
                    <strong>{formatShare(level, 0)}</strong>
                  </div>
                  <div className="phase75-metric-track">
                    <div className="phase75-metric-fill" style={{ width: `${Math.max(4, Math.min(100, level * 100))}%` }} />
                  </div>
                </div>
              ))}
              {practice.length > PRACTICE_LIMIT && (
                <div className="phase75-stat-row"><span>Also practised</span><strong>{practice.length - PRACTICE_LIMIT} more</strong></div>
              )}
            </>
          )}
          {controller && techniques.known[controller] !== undefined && (
            <div className="phase75-stat-row">
              <span>{controller} knows</span>
              <strong>{techniques.known[controller]} technique{techniques.known[controller] === 1 ? "" : "s"}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
