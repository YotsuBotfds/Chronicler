//! Differential contracts for the additive context reader. No physics ticks.

use super::*;

fn spawn(sim: &mut AgentSimulator) -> usize {
    sim.pool.spawn(0, 0, Occupation::Farmer, 30,
        0.0, 0.0, 0.0, 0, 1, 2, crate::agent::BELIEF_NONE)
}

fn needs_bits(values: Option<AgentContextNeeds>) -> Option<[u32; 6]> {
    values.map(|(a, b, c, d, e, f)| {
        [a.to_bits(), b.to_bits(), c.to_bits(), d.to_bits(), e.to_bits(), f.to_bits()]
    })
}

fn scalar_rows(sim: &AgentSimulator, ids: &[u32]) -> Vec<AgentContextRow> {
    ids.iter().map(|&id| (
        id, sim.get_agent_memories(id), sim.get_agent_needs(id),
        sim.get_agent_relationships(id),
    )).collect()
}

fn assert_rows(actual: &[AgentContextRow], expected: &[AgentContextRow]) {
    assert_eq!(actual.len(), expected.len());
    for (got, want) in actual.iter().zip(expected) {
        assert_eq!(got.0, want.0);
        assert_eq!(got.1, want.1);
        // NaNs and signed zero must be compared by bits, not float equality.
        assert_eq!(needs_bits(got.2), needs_bits(want.2));
        assert_eq!(got.3, want.3);
    }
}

fn assert_scalar_equivalent(sim: &AgentSimulator, ids: &[u32]) -> Vec<AgentContextRow> {
    let expected = scalar_rows(sim, ids);
    let actual = sim.get_agent_context_batch(ids.to_vec());
    assert_rows(&actual, &expected);
    actual
}

fn put_needs(pool: &mut AgentPool, slot: usize, values: [u32; 6]) {
    pool.need_safety[slot] = f32::from_bits(values[0]);
    pool.need_material[slot] = f32::from_bits(values[1]);
    pool.need_social[slot] = f32::from_bits(values[2]);
    pool.need_spiritual[slot] = f32::from_bits(values[3]);
    pool.need_autonomy[slot] = f32::from_bits(values[4]);
    pool.need_purpose[slot] = f32::from_bits(values[5]);
}

#[test]
fn context_batch_empty_does_not_visit_pool_vectors() {
    let mut sim = AgentSimulator::new(1, 42);
    // Deliberately incomplete pool: scanning slot zero would index an empty
    // alive vector. Empty input needs neither a lookup nor payload access.
    sim.pool.ids.push(1);
    assert!(sim.get_agent_context_batch(Vec::new()).is_empty());
}

#[test]
fn context_batch_keeps_input_order_duplicates_and_missing_shapes() {
    let mut sim = AgentSimulator::new(1, 42);
    let first = spawn(&mut sim);
    let dead = spawn(&mut sim);
    let last = spawn(&mut sim);
    let first_id = sim.pool.ids[first];
    let dead_id = sim.pool.ids[dead];
    let last_id = sim.pool.ids[last];
    sim.pool.kill(dead);
    sim.pool.need_social[first] = 0.25;
    sim.pool.need_social[last] = 0.75;
    let rows = assert_scalar_equivalent(&sim,
        &[last_id, dead_id, first_id, u32::MAX, last_id, 0]);
    assert_eq!(rows.iter().map(|r| r.0).collect::<Vec<_>>(),
        vec![last_id, dead_id, first_id, u32::MAX, last_id, 0]);
    for index in [1, 3, 5] {
        assert_eq!(rows[index], (rows[index].0, vec![], None, None));
    }
    assert_eq!(rows[0].3, Some(vec![]), "live empty bonds differ from missing");
    assert_eq!(rows[2].2.unwrap().2.to_bits(), 0.25f32.to_bits());
    assert_eq!(rows[0].2.unwrap().2.to_bits(), 0.75f32.to_bits());
}

