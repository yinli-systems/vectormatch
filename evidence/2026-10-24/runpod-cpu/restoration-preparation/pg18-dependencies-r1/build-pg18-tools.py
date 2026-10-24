#!/usr/bin/env python3
"""Draft by default. Build only two PG18 tools on an idle Linux CPU host."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import struct
import subprocess
import tarfile
import time

VERSION = '18.6'
SOURCE_SHA256 = '555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f'
SOURCE_ROOT = 'postgresql-18.6'
WORK_BASE = Path('/opt/vectormatch-cpu/tool-builds')
SAFE_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
MIN_FREE = 3 * 1024 ** 3
MAX_MEMBERS = 10000
MAX_BYTES = 256 * 1024 ** 2
MAX_MEMBER_BYTES = 32 * 1024 ** 2
CONFIGURE_FLAGS = [
    '--without-readline', '--without-zlib', '--without-icu', '--without-ssl',
    '--without-perl', '--without-python', '--without-tcl', '--without-llvm',
    '--without-lz4', '--without-zstd', '--disable-nls',
    '--with-blocksize=8', '--with-wal-blocksize=8', '--with-segsize=1',
]
FORMAT_MACROS = {
    'PG_VERSION': '"18.6"', 'PG_VERSION_NUM': '180006',
    'BLCKSZ': '8192', 'XLOG_BLCKSZ': '8192', 'RELSEG_SIZE': '131072',
    'SIZEOF_VOID_P': '8', 'MAXIMUM_ALIGNOF': '8',
}
BENCHMARK_MARKERS = [b'io.vectormatch.', b'org.openjdk.jmh.']
CANCEL_SIGNAL = None


class BuildCancelled(RuntimeError):
    pass


def request_cancel(signum, frame):
    global CANCEL_SIGNAL
    CANCEL_SIGNAL = signum


def check_cancelled():
    if CANCEL_SIGNAL is not None:
        raise BuildCancelled('build cancellation signal ' + str(CANCEL_SIGNAL))


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def create_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def validate_work_dir(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('work directory must be an absolute confined path')
    if path.parent != WORK_BASE or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}', path.name):
        raise ValueError('work directory must be one new child of ' + str(WORK_BASE))
    for ancestor in [path] + list(path.parents):
        if ancestor.is_symlink():
            raise ValueError('symlink work-directory ancestor')
    if path.exists():
        raise ValueError('work directory already exists; no automatic retry or deletion')
    return path


def plan(source, work):
    source = Path(source).absolute()
    work = validate_work_dir(work)
    if not source.is_file() or source.is_symlink() or digest(source) != SOURCE_SHA256:
        raise ValueError('official 18.6 source SHA mismatch')
    return {
        'schemaVersion': 1, 'sourceVersion': VERSION, 'source': str(source),
        'sourceSha256': SOURCE_SHA256, 'sourceBytes': source.stat().st_size,
        'workDir': str(work), 'jobs': 2, 'minimumFreeBytes': MIN_FREE,
        'configureArgv': [str(work / 'source' / SOURCE_ROOT / 'configure'),
                          '--prefix=' + str(work / 'install')] + CONFIGURE_FLAGS,
        'makeTargets': [['make', '-j2', '-C', 'src/bin/pg_controldata', 'all'],
                        ['make', '-j2', '-C', 'src/bin/pg_config', 'all']],
        'formatMacrosRequired': FORMAT_MACROS, 'pgControlVersionRequired': 1800,
        'intendedOutputPrograms': ['pg_controldata', 'pg_config'],
        'doesNotDescribeOriginalZonkyBuild': True,
        'noDatabaseDataArgument': True, 'noServerOrInitdbTarget': True,
        'networkOrPackageInstallCommands': [], 'scriptSha256': digest(Path(__file__)),
    }


def validate_members(members):
    if len(members) > MAX_MEMBERS:
        raise ValueError('source archive member bound')
    entries = {}
    total = 0
    for member in members:
        raw = member.name
        path = PurePosixPath(raw)
        if ('\x00' in raw or '\\' in raw or path.is_absolute() or '..' in path.parts
                or not path.parts or path.parts[0] != SOURCE_ROOT):
            raise ValueError('unsafe source member path')
        name = str(path)
        if name in entries or not (member.isfile() or member.isdir()):
            raise ValueError('duplicate, link, or special source member')
        if member.mode & 0o7000 or member.size < 0 or member.size > MAX_MEMBER_BYTES:
            raise ValueError('source mode or size bound')
        if member.isfile():
            total += member.size
        if total > MAX_BYTES:
            raise ValueError('source total size bound')
        entries[name] = member
    for name in entries:
        for parent in PurePosixPath(name).parents:
            if str(parent) in entries and not entries[str(parent)].isdir():
                raise ValueError('non-directory source ancestor')
    return entries, total


def unpack_source(source, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError('source extraction target must be new')
    with tarfile.open(source, 'r:bz2') as archive:
        entries, total = validate_members(archive.getmembers())
        destination.mkdir(mode=0o755)
        dirs = set()
        for name, member in entries.items():
            if member.isdir():
                dirs.add(name)
            dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != '.')
        for name in sorted(dirs, key=lambda n: (len(PurePosixPath(n).parts), n)):
            (destination / name).mkdir(mode=0o755)
        for name, member in entries.items():
            if not member.isfile():
                continue
            target = destination / name
            if any(p.is_symlink() for p in target.parents):
                raise ValueError('symlink extraction ancestor')
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o755 if member.mode & 0o111 else 0o644)
            payload = archive.extractfile(member)
            if payload is None:
                os.close(fd)
                raise ValueError('missing source payload')
            with os.fdopen(fd, 'wb') as output, payload:
                shutil.copyfileobj(payload, output, length=1024 * 1024)
            if target.stat().st_size != member.size:
                raise ValueError('source extraction size mismatch')
    return {'members': len(entries), 'regularFileBytes': total}


def verify_format(header):
    found = dict(re.findall(r'^#define\s+(\w+)\s+([^\r\n]+)$', header, re.MULTILINE))
    for name, required in FORMAT_MACROS.items():
        if found.get(name, '').strip() != required:
            raise ValueError('unexpected generated data-format macro ' + name)
    return {name: found[name].strip() for name in FORMAT_MACROS}


def verify_versions(versions):
    requirements = [('make', r'GNU Make (\d+(?:\.\d+)+)', (3, 81)),
                    ('bison', r'bison[^\r\n]*? (\d+(?:\.\d+)+)', (2, 3)),
                    ('perl', r'v(\d+(?:\.\d+)+)', (5, 14))]
    parsed = {}
    for name, expression, minimum in requirements:
        found = re.search(expression, versions[name], re.IGNORECASE)
        if not found:
            raise ValueError('unrecognized ' + name + ' version')
        value = tuple(int(part) for part in found.group(1).split('.'))
        if value < minimum:
            raise ValueError('build dependency below minimum: ' + name)
        parsed[name] = list(value)
    if not re.search(r'flex\s+\d', versions['flex']):
        raise ValueError('Flex, rather than another lex, is required')
    return parsed


def verify_tool_version(name, output):
    expected = 'PostgreSQL 18.6' if name == 'pg_config' else 'pg_controldata (PostgreSQL) 18.6'
    if name not in ('pg_config', 'pg_controldata') or output.strip() != expected:
        raise ValueError('built tool version mismatch')


def benchmark_processes(proc_root=Path('/proc')):
    matches = []
    for candidate in proc_root.iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            command = (candidate / 'cmdline').read_bytes()
        except FileNotFoundError:
            continue
        # Fail closed on other read failures. Never print full arguments or environments.
        markers = [s.decode('ascii') for s in BENCHMARK_MARKERS if s in command]
        if markers:
            matches.append({'pid': int(candidate.name), 'markers': markers})
    return matches


def filesystem_type(path):
    best = ('', None)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        mountpoint = left.split()[4].replace('\\040', ' ')
        if os.path.commonpath([str(path), mountpoint]) == mountpoint and len(mountpoint) > len(best[0]):
            best = (mountpoint, right.split()[0])
    return best[1]


def group_members(group_id):
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        except FileNotFoundError:
            continue
        if int(fields[2]) == group_id:
            rows.append({'pid': int(path.name), 'startTicks': int(fields[19])})
    return rows


def run_step(name, argv, cwd, env, logs, records, timeout):
    check_cancelled()
    log = logs / (name + '.log')
    record = {'name': name, 'argv': argv, 'cwd': str(cwd), 'startedAtUtc': utc(),
              'timeoutSeconds': timeout, 'log': str(log), 'newProcessSession': True}
    with log.open('xb') as output:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        record['pid'] = process.pid
        problem = None
        try:
            deadline = time.monotonic() + timeout
            while True:
                check_cancelled()
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout)
                try:
                    record['exitCode'] = process.wait(timeout=min(1, remaining_time))
                    check_cancelled()
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException as error:
            problem = error
            record['timedOut'] = isinstance(error, subprocess.TimeoutExpired)
            record['interrupted'] = isinstance(error, (BuildCancelled, KeyboardInterrupt))
            # This single-threaded parent has not reaped its child: the PID/session
            # anchor cannot be reused before this owned process-group signal.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    record['ownedProcessGroupKillSent'] = True
                except ProcessLookupError:
                    record['ownedProcessGroupAlreadyAbsent'] = True
                try:
                    record['exitCode'] = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    record['exitCode'] = None
            else:
                record['exitCode'] = process.returncode
        end = time.monotonic() + 3
        remaining = group_members(process.pid)
        while remaining and time.monotonic() < end:
            time.sleep(0.05)
            remaining = group_members(process.pid)
        record['remainingProcessGroupMembers'] = remaining
    record.update(completedAtUtc=utc(), logSha256=digest(log))
    records.append(record)
    if problem is not None or record['exitCode'] != 0 or remaining:
        raise RuntimeError('bounded command failed or cleanup unproven: ' + name)
    return log.read_text(errors='replace')


def execute(build_plan, confirmed):
    if not confirmed:
        raise ValueError('explicit benchmark-idle confirmation required')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('native build requires Linux x86_64')
    work = validate_work_dir(build_plan['workDir'])
    anchor = WORK_BASE if WORK_BASE.exists() else WORK_BASE.parent
    if not anchor.is_dir() or filesystem_type(anchor) != 'overlay':
        raise ValueError('build location must be the declared local overlay, not FUSE')
    if shutil.disk_usage(anchor).free < MIN_FREE:
        raise ValueError('less than 3 GiB free before tool build')
    active = benchmark_processes()
    if active:
        raise ValueError('benchmark JVM present: ' + json.dumps(active))
    tools = {name: shutil.which(name, path=SAFE_PATH) for name in ['cc', 'make', 'perl', 'bison', 'flex']}
    if any(value is None for value in tools.values()):
        raise ValueError('missing build dependencies; no installation attempted: ' + json.dumps(tools))
    if digest(build_plan['source']) != SOURCE_SHA256:
        raise ValueError('source changed before execution')
    WORK_BASE.mkdir(exist_ok=True)
    work.mkdir(mode=0o755)
    logs = work / 'logs'; logs.mkdir()
    create_json(work / 'BUILD_PLAN.json', dict(build_plan, startedAtUtc=utc()))
    records = []
    result = {'passed': False, 'commands': records, 'sourceSha256': SOURCE_SHA256,
              'pgConfigDescribes': 'THIS_TOOL_BUILD_ONLY_NOT_ORIGINAL_ZONKY_SERVER',
              'databaseDataTouched': False, 'postgresOrInitdbBuiltOrStarted': False}
    env = {'PATH': SAFE_PATH, 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
           'CC': tools['cc'], 'CFLAGS': '-O2', 'PERL': tools['perl'],
           'BISON': tools['bison'], 'FLEX': tools['flex']}
    try:
        versions = {}
        for name, argv in [('cc', [tools['cc'], '--version']), ('make', [tools['make'], '--version']),
                           ('bison', [tools['bison'], '--version']), ('flex', [tools['flex'], '--version']),
                           ('perl', [tools['perl'], '-e', 'print "$^V\\n";'])]:
            versions[name] = run_step('version-' + name, argv, work, env, logs, records, 10)
        result['parsedToolVersions'] = verify_versions(versions)
        result['tools'] = {name: {'path': value, 'sha256': digest(value)} for name, value in tools.items()}
        result['toolVersions'] = versions
        result['extraction'] = unpack_source(Path(build_plan['source']), work / 'source')
        check_cancelled()
        source = work / 'source' / SOURCE_ROOT
        if 'AC_INIT([PostgreSQL], [18.6],' not in (source / 'configure.ac').read_text():
            raise ValueError('source version mismatch')
        control = (source / 'src/include/catalog/pg_control.h').read_text()
        if not re.search(r'^#define\s+PG_CONTROL_VERSION\s+1800\s*$', control, re.MULTILINE):
            raise ValueError('PG18 control format mismatch')
        if shutil.disk_usage(work).free < MIN_FREE:
            raise ValueError('less than 3 GiB free after source extraction')
        build = work / 'build'; build.mkdir()
        run_step('configure', build_plan['configureArgv'], build, env, logs, records, 180)
        header = build / 'src/include/pg_config.h'
        result['formatMacros'] = verify_format(header.read_text())
        result['pgConfigHeaderSha256'] = digest(header)
        result['pgControlHeaderSha256'] = digest(source / 'src/include/catalog/pg_control.h')
        for name in ['pg_controldata', 'pg_config']:
            if benchmark_processes():
                raise ValueError('benchmark JVM appeared before compilation')
            run_step('make-' + name, [tools['make'], '-j2', '-C', 'src/bin/' + name, 'all'],
                     build, env, logs, records, 600)
        forbidden = [build / 'src/backend/postgres', build / 'src/bin/initdb/initdb',
                     build / 'src/bin/pg_ctl/pg_ctl']
        if any(p.exists() for p in forbidden):
            raise ValueError('unexpected server or initialization executable')
        bindir = work / 'install/bin'; bindir.mkdir(parents=True)
        result['outputs'] = {}
        for name in ['pg_controldata', 'pg_config']:
            binary = build / 'src/bin' / name / name
            with binary.open('rb') as stream:
                ident = stream.read(20)
            if len(ident) != 20 or ident[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', ident, 18)[0] != 62:
                raise ValueError('output is not native Linux x86_64 ELF')
            installed = bindir / name
            shutil.copy2(binary, installed)
            result['outputs'][name] = {'path': str(installed), 'bytes': installed.stat().st_size,
                                       'sha256': digest(installed)}
            version = run_step('output-version-' + name, [str(installed), '--version'],
                               build, env, logs, records, 10)
            verify_tool_version(name, version)
        result['thisToolBuildConfigure'] = run_step('output-this-tool-configure',
            [str(bindir / 'pg_config'), '--configure'], build, env, logs, records, 10)
        result['passed'] = True
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        result['completedAtUtc'] = utc()
        result['freeBytesAfter'] = shutil.disk_usage(work).free
        create_json(work / 'BUILD_RESULT.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--benchmark-idle-confirmed', action='store_true')
    args = parser.parse_args()
    build_plan = plan(args.source, args.work_dir)
    if args.execute:
        previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
        try:
            for signum in previous:
                signal.signal(signum, request_cancel)
            print(json.dumps(execute(build_plan, args.benchmark_idle_confirmed), indent=2))
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    else:
        print(json.dumps(dict(build_plan, draftOnly=True, executed=False), indent=2))


if __name__ == '__main__':
    main()
