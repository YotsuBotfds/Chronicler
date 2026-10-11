"""Literal adversarial evidence, real git objects, and end-to-end CLI checks.

Runs with unittest (stdlib only) as well as pytest. No native build or simulations.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from chronicler.evidence_admission import (
    AdmissionError, sha256, validate_evidence, validate_identity, validate_policy, validate_receipts, validate_source, validate_table,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'evidence_admission'


def encode(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


class EvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.git('init', '-q')
        (self.repo / 'science.py').write_text('VALUE = 42\n')
        self.git('add', 'science.py')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        source = {'commit': self.git('rev-parse', 'HEAD').decode().strip(),
                  'tree': self.git('rev-parse', 'HEAD^{tree}').decode().strip(),
                  'files': {'science.py': sha256(b'VALUE = 42\n')}, 'checkout': 'frozen'}
        native, config = b'literal fixture native bytes', b'{"fixture":true}\n'
        (self.root / 'native.so').write_bytes(native)
        (self.root / 'config.json').write_bytes(config)
        good = (FIXTURES / 'good.csv').read_bytes()
        for name in ('baseline.csv', 'candidate.csv', 'original.csv'):
            (self.root / name).write_bytes(good)
        expected = {'source': source, 'native_sha256': sha256(native), 'config_sha256': sha256(config),
                    'seeds': [7, 8], 'checkpoints': [10, 20],
                    'table': {'columns': ['seed', 'turn', 'alive', 'births', 'exposure', 'rate'],
                              'counts': ['alive', 'births', 'exposure'],
                              'ratios': [{'column': 'rate', 'numerator': 'births', 'denominator': 'exposure',
                                          'absolute_tolerance': '0'}]}}
        self.policy = {'schema_version': 1, 'lane': 'fixture', 'baseline_domain': 'public-edf7299',
                       'runs': {'baseline': copy.deepcopy(expected), 'candidate': copy.deepcopy(expected)},
                       'original_baseline': {'run': 'baseline', 'sha256': sha256(good)},
                       'review_tiers': ['tier1', 'tier2']}
        self.manifest = {'schema_version': 1, 'lane': 'fixture', 'baseline_domain': 'public-edf7299',
                         'policy_sha256': sha256(encode(self.policy)), 'members': {}, 'runs': {},
                         'original_baseline': 'original.csv'}
        for run_id in ('baseline', 'candidate'):
            self.manifest['runs'][run_id] = {'source': copy.deepcopy(source), 'native': 'native.so',
                                            'config': 'config.json', 'process': f'{run_id}-process.json', 'table': f'{run_id}.csv'}
            process = {'run_id': run_id, 'status': 'complete', 'returncode': 0, 'seeds': [7, 8], 'turns': 20,
                       'source': copy.deepcopy(source), 'native_sha256': sha256(native), 'config_sha256': sha256(config),
                       'executions': [{'seed': seed, 'status': 'complete', 'returncode': 0, 'terminal_turn': 20} for seed in (7, 8)]}
            (self.root / f'{run_id}-process.json').write_bytes(encode(process))
        self.rehash()
        self.repos = {'baseline': self.repo, 'candidate': self.repo}

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, check=True).stdout

    def rehash(self):
        names = {'native.so', 'config.json', 'original.csv', 'baseline.csv', 'candidate.csv', 'baseline-process.json', 'candidate-process.json'}
        self.manifest['members'] = {name: sha256((self.root / name).read_bytes()) for name in sorted(names)}

    def admit(self):
        return validate_evidence(self.manifest, self.policy, sha256(encode(self.policy)), self.root, self.repos)

    def receipts(self):
        evidence_hash, policy_hash = sha256(encode(self.manifest)), sha256(encode(self.policy))
        first = {'schema_version': 1, 'tier': 'tier1', 'reviewer': 'independent-a', 'status': 'approved',
                 'evidence_sha256': evidence_hash, 'policy_sha256': policy_hash, 'dependencies': {}}
        second = {**first, 'tier': 'tier2', 'reviewer': 'independent-b', 'dependencies': {'tier1': sha256(encode(first))}}
        return [encode(first), encode(second)]

    def cli_files(self):
        for name, value in [('policy.json', self.policy), ('manifest.json', self.manifest)]:
            (self.root / name).write_bytes(encode(value))
        args = [sys.executable, str(ROOT / 'scripts' / 'admit_experiment.py'), 'validate', '--root', str(self.root),
                '--policy', str(self.root / 'policy.json'), '--policy-sha256', sha256(encode(self.policy)),
                '--manifest', str(self.root / 'manifest.json'), '--source-repo', f'baseline={self.repo}',
                '--source-repo', f'candidate={self.repo}']
        return args

    def test_complete_evidence(self):
        self.assertEqual(self.admit(), {'run_rows': {'baseline': 4, 'candidate': 4}, 'member_count': 7,
                                       'original_baseline_equivalent': True})

    def test_literal_adversarial_csv_fixtures_even_after_rehash(self):
        for filename, reason in [('altered_header.csv', 'header'), ('missing_row.csv', 'incomplete'),
                                 ('duplicate_seed.csv', 'duplicate'), ('undefined_ratio.csv', 'undefined ratio'),
                                 ('fractional_count.csv', 'invalid count')]:
            with self.subTest(filename=filename):
                (self.root / 'candidate.csv').write_bytes((FIXTURES / filename).read_bytes())
                self.rehash()
                with self.assertRaisesRegex(AdmissionError, reason):
                    self.admit()

    def test_original_equivalence_after_coherent_candidate_rehash(self):
        (self.root / 'baseline.csv').write_bytes((FIXTURES / 'altered_baseline.csv').read_bytes())
        self.rehash()
        with self.assertRaisesRegex(AdmissionError, 'exact numeric equivalence'):
            self.admit()

    def test_original_equivalence_is_exact_but_independent_of_order_or_decimal_spelling(self):
        rows = (FIXTURES / 'good.csv').read_text().splitlines()
        text = '\n'.join([rows[0], *reversed(rows[1:])]) + '\n'
        (self.root / 'baseline.csv').write_text(text.replace('0.5', '0.500000'))
        self.rehash()
        self.admit()

    def test_preserved_original_hash_is_independently_pinned(self):
        (self.root / 'original.csv').write_bytes((FIXTURES / 'altered_baseline.csv').read_bytes())
        (self.root / 'baseline.csv').write_bytes((FIXTURES / 'altered_baseline.csv').read_bytes())
        self.rehash()
        with self.assertRaisesRegex(AdmissionError, 'pinned member hash'):
            self.admit()

    def test_stale_members(self):
        for name in list(self.manifest['members']):
            with self.subTest(name=name):
                original = (self.root / name).read_bytes()
                (self.root / name).write_bytes(original + b' ')
                with self.assertRaisesRegex(AdmissionError, 'stale member hash'):
                    self.admit()
                (self.root / name).write_bytes(original)

    def test_rehashed_native_or_config_still_fails_identity(self):
        for name, reason in [('native.so', 'native identity'), ('config.json', 'config identity')]:
            with self.subTest(name=name):
                original = (self.root / name).read_bytes()
                (self.root / name).write_bytes(b'altered')
                self.rehash()
                with self.assertRaisesRegex(AdmissionError, reason):
                    self.admit()
                (self.root / name).write_bytes(original)
                self.rehash()

    def test_literal_failed_and_incomplete_process_fixtures(self):
        process_path = self.root / 'candidate-process.json'
        original = json.loads(process_path.read_bytes())
        for name, mutation in json.loads((FIXTURES / 'process_mutations.json').read_bytes()).items():
            with self.subTest(case=name):
                process_path.write_bytes(encode({**original, **mutation}))
                self.rehash()
                with self.assertRaises(AdmissionError):
                    self.admit()

    def test_worker_short_terminal_turn_and_boolean_exit(self):
        process_path = self.root / 'candidate-process.json'
        original = json.loads(process_path.read_bytes())
        for field, value in [('terminal_turn', 19), ('returncode', False), ('terminal_turn', True)]:
            process = copy.deepcopy(original)
            process['executions'][1][field] = value
            process_path.write_bytes(encode(process))
            self.rehash()
            with self.assertRaises(AdmissionError):
                self.admit()

    def test_source_objects_checked_against_repository(self):
        for field in ('commit', 'tree'):
            source = copy.deepcopy(self.policy['runs']['baseline']['source'])
            source[field] = '0' * 40
            with self.assertRaises(AdmissionError):
                validate_source(source, self.repo, 'baseline')
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        source['files']['science.py'] = '0' * 64
        with self.assertRaisesRegex(AdmissionError, 'source file hash'):
            validate_source(source, self.repo, 'baseline')

    def test_live_source_rejects_dirty_and_untracked_files_and_wrong_head(self):
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        source['checkout'] = 'live'
        validate_source(source, self.repo, 'live')
        (self.repo / 'science.py').write_text('VALUE = 43\n')
        with self.assertRaisesRegex(AdmissionError, 'dirty'):
            validate_source(source, self.repo, 'live')
        self.git('checkout', '--', 'science.py')
        (self.repo / 'hidden.py').write_text('secret change\n')
        with self.assertRaisesRegex(AdmissionError, 'dirty'):
            validate_source(source, self.repo, 'live')
        self.git('add', 'hidden.py')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'next')
        with self.assertRaisesRegex(AdmissionError, 'HEAD mismatch'):
            validate_source(source, self.repo, 'live')

    def test_live_source_rejects_hidden_index_flags_on_unanchored_file(self):
        (self.repo / 'unanchored.py').write_text('VALUE = 1\n')
        self.git('add', 'unanchored.py')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'unanchored')
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        source.update(commit=self.git('rev-parse', 'HEAD').decode().strip(),
                      tree=self.git('rev-parse', 'HEAD^{tree}').decode().strip(), checkout='live')
        for flag in ('assume-unchanged', 'skip-worktree'):
            self.git('update-index', f'--{flag}', 'unanchored.py')
            (self.repo / 'unanchored.py').write_text('VALUE = 999\n')
            self.assertEqual(self.git('status', '--porcelain'), b'')
            with self.assertRaisesRegex(AdmissionError, 'hidden index flags'):
                validate_source(source, self.repo, 'live')
            (self.repo / 'unanchored.py').write_text('VALUE = 1\n')
            self.git('update-index', f'--no-{flag}', 'unanchored.py')
        validate_source(source, self.repo, 'live')

    def test_full_tree_verification_independent_of_git_status_cache(self):
        from unittest.mock import patch
        import chronicler.evidence_admission as module
        (self.repo / 'unanchored.py').write_text('VALUE = 1\n')
        self.git('add', 'unanchored.py')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'unanchored')
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        source.update(commit=self.git('rev-parse', 'HEAD').decode().strip(),
                      tree=self.git('rev-parse', 'HEAD^{tree}').decode().strip(), checkout='live')
        (self.repo / 'unanchored.py').write_text('VALUE = 2\n')
        actual_git = module._git
        with patch.object(module, '_git', side_effect=lambda repo, *args: b'' if args[0] == 'status' else actual_git(repo, *args)):
            with self.assertRaisesRegex(AdmissionError, 'tracked source content mismatch'):
                validate_source(source, self.repo, 'live')

    def test_reusable_source_and_identity_validators_reject_bad_specs(self):
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        for value in ('typo-live', None, [], {}):
            source['checkout'] = value
            with self.assertRaises(AdmissionError):
                validate_source(source, self.root / 'missing', 'bad')
        validate_identity(b'native', sha256(b'native'), 'native')
        with self.assertRaisesRegex(AdmissionError, 'identity mismatch'):
            validate_identity(b'changed', sha256(b'native'), 'native')
        with self.assertRaisesRegex(AdmissionError, 'full lowercase hash'):
            validate_identity(b'native', 'abc', 'native')

    def test_git_replacements_cannot_redefine_pinned_source(self):
        (self.repo / 'pkg').mkdir()
        (self.repo / 'pkg' / 'other.py').write_text('ORIGINAL = True\n')
        self.git('add', 'pkg/other.py')
        self.git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'original')
        source = copy.deepcopy(self.policy['runs']['baseline']['source'])
        source.update(commit=self.git('rev-parse', 'HEAD').decode().strip(),
                      tree=self.git('rev-parse', 'HEAD^{tree}').decode().strip(), checkout='live')
        original_tree = self.git('rev-parse', 'HEAD:pkg').decode().strip()
        (self.repo / 'pkg' / 'other.py').write_text('ORIGINAL = False\n')
        self.git('add', 'pkg/other.py')
        new_tree = self.git('write-tree').decode().strip()
        replacement_tree = self.git('rev-parse', f'{new_tree}:pkg').decode().strip()
        self.git('replace', original_tree, replacement_tree)
        self.assertEqual(self.git('status', '--porcelain'), b'')
        with self.assertRaises(AdmissionError):
            validate_source(source, self.repo, 'live')
        # A replacement of an anchored file must not redefine historical bytes.
        source['checkout'] = 'frozen'
        blob = self.git('rev-parse', 'HEAD:science.py').decode().strip()
        replacement_blob = self.git('rev-parse', f'{new_tree}:pkg/other.py').decode().strip()
        self.git('replace', blob, replacement_blob)
        validate_source(source, self.repo, 'historical')

    def test_git_inspection_does_not_refresh_index_or_run_fsmonitor(self):
        import chronicler.evidence_admission as module
        from unittest.mock import patch
        with patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as invoke:
            module._git(self.repo, 'status', '--porcelain')
        command = invoke.call_args.args[0]
        self.assertIn('--no-replace-objects', command)
        self.assertIn('--no-optional-locks', command)
        self.assertIn('core.fsmonitor=false', command)

    def test_reusable_table_and_receipts_reject_bad_specs(self):
        good = (FIXTURES / 'good.csv').read_bytes()
        with self.assertRaises(AdmissionError):
            validate_table(good, {}, [7, 8], [10, 20], 'bad')
        with self.assertRaises(AdmissionError):
            validate_table(good, self.policy['runs']['baseline']['table'], [7, 7], [10, 20], 'bad')
        with self.assertRaises(AdmissionError):
            validate_receipts([], [], '0' * 64, '0' * 64)

    def test_numeric_size_overflow_rejected_and_cli_emits_structured_rejection(self):
        raw = (FIXTURES / 'good.csv').read_bytes().replace(b'0.5', b'1e1000000', 1)
        (self.root / 'candidate.csv').write_bytes(raw)
        self.rehash()
        result = subprocess.run(self.cli_files(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'REJECTED')
        self.assertIn('unsupported numeric size', result.stdout)

    def test_oversized_seed_raises_admission_error_in_reusable_api(self):
        raw = (FIXTURES / 'good.csv').read_bytes().replace(b'7,10,', b'7' * 5000 + b',10,', 1)
        with self.assertRaisesRegex(AdmissionError, 'seed/turn size'):
            validate_table(raw, self.policy['runs']['baseline']['table'], [7, 8], [10, 20], 'oversize')

    def test_cross_baseline_manifest_rejected(self):
        self.manifest['baseline_domain'] = 'private-b665e198'
        with self.assertRaisesRegex(AdmissionError, 'cross-baseline'):
            self.admit()

    def test_complete_run_inventory_required(self):
        del self.manifest['runs']['candidate']
        with self.assertRaisesRegex(AdmissionError, 'incomplete or unexpected runs'):
            self.admit()

    def test_member_inventory_exact(self):
        self.manifest['members']['provisional-receipt.json'] = '0' * 64
        with self.assertRaisesRegex(AdmissionError, 'receipts/self'):
            self.admit()

    def test_missing_member(self):
        (self.root / 'candidate.csv').unlink()
        with self.assertRaisesRegex(AdmissionError, 'missing member'):
            self.admit()

    def test_unsafe_paths_and_symlinks(self):
        for name in ('../outside.csv', '/absolute.csv', 'nested/../candidate.csv', 'nested//candidate.csv', 'C:\\x.csv'):
            with self.subTest(name=name):
                self.manifest['runs']['candidate']['table'] = name
                with self.assertRaisesRegex(AdmissionError, 'unsafe'):
                    self.admit()
        self.manifest['runs']['candidate']['table'] = 'candidate.csv'
        (self.root / 'candidate.csv').unlink()
        (self.root / 'candidate.csv').symlink_to(self.root / 'baseline.csv')
        with self.assertRaisesRegex(AdmissionError, 'symlink'):
            self.admit()

    def test_alias_original_and_hardlinks(self):
        self.manifest['original_baseline'] = 'baseline.csv'
        self.manifest['members'].pop('original.csv')
        with self.assertRaisesRegex(AdmissionError, 'roles alias'):
            self.admit()
        self.manifest['original_baseline'] = 'original.csv'
        (self.root / 'original.csv').unlink()
        os.link(self.root / 'baseline.csv', self.root / 'original.csv')
        self.rehash()
        with self.assertRaisesRegex(AdmissionError, 'hard-linked'):
            self.admit()

    def test_bad_numeric_cells_and_row_shapes(self):
        good = (FIXTURES / 'good.csv').read_bytes()
        mutations = [good.replace(b'80,', value + b',', 1) for value in (b'NaN', b'Infinity', b'null', b'', b' 80', b'8_0', b'-1')]
        mutations.extend([good.replace(b'7,10,', b'07,10,', 1), good + b'\n', good.replace(b'7,10,80,', b'7,10,', 1),
                          good.replace(b'8,20,60,', b'9,20,60,', 1), good.replace(b'8,20,60,', b'8,19,60,', 1)])
        for raw in mutations:
            with self.subTest(raw=raw):
                with self.assertRaises(AdmissionError):
                    validate_table(raw, self.policy['runs']['candidate']['table'], [7, 8], [10, 20], 'bad')

    def test_exact_ratio_and_trusted_tolerance_boundary(self):
        spec = {'columns': ['seed', 'turn', 'n', 'd', 'r'], 'counts': [],
                'ratios': [{'column': 'r', 'numerator': 'n', 'denominator': 'd', 'absolute_tolerance': '0.01'}]}
        validate_table(b'seed,turn,n,d,r\n7,20,1,2,0.51\n', spec, [7], [20], 'boundary')
        with self.assertRaisesRegex(AdmissionError, 'ratio mismatch'):
            validate_table(b'seed,turn,n,d,r\n7,20,1,2,0.5100000000000000000000000000000000000001\n', spec, [7], [20], 'outside')
        spec['ratios'][0]['absolute_tolerance'] = '0'
        with self.assertRaisesRegex(AdmissionError, 'ratio mismatch'):
            validate_table(b'seed,turn,n,d,r\n7,20,1,3,0.33333333333333333333333333333\n', spec, [7], [20], 'exact')

    def test_policy_invalid_seeds_counts_and_review_tiers(self):
        for field, value in [('seeds', [True]), ('seeds', [7, 7]), ('checkpoints', [])]:
            policy = copy.deepcopy(self.policy)
            policy['runs']['baseline'][field] = value
            with self.assertRaises(AdmissionError):
                validate_policy(policy)
        for tiers in ([], ['tier1'], ['tier1', 'tier1'], ['tier1', []]):
            policy = copy.deepcopy(self.policy)
            policy['review_tiers'] = tiers
            with self.assertRaises(AdmissionError):
                validate_policy(policy)
        for counts in ([[]], ['alive', 'alive'], ['unknown']):
            policy = copy.deepcopy(self.policy)
            policy['runs']['baseline']['table']['counts'] = counts
            with self.assertRaises(AdmissionError):
                validate_policy(policy)

    def test_final_receipt_chain_reordered_arguments(self):
        receipts = self.receipts()
        result = validate_receipts(list(reversed(receipts)), self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))
        self.assertEqual(result, {'tier1': sha256(receipts[0]), 'tier2': sha256(receipts[1])})

    def test_receipt_missing_duplicate_stale_and_provisional(self):
        receipts = self.receipts()
        for field, value, reason in [('status', 'provisional', 'provisional'), ('evidence_sha256', '0' * 64, 'stale evidence'),
                                     ('policy_sha256', '0' * 64, 'stale policy'), ('reviewer', 'independent-a', 'independent'),
                                     ('tier', 'tier1', 'duplicate')]:
            with self.subTest(field=field):
                second = json.loads(receipts[1])
                second[field] = value
                with self.assertRaisesRegex(AdmissionError, reason):
                    validate_receipts([receipts[0], encode(second)], self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))
        with self.assertRaisesRegex(AdmissionError, 'exactly one'):
            validate_receipts(receipts[:1], self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))

    def test_provisional_receipt_hash_trap_requires_final_dependency_rebinding(self):
        receipts = self.receipts()
        first = json.loads(receipts[0])
        provisional = encode({**first, 'status': 'provisional'})
        second = json.loads(receipts[1])
        second['dependencies'] = {'tier1': sha256(provisional)}
        with self.assertRaisesRegex(AdmissionError, 'dependencies'):
            validate_receipts([receipts[0], encode(second)], self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))

    def test_receipt_self_reference_and_cycles(self):
        receipts = self.receipts()
        for dependency in ({'tier2': sha256(receipts[1])}, {}, {'tier1': '0' * 64},
                           {'tier1': sha256(receipts[0]), 'tier2': sha256(receipts[1])}):
            second = json.loads(receipts[1])
            second['dependencies'] = dependency
            with self.assertRaisesRegex(AdmissionError, 'dependencies'):
                validate_receipts([receipts[0], encode(second)], self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))

    def test_edit_to_upstream_final_receipt_invalidates_downstream(self):
        receipts = self.receipts()
        first = json.loads(receipts[0])
        first['reviewer'] = 'changed-reviewer'
        with self.assertRaisesRegex(AdmissionError, 'dependencies'):
            validate_receipts([encode(first), receipts[1]], self.policy['review_tiers'], sha256(encode(self.manifest)), sha256(encode(self.policy)))

    def test_cli_review_required_evidence_only_admitted_and_input_immutability(self):
        args = self.cli_files()
        before = {path: path.read_bytes() for path in self.root.iterdir() if path.is_file()}
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'REVIEW_REQUIRED')
        result = subprocess.run([*args, '--evidence-only'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'READY_FOR_REVIEW')
        receipts = []
        for index, raw in enumerate(self.receipts()):
            path = self.root / f'tier{index + 1}.json'
            path.write_bytes(raw)
            receipts.extend(['--receipt', str(path)])
        result = subprocess.run([*args, *receipts], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ADMITTED')
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw, str(path))

    def test_cli_seal_exclusive_then_validate_without_manual_member_hashes(self):
        args = self.cli_files()
        (self.root / 'manifest.json').unlink()
        plan = copy.deepcopy(self.manifest)
        plan['members'] = {}
        (self.root / 'plan.json').write_bytes(encode(plan))
        args[2] = 'seal'
        result = subprocess.run([*args, '--plan', str(self.root / 'plan.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest_bytes = (self.root / 'manifest.json').read_bytes()
        self.assertEqual(json.loads(result.stdout)['evidence_sha256'], sha256(manifest_bytes))
        self.assertEqual(json.loads(manifest_bytes), self.manifest)
        result = subprocess.run([*args, '--plan', str(self.root / 'plan.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('refuses to overwrite', result.stdout)
        self.assertEqual((self.root / 'manifest.json').read_bytes(), manifest_bytes)

    def test_cli_pinned_policy_and_strict_json(self):
        args = self.cli_files()
        path = self.root / 'policy.json'
        path.write_bytes(path.read_bytes() + b' ')
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('independently pinned', result.stdout)
        args = self.cli_files()
        path = self.root / 'manifest.json'
        path.write_bytes(b'{"schema_version":1,"schema_version":1}')
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('duplicate JSON key', result.stdout)


if __name__ == '__main__':
    unittest.main()
