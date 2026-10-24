import { useMemo, useState } from "react";
import {
  preferredSystem, presentSystems, SYSTEM_LABELS, type SystemKey, type SystemPanelProps,
} from "../../lib/systems";
import { DiplomacyPanel } from "./DiplomacyPanel";
import { EpidemicsPanel } from "./EpidemicsPanel";
import { FinancePanel } from "./FinancePanel";
import { MaritimePanel } from "./MaritimePanel";
import { TechniquesPanel } from "./TechniquesPanel";
import "./systems.css";

const PANELS: Record<SystemKey, (props: SystemPanelProps) => React.ReactElement> = {
  epidemics: EpidemicsPanel,
  finance: FinancePanel,
  diplomacy: DiplomacyPanel,
  techniques: TechniquesPanel,
  maritime: MaritimePanel,
};

/**
 * Panels for the default-off systems a bundle records. Renders nothing for a
 * bundle without any of them, so older bundles and runs with every system off
 * look exactly as before.
 */
export function SystemsPanel(props: SystemPanelProps & { surface: string }) {
  const { bundle, surface, ...panelProps } = props;
  const present = useMemo(() => presentSystems(bundle.history), [bundle.history]);
  const [chosen, setChosen] = useState<SystemKey | null>(null);
  if (present.length === 0) {
    return null;
  }
  const active = chosen && present.includes(chosen) ? chosen : (preferredSystem(surface, present) ?? present[0]);
  const Panel = PANELS[active];

  return (
    <section className="systems-shell phase75-panel" aria-label="Simulation systems">
      <header className="systems-header">
        <div>
          <div className="phase75-overline">Simulation systems</div>
          <h2>Default-off systems recorded in this run</h2>
          <p>Values are the bundle&apos;s own per-turn records at the scrubbed turn; selecting an event pins it in the inspector.</p>
        </div>
        <div className="phase75-rail-tabs systems-tabs" role="tablist" aria-label="Simulation systems">
          {present.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={key === active}
              className={`phase75-rail-tab${key === active ? " active" : ""}`}
              onClick={() => setChosen(key)}
            >
              {SYSTEM_LABELS[key]}
            </button>
          ))}
        </div>
      </header>
      <div role="tabpanel" aria-label={SYSTEM_LABELS[active]}>
        <Panel key={active} bundle={bundle} {...panelProps} />
      </div>
    </section>
  );
}
