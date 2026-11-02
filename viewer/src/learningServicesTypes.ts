/** Schema-1 paid academy materials and dated modeled service observations. */
export interface AcademyIdentity {
  seat_id: number; region: number; founder: number; founded_turn: number; seat_name: string;
}
export interface AcademyInventory extends AcademyIdentity {
  held: number | null; purchased_total: number | null; used_total: number | null; lost_total: number | null;
  retired: boolean; upkeep_source_turn: number | null; upkeep_lord: number | null; upkeep_due: number | null;
  upkeep_amount_paid: number | null; upkeep_satisfied: boolean | null;
}
export interface AcademyProcurement extends AcademyIdentity {
  lord: number; source_turn: number; upkeep_source_turn: number | null; upkeep_due: number | null;
  upkeep_amount_paid: number | null; upkeep_satisfied: boolean | null;
  scholar_upper_bound: number | null; learner_upper_bound: number | null; craft_price: number | null;
  market_stock: number; market_commitments: number | null; budget_before: number | null; held_before: number | null;
  purchased: number; paid: number; held_after: number | null; shortfalls: string[];
}
export interface AcademyTeaching extends AcademyIdentity {
  lord: number; source_turn: number; available_turn: number; learner_upper_bound: number | null;
  scholar_upper_bound: number | null; upkeep_source_turn: number | null; upkeep_lord: number | null;
  upkeep_due: number | null; upkeep_amount_paid: number | null; upkeep_satisfied: boolean | null; upkeep_applies: boolean | null;
  held_before: number | null; work_requested: number; work_available: number | null; work_reserved: number | null;
  work_delivered: number | null; learners_delivered: number | null; crafts_used: number | null;
  held_after: number | null; native_dropped: number | null;
}
export interface AcademySupplyLoss extends AcademyIdentity {
  source_turn: number; held_before: number | null; lost: number | null; held_after: number | null; reason: string;
}
export interface LearningServicesSnapshot {
  schema_version: 1; captured_turn: number; enabled: boolean; active: boolean;
  inventories: AcademyInventory[] | null; procurement_receipts: AcademyProcurement[] | null;
  teaching_receipts: AcademyTeaching[] | null; supply_losses: AcademySupplyLoss[] | null;
  totals: Record<string, number | null>;
}
