//! Livelihoods L6a: typed agent-wealth transfers and the paid-work income share.
//!
//! Two transient seams that later lanes reuse (L7 relocation uses the
//! transfer; any paid work consumer uses the income share):
//!
//! * [`transfer`] credits (positive) or debits (negative) the native wealth
//!   of named stable agent ids in whole milli-units: 1000 milli-units are one
//!   wealth unit, the unit domestic credit already equates with one treasury
//!   unit. A credit stops at `MAX_WEALTH` and a debit at zero; whatever the
//!   limit refuses is returned as the row's residual, never dropped or
//!   carried here, so the caller keeps it. A dead or unknown id receives
//!   nothing (status absent, full residual). One call per (turn, purpose,
//!   batch) key: a repeated or older key is refused before any change, so a
//!   transfer is applied exactly once. Rows are validated (purpose, unique
//!   ids, magnitude) before mutation: all or none. The receipt returned is
//!   the typed record (requested, applied, residual, status per row).
//! * [`install_paid_work`] arms a one-tick per-agent deduction of ordinary
//!   occupational income for paid work time, consumed by the next wealth
//!   phase (as `health_work_loss` is). Each row must already hold a work
//!   reservation for the turn of at least that fraction, so paid time is
//!   always reserved time. The wealth phase removes `share` of the person's
//!   ordinary income (the time is paid by wages instead, never on top) and
//!   records each actual deduction in a receipt taken once by the caller.
//! * [`extend_paid_work`] (recovery-skills RS0) merges further rows into the
//!   turn's pending install, or arms one: a later paid-work consumer of the
//!   same turn (apprentice stipends, repair wages) adds its people without
//!   replacing L6a's. Each person still has at most one paid share per turn,
//!   within their reservations for that turn.
//! * [`remit`] (recovery-skills RS4) is the one pairwise transfer: a
//!   sender pays a recipient an amount plus a courier fee under the purpose
//!   `remittance`, both parties validated before any change, with the
//!   recipient's ceiling excess refunded, once per (turn, purpose, batch).
//! * [`settle_pairs`] (connected-world A4, titled trade) is the generic
//!   pairwise payment: each row moves an amount from a payer to a payee
//!   under a pairwise purpose (`cargo_purchase`, `cargo_sale`), with no fee
//!   and no trip rule, the payee's ceiling excess staying with the payer,
//!   once per (turn, purpose, batch).
//! * [`install_retail_income`] (household retail L6b) arms a one-tick
//!   replacement of pilot-region farmers' ordinary farm income: the wealth
//!   phase records and zeroes what is left of it after the teaching,
//!   learning and paid-work deductions ([`retail_income`]), so their cash
//!   income from farming is their food sales, never both. The purchases
//!   themselves are settled inside the tick ([`settle_food_purchases`]).
//!
//! Both are transient: the key log, a pending share and an untaken receipt
//! are never checkpointed (exact checkpoints are taken between turns, when
//! none is pending). No random draws; the pool's agents are never added or
//! removed, and no slot index leaves this module as an identity.

use crate::agent::MAX_WEALTH;
use crate::pool::AgentPool;

/// Milli-units per wealth (and treasury) unit.
pub const MILLI: i64 = 1000;
/// Transfer purposes, in declaration order (append only). Codes 2-4 were
/// appended by the recovery-skills groundwork (RS0) for apprentice stipends
/// (RS1), repair wages (RS2) and remittances (RS4); 5-6 by household retail
/// (L6b) for household food purchases (settled in the tick) and granary
/// procurement from owners (paid by Python through [`transfer`]); 7 by
/// workshop economics (A3) for households buying a firm's wares (debit rows
/// of [`transfer`]; the firm's cash is a Python account); 8-9 by titled trade
/// (A4) for pairwise payments between people ([`settle_pairs`]): a merchant
/// buying owners' food (`cargo_purchase`) and, from later slices, a buyer
/// paying a cargo's holder (`cargo_sale`).
pub const PURPOSES: [&str; 10] = ["workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance",
                                  "food_purchase", "food_procurement", "wares_purchase", "cargo_purchase",
                                  "cargo_sale"];
pub const PURPOSE_WORKSHOP_WAGE: u8 = 0;
pub const PURPOSE_RELOCATION_FARE: u8 = 1;
pub const PURPOSE_APPRENTICE_STIPEND: u8 = 2;
pub const PURPOSE_REPAIR_WAGE: u8 = 3;
pub const PURPOSE_REMITTANCE: u8 = 4;
pub const PURPOSE_FOOD_PURCHASE: u8 = 5;
pub const PURPOSE_FOOD_PROCUREMENT: u8 = 6;
pub const PURPOSE_WARES_PURCHASE: u8 = 7;
pub const PURPOSE_CARGO_PURCHASE: u8 = 8;
pub const PURPOSE_CARGO_SALE: u8 = 9;
/// Purposes [`settle_pairs`] accepts (pairwise payments between people).
pub const PAIRWISE_PURPOSES: [u8; 2] = [PURPOSE_CARGO_PURCHASE, PURPOSE_CARGO_SALE];
/// Largest magnitude accepted for one row (10^12 milli-units).
pub const MAX_ROW_MILLIS: i64 = 1_000_000_000_000;
/// Row statuses, in declaration order (append only).
pub const STATUS_APPLIED: u8 = 0;
pub const STATUS_LIMITED: u8 = 1;
pub const STATUS_ABSENT: u8 = 2;

#[derive(Clone, Debug, PartialEq)]
pub struct TransferRow {
    pub agent_id: u32,
    pub requested: i64,
    pub applied: i64,
    pub residual: i64,
    pub status: u8,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TransferReceipt {
    pub turn: u32,
    pub purpose: u8,
    pub batch: u32,
    pub rows: Vec<TransferRow>,
}

/// One turn's armed paid-work deduction: (expected stable id, share) by slot.
#[derive(Clone, Debug, PartialEq)]
pub struct PaidWork {
    pub turn: u32,
    pub by_slot: Vec<(u32, f32)>,
}

/// What the wealth phase actually deducted: (id, share, ordinary income
/// before the deduction, deducted amount), in slot order.
#[derive(Clone, Debug, PartialEq)]
pub struct PaidWorkReceipt {
    pub turn: u32,
    pub rows: Vec<(u32, f32, f32, f32)>,
}

/// L6b: one turn's armed replacement of farm income in the listed regions.
#[derive(Clone, Debug, PartialEq)]
pub struct RetailIncome {
    pub turn: u32,
    /// By region index: whether its farmers' remaining farm income is replaced.
    pub regions: Vec<bool>,
}

/// L6b: what the wealth phase replaced, (id, remaining ordinary farm income
/// recorded and set to zero) in slot order, one row per farmer of a listed
/// region alive at the wealth phase (zero rows included).
#[derive(Clone, Debug, PartialEq)]
pub struct RetailIncomeReceipt {
    pub turn: u32,
    pub rows: Vec<(u32, f32)>,
}

pub(crate) fn floor_millis(value: f32) -> i64 {
    if value.is_finite() && value > 0.0 { (value as f64 * MILLI as f64).floor() as i64 } else { 0 }
}

/// Apply `rows` (stable id, signed milli-units) once for `(turn, purpose, batch)`.
/// The pairwise purposes ([`PAIRWISE_PURPOSES`]) are refused: they are paid
/// only through [`settle_pairs`].
pub fn transfer(pool: &mut AgentPool, turn: u32, purpose: u8, batch: u32, rows: &[(u32, i64)])
    -> Result<TransferReceipt, &'static str> {
    if purpose as usize >= PURPOSES.len() {
        return Err("unknown wealth transfer purpose");
    }
    if PAIRWISE_PURPOSES.contains(&purpose) {
        // A4: payments between people are paid only pairwise (settle_pairs),
        // so a one-sided credit can never mint wealth under these purposes.
        return Err("a pairwise wealth transfer purpose is paid only through settle_pairs");
    }
    let mut seen = std::collections::HashSet::with_capacity(rows.len());
    for &(id, amount) in rows {
        if !seen.insert(id) {
            return Err("duplicate agent in wealth transfer");
        }
        if amount.unsigned_abs() > MAX_ROW_MILLIS as u64 {
            return Err("wealth transfer amount out of range");
        }
    }
    if pool.wealth_transfer_log.iter().any(|&(t, p, b)| p == purpose && b == batch && t >= turn) {
        return Err("wealth transfer already applied for this turn, purpose and batch");
    }
    let slots = pool.build_id_slots();
    let mut out = Vec::with_capacity(rows.len());
    for &(agent_id, requested) in rows {
        let slot = slots.get(agent_id).filter(|&s| pool.is_alive(s) && pool.ids[s] == agent_id);
        let Some(slot) = slot else {
            out.push(TransferRow { agent_id, requested, applied: 0, residual: requested, status: STATUS_ABSENT });
            continue;
        };
        let wealth = pool.wealth[slot];
        let applied = if requested >= 0 {
            requested.min(floor_millis(MAX_WEALTH - wealth))
        } else {
            -((-requested).min(floor_millis(wealth)))
        };
        if applied != 0 {
            let next = (wealth as f64 + applied as f64 / MILLI as f64) as f32;
            pool.wealth[slot] = next.clamp(0.0, MAX_WEALTH);
        }
        let status = if applied == requested { STATUS_APPLIED } else { STATUS_LIMITED };
        out.push(TransferRow { agent_id, requested, applied, residual: requested - applied, status });
    }
    pool.wealth_transfer_log.retain(|&(t, _, _)| t >= turn);
    pool.wealth_transfer_log.push((turn, purpose, batch));
    Ok(TransferReceipt { turn, purpose, batch, rows: out })
}

