"""Regional transport command is a narrow extension of exact what-if."""
import random
from types import SimpleNamespace
import pytest
from chronicler import what_if as wi
from chronicler.interactive import parse_command
from chronicler.pause_transport import CONTROL, STAT, TARGET, apply


def request(**kw):
    return {"type": "what_if_prepare", "request_id": "transport", "control": CONTROL,
            "region_id": 2, "duration": 1, "turns": 3, **kw}


@pytest.mark.parametrize('changes', [dict(region_id=True),dict(region_id=-1),dict(duration=0),
    dict(duration=7),dict(duration=True),dict(turns=True),dict(turns=21),dict(path='/tmp/a')])
def test_bad_requests_rejected(changes):
    with pytest.raises(wi.WhatIfError):
        wi._request_fields(request(**changes))


def test_command_closed_and_manifest_bound():
    intervention = {"command":"set", "civ":TARGET, "stat":STAT, "value":21,
                    "region_id":2, "duration":1}
    assert wi.intervention_command(intervention) == {k:intervention[k] for k in ("command", "civ", "stat", "value")}
    assert parse_command('set @transport lab.transport_disruption 21') == ('set', (TARGET, STAT, 21))
    for changed in ({"region_id":1}, {"duration":2}, {"civ":"@world"}, {"value":27}):
        with pytest.raises(wi.WhatIfError):
            wi.intervention_command({**intervention, **changed})
    assert parse_command('set @transport lab.transport_disruption 27')[0] == 'error'
    assert parse_command('set @world lab.transport_disruption 21')[0] == 'error'


def test_preview_and_apply_preserve_native_and_record_one_event():
    pytest.importorskip('chronicler_agents')
    from test_crisis_transport_native import _setup
    world, bridge = _setup()
    try:
        w, n, rng = world.model_dump_json(), bridge._sim.checkpoint_state(), random.getstate()
        assert wi.validate_request(request(), world) == ('transport', TARGET, 21, 3, 0)
        assert (world.model_dump_json(), bridge._sim.checkpoint_state(), random.getstate()) == (w, n, rng)
        receipt = apply(world, TARGET, STAT, 21)
        assert receipt.effective_counter == 2 and receipt.effective_through_turn == world.turn
        assert receipt.event.event_id == f'{world.turn}:lab_transport_disruption:0'
        assert receipt.event.source == 'lab'
        assert world.events_timeline[-1] == receipt.event
        assert not apply(world, TARGET, STAT, 21).changed
        assert len([e for e in world.events_timeline if e.event_type == 'lab_transport_disruption']) == 1
        assert bridge._sim.checkpoint_state() == n and random.getstate() == rng
        world.regions[2].route_suspensions['trade_route'] = 9
        assert not apply(world, TARGET, STAT, 21).changed
        retained = wi.validate_request(request(), world)
        assert retained[-1] == 9
        assert world.regions[2].route_suspensions['trade_route'] == 9
        with pytest.raises(wi.WhatIfError):
            wi.validate_request(request(region_id=99), world)
    finally:
        bridge.close()


@pytest.mark.skipif(__import__('os').name != 'posix', reason='POSIX child process group required')
def test_native_whatif_loaded_cargo_and_recovery(tmp_path):
    from test_what_if_process import _assert_real_native
    _assert_real_native()
    import os, queue, sys
    if os.environ.get('PYTHONHASHSEED') != '0' or sys.flags.hash_randomization:
        from test_what_if_process import _run_hash_zero_native_fixture
        _run_hash_zero_native_fixture(tmp_path, fixture_file=__file__,
                                      function_name='test_native_whatif_loaded_cargo_and_recovery')
        return
    from chronicler import main
    from chronicler.batch_manifest import simulation_config, output_config
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    from test_crisis_transport_native import _setup, _advance, _rows
    world, bridge = _setup()
    pair = None
    try:
        for _ in range(3):
            _, rows = _advance(world, bridge)
            candidates = [r for r in _rows(rows, 'reserved') if
                          (r.origin_region, r.dest_region, r.good_slot) == (0, 2, 0)]
            if candidates:
                break
        assert candidates
        voyage = candidates[0].voyage_id
        _, rows = _advance(world, bridge)
        departed = _rows(rows, 'departed', voyage)
        assert len(departed) == 1 and departed[0].quantity > 0
        args = main._build_parser().parse_args(['--seed','42','--turns','12','--regions','3','--civs','1',
            '--agents','hybrid','--simulate-only','--output',str(tmp_path/'out.md'), '--state',str(tmp_path/'state.json')])
        config = {'agent_mode':'hybrid', 'agent_scale_mode':'fixed', 'validation_sidecar':False,
                  'relationship_stats':False, 'simulation_args':simulation_config(args), 'output_args':output_config(args)}
        state = RunState(world=world, agent_bridge=bridge, memories={}, history=[], chronicle_entries=[],
            era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=12, run_config=config)
        def save(path):
            write_checkpoint(path, state)
        pair = wi.WhatIfPairs(tmp_path, queue.Queue(), SimpleNamespace(save_private=save))
        world_before, native_before = world.model_dump_json(), bridge._sim.checkpoint_state()
        rng_before = random.getstate()
        status = pair.prepare(request(turns=7), world)
        manifest = status['manifest']
        assert manifest['schema_version'] == 3 and manifest['intervention']['region_name'] == world.regions[2].name
        assert manifest['intervention']['effective_counter'] == 2
        assert pair.prepare(request(turns=7), world)['state'] == 'prepared'
        with pytest.raises(wi.WhatIfError, match='different'):
            pair.prepare(request(turns=7, duration=2), world)
        pair.run('transport')
        job = pair.jobs['transport']
        job.thread.join(35)
        assert not job.thread.is_alive() and job.state == 'complete', job.message
        assert world.model_dump_json() == world_before and bridge._sim.checkpoint_state() == native_before
        assert random.getstate() == rng_before
        bundles = {arm:job.result[arm]['bundle'] for arm in ('baseline','intervention')}
        def frame(arm, turn):
            s = next(row for row in bundles[arm]['history'] if row['turn'] == turn)
            return s['transaction_receipts']['rows']
        first = world.turn + 1
        a,b = frame('baseline',first),frame('intervention',first)
        assert any(r['operation']=='arrived' and r['voyage_id']==voyage for r in a)
        assert any(r['operation']=='returned' and r['voyage_id']==voyage for r in b)
        recovery = [r for t in range(first+1,first+7) for r in frame('intervention',t)]
        arrivals = [r for r in recovery if r['operation']=='arrived' and r['dest_region']==2 and r['good_slot']==0]
        assert any(any(q['operation']=='reserved' and q['voyage_id']==r['voyage_id'] for q in recovery)
                   and any(q['operation']=='departed' and q['voyage_id']==r['voyage_id'] for q in recovery)
                   for r in arrivals)
        for arm in ('baseline','intervention'):
            loaded = read_checkpoint(job.directory/arm/'final.ckpt')
            assert loaded.exact
            try:
                records=loaded.state.run_config.get('interventions',[])
                assert len(records) == (arm == 'intervention')
                events=[e for e in loaded.state.world.events_timeline if e.event_type=='lab_transport_disruption']
                assert len(events) == (arm == 'intervention')
            finally:
                loaded.state.agent_bridge.close()
    finally:
        if pair is not None:
            pair.close()
        bridge.close()
