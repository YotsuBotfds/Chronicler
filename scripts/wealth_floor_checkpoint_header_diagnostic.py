#!/usr/bin/env python3
"""Pending new-volume, remote-only observation of four original CP headers.

Outer ZIP deflate streaming is allowed. Inner CP sections are never inflated,
unpickled, restored or imported. Old A/W input bounds and authority stay intact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import struct
import sys
import zipfile
import zlib

import wealth_floor_failed_cohort_diagnostic as L

A, W, R, D = L.A, L.W, L.R, L.D
REVIEWED_HEADER_ACTIVATION = "7ba1b637090221d5ac5ec530f07b4f8343548c5397787c58236d7e14b49c948e"
INPUT_FILE = "docs/integration/wealth-floor-checkpoint-header-only-inputs.json"
INPUT_SHA256 = "3869d66afaa00e567f7a9219c0edd57e413ee75d29f7df1024d0522aafb045be"
OLD_PUBLICATIONS = L.PUBLICATION_FILE
BRANCH = "lead/cloud-wealth-floor-checkpoint-header-diagnostic-20261029"
WORKFLOW = ".github/workflows/wealth-floor-checkpoint-header-diagnostic.yml"
TEMPLATE = "docs/workflows/wealth-floor-checkpoint-header-diagnostic.yml"
TEMPLATE_SHA256 = "26763af57ba5fc81e12a3d395f2bede8fe63408d11506f7524eb3b233c6b552a"
JOB_NAME = "Observe four original checkpoint headers"
MAX_STAGE = 5_500_000_000  # NEW named decimal-volume contract; no A/W mutation.
EXACT_INPUT_BYTES = 5_457_873_896
MAX_OUTPUT = 8 * 1024**2
RESERVE = 8 * 1024**2
MAX_CENTRAL = 64 * 1024**2
MAX_ENTRIES = 100000
MAX_EXPANDED = 6 * 1024**3
MAX_CP = 64 * 1024**2
MAX_HEADER = 65536
CHUNK = 1024**2
MAGIC = b"\x89CHRONICLER-CKPT\r\n\x1a\n"
SOURCE_PINS = dict(L.SOURCE_PINS,
    **{"scripts/wealth_floor_failed_cohort_diagnostic.py": "8fb7a93fdf70df99ea0f947651dbd8ca92b6454f4d8df0cb7e8633af2ee2cfe9",
       "scripts/wealth_floor_outcome_checkpoints.py": "34aa2afe4ec99422f88fd12ef7832c78d942810846550c4cf5fc9b1b743d7961"})


def registration():
    A.require(A.hash_shape(REVIEWED_HEADER_ACTIVATION), "new header-only activation pending")
    return REVIEWED_HEADER_ACTIVATION


@dataclass(frozen=True)
class HeaderArchivePin:
    world: str
    artifact_id: int
    name: str
    size: int
    sha256: str
    expires_at: str
    def __post_init__(self):
        A.require(type(self.world) is str and self.world in ("template", "procedural")
            and type(self.artifact_id) is int and self.artifact_id > 0,
            "header archive role/ID")
        A.require(self.name == f"wealth-outcome-full-{self.world}-failed-checkpoints-{W.PRODUCER_RUN}-1"
            and type(self.size) is int and 0 < self.size <= MAX_STAGE and A.hash_shape(self.sha256), "new header archive pin")
        W.strict_utc(self.expires_at)


def stage_admission(resources, pins):
    A.require(type(pins) is tuple and len(pins) == 2 and all(type(p) is HeaderArchivePin for p in pins)
        and {p.world for p in pins} == {"template", "procedural"}, "two closed header archives")
    total = sum(p.size for p in pins)
    A.require(total == EXACT_INPUT_BYTES and total + MAX_OUTPUT + RESERVE <= MAX_STAGE, "new decimal staging contract")
    A.require(type(resources.get("disk_free_bytes")) is int and resources["disk_free_bytes"] >= 12 * 1024**3
        and resources["disk_free_bytes"] >= total + MAX_OUTPUT + RESERVE + 3 * 1024**3
        and type(resources.get("ram_available_bytes")) is int and resources["ram_available_bytes"] >= 2 * 1024**3,
        "header resource admission")
    return dict(compressed_bytes=total, output_bytes=MAX_OUTPUT, reserve_bytes=RESERVE,
        new_staging_ceiling_decimal_bytes=MAX_STAGE, old_A_W_limits_unchanged=True)


def expected_members(bundle):
    rows = bundle["member_index_pins"]
    A.require(type(rows) is list and 0 < len(rows) < MAX_ENTRIES, "finite selector rows")
    out = {}
    for row in rows:
        name = A.canonical_name(row.get("path"))
        A.require(name.endswith('.ckpt') and name not in out and type(row.get("bytes")) is int
            and 0 < row["bytes"] <= MAX_CP and row.get("sha256") is None, "original selector byte-only pin")
        out[name] = row["bytes"]
    name = bundle["selector_member"]
    A.require(name == "failed-checkpoint-body-selection.json" and name not in out
        and type(bundle["selector_file_bytes"]) is int and 0 < bundle["selector_file_bytes"] <= CHUNK
        and A.hash_shape(bundle["selector_file_sha256"]), "selector file pin")
    out[name] = bundle["selector_file_bytes"]
    A.require(len(out) == bundle["expected_index_files_from_selector"]
        and sum(out.values()) == bundle["expected_expanded_bytes_from_selector"] <= MAX_EXPANDED,
        "whole selector-derived index bounds")
    return out


def read_at(stream, offset, count, size, budget):
    A.require(type(offset) is int and type(count) is int and 0 <= offset <= size
        and 0 <= count <= CHUNK and offset + count <= size, "header ZIP index span")
    budget.check(); stream.seek(offset); raw = stream.read(count); budget.check()
    A.require(type(raw) is bytes and len(raw) == count, "header ZIP index EOF")
    return raw


def zip64_values(extra, size, compressed, offset, disk):
    """Interpret central ZIP64 scalars explicitly; never allocate by a scalar."""
    position = 0; field = None
    while position < len(extra):
        A.require(position + 4 <= len(extra), "truncated ZIP extra field")
        kind, length = struct.unpack_from('<HH', extra, position); position += 4
        A.require(position + length <= len(extra), "truncated ZIP extra payload")
        if kind == 1:
            A.require(field is None, "duplicate ZIP64 extra")
            field = extra[position:position + length]
        position += length
    values = [size, compressed, offset, disk]; cursor = 0
    for i, (sentinel, width) in enumerate(((0xffffffff, 8), (0xffffffff, 8), (0xffffffff, 8), (0xffff, 4))):
        if values[i] == sentinel:
            A.require(field is not None and cursor + width <= len(field), "missing ZIP64 scalar")
            values[i] = int.from_bytes(field[cursor:cursor + width], 'little'); cursor += width
    return tuple(values)


def header_index_preflight(stream, size, expected, budget):
    """NEW explicit high-volume EOCD/ZIP64 contract, before ZipFile allocation."""
    A.require(type(size) is int and 0 < size <= MAX_STAGE and type(expected) is dict
        and 0 < len(expected) <= MAX_ENTRIES and sum(expected.values()) <= MAX_EXPANDED, "header ZIP volume contract")
    tail = read_at(stream, max(0, size - 65557), min(size, 65557), size, budget)
    end = tail.rfind(b'PK\x05\x06'); A.require(end >= 0 and end + 22 <= len(tail), "missing header ZIP footer")
    e = struct.unpack('<4s4H2LH', tail[end:end + 22])
    A.require(end + 22 + e[7] == len(tail) and e[1] == e[2] == 0, "ZIP footer/multidisk")
    end_pos = size - len(tail) + end; entries, central_size, central_offset = e[4], e[5], e[6]
    sentinel = entries == 65535 or central_size == 0xffffffff or central_offset == 0xffffffff
    locator = read_at(stream, end_pos - 20, 20, size, budget) if end_pos >= 20 else b''
    if locator.startswith(b'PK\x06\x07'):
        _, disk, offset, disks = struct.unpack('<4sLQL', locator)
        A.require(disk == 0 and disks == 1, "ZIP64 multidisk")
        z = struct.unpack('<4sQ2H2L4Q', read_at(stream, offset, 56, size, budget))
        A.require(z[0] == b'PK\x06\x06' and z[3] == 45 and 44 <= z[1] <= 4096
            and offset + z[1] + 12 == end_pos - 20 and z[4] == z[5] == 0 and z[6] == z[7], "ZIP64 footer span")
        entries, central_size, central_offset = z[7], z[8], z[9]
        A.require((e[3] == 65535 or e[3] == entries) and (e[4] == 65535 or e[4] == entries)
            and (e[5] == 0xffffffff or e[5] == central_size) and (e[6] == 0xffffffff or e[6] == central_offset), "ZIP64 footer disagreement")
        central_end = offset
    else:
        A.require(not sentinel and e[3] == entries, "missing ZIP64/count footer")
        central_end = end_pos
    A.require(0 < entries <= MAX_ENTRIES and 46 * entries <= central_size <= MAX_CENTRAL
        and central_offset + central_size == central_end, "new ZIP central count/span caps")
    prefixes = {str(p) for n in expected for p in PurePosixPath(n).parents if str(p) != '.'}
    A.require(not expected.keys() & prefixes, "selector path prefix conflict")
    position = central_offset; names = []; regular = set(); expanded = 0
    while position < central_end:
        h = struct.unpack('<4s6H3L5H2L', read_at(stream, position, 46, size, budget))
        A.require(h[0] == b'PK\x01\x02' and not h[3] & 1 and h[4] in (0, 8), "unsupported central entry")
        length = 46 + h[10] + h[11] + h[12]
        A.require(h[10] > 0 and position + length <= central_end, "truncated central entry")
        raw_name = read_at(stream, position + 46, h[10], size, budget)
        try: name = raw_name.decode('utf-8' if h[3] & 0x800 else 'cp437')
        except UnicodeError: raise A.AdmissionError("invalid ZIP name encoding") from None
        directory = name.endswith('/'); base = A.canonical_name(name, directory=directory)
        extra = read_at(stream, position + 46 + h[10], h[11], size, budget)
        file_size, compressed, local, disk = zip64_values(extra, h[9], h[8], h[16], h[13])
        mode = stat.S_IFMT(h[15] >> 16)
        A.require(disk == 0 and 0 <= local < central_offset and compressed <= size, "central member offset/disk")
        if directory:
            A.require(base in prefixes and mode in (0, stat.S_IFDIR) and file_size == compressed == h[7] == 0
                and h[4] == 0, "unexpected ZIP directory")
        else:
            A.require(mode in (0, stat.S_IFREG) and base in expected and base not in regular
                and file_size == expected[base], "exact selector member closure/size")
            regular.add(base); expanded += file_size
            A.require(expanded <= MAX_EXPANDED, "whole expanded header contract cap")
        names.append(name); A.require(len(names) <= entries, "central entry count")
        position += length
    A.require(position == central_end and len(names) == entries and len(set(names)) == entries
        and regular == expected.keys() and expanded == sum(expected.values()), "complete selector index closure")
    return tuple(names)


def parse_checkpoint_prefix(prefix, total_bytes, budget):
    A.require(type(prefix) is bytes and len(prefix) <= MAX_HEADER + len(MAGIC) + 4
        and type(total_bytes) is int and 0 < total_bytes <= MAX_CP and prefix.startswith(MAGIC)
        and len(prefix) >= len(MAGIC) + 4, "checkpoint magic/size")
    start = len(MAGIC) + 4; length = struct.unpack('<I', prefix[len(MAGIC):start])[0]
    A.require(0 < length <= MAX_HEADER and start + length <= len(prefix), "fixed checkpoint header bound")
    raw = prefix[start:start + length]; header = A.parse_json(raw, budget)
    A.require(type(header.get('version')) is int and header['version'] == 1
        and header.get('format') == 'chronicler-run-checkpoint' and type(header.get('exact')) is bool
        and type(header.get('world')) is dict and type(header.get('run_config')) is dict
        and type(header.get('identity')) is dict and type(header.get('lineage')) is list
        and type(header.get('sections')) is list and 0 < len(header['sections']) <= 32, "typed checkpoint header")
    for name in ('seed', 'turn', 'start_turn', 'num_turns'):
        A.require(type(header.get(name)) is int and header[name] >= 0, "typed checkpoint horizon")
    for name in ('regions', 'civilizations'):
        A.require(type(header['world'].get(name)) is int and header['world'][name] >= 0, "typed current world count")
    for name in ('source', 'native', 'environment'):
        A.require(name not in header['identity'] or type(header['identity'][name]) is dict, "typed identity subobject")
    if 'agent_mode' in header['run_config']:
        A.require(type(header['run_config']['agent_mode']) is str, "typed agent mode")
    if 'validation_sidecar' in header['run_config']:
        A.require(type(header['run_config']['validation_sidecar']) is bool, "typed sidecar flag")
    offset = 0; names = set()
    for section in header['sections']:
        A.require(type(section) is dict and type(section.get('name')) is str and section['name'] not in names
            and type(section.get('codec')) is str and len(section['codec']) <= 64
            and type(section.get('offset')) is int and section['offset'] == offset
            and type(section.get('length')) is int and section['length'] >= 0
            and type(section.get('raw_length')) is int and section['raw_length'] >= 0
            and A.hash_shape(section.get('sha256')), "typed contiguous packed section descriptor")
        names.add(section['name']); offset += section['length']
        A.require(start + length + offset <= total_bytes, "packed section extent beyond CP")
    A.require(start + length + offset == total_bytes, "packed CP extent EOF")
    return dict(header=header, header_json_bytes=length, header_json_sha256=hashlib.sha256(raw).hexdigest(),
        inner_section_digests_verified=False, inner_sections_inflated=False)


def old_shape_observations(header, config):
    world = header['world']; run = header['run_config']; sections = [s['name'] for s in header['sections']]
    bits = dict(regions_equals_requested=world.get('regions') == config['regions'],
        current_civilizations_equals_initial_requested=world.get('civilizations') == config['civs'],
        agent_mode_hybrid=run.get('agent_mode') == 'hybrid', validation_sidecar_true=run.get('validation_sidecar') is True,
        sections_exact_python_agent0=sections == ['python', 'native.agent.0'])
    return dict(current_world_counts=world, requested_initial_config=config, agent_mode=run.get('agent_mode'),
        validation_sidecar=run.get('validation_sidecar'), section_names=sections, old_K_predicate_bits=bits,
        old_compound_result=all(bits.values()), interpretation='Observed operands only; no legitimate/invalid civilization judgment or physics admission.')


class HeaderClient(W.ClosedClient):
    def __init__(self, token, pins, budget, *, current_run_id, opener_factory=None):
        A.require(type(pins) is tuple and len(pins) == 2 and all(type(p) is HeaderArchivePin for p in pins)
            and {p.world for p in pins} == {'template','procedural'} and sum(p.size for p in pins) == EXACT_INPUT_BYTES,
            "new fixed header download scope")
        A.require(type(token) is str and token and not any(c.isspace() for c in token)
            and type(current_run_id) is int and current_run_id > 0, "header job credential/ID")
        self.token, self.budget = token, budget; self.opener_factory = opener_factory or W.urllib.request.build_opener
        self.zip_endpoints = frozenset(W.API + '/actions/artifacts/' + str(p.artifact_id) + '/zip' for p in pins)
        self.metadata_endpoints = frozenset((W.API + f'/actions/runs/{W.PRODUCER_RUN}/attempts/1',
            W.API + f'/actions/runs/{W.PRODUCER_RUN}/attempts/1/jobs?per_page=100',
            W.API + f'/actions/runs/{W.PRODUCER_RUN}/artifacts?per_page=100',
            W.API + f'/actions/runs/{current_run_id}/attempts/1',
            W.API + f'/actions/runs/{current_run_id}/attempts/1/jobs?per_page=100'))


def stream_header_archive(response, pin, write, check):
    """NEW pin type/input-volume contract; unchanged bounded streaming pattern."""
    A.require(type(pin) is HeaderArchivePin and callable(getattr(response, 'read1', None)), "typed header stream")
    W.check_length(response.headers, pin.size, exact=True); digest = hashlib.sha256(); count = 0
    while True:
        check(); requested = min(CHUNK, pin.size + 1 - count); raw = response.read1(requested); check()
        A.require(type(raw) is bytes and len(raw) <= requested, "bounded header stream read")
        if not raw: break
        count += len(raw); A.require(count <= pin.size, "header ZIP overrun")
        digest.update(raw); A.require(write(raw) == len(raw), "partial header archive write"); check()
    A.require(count == pin.size and digest.hexdigest() == pin.sha256, "header ZIP exact EOF/SHA")
    return dict(artifact_id=pin.artifact_id, bytes=count, sha256=digest.hexdigest())


CONFIG = {'template': dict(regions=8, civs=4, turns=500), 'procedural': dict(regions=32, civs=10, turns=300)}
SCHEDULE = {'template': (48, 101, 201), 'procedural': (44, 141, 161)}
CANDIDATE = '503070175e3e78d9014add158ead8f16ce940843'
PACKAGE = '49d78e877f981c4af2440e9dadbde7dd211e2fff0d2f1be68e7a4e5c10310e0a'
NATIVE = 'b56c43f16722be2c8fc6fbe5c021ec292f9a6856783d946af56d97e91575e619'
ROOT_5F = '1e34c549899abe779baa7d8ab42f39a35fd790df6e1156130590b8124bdcf007'


def build_plan(data, public):
    A.require(type(data) is dict and data.get('schema_version') == 1 and data.get('contract') == 'four-original-checkpoint-headers-v1'
        and data.get('original_control_source') == W.PRODUCER_SOURCE and data.get('original_run') == W.PRODUCER_RUN
        and type(data.get('attempt')) is int and data['attempt'] == 1 and data.get('jobs') == dict(W.PRODUCER_JOBS)
        and data.get('metadata_root_qualification_sha256') == ROOT_5F
        and data.get('original_publication_policy_sha256') == L.PUBLICATION_SHA256,
        'header input authority roles')
    reference = data.get('candidate_identity_reference', {})
    A.require(reference.get('source') == CANDIDATE and reference.get('package_digest') == PACKAGE
        and reference.get('native_sha256') == NATIVE, 'candidate identity reference role')
    A.require(type(data.get('bundles')) is dict and set(data['bundles']) == set(CONFIG)
        and type(data.get('targets')) is dict and set(data['targets']) == set(CONFIG), 'both header worlds required')
    A.require(type(public) is dict and type(public.get('artifacts')) is list and len(public['artifacts']) == 10,
        'original ten metadata publications')
    official = {p['id']: p for p in public['artifacts']}; pins = []; expected = {}
    for world in ('template', 'procedural'):
        bundle = data['bundles'][world]
        A.require(type(bundle.get('digest')) is str and bundle['digest'].startswith('sha256:'), 'header artifact digest type')
        fields = ('id','name','size_in_bytes','digest','expires_at','expired','workflow_run')
        A.require(bundle['id'] in official and A.json_bytes({k:bundle[k] for k in fields}) == A.json_bytes(official[bundle['id']]),
            'header archive cross-bound to original publication')
        pin = HeaderArchivePin(world, bundle['id'], bundle['name'], bundle['size_in_bytes'], bundle['digest'][7:], bundle['expires_at'])
        pins.append(pin); expected[world] = expected_members(bundle)
        A.require(len(expected[world]) == (801 if world == 'template' else 901), 'exact selector index coverage')
        targets = data['targets'][world]; seed, valid, unvalidated = SCHEDULE[world]
        A.require(type(targets) is list and len(targets) == 2, 'two exact header targets per ZIP')
        for target, label, turn in zip(targets, ('last_valid','first_unvalidated'), (valid,unvalidated), strict=True):
            wanted = f'raw/full_gate/batch_42/seed_{seed}/checkpoint_turn_{turn}.ckpt'
            A.require(target.get('label') == label and target.get('path') == wanted and target.get('seed') == seed
                and target.get('turn') == turn and type(target.get('file_bytes')) is int
                and target['file_bytes'] == expected[world][wanted] and target.get('selector_body_sha256') is None,
                'source-derived exact target/selector bytes')
            known = target.get('known_wholefile_sha256')
            A.require(A.hash_shape(known) if label == 'last_valid' else known is None, 'known versus unobserved SHA roles')
    A.require(sum(p.size for p in pins) == EXACT_INPUT_BYTES and EXACT_INPUT_BYTES + MAX_OUTPUT + RESERVE <= MAX_STAGE,
        'new volume math differs')
    return dict(pins=tuple(pins), expected=expected, bundles=data['bundles'], targets=data['targets'])


def read_member(archive, info, budget, *, checkpoint):
    limit = MAX_CP if checkpoint else CHUNK
    A.require(0 < info.file_size <= limit, 'selected entry size')
    digest = hashlib.sha256(); crc = count = 0; prefix = bytearray(); pieces = []
    with archive.open(info) as stream:
        while True:
            budget.check(); block = stream.read(min(CHUNK, info.file_size + 1 - count)); budget.check()
            if not block: break
            count += len(block); A.require(count <= info.file_size, 'selected CP/selector overrun')
            digest.update(block); crc = zlib.crc32(block, crc)
            if checkpoint:
                if len(prefix) < MAX_HEADER + len(MAGIC) + 4:
                    prefix.extend(block[:MAX_HEADER + len(MAGIC) + 4 - len(prefix)])
            else:
                pieces.append(block)
    A.require(count == info.file_size and crc & 0xffffffff == info.CRC, 'selected full EOF/CRC')
    return dict(bytes=count, sha256=digest.hexdigest(), crc32=info.CRC), bytes(prefix) if checkpoint else b''.join(pieces)


def inspect_bundle(path, pin, bundle, targets, budget, emit_header):
    A.require(type(pin) is HeaderArchivePin and type(targets) is list and len(targets) == 2,
        'typed two-target header bundle')
    expected = expected_members(bundle); observed = []; selector_pin = None
    with A._regular(path, budget) as (stream, before):
        A.require(before.st_size == pin.size and A._archive_hash(stream, pin.size, budget) == pin.sha256,
            'whole header ZIP identity before reading')
        names = header_index_preflight(stream, pin.size, expected, budget)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist(); A.require(len(infos) == len(names), 'actual ZIP index count')
            files = {}
            for info, original in zip(infos, names, strict=True):
                A.require(info.orig_filename == info.filename == original, 'actual ZIP name normalization')
                name = A.canonical_name(info.filename, directory=info.is_dir())
                if info.is_dir(): continue
                A.require(name in expected and info.file_size == expected[name], 'actual selector-derived index size')
                files[name] = info
            A.require(set(files) == set(expected), 'actual selector-derived index closure')
            selector_pin, raw = read_member(archive, files[bundle['selector_member']], budget, checkpoint=False)
            A.require(selector_pin['bytes'] == bundle['selector_file_bytes']
                and selector_pin['sha256'] == bundle['selector_file_sha256'], 'original selector CRC/SHA pin')
            selector = A.parse_json(raw, budget)
            rows = selector.get('selected')
            A.require(type(rows) is list and not selector.get('omitted') and not selector.get('missing_or_already_retired')
                and selector.get('selection_complete_for_remaining_verified_files') is True,
                'original complete failed-body selection')
            selector_map = {}
            for row in rows:
                A.require(type(row) is dict and row.get('path') not in selector_map
                    and row.get('current_body_sha256') is None, 'byte-only unique original selector row')
                selector_map[row['path']] = row['bytes']
            A.require(selector_map == {k:v for k,v in expected.items() if k != bundle['selector_member']},
                'original selector/index row equality')
            reference = None
            for target in targets:
                name = target['path']; A.require(name in selector_map and target['file_bytes'] == selector_map[name], 'target selector identity')
                file_pin, prefix = read_member(archive, files[name], budget, checkpoint=True)
                known = target.get('known_wholefile_sha256')
                A.require(known is None or file_pin['sha256'] == known, 'known original whole CP SHA differs')
                parsed = parse_checkpoint_prefix(prefix, file_pin['bytes'], budget); header = parsed['header']
                if target['label'] == 'last_valid': reference = header['identity']
                A.require(reference is not None, 'last-valid identity reference precedes unvalidated target')
                observations = old_shape_observations(header, CONFIG[pin.world])
                observations.update(source_matches_candidate=header['identity'].get('source',{}).get('git_sha') == CANDIDATE,
                    package_matches_candidate=header['identity'].get('source',{}).get('package_digest') == PACKAGE,
                    native_matches_candidate=header['identity'].get('native',{}).get('sha256') == NATIVE,
                    identity_equal_last_valid=A.json_bytes(header['identity']) == A.json_bytes(reference),
                    current_identity_scope='Authenticated last-valid header reference; original in-memory K current_identity was not independently serialized.',
                    fresh_parent_lineage_observed=header.get('lineage') == [] and header['run_config'].get('lineage') == []
                        and header['run_config'].get('resume_info') is None,
                    target_seed_turn_horizon_matches=header['seed'] == target['seed'] and header['turn'] == target['turn']
                        and header['num_turns'] == CONFIG[pin.world]['turns'] and header['start_turn'] == 0)
                header_start = len(MAGIC) + 4; raw_header = prefix[header_start:header_start + parsed['header_json_bytes']]
                emit_header(pin.world, target['label'], raw_header)
                observed.append(dict(label=target['label'], path=name, source_schedule_classification=target['schedule_status'],
                    file=file_pin, existing_whole_sha256=known, compared_to_existing_sha=known is not None,
                    sha_origin='original_partial_capture_journal_verified' if known is not None else 'newly_observed_under_authenticated_zip',
                    **parsed, observations=observations, checkpoint_state_decoded=False, physics_qualified=False))
        A.require(A._archive_hash(stream, pin.size, budget) == pin.sha256, 'whole header ZIP changed after selected read')
    return dict(artifact_id=pin.artifact_id, archive_bytes=pin.size, archive_sha256=pin.sha256,
        complete_index_files=len(expected), complete_index_expanded_bytes=sum(expected.values()),
        selector_file=selector_pin, selected_headers=observed, all_other_CP_entries_unexpanded=True,
        full_payload_crc_or_physics_qualification=False, checkpoint_inner_sections_decoded=False)


def source_snapshot(control, budget):
    A.require(Path(L.__file__).resolve() == control/'scripts/wealth_floor_failed_cohort_diagnostic.py'
        and Path(W.__file__).resolve() == control/'scripts/wealth_floor_full_archive_audit.py'
        and Path(A.__file__).resolve() == control/'scripts/wealth_floor_baseline_admission.py'
        and Path(R.__file__).resolve() == control/'scripts/wealth_floor_build_resources.py'
        and Path(D.__file__).resolve() == control/'scripts/wealth_floor_hosted_deployment.py', 'loaded header dependency origin')
    names = (*SOURCE_PINS, 'scripts/wealth_floor_checkpoint_header_diagnostic.py', INPUT_FILE, OLD_PUBLICATIONS, TEMPLATE, WORKFLOW)
    rows = {}
    for name in names:
        raw = A.bounded_read(control/name, A.MAX_METADATA_BYTES, budget); digest = hashlib.sha256(raw).hexdigest()
        if name in SOURCE_PINS: A.require(digest == SOURCE_PINS[name], 'protected header dependency differs')
        if name == INPUT_FILE: A.require(digest == INPUT_SHA256, 'header policy differs')
        if name == OLD_PUBLICATIONS: A.require(digest == L.PUBLICATION_SHA256, 'original publication policy differs')
        rows[name] = dict(bytes=len(raw), sha256=digest)
    dormant = A.bounded_read(control/TEMPLATE, 65536, budget); active = A.bounded_read(control/WORKFLOW, 65536, budget)
    A.require(hashlib.sha256(dormant).hexdigest() == TEMPLATE_SHA256 and dormant == active, 'exact header active workflow copy')
    A.require(A.MAX_COMPRESSED_BYTES == 2126779694 and W.MAX_STAGED == 2133433148,
        'old input ceilings were mutated')  # Observed invariants, not new-input admission.
    A.require(all(v is None for v in A.REVIEWED_CANDIDATE_PROOFS.values())
        and all(getattr(W,n) is None for n in ('REVIEWED_OUTPUTS','REVIEWED_CLOSURES','REVIEWED_OUTCOMES',
            'REVIEWED_RESOURCE_POLICY','REVIEWED_COMPLETION')), 'full authority must remain NULL')
    return rows


def current_producer(client, run_id, source):
    run = client.metadata(W.API+f'/actions/runs/{run_id}/attempts/1')
    jobs = client.metadata(W.API+f'/actions/runs/{run_id}/attempts/1/jobs?per_page=100')
    A.require(run.get('id') == run_id and type(run.get('run_attempt')) is int and run['run_attempt'] == 1
        and run.get('head_sha') == source and run.get('event') == 'push' and run.get('head_branch') == BRANCH
        and run.get('path') == WORKFLOW and run.get('status') == 'in_progress' and run.get('conclusion') is None
        and run.get('repository',{}).get('id') == L.REPOSITORY_ID, 'current header producer')
    A.require(type(jobs.get('total_count')) is int and jobs['total_count'] == 1
        and type(jobs.get('jobs')) is list and len(jobs['jobs']) == 1, 'one header diagnostic job')
    job = jobs['jobs'][0]
    A.require(type(job.get('id')) is int and job['id'] > 0 and job.get('run_id') == run_id
        and type(job.get('run_attempt')) is int and job['run_attempt'] == 1 and job.get('head_sha') == source
        and job.get('name') == JOB_NAME and job.get('status') == 'in_progress' and job.get('conclusion') is None,
        'current header job identity')
    return dict(run_id=run_id, attempt=1, job_id=job['id'], source=source, branch=BRANCH, workflow=WORKFLOW)


def immutable_retention(pins, *, now=None):
    """Recheck source-owned expiries without extending the original cutoff."""
    A.require(type(pins) is list and len(pins) == 10
        and all(type(p) is dict and type(p.get('id')) is int for p in pins)
        and len({p['id'] for p in pins}) == 10, 'ten immutable expiry inputs')
    cutoff = min(W.strict_utc(L.ORIGINAL_CUTOFF), *(W.strict_utc(p.get('expires_at')) for p in pins))
    now = datetime.now(timezone.utc) if now is None else now
    A.require(isinstance(now, datetime) and now.tzinfo is not None and now < cutoff,
        'immutable original retention expired at finalization')
    return dict(checked_at=now.astimezone(timezone.utc).isoformat(), source_artifact_count=10,
        effective_earliest_expires_at=cutoff.strftime('%Y-%m-%dT%H:%M:%SZ'), original_retention_extended=False)


def execute():
    registration()  # First: no credential/path/resource/ZIP work while pending.
    resource.setrlimit(resource.RLIMIT_CPU, (1200,1200)); resource.setrlimit(resource.RLIMIT_AS, (2*1024**3,2*1024**3))
    overall = L.OverallClock(); root = None
    try:
        with L.hard_wall(3300):
            A.require(sys.platform == 'linux' and sys.version_info[:3] == (3,13,17), 'registered header Linux/Python')
            A.require(os.environ.get('GITHUB_REF') == 'refs/heads/'+BRANCH and os.environ.get('GITHUB_EVENT_NAME') == 'push'
                and os.environ.get('GITHUB_RUN_ATTEMPT') == '1' and os.environ.get('GITHUB_JOB') == 'headers',
                'closed first-attempt header context')
            source = os.environ.get('GITHUB_SHA',''); run_text = os.environ.get('GITHUB_RUN_ID','')
            A.require(len(source) == 40 and all(c in '0123456789abcdef' for c in source)
                and run_text.isascii() and run_text.isdecimal() and 0 < int(run_text), 'header source/run')
            run_id = int(run_text); control = Path(__file__).resolve().parents[1]; temporary = Path(os.environ['RUNNER_TEMP']).resolve()
            deployment = D.hosted_vm_precondition()
            A.require(os.environ.get('PYTHON_CPU_COUNT') == '1' and os.environ.get('PYTHONHASHSEED') == '0'
                and all(os.environ.get(k) == '1' for k in L.CAP_KEYS), 'header reader caps')
            available = sorted(os.sched_getaffinity(0)); A.require(available, 'reader CPU visibility')
            os.sched_setaffinity(0, {available[0]})
            runtime = dict(affinity=sorted(os.sched_getaffinity(0)), logical_cpu_count=1, caps={k:os.environ[k] for k in L.CAP_KEYS},
                cpu_limit_seconds=1200, address_space_bytes=2*1024**3)
            resources = A._resources(temporary, admission=True)
            sources_before = source_snapshot(control, overall)
            policy = A.parse_json(A.bounded_read(control/INPUT_FILE, A.MAX_METADATA_BYTES, overall), overall)
            public = A.parse_json(A.bounded_read(control/OLD_PUBLICATIONS, A.MAX_METADATA_BYTES, overall), overall)
            plan = build_plan(policy, public); admission = stage_admission(resources, plan['pins'])
            root = temporary/'wealth-four-checkpoint-headers'; A.require(len(str(root)) <= 128, 'bounded header output path')
            L.fresh_directory(root, overall); L.fresh_directory(root/'archives', overall); L.fresh_directory(root/'diagnostic', overall)
            output = L.Outputs(root/'diagnostic')
            output.save('pending.json', dict(header_observations_complete=False, physics_qualified=False,
                worlds_admitted=False, checkpoint_restore=False), overall)
            output.save('sources-before.json', sources_before, overall)
            transport = L.TransportBudget(overall); transport.floor_probe = lambda:A._resources(root)
            client = HeaderClient(os.environ.get('GH_TOKEN'), plan['pins'], transport, current_run_id=run_id)
            with L.hard_wall(1200):
                producer = current_producer(client, run_id, source)
                before = L.original_publication(client, public['artifacts']); output.save('origin-before.json', before, transport)
                downloads = {}
                for pin in plan['pins']:
                    url = W.API+'/actions/artifacts/'+str(pin.artifact_id)+'/zip'
                    with client.response(url, zip_input=True) as response:
                        with L.fresh_file(root/'archives'/(pin.world+'.zip'), transport) as stream:
                            downloads[pin.world] = stream_header_archive(response,pin,stream.write,transport.check)
                after = L.original_publication(client, public['artifacts']); after_producer = current_producer(client,run_id,source)
                A.require(A.json_bytes(before) == A.json_bytes(after) and A.json_bytes(producer) == A.json_bytes(after_producer),
                    'header input/current producer changed during transfer')
                output.save('origin-after-transfer.json', after, transport); transfer_clocks = transport.check()
            audit = L.AuditBudget(overall); audit.floor_probe = lambda:A._resources(root)
            reports = {}
            with L.hard_wall(1800):
                for pin in plan['pins']:
                    def emit(world,label,raw):
                        output.save(world+'-'+label+'-header.json',raw,audit,raw=True)
                    reports[pin.world] = inspect_bundle(root/'archives'/(pin.world+'.zip'),pin,plan['bundles'][pin.world],
                        plan['targets'][pin.world],audit,emit)
                    output.save(pin.world+'-headers.json',reports[pin.world],audit)
                sources_after = source_snapshot(control,audit)
                A.require(A.json_bytes(sources_before) == A.json_bytes(sources_after),'header source changed')
                output.save('sources-after.json',sources_after,audit)
                report = dict(schema_version=1, kind='four-original-checkpoint-header-observations',
                    status='pending_completed_diagnostic_producer_and_consumer_verification', header_observations_complete=True,
                    producer=producer, original_publication=after, deployment=deployment, initial_resources=resources,
                    new_volume_admission=admission, reader_runtime=runtime, downloads=downloads,
                    header_reports={world:{k:v for k,v in r.items() if k!='selected_headers'} for world,r in reports.items()},
                    selected_header_count=sum(len(r['selected_headers']) for r in reports.values()),
                    transfer_measured=transfer_clocks, selected_read_and_metadata_measured=audit.check(),
                    controller_wall_before_final_serialization=overall.check(),
                    measured_scope='Single process clocks; final serialization/upload excluded, hard deadlines cover final writes.',
                    all_old_A_W_authority_null=True, old_input_caps_unchanged=True, all_other_CP_payloads_unexpanded=True,
                    checkpoint_inner_sections_inflated=False, checkpoint_unpickled=False, checkpoint_restored=False,
                    native_or_World_executed=False, full_payload_or_physics_qualification=False,
                    original_current_identity_scope='Not independently serialized; last-valid captured header is an explicit comparison reference.')
                row = output.save('diagnostic.json',report,audit)
                retention_before_completion = immutable_retention(public['artifacts'])
                output.save('completion.json',dict(header_observations_complete=True, report=row, files=dict(output.rows),
                    total_bytes=output.total, completed_producer_required=True, physics_qualification=False,
                    retention_before_completion=retention_before_completion),audit)
                A.require(A.json_bytes(source_snapshot(control,audit)) == A.json_bytes(sources_after),'late header source drift')
                overall.check(); audit.check()
                retention_after_completion = immutable_retention(public['artifacts'])
                print(A.json_bytes(dict(status='HEADER_OBSERVATIONS_PENDING_COMPLETED_JOB',report_sha256=row['sha256'],
                    completion_sha256=output.rows['completion.json']['sha256'],
                    retention_after_completion=retention_after_completion,worlds=False)).decode(),end='')
                return 0
    except BaseException as exc:
        if root is not None:
            try:L.retain_failure(root,exc)
            except BaseException:pass
        print(A.json_bytes(dict(status='REFUSED',header_observations_complete=False,**L.safe_failure(exc),
            checkpoint_restore=False,worlds=False)).decode(),end='')
        return 1


def main(argv=None):
    registration()
    A.require((sys.argv[1:] if argv is None else argv) == ['--execute'], 'closed header diagnostic command')
    return execute()


if __name__ == '__main__':
    try:raise SystemExit(main())
    except A.AdmissionError:
        print(A.json_bytes(dict(status='PENDING_HEADER_REVIEW',archive_acquired=False,worlds=False)).decode(),end='')
        raise SystemExit(2)