/// One remittance row as applied (RS4, [`remit`]); milli-units.
/// `sent` is what left the sender, `fee` the part of it the courier sink
/// kept, `credited` what reached the recipient and `refunded` what the
/// recipient's wealth ceiling refused and went back to the sender, so
/// `sent == fee + credited + refunded` and the sender's net loss is
/// `fee + credited`.
#[derive(Clone, Debug, PartialEq)]
pub struct RemitRow {
    pub sender: u32,
    pub recipient: u32,
    pub sent: i64,
    pub fee: i64,
    pub credited: i64,
    pub refunded: i64,
    pub status: u8,
}

/// RS4 remittances: apply `rows` (sender id, recipient id, amount, fee in
/// milli-units) once for `(turn, PURPOSE_REMITTANCE, batch)`, in the key log
/// [`transfer`] uses.
///
/// The whole call is validated before any change: unique senders, a
/// sender is never its own recipient, `amount > 0`, `fee >= 0` and
/// `amount + fee` within [`MAX_ROW_MILLIS`]; a repeated or older key is
/// refused. Each row then validates both parties before it changes
/// anything: a party dead, unknown, or away on a merchant trip makes the
/// row ABSENT and moves nothing. Otherwise the sender pays `amount + fee`,
/// limited by its own wealth (never below zero); what was taken is split
/// pro rata between the courier fee (rounded down) and the carried amount.
/// The recipient is credited the carried amount up to `MAX_WEALTH`; any
/// excess is refunded to the sender. A row is LIMITED when the sender could
/// not pay in full or anything was refunded, APPLIED otherwise. Rows apply
/// in the given order, so a recipient's earlier credit counts towards a
/// later row it sends. Nothing is created: the sender loses exactly
/// `fee + credited`, the recipient gains `credited`, and the fee leaves the
/// pool (the caller discloses the sink). No random draws.
pub fn remit(pool: &mut AgentPool, turn: u32, batch: u32, rows: &[(u32, u32, i64, i64)])
    -> Result<Vec<RemitRow>, &'static str> {
    let purpose = PURPOSE_REMITTANCE;
    let mut senders = std::collections::HashSet::with_capacity(rows.len());
    for &(sender, recipient, amount, fee) in rows {
        if !senders.insert(sender) {
            return Err("duplicate sender in remittance");
        }
        if sender == recipient {
            return Err("a remittance sender cannot be its own recipient");
        }
        if amount <= 0 || fee < 0 || amount.saturating_add(fee) > MAX_ROW_MILLIS {
            return Err("remittance amount out of range");
        }
    }
    if pool.wealth_transfer_log.iter().any(|&(t, p, b)| p == purpose && b == batch && t >= turn) {
        return Err("wealth transfer already applied for this turn, purpose and batch");
    }
    let slots = pool.build_id_slots();
    let mut out = Vec::with_capacity(rows.len());
    for &(sender, recipient, amount, fee) in rows {
        let present = |id: u32| slots.get(id)
            .filter(|&s| pool.is_alive(s) && pool.ids[s] == id && !pool.is_on_trip(s));
        let (Some(from), Some(to)) = (present(sender), present(recipient)) else {
            out.push(RemitRow { sender, recipient, sent: 0, fee: 0, credited: 0, refunded: 0, status: STATUS_ABSENT });
            continue;
        };
        let asked = amount + fee;
        let sent = asked.min(floor_millis(pool.wealth[from]));
        // The fee's share of what was actually taken (rounded down; exact when paid in full).
        let fee_paid = if sent == asked { fee } else { ((sent as i128 * fee as i128) / asked as i128) as i64 };
        let carried = sent - fee_paid;
        let credited = carried.min(floor_millis(MAX_WEALTH - pool.wealth[to]));
        let refunded = carried - credited;
        let net = sent - refunded;
        if net != 0 {
            let next = (pool.wealth[from] as f64 - net as f64 / MILLI as f64) as f32;
            pool.wealth[from] = next.clamp(0.0, MAX_WEALTH);
        }
        if credited != 0 {
            let next = (pool.wealth[to] as f64 + credited as f64 / MILLI as f64) as f32;
            pool.wealth[to] = next.clamp(0.0, MAX_WEALTH);
        }
        let status = if sent == asked && refunded == 0 { STATUS_APPLIED } else { STATUS_LIMITED };
        out.push(RemitRow { sender, recipient, sent, fee: fee_paid, credited, refunded, status });
    }
    pool.wealth_transfer_log.retain(|&(t, _, _)| t >= turn);
    pool.wealth_transfer_log.push((turn, purpose, batch));
    Ok(out)
}

/// One pairwise payment row as applied (A4, [`settle_pairs`]); milli-units.
/// `sent` is what the payer could pay (its wealth limits it), `credited`
/// what reached the payee and `refunded` what the payee's wealth ceiling
/// refused, which never left the payer: `sent == credited + refunded` and the
/// payer's net loss is `credited`.
#[derive(Clone, Debug, PartialEq)]
pub struct PairRow {
    pub payer: u32,
    pub payee: u32,
    pub requested: i64,
    pub sent: i64,
    pub credited: i64,
    pub refunded: i64,
    pub status: u8,
}

/// A4 titled trade: apply `rows` (payer id, payee id, amount in milli-units)
/// once for `(turn, purpose, batch)`, in the key log [`transfer`] uses.
///
/// The whole call is validated before any change: `purpose` is pairwise
/// ([`PAIRWISE_PURPOSES`]); a payer is never its own payee; no (payer, payee)
/// pair repeats; no id is both a payer and a payee in one call;
/// `0 < amount <= MAX_ROW_MILLIS`; a repeated or older key is refused. Each
/// row then checks both parties: a party dead or unknown makes the row ABSENT
/// and moves nothing. Otherwise the payer pays `min(amount, what it still
/// holds)` (its whole milli-units at the start of the call, less what its
/// earlier rows credited) and the payee is credited that up to its room below
/// `MAX_WEALTH` (at the start of the call, less earlier credits); a credit
/// the ceiling refuses never leaves the payer. There is **no trip rule**: a
/// payment by title reaches a party away on a merchant trip, as retail
/// settlement does. A row is LIMITED when the payer could not pay in full or
/// anything was refused, APPLIED otherwise. Each person's net change is
/// applied to their wealth once, after every row, so rows never see each
/// other's f32 rounding. Nothing is created: the payers lose exactly what
/// the payees gain (`credited`). No random draws.
pub fn settle_pairs(pool: &mut AgentPool, turn: u32, purpose: u8, batch: u32, rows: &[(u32, u32, i64)])
    -> Result<Vec<PairRow>, &'static str> {
    if !PAIRWISE_PURPOSES.contains(&purpose) {
        return Err("not a pairwise wealth transfer purpose");
    }
    let mut pairs = std::collections::HashSet::with_capacity(rows.len());
    let mut payers = std::collections::HashSet::new();
    let mut payees = std::collections::HashSet::new();
    for &(payer, payee, amount) in rows {
        if payer == payee {
            return Err("a pairwise payer cannot be its own payee");
        }
        if !pairs.insert((payer, payee)) {
            return Err("duplicate payer and payee in pairwise transfer");
        }
        if amount <= 0 || amount > MAX_ROW_MILLIS {
            return Err("pairwise transfer amount out of range");
        }
        payers.insert(payer);
        payees.insert(payee);
    }
    if payers.iter().any(|id| payees.contains(id)) {
        return Err("an agent cannot be both a payer and a payee in one pairwise transfer");
    }
    if pool.wealth_transfer_log.iter().any(|&(t, p, b)| p == purpose && b == batch && t >= turn) {
        return Err("wealth transfer already applied for this turn, purpose and batch");
    }
    let slots = pool.build_id_slots();
    let living = |id: u32| slots.get(id).filter(|&s| pool.is_alive(s) && pool.ids[s] == id);
    let mut left: std::collections::HashMap<u32, i64> = std::collections::HashMap::new();
    let mut room: std::collections::HashMap<u32, i64> = std::collections::HashMap::new();
    let mut net: std::collections::BTreeMap<u32, (usize, i64)> = std::collections::BTreeMap::new();
    let mut out = Vec::with_capacity(rows.len());
    for &(payer, payee, requested) in rows {
        let (Some(from), Some(to)) = (living(payer), living(payee)) else {
            out.push(PairRow { payer, payee, requested, sent: 0, credited: 0, refunded: 0, status: STATUS_ABSENT });
            continue;
        };
        let have = left.entry(payer).or_insert_with(|| floor_millis(pool.wealth[from]));
        let sent = requested.min(*have);
        let space = room.entry(payee).or_insert_with(|| floor_millis(MAX_WEALTH - pool.wealth[to]));
        let credited = sent.min(*space);
        let refunded = sent - credited;
        *have -= credited;
        *space -= credited;
        net.entry(payer).or_insert((from, 0)).1 -= credited;
        net.entry(payee).or_insert((to, 0)).1 += credited;
        let status = if sent == requested && refunded == 0 { STATUS_APPLIED } else { STATUS_LIMITED };
        out.push(PairRow { payer, payee, requested, sent, credited, refunded, status });
    }
    for (_, (slot, change)) in net {
        if change != 0 {
            let next = (pool.wealth[slot] as f64 + change as f64 / MILLI as f64) as f32;
            pool.wealth[slot] = next.clamp(0.0, MAX_WEALTH);
        }
    }
    pool.wealth_transfer_log.retain(|&(t, _, _)| t >= turn);
    pool.wealth_transfer_log.push((turn, purpose, batch));
    Ok(out)
}

