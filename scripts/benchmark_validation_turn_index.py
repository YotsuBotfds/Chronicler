import argparse
import hashlib
import json
import pickle
import resource
import sys
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, required=True)
p.add_argument('--inputs', type=Path, required=True)
p.add_argument('--synthetic', type=Path, nargs='+', required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.source / 'src'))
from chronicler import validation_io as V
from chronicler.artifact_io import strict_json_dumps

out = {'source': str(a.source), 'inputs': str(a.inputs), 'filtering': []}
for path in [a.inputs / 'validation_needs.arrow', *a.synthetic]:
    started = time.perf_counter(); cpu = time.process_time()
    columns = V._read_arrow_columns(path)
    load_wall = time.perf_counter() - started; load_cpu = time.process_time() - cpu
    started = time.perf_counter(); cpu = time.process_time()
    turns = V._available_turns_from_columns(columns)
    wall = time.perf_counter() - started; cpu_total = time.process_time() - cpu
    digest = hashlib.sha256()
    rows = 0
    for turn in turns:
        started = time.perf_counter(); cpu = time.process_time()
        selected = V._columns_for_turn(columns, turn)
        wall += time.perf_counter() - started; cpu_total += time.process_time() - cpu
        rows += len(next(iter(selected.values())))
        digest.update(pickle.dumps((turn, selected), protocol=5))
    out['filtering'].append({'path': str(path), 'rows': rows, 'turns': len(turns),
                             'load_wall_s': load_wall, 'load_cpu_s': load_cpu,
                             'select_wall_s': wall, 'select_cpu_s': cpu_total,
                             'sha256': digest.hexdigest()})
    del columns, selected
started = time.perf_counter(); cpu = time.process_time()
report = V.run_oracles(a.inputs, ['all'], profile='subset', legacy_batch=True)
encoded = strict_json_dumps(report).encode()
out['validation'] = {'wall_s': time.perf_counter() - started,
                     'cpu_s': time.process_time() - cpu, 'report_bytes': len(encoded),
                     'sha256': hashlib.sha256(encoded).hexdigest(),
                     'statuses': {key: row['status'] for key, row in report['results'].items()}}
out['max_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
out['validation_source_sha256'] = hashlib.sha256((a.source / 'src/chronicler/validation_io.py').read_bytes()).hexdigest()
a.out.write_text(json.dumps(out, indent=2) + '\n')