#[test]
fn context_batch_chooses_first_live_duplicate_pool_id() {
    let mut sim = AgentSimulator::new(1, 42);
    let dead_first = spawn(&mut sim);
    let first_live = spawn(&mut sim);
    let later_live = spawn(&mut sim);
    let id = sim.pool.ids[dead_first];
    sim.pool.ids[first_live] = id;
    sim.pool.ids[later_live] = id;
    sim.pool.kill(dead_first);
    sim.pool.need_safety[first_live] = 0.125;
    sim.pool.need_safety[later_live] = 0.875;
    sim.pool.memory_count[first_live] = 1;
    sim.pool.memory_intensities[first_live][0] = -128;
    sim.pool.memory_count[later_live] = 1;
    sim.pool.memory_intensities[later_live][0] = 127;
    sim.pool.rel_count[first_live] = 1;
    sim.pool.rel_sentiments[first_live][0] = -7;
    sim.pool.rel_count[later_live] = 1;
    sim.pool.rel_sentiments[later_live][0] = 8;
    let rows = assert_scalar_equivalent(&sim, &[id, id]);
    assert_eq!(rows[0].1[0].3, -128);
    assert_eq!(rows[0].2.unwrap().0.to_bits(), 0.125f32.to_bits());
    assert_eq!(rows[0].3.as_ref().unwrap()[0].1, -7);
    sim.pool.kill(first_live);
    let rows = assert_scalar_equivalent(&sim, &[id]);
    assert_eq!(rows[0].1[0].3, 127);
    assert_eq!(rows[0].2.unwrap().0.to_bits(), 0.875f32.to_bits());
}

#[test]
fn context_batch_preserves_zero_id_scalar_split() {
    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    sim.pool.ids[slot] = 0;
    sim.pool.memory_count[slot] = 1;
    sim.pool.memory_event_types[slot][0] = 9;
    sim.pool.memory_is_legacy[slot] = 1;
    sim.pool.need_safety[slot] = 0.5;
    sim.pool.rel_count[slot] = 1;
    sim.pool.rel_target_ids[slot][0] = 77;
    let rows = assert_scalar_equivalent(&sim, &[0, 0, u32::MAX]);
    assert_eq!(rows[0].1[0], (9, 0, 0, 0, 0, true));
    assert_eq!(rows[0].2.unwrap().0, 0.5);
    assert_eq!(rows[0].3, None, "zero never resolves relationships");
    sim.pool.kill(slot);
    assert_eq!(assert_scalar_equivalent(&sim, &[0])[0], (0, vec![], None, None));
}

#[test]
fn context_batch_sparse_high_ids_and_slot_reuse_are_fresh_each_call() {
    let mut sim = AgentSimulator::new(1, 42);
    let low = spawn(&mut sim);
    let reused_slot = spawn(&mut sim);
    let old_id = sim.pool.ids[reused_slot];
    sim.pool.ids[low] = u32::MAX;
    sim.pool.need_safety[low] = 0.25;
    assert_scalar_equivalent(&sim, &[u32::MAX, old_id, 1 << 31, u32::MAX]);
    sim.pool.kill(reused_slot);
    assert_eq!(assert_scalar_equivalent(&sim, &[old_id])[0], (old_id, vec![], None, None));
    let newborn = spawn(&mut sim);
    assert_eq!(newborn, reused_slot);
    let new_id = sim.pool.ids[newborn];
    assert_ne!(new_id, old_id);
    sim.pool.need_safety[newborn] = 0.75;
    let rows = assert_scalar_equivalent(&sim, &[new_id, old_id, u32::MAX]);
    assert_eq!(rows[0].2.unwrap().0, 0.75);
    assert_eq!(rows[1], (old_id, vec![], None, None));
    assert_eq!(rows[2].2.unwrap().0, 0.25);
}

#[test]
fn context_batch_all_store_positions_legacy_bits_and_bond_codes_match() {
    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    let id = sim.pool.ids[slot];
    sim.pool.memory_count[slot] = 8;
    sim.pool.rel_count[slot] = 8;
    for i in 0..8 {
        sim.pool.memory_event_types[slot][i] = 255 - i as u8;
        sim.pool.memory_source_civs[slot][i] = i as u8 * 31;
        sim.pool.memory_turns[slot][i] = u16::MAX - i as u16;
        sim.pool.memory_intensities[slot][i] = [-128, -127, -1, 0, 1, 63, 126, 127][i];
        sim.pool.memory_decay_factors[slot][i] = i as u8 * 29;
        sim.pool.rel_target_ids[slot][i] = u32::MAX - i as u32;
        sim.pool.rel_sentiments[slot][i] = [-128, -127, -1, 0, 1, 63, 126, 127][i];
        sim.pool.rel_bond_types[slot][i] = i as u8;
        sim.pool.rel_formed_turns[slot][i] = u16::MAX - i as u16;
    }
    for bits in 0u8..=u8::MAX {
        sim.pool.memory_is_legacy[slot] = bits;
        let rows = assert_scalar_equivalent(&sim, &[id, 999_999, id]);
        assert_eq!(rows[0].1.len(), 8);
        assert_eq!(rows[0].3.as_ref().unwrap().len(), 8);
        for i in 0..8 {
            assert_eq!(rows[0].1[i].5, bits & (1 << i) != 0);
            assert_eq!(rows[0].3.as_ref().unwrap()[i].2, i as u8);
        }
    }
    let mut rows = sim.get_agent_context_batch(vec![id, id]);
    rows[0].1[0].0 = 0;
    rows[0].3.as_mut().unwrap().clear();
    assert_eq!(rows[1].1[0].0, 255, "duplicate outputs own distinct lists");
    assert_eq!(rows[1].3.as_ref().unwrap().len(), 8);
    assert_eq!(sim.pool.memory_event_types[slot][0], 255);
    assert_eq!(sim.pool.rel_count[slot], 8);
}

