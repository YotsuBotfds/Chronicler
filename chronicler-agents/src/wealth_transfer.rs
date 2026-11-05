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
//!
//! Both are transient: the key log, a pending share and an untaken receipt
//! are never checkpointed (exact checkpoints are taken between turns, when
//! none is pending). No random draws; the pool's agents are never added or
//! removed, and no slot index leaves this module as an identity.

use crate::agent::MAX_WEALTH;
use crate::pool::AgentPool;

/// Milli-units per wealth (and treasury) unit.
pub const MILLI: i64 = 1000;
/// Transfer purposes, in declaration order (append only). The last three
/// were appended by the recovery-skills groundwork (RS0) for apprentice
/// stipends (RS1), repair wages (RS2) and remittances (RS4).
pub const PURPOSES: [&str; 5] = ["workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance"];
pub const PURPOSE_WORKSHOP_WAGE: u8 = 0;
pub const PURPOSE_RELOCATION_FARE: u8 = 1;
pub const PURPOSE_APPRENTICE_STIPEND: u8 = 2;
pub const PURPOSE_REPAIR_WAGE: u8 = 3;
pub const PURPOSE_REMITTANCE: u8 = 4;
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

fn floor_millis(value: f32) -> i64 {
    if value.is_finite() && value > 0.0 { (value as f64 * MILLI as f64).floor() as i64 } else { 0 }
}

/// Apply `rows` (stable id, signed milli-units) once for `(turn, purpose, batch)`.
pub fn transfer(pool: &mut AgentPool, turn: u32, purpose: u8, batch: u32, rows: &[(u32, i64)])
    -> Result<TransferReceipt, &'static str> {
    if purpose as usize >= PURPOSES.len() {
        return Err("unknown wealth transfer purpose");
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
        assert!(transfer(&mut pool, 5, 9, 0, &[(a, 1)]).is_err());
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
        assert_eq!(PURPOSES, ["workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance"]);
        assert_eq!((PURPOSE_APPRENTICE_STIPEND, PURPOSE_REPAIR_WAGE, PURPOSE_REMITTANCE), (2, 3, 4));
        let mut pool = pool_with(&[1.0]);
        let a = pool.ids[0];
        for purpose in [PURPOSE_APPRENTICE_STIPEND, PURPOSE_REPAIR_WAGE, PURPOSE_REMITTANCE] {
            transfer(&mut pool, 2, purpose, 0, &[(a, 100)]).unwrap();
        }
        assert!(transfer(&mut pool, 2, 5, 0, &[(a, 100)]).is_err());
        assert!((pool.wealth[0] - 1.3).abs() < 1e-5);
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
}
