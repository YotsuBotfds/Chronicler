//! A6-3 one-turn knowledge gate. Own past residence comes from the dated
//! Python ledger; personal ties and held packets come from the pre-tick pool.
//! Provenance is receipt data only and never enters score arithmetic.
use std::collections::BTreeMap;
use crate::{pool::AgentPool, agent};

pub struct AdaptiveInformation {
    pub turn: u32,
    pub known: Vec<(u32,u16)>,
}
impl AdaptiveInformation {
    pub fn knows(&self, id: u32, region: u16) -> bool { self.known.binary_search(&(id,region)).is_ok() }
}
/// Positive intensity after this turn's ordinary decay is the packet
/// substrate's expiry authority. It has no separate expiry timestamp.
fn dated_packet(pool: &AgentPool, slot: usize, i: usize, turn: u32) -> bool {
    let th = pool.pkt_type_and_hops[slot][i];
    let kind = crate::knowledge::unpack_type(th);
    kind != 0 && crate::knowledge::InfoType::from_u8(kind).is_some()
        && (pool.pkt_source_turn[slot][i] as u32) < turn
        && pool.pkt_intensity[slot][i] > crate::knowledge::decay_rate(kind)
}
pub fn build(pool: &AgentPool, turn: u32, own: &[(u32,u16)]) -> (AdaptiveInformation,Vec<(u32,u16,u8)>) {
    let slots = pool.build_id_slots();
    let mut sources: BTreeMap<(u32,u16),u8> = BTreeMap::new();
    for &(id,region) in own {
        if slots.get(id).is_some_and(|s| pool.is_alive(s)) { *sources.entry((id,region)).or_default() |= 1; }
    }
    for slot in 0..pool.ids.len() {
        if !pool.is_alive(slot) { continue; }
        let id = pool.ids[slot];
        for i in 0..(pool.rel_count[slot] as usize).min(8) {
            if pool.rel_bond_types[slot][i] == crate::relationships::EMPTY_BOND_TYPE
                || pool.rel_formed_turns[slot][i] as u32 >= turn { continue; }
            if let Some(target) = slots.get(pool.rel_target_ids[slot][i]) {
                if pool.is_alive(target) { *sources.entry((id,pool.regions[target])).or_default() |= 2; }
            }
        }
        for i in 0..agent::PACKET_SLOTS {
            if dated_packet(pool,slot,i,turn) { *sources.entry((id,pool.pkt_source_region[slot][i])).or_default() |= 4; }
        }
    }
    let known = sources.keys().copied().collect();
    (AdaptiveInformation { turn, known }, sources.into_iter().map(|((id,r),mask)|(id,r,mask)).collect())
}
pub fn trade_destinations(pool: &AgentPool, ids: &[u32], turn: u32) -> Vec<(u32,Vec<u16>)> {
    let slots = pool.build_id_slots();
    let mut ids = ids.to_vec(); ids.sort_unstable(); ids.dedup();
    ids.into_iter().map(|id| {
        let mut known = Vec::new();
        if let Some(s) = slots.get(id).filter(|&s| pool.is_alive(s)) {
            for i in 0..agent::PACKET_SLOTS {
                if dated_packet(pool,s,i,turn)
                    && crate::knowledge::unpack_type(pool.pkt_type_and_hops[s][i]) == crate::knowledge::InfoType::TradeOpportunity as u8
                    && pool.pkt_source_region[s][i] != pool.regions[s] { known.push(pool.pkt_source_region[s][i]); }
            }
        }
        known.sort_unstable(); known.dedup(); (id,known)
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn knowledge_sources_are_personal_dated_and_expiry_checked() {
        let mut pool = AgentPool::new(3);
        let a = pool.spawn(0,0,crate::Occupation::Farmer,25,0.5,0.5,0.5,0,1,2,255);
        let b = pool.spawn(2,0,crate::Occupation::Farmer,25,0.5,0.5,0.5,0,1,2,255);
        pool.rel_count[a]=1; pool.rel_target_ids[a][0]=pool.ids[b]; pool.rel_bond_types[a][0]=0;
        pool.rel_formed_turns[a][0]=1;
        pool.pkt_type_and_hops[a][0]=crate::knowledge::pack_type_hops(2,0);
        pool.pkt_source_region[a][0]=3; pool.pkt_source_turn[a][0]=2; pool.pkt_intensity[a][0]=200;
        pool.pkt_type_and_hops[a][1]=crate::knowledge::pack_type_hops(2,0);
        pool.pkt_source_region[a][1]=4; pool.pkt_source_turn[a][1]=3; pool.pkt_intensity[a][1]=200;
        pool.pkt_type_and_hops[a][2]=crate::knowledge::pack_type_hops(2,0);
        pool.pkt_source_region[a][2]=5; pool.pkt_source_turn[a][2]=2; pool.pkt_intensity[a][2]=1;
        let (info,receipt)=build(&pool,3,&[(pool.ids[a],1)]);
        assert!(info.knows(pool.ids[a],1)); assert!(info.knows(pool.ids[a],2)); assert!(info.knows(pool.ids[a],3));
        assert!(!info.knows(pool.ids[b],3)); assert!(!info.knows(pool.ids[a],4)); assert!(!info.knows(pool.ids[a],5));
        assert_eq!(receipt,vec![(pool.ids[a],1,1),(pool.ids[a],2,2),(pool.ids[a],3,4)]);
        assert_eq!(trade_destinations(&pool,&[pool.ids[a]],3),vec![(pool.ids[a],vec![3])]);
        pool.kill(b);
        let (info,_) = build(&pool,3,&[]); assert!(!info.knows(pool.ids[a],2));
    }
}
