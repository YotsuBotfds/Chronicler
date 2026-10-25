/**
 * Read-only helpers for nomads (`history[n].nomads`), great-person agendas
 * (`history[n].gp_agendas`) and the governance runtime
 * (`history[n].civ_stats[civ].governance`).
 */
import type { Bundle, GovernanceSnapshot, GpAgenda, TurnSnapshot } from "../types";
import { buildSegments, humanize, type StripRow } from "./systems";

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";

// --- Nomads ---

/** Subsistence modes in `nomads.SUBSISTENCE_MODES` order. */
export const MODE_ORDER = ["sedentary", "agro_pastoral", "nomadic"] as const;

export const MODE_LABELS: Record<string, string> = {
  sedentary: "Sedentary",
  agro_pastoral: "Agro-pastoral",
  nomadic: "Nomadic",
};

/** Ordinal: settled grey, herding mid, nomadic strongest. */
export const MODE_COLORS: Record<string, string> = {
  sedentary: "#4a4a46",
  agro_pastoral: "#b58a2a",
  nomadic: "#e3b341",
};

export function modeLabel(mode: string): string {
  return MODE_LABELS[mode] ?? humanize(mode);
}

/** One row per civilization that was ever pastoral or nomadic: its mode over time. */
export function modeRows(history: TurnSnapshot[], civs: string[], color: (civ: string) => string): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return civs
    .filter((civ) => history.some((snapshot) => {
      const mode = snapshot.nomads?.modes[civ];
      return mode !== undefined && mode !== "sedentary";
    }))
    .map((civ) => {
      const modes = history.map((snapshot) => snapshot.nomads?.modes[civ] ?? null);
      const segments = buildSegments(turns, modes).map((segment) => {
        const fill = MODE_COLORS[segment.key] ?? MODE_COLORS.sedentary;
        return {
          start: segment.start,
          end: segment.end,
          color: fill,
          label: `${civ}: ${modeLabel(segment.key)}, turns ${segment.start}-${segment.end - 1}`,
          text: modeLabel(segment.key),
          textColor: segment.key === "sedentary" ? LIGHT_INK : DARK_INK,
        };
      });
      return { id: civ, label: civ, swatch: color(civ), segments };
    });
}

/** Civilizations whose herds were ever recorded, in world order. */
export function herdCivs(history: TurnSnapshot[], worldCivs: string[]): string[] {
  const names = new Set<string>();
  for (const snapshot of history) {
    for (const [civ, herd] of Object.entries(snapshot.nomads?.herds ?? {})) {
      if (herd > 0) {
        names.add(civ);
      }
    }
  }
  return worldCivs.filter((civ) => names.has(civ)).concat([...names].filter((civ) => !worldCivs.includes(civ)).sort());
}

export const NOMAD_COUNTERS: Array<[string, string]> = [
  ["raids", "Raids"],
  ["raids_repulsed", "Raids repulsed"],
  ["plunder", "Plunder taken"],
  ["raid_deaths", "Killed in raids"],
  ["tributes", "Tribute pacts"],
  ["tribute_paid", "Tribute paid"],
  ["hordes_formed", "Hordes formed"],
  ["horde_rides", "Horde rides"],
  ["nomad_conquests", "Nomad conquests"],
  ["sedentarizations", "Peoples settled"],
  ["dzuds", "Dzud winters"],
  ["herds_lost_dzud", "Herds lost to dzud"],
  ["herds_lost_pasture", "Herds lost to poor pasture"],
];

// --- Great-person agendas ---

export const ROLE_LABELS: Record<string, string> = {
  general: "General",
  merchant: "Merchant",
  prophet: "Prophet",
  scientist: "Scientist",
};