/// Split `total` milli over `weights` (tie key, weight >= 0) in proportion,
/// by largest remainder: the shares sum to `total` exactly when any weight
/// is positive (all zero otherwise); equal remainders go to the smaller key
/// first. With integer weights and `total` at most their sum, no share
/// exceeds its weight.
pub fn split_largest_remainder(total: i64, weights: &[(u64, i64)]) -> Vec<i64> {
    let sum: i128 = weights.iter().map(|&(_, w)| w.max(0) as i128).sum();
    let mut out = vec![0i64; weights.len()];
    if total <= 0 || sum == 0 {
        return out;
    }
    let mut remainders = Vec::with_capacity(weights.len());
    for (i, &(key, w)) in weights.iter().enumerate() {
        let product = total as i128 * w.max(0) as i128;
        out[i] = (product / sum) as i64;
        remainders.push((product % sum, key, i));
    }
    let left = total - out.iter().sum::<i64>();
    remainders.sort_unstable_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)));
    for &(_, _, i) in remainders.iter().take(left.max(0) as usize) {
        out[i] += 1;
    }
    out
}

/// L6b: one pilot region's food purchases to settle, in milli-units.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct FoodPurchases {
    /// Per buying household: its payers (stable id, wealth in whole milli
    /// before the purchases) and the price of what it bought, at most the
    /// payers' total.
    pub households: Vec<(Vec<(u32, i64)>, i64)>,
    /// (seller stable id, milli-food sold), distinct living ids, ascending
    /// (a dead owner's claim is withheld, never sold).
    pub sales: Vec<(u32, i64)>,
}

/// L6b: one region's settled money: `paid == credited + refunded` and
/// `refunded == refused_ceiling`.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct FoodPurchaseMoney {
    pub paid: i64,
    pub credited: i64,
    pub refunded: i64,
    pub refused_ceiling: i64,
}

/// L6b: settle the tick's household food purchases once, under the purpose
/// `food_purchase` (the key (turn, 5, 0) is consumed).
///
/// Per region: each household's price is debited from its payers in
/// proportion to their wealth (largest remainder in whole milli, ties by
/// id; never below zero). The region's payments are credited to its sellers
/// in proportion to the food each sold (ties by id), by stable id wherever
/// they live. A credit is limited by the seller's room below `MAX_WEALTH`
/// measured before the purchases (regions in the given order share it); what
/// the ceiling refuses is refunded to that region's payers in proportion to
/// what they paid. Every seller must be alive: the retail step withholds a
/// dead owner's claim, so a sale by nobody living is a logic error (panics). Each person's net change is applied once, so a payer is
/// never refunded above what they paid and `paid == credited + refunded`
/// exactly. Returns per region the money and per stable id (ascending)
/// (id, paid, credited, refunded) for everyone who paid or sold.
pub fn settle_food_purchases(pool: &mut AgentPool, turn: u32, regions: &[FoodPurchases])
    -> Result<(Vec<FoodPurchaseMoney>, Vec<(u32, i64, i64, i64)>), &'static str> {
    if pool.wealth_transfer_log.iter().any(|&(t, p, b)| p == PURPOSE_FOOD_PURCHASE && b == 0 && t >= turn) {
        return Err("household food purchases already settled for this turn");
    }
    let slots = pool.build_id_slots();
    let living = |id: u32| slots.get(id).filter(|&s| pool.is_alive(s) && pool.ids[s] == id);
    let mut book: std::collections::BTreeMap<u32, [i64; 3]> = std::collections::BTreeMap::new();
    let mut room: std::collections::HashMap<u32, Option<i64>> = std::collections::HashMap::new();
    let mut out = Vec::with_capacity(regions.len());
    for region in regions {
        let mut money = FoodPurchaseMoney::default();
        let mut debits: Vec<(u32, i64)> = Vec::new();
        for (payers, amount) in &region.households {
            let cash: i64 = payers.iter().map(|p| p.1.max(0)).sum();
            assert!(*amount >= 0 && *amount <= cash, "a food purchase above its payers' cash");
            let weights: Vec<(u64, i64)> = payers.iter().map(|&(id, w)| (id as u64, w)).collect();
            for (&(id, _), share) in payers.iter().zip(split_largest_remainder(*amount, &weights)) {
                if share > 0 {
                    debits.push((id, share));
                    book.entry(id).or_default()[0] += share;
                    money.paid += share;
                }
            }
        }
        let weights: Vec<(u64, i64)> = region.sales.iter().map(|&(id, q)| (id as u64, q)).collect();
        for (&(id, sold), credit) in region.sales.iter().zip(split_largest_remainder(money.paid, &weights)) {
            if sold <= 0 && credit == 0 {
                continue;
            }
            let left = room.entry(id).or_insert_with(|| living(id).map(|s| floor_millis(MAX_WEALTH - pool.wealth[s])));
            let Some(left) = left else { panic!("a food sale by no living seller") };
            let accepted = credit.min(*left);
            *left -= accepted;
            book.entry(id).or_default()[1] += accepted;
            money.credited += accepted;
            money.refused_ceiling += credit - accepted;
        }
        let refused = money.refused_ceiling;
        let weights: Vec<(u64, i64)> = debits.iter().map(|&(id, d)| (id as u64, d)).collect();
        for (&(id, _), refund) in debits.iter().zip(split_largest_remainder(refused, &weights)) {
            if refund > 0 {
                book.entry(id).or_default()[2] += refund;
                money.refunded += refund;
            }
        }
        out.push(money);
    }
    let updates: Vec<(usize, i64)> = book.iter()
        .filter_map(|(&id, &[paid, credited, refunded])| {
            let net = credited + refunded - paid;
            if net == 0 { None } else { living(id).map(|slot| (slot, net)) }
        })
        .collect();
    for (slot, net) in updates {
        let next = (pool.wealth[slot] as f64 + net as f64 / MILLI as f64) as f32;
        pool.wealth[slot] = next.clamp(0.0, MAX_WEALTH);
    }
    pool.wealth_transfer_log.retain(|&(t, _, _)| t >= turn);
    pool.wealth_transfer_log.push((turn, PURPOSE_FOOD_PURCHASE, 0));
    Ok((out, book.into_iter().map(|(id, [p, c, r])| (id, p, c, r)).collect()))
}

/// Stable ids of the living agents away on a merchant trip (loading or in
/// transit), ascending. Reads only.
pub fn trip_ids(pool: &AgentPool) -> Vec<u32> {
    let mut ids: Vec<u32> = (0..pool.capacity())
        .filter(|&s| pool.is_alive(s) && pool.is_on_trip(s)).map(|s| pool.ids[s]).collect();
    ids.sort_unstable();
    ids
}

/// Arm `rows` (stable id, share of this turn's ordinary income) for the next
/// wealth phase. Refuses a pending share, invalid or duplicate rows, dead or
/// unknown ids, and any share above the person's work reservation for `turn`.
pub fn install_paid_work(pool: &mut AgentPool, turn: u32, rows: &[(u32, f32)]) -> Result<(), &'static str> {
    if pool.paid_work.is_some() {
        return Err("paid work share already pending");
    }
    let slots = pool.build_id_slots();
    let mut seen = std::collections::HashSet::with_capacity(rows.len());
    let mut resolved = Vec::with_capacity(rows.len());
    for &(id, share) in rows {
        if !(share > 0.0 && share <= 1.0) {
            return Err("paid work share must be in (0, 1]");
        }
        if !seen.insert(id) {
            return Err("duplicate agent in paid work");
        }
        let slot = match slots.get(id) {
            Some(slot) if pool.is_alive(slot) && pool.ids[slot] == id => slot,
            _ => return Err("paid work names no living agent"),
        };
        let reserved: f32 = pool.work_reservations.iter()
            .filter(|r| r.turn == turn && r.agent_id == id).map(|r| r.fraction).sum();
        if share > reserved + 1e-6 {
            return Err("paid work exceeds the agent's work reservation this turn");
        }
        resolved.push((slot, id, share));
    }
    let mut by_slot = vec![(0u32, 0.0f32); pool.capacity()];
    for (slot, id, share) in resolved {
        by_slot[slot] = (id, share);
    }
    pool.paid_work = Some(PaidWork { turn, by_slot });
    pool.paid_work_receipt = None;
    Ok(())
}

