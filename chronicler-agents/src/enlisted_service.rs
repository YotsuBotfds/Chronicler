//! D4 service input. A roster is an attachment, never a native location.
//! Army-fed people do not also consume/produce civilian food. Transient only.
#[derive(Clone)]
pub struct EnlistedService {
    pub turn: u32,
    pub rows: Vec<(u32, f32)>,
    pub suppress_war_mortality: bool,
}
impl crate::pool::AgentPool {
    pub fn army_food(&self, slot: usize) -> Option<f32> {
        let input = self.enlisted_service.as_ref()?;
        let id = *self.ids.get(slot)?;
        input.rows.binary_search_by_key(&id, |r| r.0).ok().map(|i| input.rows[i].1)
    }
    pub fn enlisted(&self, slot: usize) -> bool { self.army_food(slot).is_some() }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn service_is_by_stable_id_uses_actual_food_and_is_not_persisted() {
        let mut pool = crate::AgentPool::new(1);
        let s = pool.spawn(0,0,crate::Occupation::Farmer,25,0.5,0.5,0.5,0,1,2,255);
        pool.enlisted_service = Some(EnlistedService { turn: 3, rows: vec![(pool.ids[s],0.25)], suppress_war_mortality:false });
        assert_eq!(crate::provisioning::food_for(&pool,s,1.0),0.25);
        assert_eq!(pool.regions[s],0);
        let restored: crate::AgentPool = crate::persist::decode(crate::persist::KIND_AGENT,
            &crate::persist::encode(crate::persist::KIND_AGENT,&pool)).unwrap();
        assert!(restored.enlisted_service.is_none());
        pool.kill(s);
        let fresh = pool.spawn(0,0,crate::Occupation::Farmer,25,0.5,0.5,0.5,0,1,2,255);
        assert_eq!(fresh,s);
        assert!(!pool.enlisted(fresh));
        assert_eq!(crate::provisioning::food_for(&pool,fresh,0.75),0.75);
    }
}