/** The simulation's own phrasing (`gp_agendas._PHRASES`), with the target resolved to a name. */
export function agendaGoal(agenda: Pick<GpAgenda, "kind" | "target">, bundle: Bundle): string {
  const target = agenda.target;
  const civName = (value: string | null) => {
    const index = value === null ? Number.NaN : Number(value);
    return Number.isInteger(index) ? (bundle.world_state.civilizations[index]?.name ?? `civ ${value}`) : (value ?? "?");
  };
  switch (agenda.kind) {
    case "lead_campaign": return `lead a campaign to take ${target ?? "?"}`;
    case "seize_throne": return "seize the throne";
    case "open_trade_route": return `open a trade route to ${civName(target)}`;
    case "protect_trade_route": return `keep the trade road to ${civName(target)} open`;
    case "found_trading_house": return "found a trading house";
    case "lend_to_crown": return "lend to the crown";
    case "spread_faith": return `bring the faith to ${target ?? "?"}`;
    case "found_shrine": return `raise a pilgrimage shrine in ${target ?? "?"}`;
    case "advance_learning": return `carry learning into the ${target ?? "next"} era`;
    case "invent_technique": return `discover ${target ? humanize(target) : "a technique"}`;
    default: return target ? `${humanize(agenda.kind)} (${target})` : humanize(agenda.kind);
  }
}

/** Region named by an agenda's target, when the kind targets a region. */
export function agendaRegion(agenda: Pick<GpAgenda, "kind" | "target">): string | null {
  return ["lead_campaign", "spread_faith", "found_shrine"].includes(agenda.kind) ? agenda.target : null;
}

export function civNameAt(bundle: Bundle, index: number): string {
  return bundle.world_state.civilizations[index]?.name ?? `civ ${index}`;
}

// --- Governance ---

export function governanceOf(snapshot: TurnSnapshot | null, civ: string): GovernanceSnapshot | null {
  return snapshot?.civ_stats[civ]?.governance ?? null;
}

/** True when any civilization row carries governance stats. */
export function hasGovernanceRecord(history: TurnSnapshot[]): boolean {
  return history.some((snapshot) => Object.values(snapshot.civ_stats).some((row) => row.governance != null));
}

/** Civilizations with governance stats anywhere, in world order. */
export function governanceCivs(history: TurnSnapshot[], worldCivs: string[]): string[] {
  const names = new Set<string>();
  for (const snapshot of history) {
    for (const [civ, row] of Object.entries(snapshot.civ_stats)) {
      if (row.governance) {
        names.add(civ);
      }
    }
  }
  return worldCivs.filter((civ) => names.has(civ));
}

const FORM_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#8f6fd8", "#5aa6a6", "#a3a13a"];

/** A fixed colour per government form, in order of first appearance. */
export function formPalette(history: TurnSnapshot[]): Map<string, string> {
  const forms = new Map<string, string>();
  for (const snapshot of history) {
    for (const row of Object.values(snapshot.civ_stats)) {
      const form = row.governance?.government_form;
      if (form && !forms.has(form)) {
        forms.set(form, FORM_COLORS[forms.size % FORM_COLORS.length]);
      }
    }
  }
  return forms;
}

/** One row per civilization: its form of government over time; a red mark under PSI-crisis turns. */
export function formRows(
  history: TurnSnapshot[],
  civs: string[],
  palette: Map<string, string>,
  color: (civ: string) => string,
): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return civs.map((civ) => {
    const forms = history.map((snapshot) => {
      const row = snapshot.civ_stats[civ];
      return row && row.alive !== false ? (row.governance?.government_form ?? null) : null;
    });
    const segments = buildSegments(turns, forms).map((segment) => ({
      start: segment.start,
      end: segment.end,
      color: palette.get(segment.key) ?? "#6b7280",
      label: `${civ}: ${humanize(segment.key)}, turns ${segment.start}-${segment.end - 1}`,
      text: humanize(segment.key),
      textColor: DARK_INK,
    }));
    const crises = history.map((snapshot) => (snapshot.civ_stats[civ]?.governance?.psi_crisis ? "crisis" : null));
    const marks = buildSegments(turns, crises).map((segment) => ({
      start: segment.start,
      end: segment.end,
      color: "#ef4444",
      label: `${civ}: age of troubles (PSI crisis), turns ${segment.start}-${segment.end - 1}`,
    }));
    return { id: civ, label: civ, swatch: color(civ), segments, marks };
  });
}
