//! Written native/PyO3 contracts; source inclusion is not execution evidence.
use super::*;
use pyo3::types::{PyBytes, PyBytesMethods};

#[test]
fn care_prefix_configuration_is_preparation_scoped_and_restore_resets_it() {
    let mut sim = AgentSimulator::new(1, 42);
    assert!(sim.pool.health_care_observation.is_none());
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let schemas = (AgentSimulator::checkpoint_schema(), EcologySimulator::checkpoint_schema(),
        PoliticsSimulator::checkpoint_schema());
    assert_eq!(schemas.0.1, "dcf0c34097c88451");
    assert_eq!(schemas.1.1, "4ab7f8c199b5e5f8");
    assert_eq!(schemas.2.1, "b1a710f3450f5015");
    for (digest, turns, start) in [(vec![0; 31], 32, 0), (vec![0; 32], 0, 0),
        (vec![0; 32], 33, 0), (vec![0; 32], 32, u32::MAX)] {
        assert!(sim.configure_health_care_observation(start, &digest, turns).is_err());
        assert!(sim.pool.health_care_observation.is_none());
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    }
    assert!(sim.configure_health_care_observation(0, &[0x5a; 32], 32).unwrap());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
    assert!(sim.configure_health_care_observation(0, &[0x5a; 32], 32).is_err());
    assert!(sim.prepare_health_work(vec![], vec![], vec![], 0.5, 0.2, "retained_kin").unwrap().is_empty());
    // Real finish still returns its original result when stages are missing.
    let result = sim.finish_health_work(0, 0.0).unwrap();
    assert_eq!(result, (vec![], vec![], vec![(0, 0.0, 0.0, 0)]));
    assert_eq!((AgentSimulator::checkpoint_schema(), EcologySimulator::checkpoint_schema(),
        PoliticsSimulator::checkpoint_schema()), schemas);
    let restored: AgentSimulator = crate::persist::decode(crate::persist::KIND_AGENT, &before).unwrap();
    assert!(restored.pool.health_care_observation.is_none());
    assert!(restored.health_work.is_none());
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &restored), before);
    let mut prepared = AgentSimulator::new(1, 42);
    prepared.prepare_health_work(vec![], vec![], vec![], 0.5, 0.2, "spouse").unwrap();
    assert!(prepared.configure_health_care_observation(0, &[0; 32], 32).is_err());
    assert!(prepared.pool.health_care_observation.is_none());
}

#[test]
fn care_prefix_pyo3_export_is_immutable_non_draining_and_schema_neutral() {
    Python::initialize();
    Python::attach(|py| {
        let object = Py::new(py, AgentSimulator::new(1, 42)).unwrap();
        let object = object.bind(py);
        assert!(object.call_method0("get_health_care_observation").unwrap().is_none());
        assert!(object.call_method1("configure_health_care_observation", (0u32, PyBytes::new(py, &[0x71; 32])))
            .unwrap().extract::<bool>().unwrap());
        assert!(object.call_method0("get_health_care_observation").unwrap().is_none());
        object.call_method1("prepare_health_work", (Vec::<u32>::new(), Vec::<u32>::new(),
            Vec::<u16>::new(), 0.5f32, 0.2f32)).unwrap();
        object.call_method1("finish_health_work", (0u32, 0.0f32)).unwrap();
        let mut sim = object.borrow_mut();
        let _snapshot = sim.get_snapshot().unwrap();
        let cached = sim.snapshot_cache.clone().unwrap();
        let state = crate::persist::encode(crate::persist::KIND_AGENT, &*sim);
        let rng = (sim.master_seed, sim.turn);
        drop(sim);
        let first = object.call_method0("get_health_care_observation").unwrap();
        assert!(first.is_instance_of::<PyBytes>());
        let first = first.cast::<PyBytes>().unwrap();
        let saved = first.as_bytes().to_vec();
        assert_eq!(&saved[..8], b"CAREOBS1");
        assert_eq!(u32::from_le_bytes(saved[12..16].try_into().unwrap()), 4);
        assert_eq!(u16::from_le_bytes(saved[26..28].try_into().unwrap()), 7);
        assert_eq!(&saved[92..124], &[0x71; 32]);
        assert_eq!(&saved[124..196], &[0; 72]);
        assert!(first.call_method1("__setitem__", (0, 0)).is_err());
        for _ in 0..3 {
            let next = object.call_method0("get_health_care_observation").unwrap();
            assert_eq!(next.cast::<PyBytes>().unwrap().as_bytes(), saved);
            let sim = object.borrow();
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &*sim), state);
            assert_eq!((sim.master_seed, sim.turn), rng);
            let held = sim.snapshot_cache.as_ref().unwrap();
            assert!(Arc::ptr_eq(&cached.schema(), &held.schema()));
            for (left, right) in cached.columns().iter().zip(held.columns()) {
                assert!(Arc::ptr_eq(left, right));
            }
        }
        let restored: AgentSimulator = crate::persist::decode(crate::persist::KIND_AGENT, &state).unwrap();
        assert!(restored.get_health_care_observation(py).is_none());
        // Existing exported PyBytes remains valid after its source is restored.
        assert_eq!(first.as_bytes(), saved);
    });
}