/// Merge `rows` (stable id, share) into the pending paid-work install of
/// `turn`, or arm one when none is pending, all or none. Refuses a pending
/// install of another turn, an invalid share, duplicate ids within `rows`,
/// dead or unknown ids, an id that already has a pending share this turn,
/// and any share above the id's total work reservations for `turn`.
/// [`install_paid_work`] keeps refusing any pending install, so the L6a
/// payroll installs first and later consumers extend.
pub fn extend_paid_work(pool: &mut AgentPool, turn: u32, rows: &[(u32, f32)]) -> Result<(), &'static str> {
    if pool.paid_work.as_ref().is_some_and(|p| p.turn != turn) {
        return Err("paid work share pending for another turn");
    }
    let slots = pool.build_id_slots();
    let mut seen = std::collections::HashSet::with_capacity(rows.len());
    let mut resolved = Vec::with_capacity(rows.len());
    for &(id, share) in rows {
        if !(share > 0.0 && share <= 1.0) {
            return Err("paid work share must be in (0, 1]");
        }
        if !seen.insert(id) {
            return Err("duplicate agent in paid work");
        }
        let slot = match slots.get(id) {
            Some(slot) if pool.is_alive(slot) && pool.ids[slot] == id => slot,
            _ => return Err("paid work names no living agent"),
        };
        if let Some(plan) = pool.paid_work.as_ref() {
            if matches!(plan.by_slot.get(slot), Some(&(held, pending)) if held == id && pending > 0.0) {
                return Err("agent already has a paid work share this turn");
            }
        }
        let reserved: f32 = pool.work_reservations.iter()
            .filter(|r| r.turn == turn && r.agent_id == id).map(|r| r.fraction).sum();
        if share > reserved + 1e-6 {
            return Err("paid work exceeds the agent's work reservation this turn");
        }
        resolved.push((slot, id, share));
    }
    let capacity = pool.capacity();
    if pool.paid_work.is_none() {
        pool.paid_work = Some(PaidWork { turn, by_slot: vec![(0u32, 0.0f32); capacity] });
        pool.paid_work_receipt = None;
    }
    let plan = pool.paid_work.as_mut().expect("armed above");
    if plan.by_slot.len() < capacity {
        plan.by_slot.resize(capacity, (0, 0.0));
    }
    for (slot, id, share) in resolved {
        plan.by_slot[slot] = (id, share);
    }
    Ok(())
}

/// L6b: arm the next wealth phase to replace the remaining ordinary farm
/// income of farmers in `regions` (indices, distinct, below `num_regions`).
/// Refuses a pending install; validates before any change.
pub fn install_retail_income(pool: &mut AgentPool, turn: u32, regions: &[u16], num_regions: usize)
    -> Result<(), &'static str> {
    if pool.retail_income.is_some() {
        return Err("retail income replacement already pending");
    }
    let mut mask = vec![false; num_regions];
    for &r in regions {
        let Some(seen) = mask.get_mut(r as usize) else { return Err("retail income region out of range") };
        if *seen {
            return Err("duplicate region in retail income");
        }
        *seen = true;
    }
    pool.retail_income = Some(RetailIncome { turn, regions: mask });
    pool.retail_income_receipt = None;
    Ok(())
}

/// Wealth phase, after teaching, learning and paid work: a farmer of a
/// listed region has the rest of the ordinary farm income set to zero (health
/// loss then multiplies zero). The receipt records the income the farmer
/// would have received: that remainder after this turn's health loss
/// (`health`, the slot's `(id, loss)`; the same arithmetic as the wealth
/// phase), so a sick farmer's replacement is not overstated. (Health loss
/// also reduces the farmer's title, through the title weights.) Everyone else
/// keeps their income.
#[inline]
pub fn retail_income(plan: &Option<RetailIncome>, receipt: &mut Vec<(u32, f32)>, occupation: u8, region: usize,
                     agent_id: u32, income: f32, health: Option<&(u32, f32)>) -> f32 {
    match plan {
        Some(plan) if occupation == crate::agent::Occupation::Farmer as u8
            && plan.regions.get(region).copied().unwrap_or(false) => {
            let received = match health {
                Some(&(id, loss)) if id == agent_id && loss != 0.0 => income * (1.0 - loss),
                _ => income,
            };
            receipt.push((agent_id, received));
            0.0
        }
        _ => income,
    }
}

