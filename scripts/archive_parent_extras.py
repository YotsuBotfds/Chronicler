"""Copy one finalized parent's nonvalidation JSON into verified lossless gzip.

Source files are never written, removed, renamed, or restored in place.
Archive and restore destinations must both be fresh external directories.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import uuid
import zlib

KIND = 'chronicler-parent-extra-archive'
FIXED = {'state.json', 'state.historiography.json', 'state.languages.json'}
BLOCK = 1 << 20
MAX_SELECTED_BYTES = 64 << 20
MAX_PARENT_BYTES = 512 << 20
MAX_PARENT_FILES = 10_000
MAX_PARENT_ENTRIES = 12_000
MAX_SELECTED_FILES = 256
MIN_FREE_BYTES = 3 << 30
HEX = re.compile(r'[0-9a-f]{64}\Z')


def now():
    return datetime.now(timezone.utc).isoformat()


def relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/'))
            or PurePosixPath(name).as_posix() != name):
        raise ValueError('paths must be canonical relative POSIX file paths')
    return name


def eligible(name):
    return ('/' not in relative(name) and
            (name in FIXED or (name.startswith('memories_') and name.endswith('.json'))))


def location(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('parent traversal is unsupported')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'symlink path or parent is unsupported: {part}')
    if path.resolve(strict=False) != path:
        raise ValueError(f'path alias is unsupported: {path}')
    return path


def canonical(path):
    path = location(path)
    path.resolve(strict=True)
    return path


def regular(path):
    path = canonical(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(f'require a regular file without hardlink aliases: {path}')
    return path


def sha(path, max_bytes=MAX_PARENT_BYTES):
    path = regular(path)
    before = path.stat()
    if before.st_size > max_bytes:
        raise ValueError('file hash byte bound exceeded')
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        while block := stream.read(min(BLOCK, before.st_size - total + 1)):
            total += len(block)
            if total > before.st_size:
                raise ValueError('source grew beyond file hash byte bound')
            digest.update(block)
    after = regular(path).stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if total != before.st_size or any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError('file changed while hashing')
    return digest.hexdigest()


def snapshot(path):
    path = regular(path)
    before = path.stat()
    digest = sha(path)
    after = regular(path).stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise ValueError(f'source changed while reading: {path}')
    return {'sha256': digest, 'bytes': before.st_size, 'mode': stat.S_IMODE(before.st_mode),
            'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns,
            'device': before.st_dev, 'inode': before.st_ino}


def strict_json(path, max_bytes=32 << 20):
    path = regular(path)
    if path.stat().st_size > max_bytes:
        raise ValueError('JSON input exceeds byte bound')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON object key')
            result[key] = value
        return result
    with path.open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('JSON input grew beyond byte bound')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def sync_dir(path):
    # Windows does not expose directory fsync through this portable API.
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def status(output, value):
    temporary = output / f'.status-{uuid.uuid4().hex}.tmp'
    write_new(temporary, value)
    os.replace(temporary, output / 'status.json')
    sync_dir(output)


def new_destination(path, forbidden):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise FileExistsError(f'fresh destination required: {path}')
    parent = canonical(path.parent)
    if not parent.is_dir() or '..' in path.parts:
        raise ValueError('destination requires an existing canonical directory parent')
    for root in forbidden:
        root = location(root)
        if path == root or path.is_relative_to(root) or root.is_relative_to(path):
            raise ValueError('destination must be outside source and archive evidence')
    return path


def space(path, additional=0):
    if shutil.disk_usage(path).free < MIN_FREE_BYTES + additional:
        raise ValueError('3 GiB free-space reserve would be crossed')


def inventory(parent):
    parent = canonical(parent)
    rows, paths = {}, []
    total = 0
    entries = 0
    pending = [parent]
    while pending:
        with os.scandir(canonical(pending.pop())) as children:
            for child in children:
                entries += 1
                if entries > MAX_PARENT_ENTRIES:
                    raise ValueError('parent inventory exceeds fixed entry bound')
                path = Path(child.path)
                info = child.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    paths.append(path)
                    total += info.st_size
                    if len(paths) > MAX_PARENT_FILES or total > MAX_PARENT_BYTES:
                        raise ValueError('parent inventory exceeds fixed file/byte bound')
                else:
                    raise ValueError('parent contains a symlink or special file')
    for path in sorted(paths):
        row = snapshot(path)
        name = relative(path.relative_to(parent).as_posix())
        rows[name] = row
    return rows


def manifest_parent(batch, seed, expected):
    batch = canonical(batch)
    path = batch / 'batch_manifest.json'
    if type(seed) is not int or not isinstance(expected, str) or not HEX.fullmatch(expected):
        raise ValueError('explicit integer seed and manifest SHA-256 required')
    if regular(path).stat().st_size > 32 << 20 or sha(path) != expected:
        raise ValueError('explicit manifest SHA-256 does not match')
    manifest = strict_json(path)
    if (not isinstance(manifest, dict) or manifest.get('kind') != 'chronicler-batch'
            or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
            or manifest.get('status') != 'complete' or not isinstance(manifest.get('completed_at'), str)
            or not manifest['completed_at']):
        raise ValueError('batch manifest is not finalized complete schema1')
    turns = manifest.get('turns')
    runs, seeds = manifest.get('runs'), manifest.get('seeds')
    if (type(turns) is not int or turns <= 0 or not isinstance(runs, list) or not runs
            or not isinstance(seeds, list) or any(type(value) is not int for value in seeds)
            or len(set(seeds)) != len(seeds) or len(runs) != len(seeds)
            or not isinstance(manifest.get('source'), dict) or not manifest['source']
            or not isinstance(manifest.get('native'), dict) or not manifest['native']):
        raise ValueError('incomplete manifest cohort or identity anchors')
    found = []
    selected = None
    for run in runs:
        if not isinstance(run, dict) or type(run.get('seed')) is not int:
            raise ValueError('invalid run')
        value = run['seed']
        directory = f'seed_{value}'
        files = run.get('files')
        if (run.get('dir') != directory or run.get('bundle') != f'{directory}/chronicle_bundle.json'
                or type(run.get('total_turns')) is not int or run['total_turns'] != turns
                or not isinstance(files, dict) or run['bundle'] not in files):
            raise ValueError('run is not finalized with exact requested horizon and bundle')
        for name, digest in files.items():
            if not relative(name).startswith(directory + '/') or not isinstance(digest, str) or not HEX.fullmatch(digest):
                raise ValueError('unsafe manifest input path or hash')
        found.append(value)
        if value == seed:
            selected = run
    if sorted(found) != sorted(seeds) or selected is None:
        raise ValueError('missing or duplicate requested seed')
    return batch, manifest, selected


def validation_inputs(batch, run):
    for name, expected in run['files'].items():
        if sha(batch / name) != expected:
            raise ValueError(f'manifest validation input changed: {name}')


def index_data(archive, expected):
    archive = canonical(archive)
    path = archive / 'index.json'
    if (not isinstance(expected, str) or not HEX.fullmatch(expected)
            or regular(path).stat().st_size > 32 << 20 or sha(path) != expected):
        raise ValueError('explicit index SHA-256 does not match')
    data = strict_json(path)
    if (not isinstance(data, dict) or data.get('kind') != KIND
            or type(data.get('version')) is not int or data['version'] != 1 or data.get('raw_deletion') is not False
            or not isinstance(data.get('files'), dict) or not data['files']
            or len(data['files']) > MAX_SELECTED_FILES
            or not isinstance(data.get('batch'), str) or not Path(data['batch']).is_absolute()):
        raise ValueError('unsupported or incomplete archive index')
    total = 0
    for name, row in data['files'].items():
        if (not eligible(name) or not isinstance(row, dict)
                or row.get('gzip') != f'gzip/{name}.gz'
                or type(row.get('bytes')) is not int or not 0 <= row['bytes'] <= MAX_SELECTED_BYTES
                or type(row.get('gzip_bytes')) is not int or not 0 < row['gzip_bytes'] <= MAX_SELECTED_BYTES + BLOCK
                or not isinstance(row.get('sha256'), str) or not HEX.fullmatch(row['sha256'])
                or not isinstance(row.get('gzip_sha256'), str) or not HEX.fullmatch(row['gzip_sha256'])):
            raise ValueError('unsafe archive file index or decompression bound')
        total += row['bytes']
    if total > MAX_SELECTED_BYTES:
        raise ValueError('archive raw byte total exceeds bound')
    return archive, data


def decode(path, row, output=None):
    # zlib exposes eof/unused_data: gzip.open silently accepts extra members.
    if regular(path).stat().st_size != row['gzip_bytes']:
        raise ValueError('compressed archive byte count changed')
    before = snapshot(path)
    if before['bytes'] != row['gzip_bytes'] or before['sha256'] != row['gzip_sha256']:
        raise ValueError('compressed archive bytes changed')
    decoder = zlib.decompressobj(31)
    digest = hashlib.sha256()
    total = 0
    compressed = 0
    with path.open('rb') as stream:
        while block := stream.read(min(BLOCK, row['gzip_bytes'] - compressed + 1)):
            compressed += len(block)
            if compressed > row['gzip_bytes']:
                raise ValueError('gzip compressed byte bound exceeded')
            pending = block
            while pending:
                decoded = decoder.decompress(pending, min(BLOCK, row['bytes'] - total + 1))
                total += len(decoded)
                if total > row['bytes'] or total > MAX_SELECTED_BYTES:
                    raise ValueError('gzip uncompressed byte bound exceeded')
                digest.update(decoded)
                if output is not None:
                    space(Path(output.name).parent, len(decoded) + BLOCK)
                    output.write(decoded)
                if decoder.unused_data:
                    raise ValueError('concatenated gzip members or trailing bytes are unsupported')
                pending = decoder.unconsumed_tail
    if compressed != row['gzip_bytes'] or not decoder.eof or total != row['bytes'] or digest.hexdigest() != row['sha256']:
        raise ValueError('truncated gzip or restored byte/hash mismatch')
    if snapshot(path) != before:
        raise ValueError('compressed input changed during decode')
    return {'bytes': total, 'sha256': digest.hexdigest()}


def verify(archive, expected):
    archive, data = index_data(archive, expected)
    observed = {name: decode(archive / row['gzip'], row) for name, row in data['files'].items()}
    if sha(archive / 'index.json') != expected:
        raise ValueError('index changed during verification')
    return {'kind': KIND + '-verification', 'passed': True, 'index_sha256': expected,
            'files': observed, 'raw_deletion': False}


def restore(archive, expected, output):
    archive, data = index_data(archive, expected)
    forbidden = [archive, Path(data['batch'])]
    output = new_destination(output, forbidden)
    space(output.parent, sum(row['bytes'] for row in data['files'].values()) + BLOCK)
    output.mkdir()
    sync_dir(output.parent)
    status(output, {'state': 'restoring', 'passed': False, 'index_sha256': expected, 'at': now()})
    try:
        observed = {}
        for name, row in sorted(data['files'].items()):
            with (output / name).open('xb') as stream:
                decode(archive / row['gzip'], row, stream)
                stream.flush()
                os.fsync(stream.fileno())
            observed[name] = {'bytes': (output / name).stat().st_size, 'sha256': sha(output / name)}
            if observed[name] != {'bytes': row['bytes'], 'sha256': row['sha256']}:
                raise ValueError('actual restored file differs')
        if sha(archive / 'index.json') != expected:
            raise ValueError('index changed during restore')
        result = {'kind': KIND + '-restore', 'passed': True, 'index_sha256': expected,
                  'files': observed, 'raw_deletion': False, 'completed_at': now()}
        write_new(output / 'restore-receipt.json', result)
        status(output, {'state': 'complete', 'passed': True, 'receipt_sha256': sha(output / 'restore-receipt.json')})
        return result
    except BaseException as error:
        status(output, {'state': 'failed_or_interrupted', 'passed': False, 'error': str(error), 'at': now()})
        raise


def archive_parent(batch, seed, expected, output, restore_output):
    batch, manifest, run = manifest_parent(batch, seed, expected)
    parent = canonical(batch / run['dir'])
    output = new_destination(output, [batch])
    restore_output = new_destination(restore_output, [batch])
    if output == restore_output or output.is_relative_to(restore_output) or restore_output.is_relative_to(output):
        raise ValueError('archive and restore destinations must be separate fresh siblings')
    before = inventory(parent)
    selected = sorted(name for name in before if '/' not in name and eligible(name))
    if not selected or not FIXED.issubset(selected) or len(selected) > MAX_SELECTED_FILES:
        raise ValueError('parent does not have the complete bounded state/memory selection')
    if any(f"{run['dir']}/{name}" in run['files'] for name in selected):
        raise ValueError('refuse to archive a manifest validation input')
    total = sum(before[name]['bytes'] for name in selected)
    if total > MAX_SELECTED_BYTES:
        raise ValueError('selected raw byte total exceeds bound')
    validation_inputs(batch, run)
    space(output.parent, 2 * total + BLOCK * 2)
    space(restore_output.parent, total + BLOCK)
    output.mkdir()
    (output / 'gzip').mkdir()
    sync_dir(output.parent)
    status(output, {'state': 'archiving', 'passed': False, 'manifest_sha256': expected, 'seed': seed, 'at': now()})
    try:
        files = {}
        for name in selected:
            source = parent / name
            target = output / 'gzip' / (name + '.gz')
            space(output, before[name]['bytes'] + BLOCK)
            with target.open('xb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=6, mtime=0) as encoded:
                    with regular(source).open('rb') as stream:
                        copied = 0
                        while block := stream.read(min(BLOCK, before[name]['bytes'] - copied + 1)):
                            copied += len(block)
                            if copied > before[name]['bytes']:
                                raise ValueError('source grew beyond its recorded byte bound')
                            space(output, len(block) + BLOCK)
                            encoded.write(block)
                        if copied != before[name]['bytes']:
                            raise ValueError('source shrank during compression')
                raw.flush()
                os.fsync(raw.fileno())
            if snapshot(source) != before[name]:
                raise ValueError('selected source changed during compression')
            files[name] = {**before[name], 'gzip': f'gzip/{name}.gz',
                           'gzip_bytes': target.stat().st_size, 'gzip_sha256': sha(target)}
        sync_dir(output / 'gzip')
        validation_inputs(batch, run)
        if inventory(parent) != before or sha(batch / 'batch_manifest.json') != expected:
            raise ValueError('parent or manifest changed during archive')
        index = {'kind': KIND, 'version': 1, 'batch': str(batch), 'seed': seed, 'run': run,
                 'manifest_sha256': expected, 'source': manifest['source'], 'native': manifest['native'],
                 'whole_parent_inventory': before, 'files': files, 'raw_deletion': False,
                 'gzip_policy': 'one member per file; gzip6; empty filename; mtime0; reject trailing bytes',
                 'metadata_policy': 'mode/mtime recorded only; restored bytes verified; ACL/ownership not restored'}
        write_new(output / 'index.json', index)
        index_hash = sha(output / 'index.json')
        restore(output, index_hash, restore_output)
        verify(output, index_hash)
        validation_inputs(batch, run)
        if inventory(parent) != before or sha(batch / 'batch_manifest.json') != expected:
            raise ValueError('parent or manifest changed during actual restore')
        result = {'kind': KIND + '-completion', 'passed': True, 'index_sha256': index_hash,
                  'manifest_sha256': expected, 'parent_unchanged': True, 'manifest_unchanged': True,
                  'raw_deletion': False,
                  'restore_output': str(restore_output), 'restore_receipt_sha256': sha(restore_output / 'restore-receipt.json'),
                  'raw_bytes': total, 'gzip_bytes': sum(row['gzip_bytes'] for row in files.values()),
                  'files': len(files), 'completed_at': now(), 'tool_sha256': sha(Path(__file__))}
        write_new(output / 'archive-receipt.json', result)
        status(output, {'state': 'complete', 'passed': True, 'receipt_sha256': sha(output / 'archive-receipt.json')})
        return result
    except BaseException as error:
        status(output, {'state': 'failed_or_interrupted', 'passed': False, 'error': str(error), 'at': now()})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    archive = modes.add_parser('archive')
    archive.add_argument('--batch', type=Path, required=True)
    archive.add_argument('--seed', type=int, required=True)
    archive.add_argument('--manifest-sha256', required=True)
    archive.add_argument('--output', type=Path, required=True)
    archive.add_argument('--restore-output', type=Path, required=True)
    for mode in ('restore', 'verify'):
        command = modes.add_parser(mode)
        command.add_argument('--archive', type=Path, required=True)
        command.add_argument('--index-sha256', required=True)
        if mode == 'restore':
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == 'archive':
        result = archive_parent(args.batch, args.seed, args.manifest_sha256, args.output, args.restore_output)
    elif args.mode == 'restore':
        result = restore(args.archive, args.index_sha256, args.output)
    else:
        result = verify(args.archive, args.index_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
