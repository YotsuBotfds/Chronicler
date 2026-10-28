/** Independent, observed domains. Neither establishes a private merchant cash account. */
export interface NativeTransactionObservation {
  id: string;
  source_turn: number;
  operation: string;
  merchant_id: number;
  merchant_civ: number | null;
  merchant_civ_name: string | null;
  voyage_id: string | null;
  origin_region: number;
  origin_region_name: string;
  dest_region: number;
  dest_region_name: string;
  from_region: number;
  to_region: number;
  good_slot: number;
  quantity: number;
  origin_controller_name: string | null;
  dest_controller_name: string | null;
  cargo_basis: string;
  quantity_basis: string;
  loss_reason: string | null;
  loss_id: string | null;
  cargo_title_owner?: string | null;
  financial_eligible: boolean;
}

export interface PublicPurchaseObservation {
  id: string;
  source_turn: number;
  source_region: number;
  source_region_name: string;
  dest_region: number;
  dest_region_name: string;
  buyer: number;
  buyer_name: string;
  keeper: number;
  keeper_name: string;
  source_controller: number;
  source_controller_name: string;
  good: string;
  purchase_kind: string;
  sent: number;
  received: number;
  transit_loss: number;
  buyer_paid: number;
  foreign_ruler_credited: number;
  domestic_producer_sink: number;
  buyer_treasury_before: number;
  buyer_treasury_after: number;
  seller_treasury_before: number | null;
  seller_treasury_after: number | null;
  buyer_demand: number;
  source_demand: number;
  source_market_price: number;
  price_basis: string;
  treasury_basis: string;
  quantity_basis: string;
  financial_eligible: boolean;
}

export interface PublicPurchaseFrame {
  source_turn: number | null;
  as_of_turn?: number;
  phase: string;
  available: boolean;
  complete: boolean;
  unavailable_reason?: string | null;
  max_rows?: number;
  dropped_rows?: number;
  retained_key_duplicates?: number;
  duplicate_detection_complete?: boolean;
  observed_purchases?: number;
  rows: PublicPurchaseObservation[];
  counters?: Record<string, number>;
}

export interface TransactionReceiptsSnapshot {
  source_turn: number | null;
  phase: string;
  complete: boolean;
  mobility_executed: boolean;
  dropped_rows?: number;
  max_rows?: number;
  active_count?: number;
  known_active_count?: number;
  counters?: Record<string, number>;
  rows: NativeTransactionObservation[];
  public_purchases?: PublicPurchaseFrame;
}