/// Wealth phase: the ordinary income left after paid work at `slot`,
/// recording the actual deduction. The id guard keeps a reused slot clean.
#[inline]
pub fn paid_work_income(paid: &Option<PaidWork>, receipt: &mut Vec<(u32, f32, f32, f32)>,
                        agent_id: u32, slot: usize, income: f32) -> f32 {
    let Some(plan) = paid else { return income };
    match plan.by_slot.get(slot) {
        Some(&(id, share)) if id == agent_id && share > 0.0 => {
            let deducted = income * share;
            receipt.push((id, share, income, deducted));
            income - deducted
        }
        _ => income,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::Occupation;
    use crate::workshop_work::{reserve, CATEGORY_WORKSHOP};

    fn pool_with(wealth: &[f32]) -> AgentPool {
        let mut pool = AgentPool::new(wealth.len());
        for &w in wealth {
            let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2, 0);
            pool.wealth[slot] = w;
        }
        pool
    }

    #[test]
    fn credits_stop_at_the_ceiling_and_debits_at_zero_with_residuals_kept() {
        let mut pool = pool_with(&[10.0, 99.5, 0.25]);
        let (a, b, c) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        let r = transfer(&mut pool, 5, PURPOSE_WORKSHOP_WAGE, 0, &[(a, 1500), (b, 900), (c, -400)]).unwrap();
        assert_eq!(r.rows[0], TransferRow { agent_id: a, requested: 1500, applied: 1500, residual: 0, status: STATUS_APPLIED });
        assert_eq!((r.rows[1].applied, r.rows[1].residual, r.rows[1].status), (500, 400, STATUS_LIMITED));
        assert_eq!((r.rows[2].applied, r.rows[2].residual, r.rows[2].status), (-250, -150, STATUS_LIMITED));
        assert!((pool.wealth[0] - 11.5).abs() < 1e-5);
        assert!(pool.wealth[1] <= MAX_WEALTH && (pool.wealth[1] - MAX_WEALTH).abs() < 1e-4);
        assert_eq!(pool.wealth[2], 0.0);
    }

    #[test]
    fn each_key_applies_once_and_bad_rows_change_nothing() {
        let mut pool = pool_with(&[1.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        assert!(transfer(&mut pool, 5, 10, 0, &[(a, 1)]).is_err());
        assert!(transfer(&mut pool, 5, 0, 0, &[(a, 1), (a, 2)]).is_err());
        assert!(transfer(&mut pool, 5, 0, 0, &[(a, MAX_ROW_MILLIS + 1)]).is_err());
        assert_eq!((pool.wealth[0], pool.wealth[1]), (1.0, 1.0));
        transfer(&mut pool, 5, 0, 3, &[(a, 1000)]).unwrap();
        assert!(transfer(&mut pool, 5, 0, 3, &[(b, 1000)]).is_err());
        assert!(transfer(&mut pool, 4, 0, 3, &[(b, 1000)]).is_err());   // an older turn
        transfer(&mut pool, 5, 0, 4, &[(b, 1000)]).unwrap();           // another batch
        transfer(&mut pool, 6, 0, 3, &[(a, 1000)]).unwrap();           // the next turn
        assert!((pool.wealth[0] - 3.0).abs() < 1e-6 && (pool.wealth[1] - 2.0).abs() < 1e-6);
    }

    #[test]
    fn dead_and_unknown_ids_receive_nothing() {
        let mut pool = pool_with(&[1.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        pool.kill(1);
        let r = transfer(&mut pool, 1, 0, 0, &[(a, 10), (b, 10), (999_999, 10)]).unwrap();
        let statuses: Vec<u8> = r.rows.iter().map(|x| x.status).collect();
        assert_eq!(statuses, vec![STATUS_APPLIED, STATUS_ABSENT, STATUS_ABSENT]);
        assert_eq!((r.rows[1].applied, r.rows[1].residual), (0, 10));
    }

    #[test]
    fn paid_work_must_be_reserved_and_is_consumed_by_slot_and_id() {
        let mut pool = pool_with(&[1.0, 1.0, 1.0]);
        let (a, b, c) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        reserve(&mut pool, 7, CATEGORY_WORKSHOP, &[(a, 0.3), (b, 0.3)]).unwrap();
        assert!(install_paid_work(&mut pool, 7, &[(c, 0.3)]).is_err());           // not reserved
        assert!(install_paid_work(&mut pool, 7, &[(a, 0.4)]).is_err());           // above the reservation
        assert!(install_paid_work(&mut pool, 7, &[(a, 0.0)]).is_err());
        assert!(install_paid_work(&mut pool, 7, &[(a, 0.3), (a, 0.3)]).is_err());
        assert!(pool.paid_work.is_none());
        install_paid_work(&mut pool, 7, &[(a, 0.3), (b, 0.15)]).unwrap();
        assert!(install_paid_work(&mut pool, 7, &[(a, 0.3)]).is_err());           // already pending
        let plan = pool.paid_work.take();
        let mut receipt = Vec::new();
        assert!((paid_work_income(&plan, &mut receipt, a, 0, 1.0) - 0.7).abs() < 1e-6);
        assert!((paid_work_income(&plan, &mut receipt, b, 1, 2.0) - 1.7).abs() < 1e-6);
        // A reused slot (another id) and an unlisted slot keep their income.
        assert_eq!(paid_work_income(&plan, &mut receipt, 12345, 1, 2.0), 2.0);
        assert_eq!(paid_work_income(&plan, &mut receipt, c, 2, 2.0), 2.0);
        assert_eq!(receipt.len(), 2);
        assert!((receipt[1].3 - 0.3).abs() < 1e-6);
    }

    #[test]
    fn appended_purposes_keep_the_old_codes() {
        assert_eq!(PURPOSES, ["workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance",
                              "food_purchase", "food_procurement", "wares_purchase", "cargo_purchase", "cargo_sale"]);
        assert_eq!((PURPOSE_APPRENTICE_STIPEND, PURPOSE_REPAIR_WAGE, PURPOSE_REMITTANCE), (2, 3, 4));
        assert_eq!((PURPOSE_FOOD_PURCHASE, PURPOSE_FOOD_PROCUREMENT, PURPOSE_WARES_PURCHASE), (5, 6, 7));
        assert_eq!((PURPOSE_CARGO_PURCHASE, PURPOSE_CARGO_SALE), (8, 9));
        let mut pool = pool_with(&[1.0]);
        let a = pool.ids[0];
        for purpose in [PURPOSE_APPRENTICE_STIPEND, PURPOSE_REPAIR_WAGE, PURPOSE_REMITTANCE,
                        PURPOSE_FOOD_PURCHASE, PURPOSE_FOOD_PROCUREMENT, PURPOSE_WARES_PURCHASE] {
            transfer(&mut pool, 2, purpose, 0, &[(a, 100)]).unwrap();
        }
        // The pairwise purposes are refused by the one-sided transfer (only
        // settle_pairs pays them), as is any unknown code.
        for purpose in [PURPOSE_CARGO_PURCHASE, PURPOSE_CARGO_SALE, 10] {
            assert!(transfer(&mut pool, 2, purpose, 0, &[(a, 100)]).is_err());
            assert!(transfer(&mut pool, 2, purpose, 0, &[(a, -100)]).is_err());
        }
        assert!((pool.wealth[0] - 1.6).abs() < 1e-5);
        assert!(pool.wealth_transfer_log.iter().all(|&(_, p, _)| !PAIRWISE_PURPOSES.contains(&p)));
    }

    #[test]
    fn settle_pairs_pays_owners_from_the_payer_once_and_conserves_wealth() {
        let mut pool = pool_with(&[10.0, 1.0, 2.0]);
        let (m, a, b) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        let rows = settle_pairs(&mut pool, 4, PURPOSE_CARGO_PURCHASE, 3, &[(m, a, 1500), (m, b, 2500)]).unwrap();
        assert_eq!(rows[0], PairRow { payer: m, payee: a, requested: 1500, sent: 1500, credited: 1500, refunded: 0,
                                      status: STATUS_APPLIED });
        assert_eq!((rows[1].credited, rows[1].status), (2500, STATUS_APPLIED));
        assert_eq!((milli(&pool, 0), milli(&pool, 1), milli(&pool, 2)), (6000, 2500, 4500));
        // The key settles once; an older turn is refused; another batch or turn is its own key.
        assert!(settle_pairs(&mut pool, 4, PURPOSE_CARGO_PURCHASE, 3, &[(m, a, 1)]).is_err());
        assert!(settle_pairs(&mut pool, 3, PURPOSE_CARGO_PURCHASE, 3, &[(m, a, 1)]).is_err());
        assert!(settle_pairs(&mut pool, 4, PURPOSE_CARGO_SALE, 3, &[(m, a, 1)]).is_ok());
        assert!(settle_pairs(&mut pool, 4, PURPOSE_CARGO_PURCHASE, 4, &[(m, a, 1)]).is_ok());
    }

    #[test]
    fn settle_pairs_validates_the_whole_call_before_any_change() {
        let mut pool = pool_with(&[5.0, 5.0, 5.0]);
        let (m, a, b) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        let before = pool.wealth.clone();
        for purpose in [0u8, PURPOSE_REMITTANCE, PURPOSE_FOOD_PURCHASE, PURPOSE_WARES_PURCHASE, 10] {
            assert!(settle_pairs(&mut pool, 1, purpose, 0, &[(m, a, 10)]).is_err());
        }
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, m, 10)]).is_err());
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, a, 10), (m, a, 5)]).is_err());
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, a, 10), (a, b, 5)]).is_err());
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, a, 0)]).is_err());
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, a, -5)]).is_err());
        assert!(settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &[(m, a, MAX_ROW_MILLIS + 1)]).is_err());
        assert_eq!(pool.wealth, before);
        assert!(pool.wealth_transfer_log.is_empty());
    }

    #[test]
    fn settle_pairs_limits_at_the_payers_wealth_and_refunds_the_payees_ceiling() {
        let mut pool = pool_with(&[3.0, 99.5, 1.0]);
        let (m, rich, poor) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        let rows = settle_pairs(&mut pool, 2, PURPOSE_CARGO_PURCHASE, 0, &[(m, rich, 1000), (m, poor, 5000)]).unwrap();
        // The rich payee takes 500 of 1000 (ceiling); the rest never left the payer.
        assert_eq!(rows[0], PairRow { payer: m, payee: rich, requested: 1000, sent: 1000, credited: 500, refunded: 500,
                                      status: STATUS_LIMITED });
        // The payer then holds 2500: the second row is limited by its wealth.
        assert_eq!(rows[1], PairRow { payer: m, payee: poor, requested: 5000, sent: 2500, credited: 2500, refunded: 0,
                                      status: STATUS_LIMITED });
        assert_eq!(milli(&pool, 0), 0);
        assert!((pool.wealth[1] - MAX_WEALTH).abs() < 1e-4 && pool.wealth[1] <= MAX_WEALTH);
        assert_eq!(milli(&pool, 2), 3500);
    }

    #[test]
    fn settle_pairs_moves_nothing_for_dead_or_unknown_parties_and_ignores_trips() {
        let mut pool = pool_with(&[4.0, 1.0, 1.0, 1.0]);
        let (m, dead, away, other) = (pool.ids[0], pool.ids[1], pool.ids[2], pool.ids[3]);
        pool.kill(1);
        pool.trip_phase[2] = crate::agent::TRIP_PHASE_TRANSIT;
        assert!(pool.is_on_trip(2));
        let rows = settle_pairs(&mut pool, 6, PURPOSE_CARGO_PURCHASE, 1,
                                &[(m, dead, 500), (m, 999_999, 500), (m, away, 700), (m, other, 300)]).unwrap();
        let statuses: Vec<u8> = rows.iter().map(|r| r.status).collect();
        assert_eq!(statuses, vec![STATUS_ABSENT, STATUS_ABSENT, STATUS_APPLIED, STATUS_APPLIED]);
        assert_eq!((rows[0].sent, rows[1].credited), (0, 0));
        // Title-based payment reaches a party on a merchant trip (no trip rule).
        assert_eq!((milli(&pool, 0), milli(&pool, 2), milli(&pool, 3)), (3000, 1700, 1300));
        let _ = away;
    }

    #[test]
    fn settle_pairs_applies_each_net_change_once_without_f32_drift_between_rows() {
        // A payer with an f32 balance just under a milli boundary pays many rows
        // in full: rows see the whole-milli budget, never each other's rounding.
        let mut pool = pool_with(&[7.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        let payer = pool.ids[0];
        let budget = floor_millis(pool.wealth[0]);
        let payees: Vec<u32> = pool.ids[1..].to_vec();
        let share = budget / payees.len() as i64;
        let rows: Vec<(u32, u32, i64)> = payees.iter().map(|&p| (payer, p, share)).collect();
        let got = settle_pairs(&mut pool, 1, PURPOSE_CARGO_PURCHASE, 0, &rows).unwrap();
        assert!(got.iter().all(|r| r.status == STATUS_APPLIED && r.credited == share));
        let paid: i64 = got.iter().map(|r| r.credited).sum();
        let before = budget as f64 / 1000.0;
        assert!(((pool.wealth[0] as f64) - (before - paid as f64 / 1000.0)).abs() < 2e-3);
    }

    #[test]
    fn wares_purchases_are_debit_rows_settled_once_per_firm_and_turn() {
        // A3: households pay a firm by debit rows (the firm's cash is Python's).
        let mut pool = pool_with(&[2.0, 0.25]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let got = transfer(&mut pool, 9, PURPOSE_WARES_PURCHASE, 3, &[(a, -1500), (b, -400)]).unwrap();
        assert_eq!(got.rows[0], TransferRow { agent_id: a, requested: -1500, applied: -1500, residual: 0,
                                              status: STATUS_APPLIED });
        assert_eq!((got.rows[1].applied, got.rows[1].residual, got.rows[1].status), (-250, -150, STATUS_LIMITED));
        assert!((pool.wealth[0] - 0.5).abs() < 1e-6 && pool.wealth[1] == 0.0);
        // The same firm (batch) and turn settles once; another firm the same turn is its own key.
        assert!(transfer(&mut pool, 9, PURPOSE_WARES_PURCHASE, 3, &[(a, -10)]).is_err());
        assert!(transfer(&mut pool, 9, PURPOSE_WARES_PURCHASE, 4, &[(a, -10)]).is_ok());
    }

    #[test]
    fn extend_merges_into_an_l6a_install_and_keeps_one_share_per_person() {
        use crate::workshop_work::{CATEGORY_APPRENTICE, CATEGORY_REPAIR};
        let mut pool = pool_with(&[1.0, 1.0, 1.0, 1.0]);
        let (a, b, c, d) = (pool.ids[0], pool.ids[1], pool.ids[2], pool.ids[3]);
        reserve(&mut pool, 7, CATEGORY_WORKSHOP, &[(a, 0.3)]).unwrap();
        reserve(&mut pool, 7, CATEGORY_APPRENTICE, &[(b, 0.25)]).unwrap();
        reserve(&mut pool, 7, CATEGORY_REPAIR, &[(c, 0.5)]).unwrap();
        install_paid_work(&mut pool, 7, &[(a, 0.3)]).unwrap();          // L6a-style install
        pool.paid_work_receipt = Some(PaidWorkReceipt { turn: 6, rows: Vec::new() });
        extend_paid_work(&mut pool, 7, &[(b, 0.25)]).unwrap();
        extend_paid_work(&mut pool, 7, &[(c, 0.4)]).unwrap();
        let plan = pool.paid_work.clone().unwrap();
        assert_eq!(plan.turn, 7);
        assert_eq!(&plan.by_slot[..4], &[(a, 0.3), (b, 0.25), (c, 0.4), (0, 0.0)]);
        // Merging never touches an untaken receipt; install still refuses.
        assert_eq!(pool.paid_work_receipt.as_ref().map(|r| r.turn), Some(6));
        assert!(install_paid_work(&mut pool, 7, &[(d, 0.1)]).is_err());
        let mut receipt = Vec::new();
        assert!((paid_work_income(&pool.paid_work, &mut receipt, b, 1, 2.0) - 1.5).abs() < 1e-6);
        assert!((paid_work_income(&pool.paid_work, &mut receipt, c, 2, 1.0) - 0.6).abs() < 1e-6);
        assert_eq!(paid_work_income(&pool.paid_work, &mut receipt, d, 3, 1.0), 1.0);
    }

    #[test]
    fn extend_arms_a_fresh_install_when_none_is_pending() {
        let mut pool = pool_with(&[1.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        reserve(&mut pool, 3, crate::workshop_work::CATEGORY_REPAIR, &[(a, 0.5), (b, 0.5)]).unwrap();
        pool.paid_work_receipt = Some(PaidWorkReceipt { turn: 2, rows: Vec::new() });
        extend_paid_work(&mut pool, 3, &[(b, 0.5)]).unwrap();
        let plan = pool.paid_work.clone().unwrap();
        assert_eq!((plan.turn, plan.by_slot.len()), (3, pool.capacity()));
        assert_eq!(&plan.by_slot[..2], &[(0, 0.0), (b, 0.5)]);
        assert!(pool.paid_work_receipt.is_none());         // as install clears it
        extend_paid_work(&mut pool, 3, &[(a, 0.2)]).unwrap();
        assert_eq!(pool.paid_work.as_ref().unwrap().by_slot[0], (a, 0.2));
        // An empty extension with nothing pending arms an empty install, as install does.
        let mut empty = pool_with(&[1.0]);
        extend_paid_work(&mut empty, 4, &[]).unwrap();
        assert!(empty.paid_work.as_ref().is_some_and(|p| p.turn == 4 && p.by_slot.iter().all(|&(id, s)| id == 0 && s == 0.0)));
    }

    #[test]
    fn extend_refuses_bad_rows_all_or_none() {
        use crate::workshop_work::CATEGORY_APPRENTICE;
        let mut pool = pool_with(&[1.0, 1.0, 1.0, 1.0]);
        let (a, b, c, d) = (pool.ids[0], pool.ids[1], pool.ids[2], pool.ids[3]);
        reserve(&mut pool, 7, CATEGORY_WORKSHOP, &[(a, 0.3)]).unwrap();
        reserve(&mut pool, 7, CATEGORY_APPRENTICE, &[(b, 0.25), (c, 0.25)]).unwrap();
        install_paid_work(&mut pool, 7, &[(a, 0.3)]).unwrap();
        let before = pool.paid_work.clone();
        // Invalid shares.
        for share in [0.0, -0.1, 1.5, f32::NAN, f32::INFINITY] {
            assert!(extend_paid_work(&mut pool, 7, &[(b, share)]).is_err());
        }
        // Duplicate ids within the rows.
        assert!(extend_paid_work(&mut pool, 7, &[(b, 0.2), (b, 0.1)]).is_err());
        // Unknown and dead ids.
        assert!(extend_paid_work(&mut pool, 7, &[(b, 0.2), (999_999, 0.1)]).is_err());
        pool.kill(3);
        assert!(extend_paid_work(&mut pool, 7, &[(d, 0.1)]).is_err());
        // An id that already has a pending share this turn (L6a's or an earlier extension).
        assert!(extend_paid_work(&mut pool, 7, &[(b, 0.2), (a, 0.1)]).is_err());
        // A share above the id's total reservations, or with none.
        assert!(extend_paid_work(&mut pool, 7, &[(b, 0.3)]).is_err());
        assert_eq!(pool.paid_work, before);
        extend_paid_work(&mut pool, 7, &[(b, 0.25)]).unwrap();
        assert!(extend_paid_work(&mut pool, 7, &[(b, 0.1)]).is_err());
        // A pending install of another turn (an older one the tick never took).
        assert!(extend_paid_work(&mut pool, 8, &[(c, 0.25)]).is_err());
        let mut fresh = pool_with(&[1.0, 1.0]);
        let (e, f) = (fresh.ids[0], fresh.ids[1]);
        reserve(&mut fresh, 2, CATEGORY_APPRENTICE, &[(e, 0.25)]).unwrap();
        assert!(extend_paid_work(&mut fresh, 2, &[(e, 0.25), (f, 0.1)]).is_err());   // unreserved
        assert!(fresh.paid_work.is_none());
    }

    #[test]
    fn the_wealth_phase_consumes_the_share_once_and_the_next_turn_is_ordinary() {
        use crate::region::RegionState;
        use crate::signals::TickSignals;
        let mut region = RegionState::new(0);
        region.resource_types = [0, 255, 255];
        region.resource_yields = [1.0, 0.0, 0.0];
        let regions = vec![region];
        let signals = TickSignals { civs: Vec::new(), contested_regions: vec![false] };
        let mut paid = pool_with(&[5.0, 5.0]);
        let mut control = pool_with(&[5.0, 5.0]);
        let (a, b) = (paid.ids[0], paid.ids[1]);
        reserve(&mut paid, 3, CATEGORY_WORKSHOP, &[(a, 0.25)]).unwrap();
        install_paid_work(&mut paid, 3, &[(a, 0.25)]).unwrap();
        let mut pct = vec![0.0f32; 2];
        crate::tick::wealth_tick(&mut paid, &regions, &signals, &mut pct);
        crate::tick::wealth_tick(&mut control, &regions, &signals, &mut pct);
        assert!(paid.paid_work.is_none());
        let receipt = paid.paid_work_receipt.take().unwrap();
        assert_eq!((receipt.turn, receipt.rows.len(), receipt.rows[0].0), (3, 1, a));
        let (_, share, ordinary, deducted) = receipt.rows[0];
        assert!((deducted - share * ordinary).abs() < 1e-7 && ordinary > 0.0);
        let decay = 1.0 - crate::agent::WEALTH_DECAY;
        assert!((control.wealth[0] - paid.wealth[0] - deducted * decay).abs() < 1e-6);
        assert_eq!(paid.wealth[1], control.wealth[1]);
        assert!(paid.ids[1] == b);
        // The next wealth phase has nothing armed: ordinary income for everyone.
        let gap = control.wealth[0] - paid.wealth[0];
        crate::tick::wealth_tick(&mut paid, &regions, &signals, &mut pct);
        crate::tick::wealth_tick(&mut control, &regions, &signals, &mut pct);
        assert!(paid.paid_work_receipt.is_none());
        assert!((control.wealth[0] - paid.wealth[0] - gap * decay).abs() < 1e-6);
    }

    // --- RS4 remittances (`remit`) ---------------------------------------

    fn milli(pool: &AgentPool, slot: usize) -> i64 { (pool.wealth[slot] as f64 * 1000.0).round() as i64 }

    #[test]
    fn remit_pays_amount_and_fee_in_full_when_the_sender_can() {
        let mut pool = pool_with(&[10.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let rows = remit(&mut pool, 9, 0, &[(a, b, 850, 150)]).unwrap();
        assert_eq!(rows, vec![RemitRow { sender: a, recipient: b, sent: 1000, fee: 150, credited: 850, refunded: 0,
                                         status: STATUS_APPLIED }]);
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), (9000, 1850));
        assert_eq!(pool.wealth_transfer_log, vec![(9, PURPOSE_REMITTANCE, 0)]);
    }

    #[test]
    fn remit_is_limited_by_the_senders_wealth_and_never_goes_negative() {
        let mut pool = pool_with(&[0.5, 1.0, 0.0, 1.0]);
        let (a, b, c, d) = (pool.ids[0], pool.ids[1], pool.ids[2], pool.ids[3]);
        let rows = remit(&mut pool, 3, 0, &[(a, b, 850, 150), (c, d, 100, 20)]).unwrap();
        // 500 taken of 1000: the fee keeps its pro-rata share, rounded down.
        assert_eq!(rows[0], RemitRow { sender: a, recipient: b, sent: 500, fee: 75, credited: 425, refunded: 0,
                                       status: STATUS_LIMITED });
        // A sender with nothing sends nothing: limited, not absent.
        assert_eq!(rows[1], RemitRow { sender: c, recipient: d, sent: 0, fee: 0, credited: 0, refunded: 0,
                                       status: STATUS_LIMITED });
        assert_eq!(pool.wealth[0], 0.0);
        assert_eq!((milli(&pool, 1), milli(&pool, 2), milli(&pool, 3)), (1425, 0, 1000));
        // Odd split: the fee rounds down and the carried amount takes the remainder.
        let mut odd = pool_with(&[0.25, 1.0]);
        let (e, f) = (odd.ids[0], odd.ids[1]);
        let r = remit(&mut odd, 1, 0, &[(e, f, 850, 150)]).unwrap();
        assert_eq!((r[0].sent, r[0].fee, r[0].credited), (250, 37, 213));
        assert_eq!(r[0].sent, r[0].fee + r[0].credited + r[0].refunded);
    }

    #[test]
    fn remit_refunds_what_the_recipients_ceiling_refuses() {
        let mut pool = pool_with(&[10.0, 99.6]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let r = remit(&mut pool, 4, 0, &[(a, b, 850, 150)]).unwrap();
        let room = floor_millis(MAX_WEALTH - 99.6f32);
        assert_eq!((r[0].sent, r[0].fee, r[0].credited, r[0].refunded, r[0].status),
                   (1000, 150, room, 850 - room, STATUS_LIMITED));
        assert!(pool.wealth[1] <= MAX_WEALTH && (pool.wealth[1] - MAX_WEALTH).abs() < 1e-4);
        // The sender lost only the fee and what was credited.
        assert_eq!(milli(&pool, 0), 10_000 - 150 - room);
        // A recipient already at the ceiling: everything carried comes back.
        let mut full = pool_with(&[5.0, MAX_WEALTH]);
        let (c, d) = (full.ids[0], full.ids[1]);
        let r = remit(&mut full, 4, 0, &[(c, d, 400, 100)]).unwrap();
        assert_eq!((r[0].sent, r[0].fee, r[0].credited, r[0].refunded, r[0].status), (500, 100, 0, 400, STATUS_LIMITED));
        assert_eq!((milli(&full, 0), full.wealth[1]), (4900, MAX_WEALTH));
    }

    #[test]
    fn remit_moves_nothing_for_a_dead_unknown_or_travelling_party() {
        let mut pool = pool_with(&[5.0, 5.0, 5.0, 5.0, 5.0, 5.0]);
        let ids: Vec<u32> = pool.ids[..6].to_vec();
        pool.kill(1);                                                    // dead recipient
        pool.kill(2);                                                    // dead sender
        pool.trip_phase[4] = crate::agent::TRIP_PHASE_TRANSIT;           // recipient on a trip
        let before: Vec<i64> = (0..6).map(|s| milli(&pool, s)).collect();
        let rows = remit(&mut pool, 2, 0, &[(ids[0], ids[1], 100, 10), (ids[2], ids[3], 100, 10),
            (ids[3], 999_999, 100, 10), (ids[5], ids[4], 100, 10), (ids[0] + 1_000_000, ids[3], 100, 10)]);
        // Duplicate-free senders: ids[0] once, ids[2], ids[3], ids[5] and an unknown one.
        let rows = rows.unwrap();
        assert!(rows.iter().all(|r| r.status == STATUS_ABSENT && r.sent == 0 && r.fee == 0
                                   && r.credited == 0 && r.refunded == 0));
        let after: Vec<i64> = (0..6).map(|s| milli(&pool, s)).collect();
        assert_eq!(before, after);
        // A sender on a trip is absent too, and the key is still consumed once.
        assert!(remit(&mut pool, 2, 0, &[(ids[3], ids[5], 100, 10)]).is_err());
        let mut trip = pool_with(&[5.0, 5.0]);
        let (a, b) = (trip.ids[0], trip.ids[1]);
        trip.trip_phase[0] = crate::agent::TRIP_PHASE_LOADING;
        assert_eq!(remit(&mut trip, 1, 0, &[(a, b, 100, 0)]).unwrap()[0].status, STATUS_ABSENT);
        assert_eq!(trip_ids(&trip), vec![a]);
    }

    #[test]
    fn remit_names_stable_ids_not_reused_slots() {
        let mut pool = pool_with(&[5.0, 5.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        pool.kill(1);
        let slot = pool.spawn(0, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2, 0);
        assert_eq!(slot, 1);
        pool.wealth[1] = 2.0;
        let stranger = pool.ids[1];
        assert_ne!(stranger, b);
        let rows = remit(&mut pool, 6, 0, &[(a, b, 500, 0)]).unwrap();
        assert_eq!(rows[0].status, STATUS_ABSENT);
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), (5000, 2000));
        let rows = remit(&mut pool, 7, 0, &[(a, stranger, 500, 0)]).unwrap();
        assert_eq!((rows[0].status, rows[0].credited), (STATUS_APPLIED, 500));
    }

    #[test]
    fn remit_applies_each_key_once_and_refuses_bad_calls_unchanged() {
        let mut pool = pool_with(&[5.0, 5.0, 5.0]);
        let (a, b, c) = (pool.ids[0], pool.ids[1], pool.ids[2]);
        for bad in [vec![(a, b, 100, 10), (a, c, 100, 10)],     // duplicate sender
                    vec![(a, a, 100, 10)],                      // own recipient
                    vec![(a, b, 0, 10)], vec![(a, b, -5, 10)],  // no amount
                    vec![(a, b, 100, -1)],                      // negative fee
                    vec![(a, b, MAX_ROW_MILLIS, 1)]] {          // out of range
            assert!(remit(&mut pool, 5, 0, &bad).is_err());
        }
        assert!(pool.wealth_transfer_log.is_empty());
        assert_eq!((milli(&pool, 0), milli(&pool, 1), milli(&pool, 2)), (5000, 5000, 5000));
        remit(&mut pool, 5, 0, &[(a, b, 100, 0)]).unwrap();
        assert!(remit(&mut pool, 5, 0, &[(b, c, 100, 0)]).is_err());           // the same key
        assert!(transfer(&mut pool, 5, PURPOSE_REMITTANCE, 0, &[(c, 100)]).is_err());  // shared key log
        assert!(remit(&mut pool, 4, 0, &[(b, c, 100, 0)]).is_err());           // an older turn
        remit(&mut pool, 5, 1, &[(b, c, 100, 0)]).unwrap();                    // another batch
        transfer(&mut pool, 5, PURPOSE_RELOCATION_FARE, 0, &[(c, -100)]).unwrap();  // another purpose
        remit(&mut pool, 6, 0, &[(c, a, 100, 0)]).unwrap();                    // the next turn
        assert_eq!((milli(&pool, 0), milli(&pool, 1), milli(&pool, 2)), (5000, 5000, 4900));
        // An empty call consumes its key and changes nothing.
        let mut empty = pool_with(&[1.0]);
        assert!(remit(&mut empty, 2, 0, &[]).unwrap().is_empty());
        assert!(remit(&mut empty, 2, 0, &[]).is_err());
    }

    #[test]
    fn remit_rows_apply_in_order_and_conserve_wealth() {
        let mut pool = pool_with(&[3.0, 0.0, 50.0, 99.9, 7.25]);
        let ids: Vec<u32> = pool.ids[..5].to_vec();
        // b receives from a, then sends on what it received; two senders share one recipient.
        let rows = [(ids[0], ids[1], 900, 100), (ids[1], ids[2], 500, 100), (ids[2], ids[3], 800, 200),
                    (ids[4], ids[3], 300, 60)];
        let before: Vec<i64> = (0..5).map(|s| milli(&pool, s)).collect();
        let out = remit(&mut pool, 8, 2, &rows).unwrap();
        assert_eq!((out[1].sent, out[1].status), (600, STATUS_APPLIED));
        let mut fees = 0;
        let mut expect = before.clone();
        for (r, (s, t, _, _)) in out.iter().zip(rows) {
            assert_eq!(r.sent, r.fee + r.credited + r.refunded);
            let si = ids.iter().position(|&x| x == s).unwrap();
            let ti = ids.iter().position(|&x| x == t).unwrap();
            expect[si] -= r.fee + r.credited;
            expect[ti] += r.credited;
            fees += r.fee;
        }
        let after: Vec<i64> = (0..5).map(|s| milli(&pool, s)).collect();
        for i in 0..5 { assert!((after[i] - expect[i]).abs() <= 1, "{i}: {} vs {}", after[i], expect[i]); }
        let total = |v: &[i64]| v.iter().sum::<i64>();
        assert!((total(&before) - total(&after) - fees).abs() <= 2);
        assert!(out[3].refunded > 0 || out[2].refunded > 0);     // the ceiling was reached
    }

    // --- L6b household retail -------------------------------------------

    #[test]
    fn largest_remainder_sums_exactly_and_breaks_ties_by_key() {
        assert_eq!(split_largest_remainder(301, &[(1, 300), (2, 300), (3, 150)]), vec![121, 120, 60]);
        assert_eq!(split_largest_remainder(301, &[(2, 300), (1, 300), (3, 150)]), vec![120, 121, 60]);
        assert_eq!(split_largest_remainder(2, &[(9, 1), (4, 1), (7, 1)]), vec![0, 1, 1]);
        assert_eq!(split_largest_remainder(5, &[(1, 0), (2, 0)]), vec![0, 0]);
        assert_eq!(split_largest_remainder(0, &[(1, 3)]), vec![0]);
        assert_eq!(split_largest_remainder(7, &[(1, 7), (2, 0)]), vec![7, 0]);
        // Never above a weight when the total is at most their sum.
        for total in 0..=60 {
            let w = [(5u64, 17i64), (2, 1), (8, 29), (1, 13)];
            let out = split_largest_remainder(total, &w);
            assert_eq!(out.iter().sum::<i64>(), total);
            assert!(out.iter().zip(&w).all(|(&s, &(_, wt))| s >= 0 && s <= wt));
        }
    }

    #[test]
    fn food_purchases_settle_once_with_ceiling_refunds() {
        let mut pool = pool_with(&[3.0, 1.0, 99.995, 5.0, 2.0]);
        let ids: Vec<u32> = pool.ids[..5].to_vec();
        let room = floor_millis(MAX_WEALTH - pool.wealth[2]);
        let regions = [
            // ids[0] and ids[1] pay one household's 900 by wealth (3000 : 1000).
            FoodPurchases { households: vec![(vec![(ids[0], 3000), (ids[1], 1000)], 900)],
                            sales: vec![(ids[2], 300), (ids[3], 300)] },
            // ids[3] buys in the second region from ids[2] (shares its room) and ids[4].
            FoodPurchases { households: vec![(vec![(ids[3], 5000)], 100)], sales: vec![(ids[2], 1), (ids[4], 1)] },
        ];
        let before: i64 = (0..5).map(|s| milli(&pool, s)).sum();
        let (money, book) = settle_food_purchases(&mut pool, 9, &regions).unwrap();
        assert_eq!(money[0], FoodPurchaseMoney { paid: 900, credited: 450 + room, refunded: 450 - room,
                                                 refused_ceiling: 450 - room });
        assert_eq!(money[1], FoodPurchaseMoney { paid: 100, credited: 50, refunded: 50, refused_ceiling: 50 });
        for m in &money { assert_eq!((m.paid, m.refunded), (m.credited + m.refunded, m.refused_ceiling)); }
        // Debits by wealth (675 : 225), refunds in proportion to what each paid.
        let refund0 = split_largest_remainder(450 - room, &[(ids[0] as u64, 675), (ids[1] as u64, 225)]);
        assert_eq!(book, vec![(ids[0], 675, 0, refund0[0]), (ids[1], 225, 0, refund0[1]),
                              (ids[2], 0, room, 0), (ids[3], 100, 450, 50), (ids[4], 0, 50, 0)]);
        assert_eq!(milli(&pool, 3), 5000 + 450 - 100 + 50);
        assert!(pool.wealth[2] <= MAX_WEALTH);
        let after: i64 = (0..5).map(|s| milli(&pool, s)).sum();
        assert!((before - after).abs() <= 2);
        // The key is consumed: a replay under purpose 5, batch 0 is refused.
        assert_eq!(pool.wealth_transfer_log, vec![(9, PURPOSE_FOOD_PURCHASE, 0)]);
        assert!(transfer(&mut pool, 9, PURPOSE_FOOD_PURCHASE, 0, &[(ids[0], 1)]).is_err());
        transfer(&mut pool, 9, PURPOSE_FOOD_PROCUREMENT, 0, &[(ids[0], 1)]).unwrap();
    }

    #[test]
    #[should_panic(expected = "a food sale by no living seller")]
    fn a_sale_by_a_dead_seller_is_a_logic_error() {
        // The retail step withholds a dead owner's claim; nothing may sell it.
        let mut pool = pool_with(&[5.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        pool.kill(1);
        let _ = settle_food_purchases(&mut pool, 1, &[FoodPurchases { households: vec![(vec![(a, 5000)], 100)],
                                                              sales: vec![(b, 1)] }]);
    }

    #[test]
    #[should_panic(expected = "a food purchase above its payers' cash")]
    fn a_purchase_above_the_payers_cash_is_a_logic_error() {
        let mut pool = pool_with(&[1.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let _ = settle_food_purchases(&mut pool, 1, &[FoodPurchases { households: vec![(vec![(a, 1000)], 1001)],
                                                              sales: vec![(b, 1)] }]);
    }

    fn farm_region(id: u16) -> crate::region::RegionState {
        let mut region = crate::region::RegionState::new(id);
        region.resource_types = [0, 255, 255];
        region.resource_yields = [1.0, 0.0, 0.0];
        region
    }

    #[test]
    fn retail_income_is_replaced_once_after_paid_work_and_the_next_turn_is_ordinary() {
        use crate::signals::TickSignals;
        let regions = vec![farm_region(0), farm_region(1)];
        let signals = TickSignals { civs: Vec::new(), contested_regions: vec![false; 2] };
        // Farmers a (paid work 0.25) and b in pilot region 0, a soldier s
        // there, and farmer c in region 1.
        let make = || {
            let mut pool = pool_with(&[5.0, 5.0]);
            let s = pool.spawn(0, 0, Occupation::Soldier, 30, 0.5, 0.5, 0.5, 0, 1, 2, 0);
            pool.wealth[s] = 5.0;
            let c = pool.spawn(1, 0, Occupation::Farmer, 30, 0.5, 0.5, 0.5, 0, 1, 2, 0);
            pool.wealth[c] = 5.0;
            pool
        };
        let (mut pilot, mut control) = (make(), make());
        let (a, b) = (pilot.ids[0], pilot.ids[1]);
        for pool in [&mut pilot, &mut control] {
            let id = pool.ids[0];
            reserve(pool, 3, CATEGORY_WORKSHOP, &[(id, 0.25)]).unwrap();
            install_paid_work(pool, 3, &[(id, 0.25)]).unwrap();
        }
        assert!(install_retail_income(&mut pilot, 3, &[0, 0], 2).is_err());     // duplicate
        assert!(install_retail_income(&mut pilot, 3, &[2], 2).is_err());        // out of range
        assert!(pilot.retail_income.is_none());
        install_retail_income(&mut pilot, 3, &[0], 2).unwrap();
        assert!(install_retail_income(&mut pilot, 3, &[1], 2).is_err());        // pending
        let mut pct = vec![0.0f32; 4];
        crate::tick::wealth_tick(&mut pilot, &regions, &signals, &mut pct);
        crate::tick::wealth_tick(&mut control, &regions, &signals, &mut pct);
        assert!(pilot.retail_income.is_none());
        let receipt = pilot.retail_income_receipt.take().unwrap();
        assert_eq!(receipt.turn, 3);
        assert_eq!(receipt.rows.iter().map(|r| r.0).collect::<Vec<_>>(), vec![a, b]);
        // a's replaced income is what paid work left; the paid share is unchanged.
        let paid = pilot.paid_work_receipt.take().unwrap();
        let control_paid = control.paid_work_receipt.take().unwrap();
        assert_eq!(paid, control_paid);
        let (_, share, ordinary, deducted) = paid.rows[0];
        assert!((receipt.rows[0].1 - (ordinary - deducted)).abs() < 1e-7 && share == 0.25);
        assert!((receipt.rows[1].1 - ordinary).abs() < 1e-7 && ordinary > 0.0);
        // Pilot farmers earn no farm income; the soldier and region 1 are unchanged.
        let decay = 1.0 - crate::agent::WEALTH_DECAY;
        assert!((pilot.wealth[0] - 5.0 * decay).abs() < 1e-6 && (pilot.wealth[1] - 5.0 * decay).abs() < 1e-6);
        assert!(control.wealth[0] > pilot.wealth[0]);
        assert_eq!((pilot.wealth[2], pilot.wealth[3]), (control.wealth[2], control.wealth[3]));
        // The next wealth phase has nothing armed: ordinary income again.
        let (w0, c0) = (pilot.wealth[1], control.wealth[1]);
        crate::tick::wealth_tick(&mut pilot, &regions, &signals, &mut pct);
        crate::tick::wealth_tick(&mut control, &regions, &signals, &mut pct);
        assert!(pilot.retail_income_receipt.is_none());
        assert!(((pilot.wealth[1] - w0 * decay) - (control.wealth[1] - c0 * decay)).abs() < 1e-6);
    }

    #[test]
    fn food_purchases_are_settled_once_per_turn() {
        let mut pool = pool_with(&[5.0, 1.0]);
        let (a, b) = (pool.ids[0], pool.ids[1]);
        let regions = [FoodPurchases { households: vec![(vec![(a, 5000)], 100)], sales: vec![(b, 1)] }];
        settle_food_purchases(&mut pool, 3, &regions).unwrap();
        let after = (milli(&pool, 0), milli(&pool, 1));
        // The same turn (or an older one) is refused before any change.
        assert!(settle_food_purchases(&mut pool, 3, &regions).is_err());
        assert!(settle_food_purchases(&mut pool, 2, &regions).is_err());
        assert_eq!((milli(&pool, 0), milli(&pool, 1)), after);
        settle_food_purchases(&mut pool, 4, &regions).unwrap();
        assert_eq!(milli(&pool, 0), after.0 - 100);
    }

    #[test]
    fn replaced_income_is_what_the_farmer_would_have_received_after_health_loss() {
        use crate::signals::TickSignals;
        let regions = vec![farm_region(0)];
        let signals = TickSignals { civs: Vec::new(), contested_regions: vec![false] };
        let (mut sick, mut control) = (pool_with(&[5.0, 5.0]), pool_with(&[5.0, 5.0]));
        let (a, b) = (sick.ids[0], sick.ids[1]);
        for pool in [&mut sick, &mut control] {
            let id = pool.ids[0];
            pool.health_work_loss = vec![(id, 0.4), (0, 0.0)];
        }
        install_retail_income(&mut sick, 3, &[0], 1).unwrap();
        let mut pct = vec![0.0f32; 2];
        crate::tick::wealth_tick(&mut sick, &regions, &signals, &mut pct);
        crate::tick::wealth_tick(&mut control, &regions, &signals, &mut pct);
        let rows = sick.retail_income_receipt.take().unwrap().rows;
        assert_eq!(rows.iter().map(|r| r.0).collect::<Vec<_>>(), vec![a, b]);
        // The control farmers received these amounts (before the 2% decay).
        let decay = 1.0 - crate::agent::WEALTH_DECAY;
        let received = |slot: usize| control.wealth[slot] / decay - 5.0;
        assert!((rows[0].1 - received(0)).abs() < 1e-5 && (rows[1].1 - received(1)).abs() < 1e-5);
        assert!((rows[0].1 - 0.6 * rows[1].1).abs() < 1e-6 && rows[1].1 > 0.0);
        assert_eq!(sick.wealth[0], 5.0 * decay);
    }
}