#[test]
fn context_batch_needs_match_raw_float_bits() {
    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    let id = sim.pool.ids[slot];
    let patterns = [
        [0, 0x8000_0000, 1, 0x8000_0001, 0x3f80_0000, 0xbf80_0000],
        [0x7f80_0000, 0xff80_0000, 0x7fc0_1234, 0xffc0_5678, 0x007f_ffff, 0x7f7f_ffff],
    ];
    for bits in patterns {
        put_needs(&mut sim.pool, slot, bits);
        let rows = assert_scalar_equivalent(&sim, &[id, id, 999_999]);
        assert_eq!(needs_bits(rows[0].2), Some(bits));
    }
}

#[test]
fn context_batch_reads_preserve_native_state_schemas_and_snapshot_arcs() {
    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    let id = sim.pool.ids[slot];
    sim.pool.memory_count[slot] = 1;
    sim.pool.memory_event_types[slot][0] = 3;
    sim.registry.register(id, crate::named_characters::CharacterRole::General,
        0, 0, 0, 1, 0, 0, 0);
    sim.queue_targeted_deaths(vec![id]);
    sim.queue_movement_leaders(vec![id], vec![0]).unwrap();
    sim.prepare_health_work(vec![id], vec![], vec![], 0.5, 0.2, "spouse").unwrap();
    let health_rows = sim.health_work.as_ref().unwrap().rows.clone();
    let losses = sim.pool.health_work_loss.clone();
    let _snapshot = sim.get_snapshot().unwrap();
    let cached = sim.snapshot_cache.clone().unwrap();
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    let rng_inputs = (sim.master_seed, sim.turn);
    let schemas = (AgentSimulator::checkpoint_schema(),
        EcologySimulator::checkpoint_schema(), PoliticsSimulator::checkpoint_schema());
    assert_eq!(schemas.0.1, "dcf0c34097c88451");
    assert_eq!(schemas.1.1, "4ab7f8c199b5e5f8");
    assert_eq!(schemas.2.1, "b1a710f3450f5015");
    for ids in [vec![], vec![id, u32::MAX, 0, id], vec![id]] {
        assert_scalar_equivalent(&sim, &ids);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &sim), before);
        assert_eq!((sim.master_seed, sim.turn), rng_inputs);
        assert_eq!(sim.health_work.as_ref().unwrap().rows, health_rows);
        assert_eq!(sim.pool.health_work_loss, losses);
        let held = sim.snapshot_cache.as_ref().expect("reader must not clear snapshot");
        assert!(Arc::ptr_eq(&cached.schema(), &held.schema()));
        assert_eq!(cached.num_columns(), held.num_columns());
        for (left, right) in cached.columns().iter().zip(held.columns()) {
            assert!(Arc::ptr_eq(left, right), "reader must retain the held array");
        }
    }
    assert_eq!((AgentSimulator::checkpoint_schema(), EcologySimulator::checkpoint_schema(),
        PoliticsSimulator::checkpoint_schema()), schemas);
    let restored: AgentSimulator = crate::persist::decode(crate::persist::KIND_AGENT, &before).unwrap();
    assert!(restored.snapshot_cache.is_none());
    assert_rows(&restored.get_agent_context_batch(vec![id, u32::MAX, id]),
        &scalar_rows(&sim, &[id, u32::MAX, id]));
    assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &restored), before);
}

