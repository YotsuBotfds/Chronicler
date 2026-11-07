import { useMemo } from "react";
import { hasRecoveryChain, packagesOn } from "../../lib/recoveryChain";
import { watershedOn } from "../../lib/watershed";
import { infrastructureOn } from "../../lib/infrastructureCondition";
import type { SystemPanelProps } from "../../lib/systems";
import { ClearingProtection } from "./ClearingProtection";
import { Remittances } from "./Remittances";
import { Apprenticeship } from "./Apprenticeship";
import { Veterans } from "./Veterans";
import { RepairProjects } from "./RepairProjects";
import { CommonsRules } from "./CommonsRules";
import { FoodAllocation } from "./FoodAllocation";
import { GrainConvoys } from "./GrainConvoys";
import { HouseholdRetail } from "./HouseholdRetail";
import { InfrastructureCondition } from "./InfrastructureCondition";
import { LearningCohorts } from "./LearningCohorts";
import { LocalBudgets } from "./LocalBudgets";
import { MaintenanceObligation } from "./MaintenanceObligation";
import { OperatingWear } from "./OperatingWear";
import { RecoveryChain } from "./RecoveryChain";
import { RecoveryCrews } from "./RecoveryCrews";
import { Relocation } from "./Relocation";
import { TimberStock } from "./TimberStock";
import { TimberSupply } from "./TimberSupply";
import { WealthAccounting } from "./WealthAccounting";
import { WorkshopEconomics } from "./WorkshopEconomics";
import { WorkshopFinance } from "./WorkshopFinance";
import { Watershed } from "./Watershed";
import { Workshops } from "./Workshops";

/**
 * Livelihoods sprint packages (default off): each section reads only its own
 * dated record and says so when it is absent; nothing is inferred across them.
 */
const PACKAGES = ["workshops", "workshop_payroll", "food_allocation", "timber_stock", "grain_convoys",
  "commons_rules", "learning_cohorts", "relocation_costs", "local_budgets", "clearing_protection",
  "remittances", "apprenticeship", "veteran_reintegration", "repair_projects", "operating_wear", "timber_supply",
  "recovery_crews", "maintenance_obligation", "household_retail", "watershed", "workshop_economics", "infrastructure_condition", "wealth_accounting"];

export function LivelihoodsPanel(panelProps: SystemPanelProps) {
  const { bundle, snapshot, currentTurn, onSelectRegion } = panelProps;
  // The recovery chain (PL5c) reads the whole run, so it mounts on the run's records, not this snapshot's.
  const chain = useMemo(() => hasRecoveryChain(bundle), [bundle]);
  // RL8: these panels tell an absent record (unknown at this snapshot) from a malformed one, so they mount
  // whenever the run records their package, not only at snapshots that carry it.
  const on = useMemo(() => packagesOn(Array.isArray(bundle?.history) ? bundle.history : []), [bundle]);
  // The watershed panel also mounts on the run's records, so a snapshot without one reads as absent.
  const watershed = useMemo(() => watershedOn(bundle.history), [bundle]);
  // B3 infrastructure condition: mounted on the run's records too (absent reads as unknown).
  const infrastructure = useMemo(() => infrastructureOn(bundle.history), [bundle]);
  const row = snapshot as unknown as Record<string, unknown> | null;
  const raw = row?.livelihoods ?? null;
  const readable = typeof raw === "object" && raw !== null && !Array.isArray(raw)
    && (raw as Record<string, unknown>).schema_version === 1;
  const record = readable ? raw as Record<string, unknown> : null;
  const at = snapshot?.turn ?? currentTurn;
  const props = { bundle, snapshot, currentTurn, onSelectRegion };
  const mount = (key: "food_allocation" | "timber_stock" | "repair_projects" | "remittances") =>
    record !== null && (record[key] != null || on[key]);
  return <div className="systems-body">
    {raw !== null && !readable ? <p className="systems-note">The livelihoods record at snapshot {at} is unreadable (malformed or of an unknown version); nothing is shown from it.</p> : null}
    {record !== null && !PACKAGES.some((key) => record[key] != null) ? <p className="systems-note">The livelihoods record at snapshot {at} names no package this viewer reads.</p> : null}
    {chain ? <RecoveryChain {...panelProps} /> : null}
    {record?.workshops != null ? <Workshops {...props} /> : null}
    {record?.workshop_payroll != null ? <WorkshopFinance {...props} /> : null}
    {record?.workshop_payroll != null || record?.workshop_economics !== undefined ? <WorkshopEconomics {...props} /> : null}
    {mount("food_allocation") ? <FoodAllocation {...props} /> : null}
    {record?.household_retail != null ? <HouseholdRetail {...props} /> : null}
    {mount("timber_stock") ? <TimberStock {...props} /> : null}
    {record?.grain_convoys != null
      ? <section className="systems-section"><GrainConvoys snapshot={snapshot} bundle={bundle} /></section> : null}
    {record?.commons_rules != null ? <CommonsRules {...props} /> : null}
    {record?.learning_cohorts != null ? <LearningCohorts {...props} /> : null}
    {record?.relocation_costs != null ? <Relocation {...props} /> : null}
    {record?.local_budgets != null ? <LocalBudgets {...props} /> : null}
    {record?.clearing_protection != null ? <ClearingProtection {...props} /> : null}
    {record?.apprenticeship != null ? <Apprenticeship {...props} /> : null}
    {record?.operating_wear != null ? <OperatingWear {...props} /> : null}
    {record?.veteran_reintegration != null ? <Veterans {...props} /> : null}
    {mount("repair_projects") ? <RepairProjects {...props} /> : null}
    {record?.recovery_crews != null ? <RecoveryCrews {...props} /> : null}
    {record?.timber_supply != null ? <TimberSupply {...props} /> : null}
    {record?.maintenance_obligation != null ? <MaintenanceObligation {...props} /> : null}
    {mount("remittances") ? <Remittances {...props} /> : null}
    {watershed ? <Watershed {...props} /> : null}
    {infrastructure ? <InfrastructureCondition {...props} /> : null}
    {record?.wealth_accounting != null ? <WealthAccounting {...props} /> : null}
    {raw === null ? <p className="systems-note">No livelihoods observation is recorded at snapshot {at}.</p> : null}
  </div>;
}
