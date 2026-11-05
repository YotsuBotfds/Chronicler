import type { SystemPanelProps } from "../../lib/systems";
import { ClearingProtection } from "./ClearingProtection";
import { Remittances } from "./Remittances";
import { Apprenticeship } from "./Apprenticeship";
import { Veterans } from "./Veterans";
import { RepairProjects } from "./RepairProjects";
import { CommonsRules } from "./CommonsRules";
import { FoodAllocation } from "./FoodAllocation";
import { GrainConvoys } from "./GrainConvoys";
import { LearningCohorts } from "./LearningCohorts";
import { LocalBudgets } from "./LocalBudgets";
import { Relocation } from "./Relocation";
import { TimberStock } from "./TimberStock";
import { WorkshopFinance } from "./WorkshopFinance";
import { Workshops } from "./Workshops";

/**
 * Livelihoods sprint packages (default off): each section reads only its own
 * dated record and says so when it is absent; nothing is inferred across them.
 */
const PACKAGES = ["workshops", "workshop_payroll", "food_allocation", "timber_stock", "grain_convoys",
  "commons_rules", "learning_cohorts", "relocation_costs", "local_budgets", "clearing_protection",
  "remittances", "apprenticeship", "veteran_reintegration", "repair_projects"];

export function LivelihoodsPanel({ bundle, snapshot, currentTurn, onSelectRegion }: SystemPanelProps) {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const raw = row?.livelihoods ?? null;
  const readable = typeof raw === "object" && raw !== null && !Array.isArray(raw)
    && (raw as Record<string, unknown>).schema_version === 1;
  const record = readable ? raw as Record<string, unknown> : null;
  const at = snapshot?.turn ?? currentTurn;
  const props = { bundle, snapshot, currentTurn, onSelectRegion };
  return <div className="systems-body">
    {raw !== null && !readable ? <p className="systems-note">The livelihoods record at snapshot {at} is unreadable (malformed or of an unknown version); nothing is shown from it.</p> : null}
    {record !== null && !PACKAGES.some((key) => record[key] != null) ? <p className="systems-note">The livelihoods record at snapshot {at} names no package this viewer reads.</p> : null}
    {record?.workshops != null ? <Workshops {...props} /> : null}
    {record?.workshop_payroll != null ? <WorkshopFinance {...props} /> : null}
    {record?.food_allocation != null ? <FoodAllocation {...props} /> : null}
    {record?.timber_stock != null ? <TimberStock {...props} /> : null}
    {record?.grain_convoys != null
      ? <section className="systems-section"><GrainConvoys snapshot={snapshot} bundle={bundle} /></section> : null}
    {record?.commons_rules != null ? <CommonsRules {...props} /> : null}
    {record?.learning_cohorts != null ? <LearningCohorts {...props} /> : null}
    {record?.relocation_costs != null ? <Relocation {...props} /> : null}
    {record?.local_budgets != null ? <LocalBudgets {...props} /> : null}
    {record?.clearing_protection != null ? <ClearingProtection {...props} /> : null}
    {record?.apprenticeship != null ? <Apprenticeship {...props} /> : null}
    {record?.veteran_reintegration != null ? <Veterans {...props} /> : null}
    {record?.repair_projects != null ? <RepairProjects {...props} /> : null}
    {record?.remittances != null ? <Remittances {...props} /> : null}
    {raw === null ? <p className="systems-note">No livelihoods observation is recorded at snapshot {at}.</p> : null}
  </div>;
}