#[test]
fn context_batch_python_boundary_types_and_scalar_float_conversion_match() {
    use pyo3::types::{PyInt, PyList, PyTuple};

    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    let id = sim.pool.ids[slot];
    sim.pool.memory_count[slot] = 1;
    sim.pool.memory_is_legacy[slot] = 1;
    put_needs(&mut sim.pool, slot,
        [0x8000_0000, 1, 0x7f80_0000, 0x7fc0_1234, 0xffc0_5678, 0x3f80_0000]);
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    Python::initialize();
    Python::attach(|py| {
        let object = Py::new(py, sim).unwrap();
        let object = object.bind(py);
        let result = object.call_method1("get_agent_context_batch", (vec![id, id, 0],)).unwrap();
        assert!(result.is_instance_of::<PyList>());
        let first = result.get_item(0).unwrap();
        assert!(first.is_instance_of::<PyTuple>());
        assert!(first.get_item(0).unwrap().is_instance_of::<PyInt>());
        assert!(first.get_item(1).unwrap().is_instance_of::<PyList>());
        assert!(first.get_item(2).unwrap().is_instance_of::<PyTuple>());
        assert!(first.get_item(3).unwrap().is_instance_of::<PyList>());
        let memory = first.get_item(1).unwrap().get_item(0).unwrap();
        assert!(memory.is_instance_of::<PyTuple>());
        assert!(memory.get_item(5).unwrap().is_instance_of::<pyo3::types::PyBool>());
        let scalar_needs = object.call_method1("get_agent_needs", (id,)).unwrap();
        let batch_needs = first.get_item(2).unwrap();
        for index in 0..6 {
            assert_eq!(batch_needs.get_item(index).unwrap().extract::<f64>().unwrap().to_bits(),
                scalar_needs.get_item(index).unwrap().extract::<f64>().unwrap().to_bits());
        }
        let missing = result.get_item(2).unwrap();
        assert_eq!(missing.get_item(1).unwrap().len().unwrap(), 0);
        assert!(missing.get_item(2).unwrap().is_none());
        assert!(missing.get_item(3).unwrap().is_none());
        first.get_item(1).unwrap().call_method0("clear").unwrap();
        assert_eq!(result.get_item(1).unwrap().get_item(1).unwrap().len().unwrap(), 1);
        let bools = object.call_method1("get_agent_context_batch", (vec![true, false],)).unwrap();
        assert_eq!(bools.get_item(0).unwrap().get_item(0).unwrap().extract::<u32>().unwrap(), 1);
        assert_eq!(bools.get_item(1).unwrap().get_item(0).unwrap().extract::<u32>().unwrap(), 0);
        let index_ids = py.eval(c"[type('Index', (), {'__index__': lambda self: 1})()]", None, None).unwrap();
        let indexed = object.call_method1("get_agent_context_batch", (index_ids,)).unwrap();
        assert_eq!(indexed.get_item(0).unwrap().get_item(0).unwrap().extract::<u32>().unwrap(), id);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &*object.borrow()), before);
    });
}

#[test]
fn context_batch_python_boundary_rejects_bad_ids_before_native_mutation() {
    use pyo3::exceptions::{PyOverflowError, PyTypeError};

    let mut sim = AgentSimulator::new(1, 42);
    let slot = spawn(&mut sim);
    let id = sim.pool.ids[slot];
    let before = crate::persist::encode(crate::persist::KIND_AGENT, &sim);
    Python::initialize();
    Python::attach(|py| {
        let object = Py::new(py, sim).unwrap();
        let object = object.bind(py);
        for expression in [c"[-1]", c"[4294967296]", c"[1, -1]"] {
            let ids = py.eval(expression, None, None).unwrap();
            let error = object.call_method1("get_agent_context_batch", (ids,)).unwrap_err();
            assert!(error.is_instance_of::<PyOverflowError>(py));
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &*object.borrow()), before);
        }
        for expression in [c"[None]", c"[1.0]", c"['1']", c"'12'", c"1"] {
            let ids = py.eval(expression, None, None).unwrap();
            let error = object.call_method1("get_agent_context_batch", (ids,)).unwrap_err();
            assert!(error.is_instance_of::<PyTypeError>(py));
            assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &*object.borrow()), before);
        }
        let accepted = py.eval(c"(1, 4294967295)", None, None).unwrap();
        let rows = object.call_method1("get_agent_context_batch", (accepted,)).unwrap();
        assert_eq!(rows.get_item(0).unwrap().get_item(0).unwrap().extract::<u32>().unwrap(), id);
        assert_eq!(rows.get_item(1).unwrap().get_item(0).unwrap().extract::<u32>().unwrap(), u32::MAX);
        assert_eq!(crate::persist::encode(crate::persist::KIND_AGENT, &*object.borrow()), before);
    });
}
