//! A1-2 one-tick observer. All amounts are copies of existing f32 operands;
//! it owns no balance and never affects a decision or random stream.
use std::collections::BTreeMap;

#[derive(Default)]
pub struct WealthObservation {
    pub turn: u32,
    pub complete: bool,
    pub rows: BTreeMap<(u16, String), f64>,
}
impl WealthObservation {
    pub fn new(turn: u32) -> Self { Self { turn, ..Self::default() } }
    pub fn add(&mut self, region: u16, component: &str, amount: f64) {
        *self.rows.entry((region, component.to_string())).or_default() += amount;
    }
}
impl crate::pool::AgentPool {
    pub(crate) fn observe_transfer(&mut self, slot: usize, before: f64, nominal: f64) {
        let actual = self.wealth[slot] as f64 - before;
        let region = self.regions[slot];
        self.observe_wealth(region, "transfer_actual", actual);
        self.observe_wealth(region, "transfer_nominal", nominal);
        self.observe_wealth(region, "transfer_rounding", actual - nominal);
    }
    pub(crate) fn observe_wealth(&mut self, region: u16, component: &str, amount: f64) {
        if let Some(o) = &mut self.wealth_observation { o.add(region, component, amount); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{AgentPool, Occupation, RegionState, TickSignals};
    #[test]
    fn stage_deltas_close_and_observer_changes_no_persisted_bytes() {
        let mut observed = AgentPool::new(4);
        for occ in [Occupation::Farmer, Occupation::Soldier, Occupation::Merchant] {
            let s = observed.spawn(0, 0, occ, 25, 0.5, 0.5, 0.5, 0, 1, 2, 255);
            observed.wealth[s] = 99.9;
        }
        let bytes = crate::persist::encode(crate::persist::KIND_AGENT, &observed);
        let mut plain: AgentPool = crate::persist::decode(crate::persist::KIND_AGENT, &bytes).unwrap();
        observed.wealth_observation = Some(WealthObservation::new(7));
        let opening: f64 = observed.wealth.iter().map(|&w| w as f64).sum();
        let mut region = RegionState::new(0);
        region.resource_yields[0] = 4.0;
        region.merchant_trade_income = 1000.0;
        let signals = TickSignals { civs: vec![], contested_regions: vec![] };
        crate::tick::wealth_tick(&mut observed, &[region.clone()], &signals, &mut [0.0;4]);
        crate::tick::wealth_tick(&mut plain, &[region], &signals, &mut [0.0;4]);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT,&plain),
                   crate::persist::encode(crate::persist::KIND_AGENT,&observed));
        let rows = &observed.wealth_observation.as_ref().unwrap().rows;
        let net: f64 = ["income_applied","decay","ceiling_floor"].iter()
            .map(|k| rows.get(&(0,k.to_string())).copied().unwrap_or(0.0)).sum();
        let closing: f64 = observed.wealth.iter().map(|&w| w as f64).sum();
        assert!((closing-opening-net).abs() < 1e-12);
        assert!(rows[&(0,"ceiling_floor".into())] < 0.0);
        assert!(rows[&(0,"decay".into())] < 0.0);
        let restored: AgentPool = crate::persist::decode(crate::persist::KIND_AGENT,
            &crate::persist::encode(crate::persist::KIND_AGENT,&observed)).unwrap();
        assert!(restored.wealth_observation.is_none());
    }
}
