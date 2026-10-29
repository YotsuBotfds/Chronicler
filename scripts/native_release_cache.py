"""Dormant Cargo timestamp adapter; never a current build/wheel receipt.

No probes at import. Initial unsupported inputs use ordinary Cargo with no
timestamp writes. Failed prepared-source revalidation or a partial write is
fatal. Eligible ordinary paths retain Cargo/maturin/install/record-build.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import sysconfig
import tomllib

# Closed metadata/FS/probe bounds; existing CI/test caps are unchanged.
SCHEMA = 1
CONTEXT_VERSION = 1
MAX_JSON = 4 * 1024**2
MAX_SOURCE_FILES = 4096
MAX_SOURCE_BYTES = 32 * 1024**2
MAX_RELEASE_FILES = 32768
MAX_RELEASE_BYTES = 1024**3
MAX_CONTEXT_FILES = 16384
MAX_DIRECTORIES = 32768
MAX_CONTEXT_BYTES = 512 * 1024**2
MAX_FILE_BYTES = 128 * 1024**2
MAX_PATH_BYTES = 1024
MAX_PROBE_BYTES = 65536
PROBE_SECONDS = 20
RELEASE = 'chronicler-agents/target/release'
WHEELS = 'chronicler-agents/target/wheels'
MANIFEST = 'chronicler-agents/target/native-release-cache-v1.json'
BUILD_ARGV = ['python', '-m', 'maturin', 'build', '--release', '--locked']
FEATURES = ['pyo3/extension-module']
PUBLIC_ENV = ('RUSTC', 'RUSTUP_TOOLCHAIN', 'CARGO_HOME', 'RUSTUP_HOME',
              'CARGO_INCREMENTAL', 'CARGO_TERM_COLOR', 'PYTHONUNBUFFERED',
              'LD_LIBRARY_PATH', 'PKG_CONFIG_PATH', 'Python_ROOT_DIR',
              'Python2_ROOT_DIR', 'Python3_ROOT_DIR', 'pythonLocation')
# GCC backend search selectors are unsupported; inspect names, never values.
UNSUPPORTED_ENV = ('COMPILER_PATH', 'GCC_EXEC_PREFIX')
CREDENTIAL_NAME = re.compile(r'TOKEN|PASSWORD|SECRET|CREDENTIAL|AUTH|PROXY', re.I)
SEMANTIC_NAME = re.compile(r'^(CARGO|RUST|PYO3|MATURIN|CC|CXX|AR|LD|CFLAGS|CXXFLAGS|LDFLAGS|PKG_CONFIG|PYTHON|LIBRARY_PATH|CPATH|C_INCLUDE_PATH|CPLUS_INCLUDE_PATH)')
HEX = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')


class Unsupported(ValueError):
    """Ordinary-build path; no timestamp mutation has occurred."""


class TimestampFailure(RuntimeError):
    """Fatal negative; a write may have happened. Stop without retry."""


class SourceDrift(RuntimeError):
    """Fatal source change after preparation; no build or cache seal."""


def require(ok, message):
    if not ok:
        raise Unsupported(message)


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(len(raw) <= MAX_JSON, 'metadata bound')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse_json(raw):
    require(type(raw) is bytes and len(raw) <= MAX_JSON, 'metadata bound')
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate metadata key')
            result[k] = v
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Unsupported('nonfinite metadata')))
    except (ValueError, UnicodeError) as exc:
        raise Unsupported('invalid metadata') from exc


def path_name(name):
    require(type(name) is str and 0 < len(name.encode()) <= MAX_PATH_BYTES and
            '\\' not in name and '\x00' not in name and not name.startswith('/') and
            str(PurePosixPath(name)) == name and
            all(p not in ('', '.', '..') for p in name.split('/')), 'noncanonical path')
    return name


def public_environment(environment):
    """Read names first; credential values never enter context, even hashed."""
    require(type(environment) is dict, 'detached environment required')
    for name in environment:
        require(type(name) is str, 'environment name')
        require(name not in UNSUPPORTED_ENV, 'unsupported semantic environment')
        if CREDENTIAL_NAME.search(name):
            continue
        require(not SEMANTIC_NAME.match(name) or name in PUBLIC_ENV, 'unsupported semantic environment')
    result = {k: environment[k] for k in PUBLIC_ENV if k in environment}
    require(all(type(v) is str and len(v.encode()) <= MAX_PATH_BYTES and
                not any(c in v for c in '\r\n\x00') and '://' not in v and '@' not in v
                for v in result.values()), 'unsupported public environment')
    require(result.get('CARGO_INCREMENTAL', '0') == '0', 'incremental unsupported')
    return result


def stable_stat(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def content_rows(rows):
    return [{k: r[k] for k in ('path', 'mode', 'bytes', 'sha256')} for r in rows]


def validate_rows(rows, prefix, max_files, max_bytes, source=False):
    require(type(rows) is list and 0 < len(rows) <= max_files, 'inventory count')
    paths, total, groups = [], 0, {}
    for r in rows:
        require(type(r) is dict and set(r) == {'path', 'mode', 'bytes', 'sha256', 'mtime_ns', 'links', 'inode_group'}, 'inventory schema')
        name = path_name(r['path']); paths.append(name)
        require(name.startswith(prefix+'/') and name != MANIFEST, 'inventory scope')
        require(type(r['mode']) is int and r['mode'] in (0o644, 0o755) and
                (not source or r['mode'] == 0o644), 'source Git mode must be 100644; unsupported mode')
        require(type(r['bytes']) is int and 0 <= r['bytes'] <= MAX_FILE_BYTES, 'file bytes')
        require(type(r['sha256']) is str and HEX.fullmatch(r['sha256']), 'file hash')
        require(type(r['mtime_ns']) is int and 0 < r['mtime_ns'] < 2**63, 'timestamp')
        require(type(r['links']) is int and 0 < r['links'] <= max_files, 'link count')
        path_name(r['inode_group']); groups.setdefault(r['inode_group'], []).append(r)
        total += r['bytes']
    require(paths == sorted(set(paths)) and total <= max_bytes, 'inventory layout/bytes')
    for label, group in groups.items():
        require(label == group[0]['path'] and all(r['links'] == len(group) for r in group), 'outside inventory hardlink alias')
        require(all((r['sha256'], r['bytes'], r['mode'], r['mtime_ns']) ==
                    (group[0]['sha256'], group[0]['bytes'], group[0]['mode'], group[0]['mtime_ns'])
                    for r in group), 'hardlink facts')
    return rows


def validate_source(rows):
    return validate_rows(rows, 'chronicler-agents', MAX_SOURCE_FILES, MAX_SOURCE_BYTES, True)


class LocalFS:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)

    def physical(self, name):
        p = self.root
        for part in path_name(name).split('/'):
            p = p/part
            require(not p.is_symlink(), 'symlink unsupported')
        return p

    def read(self, name, limit=MAX_FILE_BYTES):
        p = self.physical(name); before = p.stat()
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'bounded regular file required')
        with p.open('rb') as stream:
            raw = stream.read(limit+1)
        require(len(raw) == before.st_size and len(raw) <= limit and stable_stat(p.stat()) == stable_stat(before), 'file read drift')
        return raw

    def named_rows(self, names, max_files, max_bytes):
        require(names == sorted(set(names)) and 0 < len(names) <= max_files, 'file layout')
        rows, total, groups = [], 0, {}
        for name in names:
            p = self.physical(name); before = p.stat(); raw = self.read(name)
            require(stable_stat(p.stat()) == stable_stat(before), 'stat drift')
            total += len(raw); require(total <= max_bytes, 'input byte bound')
            r = {'path': name, 'mode': stat.S_IMODE(before.st_mode), 'bytes': len(raw),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'mtime_ns': before.st_mtime_ns,
                 'links': before.st_nlink, 'inode_group': None}
            rows.append(r); groups.setdefault((before.st_dev, before.st_ino), []).append(r)
        for group in groups.values():
            require(all(r['links'] == len(group) for r in group), 'outside inventory hardlink alias')
            for r in group: r['inode_group'] = group[0]['path']
        return rows

    def rows(self, prefix, max_files, max_bytes):
        start = self.physical(prefix); require(start.is_dir(), 'missing directory')
        names = []; directory_count = 0
        for directory, dirs, files in os.walk(start, followlinks=False):
            directory_count += 1; require(directory_count <= MAX_DIRECTORIES, 'directory bound')
            require(not any((Path(directory)/d).is_symlink() for d in dirs), 'symlink directory')
            names.extend((Path(directory)/f).relative_to(self.root).as_posix() for f in files)
            require(len(names) <= max_files, 'file count bound')
        return self.named_rows(sorted(names), max_files, max_bytes)

    def set_mtime(self, name, stamp):
        p = self.physical(name); before = p.stat()
        os.utime(p, ns=(before.st_atime_ns, stamp), follow_symlinks=False)
        require(p.stat().st_mtime_ns == stamp, 'timestamp precision mismatch')

    def wheel_empty(self):
        p = self.physical(WHEELS)
        require(not p.exists() or (p.is_dir() and not any(p.iterdir())), 'fresh empty wheel output required')

    def write_exclusive(self, name, value):
        p = self.physical(name); p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as stream: stream.write(canonical(value))


class LocalTools:
    def run(self, argv):
        import resource
        import tempfile
        def limits():
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_PROBE_BYTES, MAX_PROBE_BYTES))
        with tempfile.TemporaryFile() as stream:
            proc = subprocess.Popen(argv, stdout=stream, stderr=stream, preexec_fn=limits)
            try: proc.wait(timeout=PROBE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(); raise Unsupported('probe timeout')
            require(proc.returncode == 0 and stream.tell() <= MAX_PROBE_BYTES, 'probe failed or oversized')
            stream.seek(0); return stream.read(MAX_PROBE_BYTES+1).decode().strip()


def source_snapshot(fs, tools):
    listing = tools.run(['git', '-C', str(fs.root), 'ls-tree', '-r', '--full-tree', 'HEAD', '--', 'chronicler-agents'])
    names = []; blobs = {}
    for line in listing.splitlines():
        head, name = line.split('\t', 1)
        require(head.split()[:2] == ['100644', 'blob'] and not name.startswith('chronicler-agents/target/'), 'unsupported tracked source')
        names.append(path_name(name)); blobs[name] = head.split()[2]
    names.sort(); rows = validate_source(fs.named_rows(names, MAX_SOURCE_FILES, MAX_SOURCE_BYTES))
    for name in names:
        raw = fs.read(name)
        require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest() == blobs[name], 'source differs from Git blob')
    actual = []; crate = fs.physical('chronicler-agents'); directory_count = 0
    for directory, dirs, files in os.walk(crate, followlinks=False):
        directory_count += 1; require(directory_count <= MAX_DIRECTORIES, 'source directory bound')
        if Path(directory) == crate: dirs[:] = [d for d in dirs if d != 'target']
        require(not any((Path(directory)/d).is_symlink() for d in dirs), 'source symlink')
        actual.extend((Path(directory)/f).relative_to(fs.root).as_posix() for f in files)
        require(len(actual) <= MAX_SOURCE_FILES, 'source count bound')
    require(sorted(actual) == names, 'extra/missing source input')
    config = tomllib.loads(fs.read('chronicler-agents/Cargo.toml').decode())
    require(not any(k in config for k in ('workspace', 'build-dependencies', 'patch', 'replace')), 'external Cargo topology')
    sections = [config] + list(config.get('target', {}).values())
    for section in sections:
        for key in ('dependencies', 'dev-dependencies', 'build-dependencies'):
            for entry in section.get(key, {}).values():
                require(not isinstance(entry, dict) or not any(k in entry for k in ('path', 'git', 'registry', 'workspace')), 'nonregistry dependency')
    return rows


def context_record(public, tools, fs):
    """Actual installed Linux context; unsupported file/tool layouts fall back."""
    import importlib.metadata
    import platform
    import shutil
    require(sys.platform == 'linux' and platform.python_implementation() == 'CPython', 'platform unsupported')
    for ancestor in [fs.root/'chronicler-agents', fs.root, *fs.root.parents]:
        if ancestor != fs.root/'chronicler-agents':
            require(not (ancestor/'Cargo.toml').exists() and not (ancestor/'Cargo.toml').is_symlink(), 'ancestor workspace unsupported')
        for name in ('.cargo/config', '.cargo/config.toml', 'rust-toolchain', 'rust-toolchain.toml'):
            require(not (ancestor/name).exists() and not (ancestor/name).is_symlink(), 'Cargo/toolchain config unsupported')
    cargo_home = Path(public.get('CARGO_HOME', str(Path.home()/'.cargo')))
    require(cargo_home.is_absolute(), 'Cargo home unsupported')
    require(not any((cargo_home/n).exists() for n in ('config', 'config.toml')), 'Cargo home config unsupported')
    paths = {}
    for name in ('rustc', 'cargo', 'cc', 'ld', 'ar', 'maturin', 'ldd'):
        p = shutil.which(name); require(p is not None, 'semantic tool missing')
        paths[name] = str(Path(p).resolve(strict=True))
    for name in ('rustc', 'cargo'): paths[name] = tools.run(['rustup', 'which', name])
    require('RUSTC' not in public or str(Path(public['RUSTC']).resolve(strict=True)) == paths['rustc'], 'custom Rust compiler unsupported')
    def file_pin(path):
        p = Path(path); require(p.is_absolute(), 'absolute context path required')
        return {'resolved_path': str(p), 'files': content_rows(LocalFS(p.parent).named_rows([p.name], 1, MAX_FILE_BYTES))}
    tool_pins = {name: file_pin(path) for name, path in sorted(paths.items())}
    # Pin the installed Python -m maturin distribution, not only its launcher.
    distribution = importlib.metadata.distribution('maturin')
    listed = distribution.files
    require(listed is not None and 0 < len(listed) <= MAX_CONTEXT_FILES, 'maturin layout unknown')
    prefix = Path(sys.prefix).resolve(strict=True)
    package_names = []
    for entry in listed:
        physical = Path(distribution.locate_file(entry)).resolve(strict=True)
        require(physical.is_relative_to(prefix), 'maturin input outside interpreter prefix')
        package_names.append(physical.relative_to(prefix).as_posix())
    maturin_files = content_rows(LocalFS(prefix).named_rows(sorted(set(package_names)), MAX_CONTEXT_FILES, MAX_CONTEXT_BYTES))
    # Resolve actual compiler link helpers/startup objects; unknown layouts deny.
    extra_tools = []
    for option in ('-print-prog-name=cc1', '-print-prog-name=collect2',
                   '-print-file-name=libgcc.a', '-print-file-name=libgcc_s.so.1',
                   '-print-file-name=crtbeginS.o', '-print-file-name=crtendS.o',
                   '-print-file-name=crti.o', '-print-file-name=crtn.o', '-print-file-name=libc.so'):
        extra_tools.append(tools.run([paths['cc'], option]))
    link_inputs = [file_pin(Path(p).resolve(strict=True)) for p in extra_tools if Path(p).is_absolute()]
    require(len(link_inputs) == len(extra_tools), 'compiler link-input layout unknown')
    # ldd is limited to actual installed executable/library files, never a wheel
    # or project output. Addresses/vdso are transient and are not semantic keys.
    runtime_paths = set()
    runtime_roots = [v for k, v in paths.items() if k != 'ldd'] + [str(Path(sys.executable).resolve(strict=True))]
    runtime_roots += extra_tools[:2]
    for path in runtime_roots:
        output = tools.run([paths['ldd'], path])
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('linux-vdso.so.'):
                continue
            match = re.fullmatch(r'(?:[^ ]+ => )?(/[^ ]+) \(0x[0-9a-f]+\)', line)
            require(match is not None, 'unknown linker runtime layout')
            runtime_paths.add(str(Path(match.group(1)).resolve(strict=True)))
            require(len(runtime_paths) <= MAX_CONTEXT_FILES, 'runtime file bound')
    runtime_files = [file_pin(p) for p in sorted(runtime_paths)]
    require(runtime_files, 'missing runtime closure')
    sysroot = Path(tools.run([paths['rustc'], '--print', 'sysroot']))
    require(sysroot.is_absolute(), 'sysroot unsupported')
    sysroot_rows = content_rows(LocalFS(sysroot).rows('lib', MAX_CONTEXT_FILES, MAX_CONTEXT_BYTES))
    include = Path(sysconfig.get_path('include')).resolve(strict=True)
    headers = content_rows(LocalFS(include.parent).rows(include.name, MAX_CONTEXT_FILES, MAX_CONTEXT_BYTES))
    library = Path(sysconfig.get_config_var('LIBDIR') or '')/str(sysconfig.get_config_var('LDLIBRARY') or '')
    require(library.is_file(), 'Python library unsupported')
    abi = {k: sysconfig.get_config_var(k) for k in ('SOABI', 'EXT_SUFFIX', 'MULTIARCH', 'Py_GIL_DISABLED', 'Py_DEBUG', 'ABIFLAGS', 'SIZEOF_VOID_P', 'HOST_GNU_TYPE', 'BUILD_GNU_TYPE', 'CC', 'LDSHARED')}
    require(abi['SIZEOF_VOID_P'] in (4, 8), 'pointer ABI unsupported')
    context = {'schema': CONTEXT_VERSION, 'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'workspace': str(fs.root), 'cargo_home': str(cargo_home), 'public_env': public,
               'argv': BUILD_ARGV, 'features': FEATURES, 'tools': tool_pins,
               'rustc': tools.run([paths['rustc'], '--version', '--verbose']),
               'cargo': tools.run([paths['cargo'], '--version', '--verbose']),
               'linker': tools.run([paths['ld'], '--version']), 'cc': tools.run([paths['cc'], '--version']),
               'sysroot_path': str(sysroot), 'sysroot_files': sysroot_rows,
               'maturin_version': distribution.version, 'maturin_prefix': str(prefix), 'maturin_files': maturin_files,
               'link_inputs': link_inputs, 'runtime_files': runtime_files, 'python': sys.version,
               'python_implementation': platform.python_implementation(),
               'python_executable': file_pin(Path(sys.executable).resolve(strict=True)),
               'python_library': file_pin(library.resolve(strict=True)), 'python_include': str(include),
               'headers': headers, 'abi': abi, 'platform': platform.platform(),
               'machine': platform.machine(), 'libc': list(platform.libc_ver()),
               'image_os': os.environ.get('ImageOS'), 'image_version': os.environ.get('ImageVersion')}
    validate_context(context); return context


def validate_context(context):
    keys = {'schema', 'helper_sha256', 'workspace', 'cargo_home', 'public_env', 'argv',
            'features', 'tools', 'rustc', 'cargo', 'linker', 'cc', 'sysroot_path',
            'sysroot_files', 'maturin_version', 'python', 'python_implementation',
            'python_executable', 'python_library', 'python_include', 'headers', 'abi',
            'platform', 'machine', 'libc', 'image_os', 'image_version', 'maturin_prefix',
            'maturin_files', 'link_inputs', 'runtime_files'}
    require(type(context) is dict and set(context) == keys and
            type(context['schema']) is int and context['schema'] == CONTEXT_VERSION,
            'closed context schema')
    require(type(context['helper_sha256']) is str and HEX.fullmatch(context['helper_sha256']), 'helper hash')
    require(context['argv'] == BUILD_ARGV and context['features'] == FEATURES and
            context['python_implementation'] == 'CPython', 'build context unsupported')
    require(public_environment(context['public_env']) == context['public_env'], 'public context')
    for key in ('workspace', 'cargo_home', 'sysroot_path', 'python_include', 'maturin_prefix'):
        require(type(context[key]) is str and Path(context[key]).is_absolute() and
                len(context[key].encode()) <= MAX_PATH_BYTES, 'context path')
    for key in ('rustc', 'cargo', 'linker', 'cc', 'maturin_version', 'python',
                'platform', 'machine', 'image_os', 'image_version'):
        require(type(context[key]) is str and 0 < len(context[key].encode()) <= MAX_PROBE_BYTES,
                'unknown tool/platform identity')
    require(type(context['libc']) is list and len(context['libc']) == 2 and
            all(type(v) is str and v for v in context['libc']), 'unknown libc')
    require(type(context['abi']) is dict and set(context['abi']) == {'SOABI', 'EXT_SUFFIX',
            'MULTIARCH', 'Py_GIL_DISABLED', 'Py_DEBUG', 'ABIFLAGS', 'SIZEOF_VOID_P',
            'HOST_GNU_TYPE', 'BUILD_GNU_TYPE', 'CC', 'LDSHARED'} and
            type(context['abi']['SIZEOF_VOID_P']) is int and context['abi']['SIZEOF_VOID_P'] in (4, 8), 'closed ABI context')
    for key in ('SOABI', 'EXT_SUFFIX', 'MULTIARCH', 'HOST_GNU_TYPE', 'BUILD_GNU_TYPE', 'CC', 'LDSHARED'):
        require(type(context['abi'][key]) is str and context['abi'][key], 'unknown ABI field')
    def files(rows):
        require(type(rows) is list and 0 < len(rows) <= MAX_CONTEXT_FILES, 'context file count')
        paths, total = [], 0
        for r in rows:
            require(type(r) is dict and set(r) == {'path', 'mode', 'bytes', 'sha256'}, 'context file schema')
            paths.append(path_name(r['path']))
            require(type(r['mode']) is int and r['mode'] in (0o644, 0o755) and
                    type(r['bytes']) is int and 0 <= r['bytes'] <= MAX_FILE_BYTES and
                    type(r['sha256']) is str and HEX.fullmatch(r['sha256']), 'context file facts')
            total += r['bytes']
        require(paths == sorted(set(paths)) and total <= MAX_CONTEXT_BYTES, 'context file closure')
    def pin(value):
        require(type(value) is dict and set(value) == {'resolved_path', 'files'} and
                type(value['resolved_path']) is str and Path(value['resolved_path']).is_absolute() and
                len(value['resolved_path'].encode()) <= MAX_PATH_BYTES, 'context tool path')
        files(value['files'])
    require(type(context['tools']) is dict and set(context['tools']) == {'rustc', 'cargo', 'cc', 'ld', 'ar', 'maturin', 'ldd'}, 'closed tools')
    for value in context['tools'].values(): pin(value)
    pin(context['python_executable']); pin(context['python_library'])
    files(context['sysroot_files']); files(context['headers']); files(context['maturin_files'])
    for key in ('link_inputs', 'runtime_files'):
        require(type(context[key]) is list and 0 < len(context[key]) <= MAX_CONTEXT_FILES, 'runtime/link closure count')
        for value in context[key]: pin(value)
    canonical(context)
    return context


def cache_key(source, context):
    validate_source(source)
    validate_context(context)
    return 'cargo-release-v1-'+digest(content_rows(source))+'-'+digest(context)


def chronology(source, release):
    markers = [r['mtime_ns'] for r in release if re.fullmatch(re.escape(RELEASE)+r'/\.fingerprint/chronicler-agents-[0-9a-f]+/invoked.timestamp', r['path'])]
    require(markers and max(r['mtime_ns'] for r in source) <= min(markers), 'source/build chronology unsupported')


def seal_manifest(prepared, source, release, producer):
    require(content_rows(validate_source(source)) == content_rows(validate_source(prepared['source'])), 'source drift')
    validate_rows(release, RELEASE, MAX_RELEASE_FILES, MAX_RELEASE_BYTES); chronology(source, release)
    require(type(producer) is dict and set(producer) == {'source_commit', 'run_id', 'attempt', 'build_record_sha256', 'wheel_sha256'} and
            type(producer['source_commit']) is str and COMMIT.fullmatch(producer['source_commit']) and
            all(type(producer[k]) is int and producer[k] > 0 for k in ('run_id', 'attempt')) and
            all(type(producer[k]) is str and HEX.fullmatch(producer[k]) for k in ('build_record_sha256', 'wheel_sha256')), 'producer authority')
    result = {'schema': SCHEMA, 'key': prepared['key'], 'context': prepared['context'], 'source': source, 'release': release, 'producer': producer}
    require(result['key'] == cache_key(source, result['context']), 'producer key mismatch')
    canonical(result); return result


def admission_plan(prepared, manifest, source, release, *, primary_key, matched_key, exact_hit):
    require(prepared.get('fresh_wheel_output_checked') is True, 'fresh wheel precondition')
    require(exact_hit is True and primary_key == matched_key == prepared['key'], 'exact primary hit required')
    require(type(manifest) is dict and set(manifest) == {'schema', 'key', 'context', 'source', 'release', 'producer'} and type(manifest['schema']) is int and manifest['schema'] == SCHEMA, 'manifest schema')
    require(seal_manifest(prepared, manifest['source'], manifest['release'], manifest['producer']) == manifest and manifest['context'] == prepared['context'], 'context/key mismatch')
    require(content_rows(validate_source(source)) == content_rows(manifest['source']), 'current source differs')
    validate_rows(release, RELEASE, MAX_RELEASE_FILES, MAX_RELEASE_BYTES)
    require(release == manifest['release'], 'release inventory/timestamps differ')
    return [(r['path'], r['mtime_ns']) for r in manifest['source']]


def assert_source(actual, expected):
    if content_rows(actual) != content_rows(expected): raise SourceDrift('source content/modes changed; stop')


def prepared_source_snapshot(fs, tools, expected):
    """After prepared-source validation, inability to revalidate is fatal.

    Snapshot acquisition itself can refuse changed bytes, modes or layout before
    it returns rows. Do not let that refusal reach the ordinary-build handler.
    BaseException interruptions also escape rather than selecting a fallback.
    """
    try:
        actual = source_snapshot(fs, tools)
        assert_source(actual, expected)
    except SourceDrift:
        raise
    except Exception as exc:
        raise SourceDrift('prepared source could not be revalidated; stop') from exc
    return actual


def apply_plan(fs, plan, expected, snapshot):
    assert_source(snapshot(), expected)
    try:
        for name, stamp in plan: fs.set_mtime(name, stamp)
        after = snapshot(); assert_source(after, expected)
        require([(r['path'], r['mtime_ns']) for r in after] == plan, 'timestamp postcheck')
    except Exception as exc:
        raise TimestampFailure('timestamp application failed; stop without retry') from exc


def prepare(fs, tools, environment, context_provider=context_record):
    public = public_environment(environment); source = source_snapshot(fs, tools)
    context = context_provider(public, tools, fs); fs.wheel_empty()
    commit = tools.run(['git', '-C', str(fs.root), 'rev-parse', 'HEAD'])
    require(COMMIT.fullmatch(commit), 'current commit')
    return {'schema': SCHEMA, 'source_commit': commit, 'source': source, 'context': context,
            'key': cache_key(source, context), 'fresh_wheel_output_checked': True}


def read_metadata(path):
    path = Path(path)
    require(not path.is_symlink(), 'metadata symlink')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_JSON, 'metadata bound')
    with path.open('rb') as stream: raw = stream.read(MAX_JSON+1)
    require(len(raw) == before.st_size and stable_stat(path.stat()) == stable_stat(before), 'metadata read drift')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'admit', 'seal'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--matched-key', default='')
    parser.add_argument('--exact-hit', default='false')
    parser.add_argument('--build-record', type=Path)
    args = parser.parse_args(argv); fs, tools = LocalFS(args.root), LocalTools()
    try:
        if args.command == 'prepare':
            value = prepare(fs, tools, dict(os.environ))
            with args.prepared.open('xb') as stream: stream.write(canonical(value))
            result = {'state': 'PREPARED', 'key': value['key']}
        else:
            value = parse_json(read_metadata(args.prepared))
            require(type(value) is dict and set(value) == {'schema', 'source_commit', 'source', 'context', 'key', 'fresh_wheel_output_checked'} and type(value['schema']) is int and value['schema'] == SCHEMA, 'prepared schema')
            require(value.get('fresh_wheel_output_checked') is True, 'fresh wheel precondition')
            expected = validate_source(value['source'])
            source = prepared_source_snapshot(fs, tools, expected)
            require(context_record(public_environment(dict(os.environ)), tools, fs) == value['context'], 'current semantic context differs')
            if args.command == 'admit':
                fs.wheel_empty(); manifest = parse_json(fs.read(MANIFEST, MAX_JSON))
                release = fs.rows(RELEASE, MAX_RELEASE_FILES, MAX_RELEASE_BYTES)
                plan = admission_plan(value, manifest, source, release, primary_key=value['key'], matched_key=args.matched_key, exact_hit=args.exact_hit == 'true')
                apply_plan(fs, plan, manifest['source'],
                           lambda: prepared_source_snapshot(fs, tools, expected))
                result = {'state': 'TIMESTAMPS_RESTORED', 'key': value['key'], 'count': len(plan)}
            else:
                require(args.build_record is not None, 'current build record required')
                require(args.build_record.resolve() == fs.root/'ci-native-wheel/build.json', 'build record path')
                raw = read_metadata(args.build_record); build = parse_json(raw)
                identity = build['identity']; wheel = identity['wheel']['wheel']
                require(build['kind'] == 'native-shard-current-build-v1' and identity['source_commit'] == value['source_commit'], 'current source authority')
                require(identity['run_id'] == int(os.environ['GITHUB_RUN_ID']) and identity['attempt'] == int(os.environ['GITHUB_RUN_ATTEMPT']), 'current run authority')
                wheels = list(fs.physical(WHEELS).iterdir()); require(len(wheels) == 1 and wheels[0].name == wheel['filename'], 'one current wheel required')
                wheel_raw = fs.read(WHEELS+'/'+wheel['filename'])
                require(len(wheel_raw) == wheel['bytes'] and hashlib.sha256(wheel_raw).hexdigest() == wheel['sha256'], 'current wheel bytes')
                release = fs.rows(RELEASE, MAX_RELEASE_FILES, MAX_RELEASE_BYTES)
                manifest = seal_manifest(value, source, release, {'source_commit': identity['source_commit'], 'run_id': identity['run_id'], 'attempt': identity['attempt'], 'build_record_sha256': hashlib.sha256(raw).hexdigest(), 'wheel_sha256': wheel['sha256']})
                require(not fs.physical(MANIFEST).exists(), 'existing manifest retained')
                fs.write_exclusive(MANIFEST, manifest); result = {'state': 'SEALED', 'key': value['key']}
    except (Unsupported, OSError, KeyError, TypeError, ValueError, UnicodeError) as exc:
        result = {'state': 'ORDINARY_BUILD', 'reason': type(exc).__name__}
    # Prepared-source acquisition/assertion failures and timestamp failures escape
    # nonzero before result/output writes; ordinary rejection remains pre-write.
    with args.output.open('xb') as stream: stream.write(canonical(result))
    if args.github_output:
        with args.github_output.open('a') as stream:
            stream.write('eligible='+('true' if result['state'] in ('PREPARED', 'SEALED') else 'false')+'\n')
            if 'key' in result: stream.write('key='+result['key']+'\n')
    return result


if __name__ == '__main__':
    main()
