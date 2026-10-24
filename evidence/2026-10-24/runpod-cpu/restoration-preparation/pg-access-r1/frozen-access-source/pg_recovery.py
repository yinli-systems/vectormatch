#!/usr/bin/env python3
"""Fixed original PG clone access preparation only. Default is read-only preflight.

Never downloads, initializes, migrates SQL, sets ACLs, signals a process, or starts a server.
Linux x86_64 / Python3.8. Only preflight, dedicated account provisioning and exact PGDATA ownership are allowed.
"""
import argparse
import datetime
import grp
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import socket
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASELINE = HERE / 'expected-baseline.json'
BASELINE_SHA = '7a517d88b2759c1379f61b2f210176d96d67d4375848561fe948a09c90b5bff5'
HOST = 'ed6c0673f5cb'
PGDATA = Path('/opt/vectormatch-cpu/restorations/original-native-r1/node2/runtime/postgres18')
BINROOT = Path('/opt/vectormatch-cpu/preparation/pg18-loader-probe-r1/binaries')
CONTROL_TOOL = Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r3/install/bin/pg_controldata')
CONTROL_TOOL_SHA = '0b9c8705202342b508bbe3944f151338a11cfa2ca4f62c1e014de5f0a5ecf26b'
JOB = Path('/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1')
ACCOUNT = 'vectormatch-pg'
UID = GID = 963
PORT = 15432
MIN_FREE = 2 * 1024**3



def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def save_new(path, data):
    with Path(path).open('x') as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def ancestors(path):
    return list(reversed(Path(path).parents)) + [Path(path)]


def no_symlink(path):
    for p in ancestors(path):
        require(not p.is_symlink(), 'Symlink in fixed ancestor: ' + str(p))


def load_baseline():
    require(sha(BASELINE) == BASELINE_SHA, 'Baseline SHA mismatch')
    d = json.loads(BASELINE.read_text())
    require(d['pgData'] == str(PGDATA) and d['binaryRoot'] == str(BINROOT), 'Fixed path mismatch')
    require(d['pgFilesCount'] == 990 and len(d['pgFiles']) == 990, 'Wrong original PG inventory')
    return d


def scan_tree(root):
    no_symlink(root)
    require(root.is_dir(), 'Fixed root missing: ' + str(root))
    files, dirs = {}, set([''])
    for current, names, leaves in os.walk(str(root), followlinks=False):
        for name in names:
            p = Path(current) / name
            require(not p.is_symlink() and p.is_dir(), 'Non-directory/symlink in PG tree')
            dirs.add(str(p.relative_to(root)))
        for name in leaves:
            p = Path(current) / name
            st = p.lstat()
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'Non-regular/hardlinked PG file: ' + str(p))
            files[str(p.relative_to(root))] = p
    return files, dirs


def verify_pg(d, expected_owner=None):
    files, dirs = scan_tree(PGDATA)
    require(set(files) == set(d['pgFiles']), 'PG file inventory differs; no recovery or ownership change')
    require(dirs == {x['path'] for x in d['pgDirectories']}, 'PG directory inventory differs')
    count = total = 0
    metadata = []
    expected_modes = {x['path']: x['mode'] for x in d['pgDirectories']}
    for n in sorted(dirs):
        p = PGDATA / n
        st = p.stat()
        require(stat.S_IMODE(st.st_mode) == expected_modes[n], 'PG directory mode differs: ' + n)
        if expected_owner is not None:
            require((st.st_uid, st.st_gid) == expected_owner, 'PG directory owner differs: ' + n)
        metadata.append((n, st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid))
    for n, p in sorted(files.items()):
        e, st = d['pgFiles'][n], p.stat()
        require(st.st_size == e['bytes'] and stat.S_IMODE(st.st_mode) == e['mode'] and sha(p) == e['sha256'],
                'PG byte/size/mode baseline differs: ' + n)
        if expected_owner is not None:
            require((st.st_uid, st.st_gid) == expected_owner, 'PG file owner differs: ' + n)
        metadata.append((n, st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid))
        count += 1
        total += st.st_size
    return {'passed': True, 'files': count, 'logicalBytes': total,
            'metadataSha256': hashlib.sha256(json.dumps(metadata, separators=(',', ':')).encode()).hexdigest(),
            'scope': 'Fresh full-file readback before server start; root source backups unchanged.'}


def verify_binaries(d):
    no_symlink(BINROOT)
    expected = {e['path']: e for e in d['binaryEntries']}
    actual = set(str(p.relative_to(BINROOT)) for p in BINROOT.rglob('*'))
    # Tar has no explicit bin directory entry; extraction creates this parent.
    implicit = set()
    for n in expected:
        implicit.update(str(p) for p in Path(n).parents if str(p) != '.')
    require(actual == set(expected) | implicit, 'Original binary tree inventory differs')
    for n, e in expected.items():
        p = BINROOT / n
        st = p.lstat()
        if e['type'] == 'file':
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size == e['bytes']
                    and stat.S_IMODE(st.st_mode) == int(e['mode'], 8) and sha(p) == e['sha256'],
                    'Original binary bytes/mode differ: ' + n)
        elif e['type'] == 'directory':
            require(stat.S_ISDIR(st.st_mode), 'Binary directory differs: ' + n)
        elif e['type'] == 'symlink':
            require(stat.S_ISLNK(st.st_mode) and os.readlink(str(p)) == e['target']
                    and p.resolve() == BINROOT / e['resolvedRelativePath'], 'Binary symlink differs: ' + n)
        else:
            raise RuntimeError('Unexpected manifest entry type')
    require(sha(CONTROL_TOOL) == CONTROL_TOOL_SHA, 'Control tool SHA mismatch')
    return {'passed': True, 'manifestEntries': len(expected), 'postgresSha256': sha(BINROOT / 'bin/postgres'),
            'pgConfigDescribes': 'SEPARATE_R3_TOOL_BUILD_NOT_THIS_ORIGINAL_SERVER'}


def process_identity(pid):
    try:
        base = Path('/proc') / str(pid)
        text = (base / 'stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        raw = (base / 'cmdline').read_bytes()
        require(raw.endswith(b'\0'), 'Incomplete proc cmdline')
        return {'pid': pid, 'startTicks': int(fields[19]), 'commandSha256': hashlib.sha256(raw).hexdigest(),
                'arguments': [os.fsdecode(x) for x in raw[:-1].split(b'\0')]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def idle_check():
    found = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            raw = (p / 'cmdline').read_bytes()
            if not raw:
                continue
            args = [os.fsdecode(x) for x in raw.split(b'\0') if x]
            executable = Path(args[0]).name
            # Inspect arguments, not shell/controller source text.
            is_pg = executable in ('postgres', 'postmaster')
            is_vm_java = executable == 'java' and any('io.vectormatch.' in a for a in args)
            if is_pg or is_vm_java:
                found.append(process_identity(int(p.name)))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    require(not found, 'Postgres/VectorMatch workload still active: ' + json.dumps(found))
    return {'noPostgresOrVectorMatchJava': True, 'scope': 'Fresh /proc observation; not a global workload lock.'}


def port_check():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # No REUSEADDR/REUSEPORT: refuse any current listener/conflict.
        s.bind(('127.0.0.1', PORT))
    return {'port': PORT, 'loopbackFreshBindPassed': True, 'reservationHeld': False}


def account_plan():
    by_name = by_uid = group_name = group_gid = None
    try:
        by_name = pwd.getpwnam(ACCOUNT)
    except KeyError:
        pass
    try:
        by_uid = pwd.getpwuid(UID)
    except KeyError:
        pass
    try:
        group_name = grp.getgrnam(ACCOUNT)
    except KeyError:
        pass
    try:
        group_gid = grp.getgrgid(GID)
    except KeyError:
        pass
    if by_name is None:
        require(by_uid is None and group_name is None and group_gid is None,
                'Dedicated UID/GID/name collision; no account creation')
        return {'exists': False, 'name': ACCOUNT, 'uid': UID, 'gid': GID,
                'creationCommands': [['/usr/sbin/groupadd', '--system', '--gid', str(GID), ACCOUNT],
                    ['/usr/sbin/useradd', '--system', '--uid', str(UID), '--gid', str(GID), '--no-create-home',
                     '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', ACCOUNT]]}
    require(by_name.pw_uid == UID and by_name.pw_gid == GID and by_name.pw_dir == '/nonexistent'
            and by_name.pw_shell == '/usr/sbin/nologin' and by_uid == by_name
            and group_name is not None and group_gid == group_name and group_name.gr_gid == GID
            and group_name.gr_mem == [], 'Existing account is not exact registered dedicated identity')
    return {'exists': True, 'name': ACCOUNT, 'uid': UID, 'gid': GID}


def uid_not_in_use():
    used = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            lines = (p / 'status').read_text().splitlines()
            uid = next(x for x in lines if x.startswith('Uid:')).split()[1:]
            gid = next(x for x in lines if x.startswith('Gid:')).split()[1:]
            groups = next(x for x in lines if x.startswith('Groups:')).split()[1:]
            if str(UID) in uid or str(GID) in gid + groups:
                used.append(int(p.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    require(not used, 'Dedicated numeric UID/GID already used by processes: ' + json.dumps(used))
    return {'uid': UID, 'gid': GID, 'freshProcIdentityScanUnused': True}


def access_paths(d):
    requested = {}
    protected = sorted(set(ancestors(PGDATA)[:-1] + ancestors(BINROOT)), key=str)
    for p in protected:
        require(p.stat().st_uid == 0, 'Registered parent/binary prefix must remain root-owned: ' + str(p))
        requested[str(p)] = os.X_OK
    for e in d['binaryEntries']:
        p = BINROOT / e['path']
        requested[str(p)] = os.X_OK if e['type'] == 'directory' else os.R_OK
    requested[str(BINROOT / 'bin/postgres')] = os.R_OK | os.X_OK
    # Root can inspect an unprovisioned numeric identity safely. No account or ACL mutation.
    r, w = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            os.close(r)
            os.setgroups([])
            os.setgid(GID)
            os.setuid(UID)
            bad = [{'path': p, 'requiredAccessMask': mask} for p, mask in sorted(requested.items()) if not os.access(p, mask)]
            writable = [str(p) for p in protected if os.access(str(p), os.W_OK)]
            out = json.dumps({'uid': os.getuid(), 'gid': os.getgid(), 'blocked': bad, 'writableProtectedAncestors': writable}).encode()
            with os.fdopen(w, 'wb') as stream:
                stream.write(out)
            os._exit(0)
        except BaseException:
            os._exit(2)
    os.close(w)
    with os.fdopen(r, 'rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    _, status = os.waitpid(child, 0)
    require(status == 0 and len(raw) <= 1024 * 1024, 'Dedicated access observation failed')
    result = json.loads(raw)
    result['allRequiredParentsAndBinaryResourcesAccessible'] = not result['blocked'] and not result['writableProtectedAncestors']
    result['doesNotCheckPGDATAOwnershipYet'] = True
    return result


def control_readback():
    critical = ['PG_VERSION', 'global/pg_control']
    before = {n: sha(PGDATA / n) for n in critical}
    r = subprocess.run([str(CONTROL_TOOL), str(PGDATA)], env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'},
                       capture_output=True, text=True, timeout=15)
    after = {n: sha(PGDATA / n) for n in critical}
    fields = dict((k.strip(), v.strip()) for k, sep, v in (line.partition(':') for line in r.stdout.splitlines()) if sep)
    require(r.returncode == 0 and r.stderr == '' and before == after
            and fields.get('Database cluster state') == 'shut down'
            and fields.get('Database system identifier') == '7699920832388303129'
            and fields.get('pg_control version number') == '1800', 'Stopped clean original control identity not verified')
    return {'fields': fields, 'criticalBeforeSha256': before, 'criticalAfterSha256': after, 'stderr': r.stderr,
            'readOnly': True, 'postgresStarted': False}


def host_check(require_free=True):
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64' and platform.node() == HOST,
            'Wrong fixed Linux CPU host')
    require(os.geteuid() == 0, 'Root controller required solely for dedicated UID and controlled lifecycle')
    for p in (PGDATA, BINROOT, JOB.parent, CONTROL_TOOL):
        no_symlink(p)
    if require_free:
        require(shutil.disk_usage(PGDATA).free >= MIN_FREE, 'Less than 2GiB free; do not start recovery')


def preflight(require_access=False, expected_owner=None):
    host_check()
    d = load_baseline()
    result = {'timeUtc': now(), 'host': HOST, 'scope': 'Original-clone functional read-only SQL preparation; no performance claim',
              'idle': idle_check(), 'port': port_check(), 'account': account_plan(), 'pg': verify_pg(d, expected_owner),
              'binaries': verify_binaries(d), 'control': control_readback(), 'access': access_paths(d),
              'freeBytes': shutil.disk_usage(PGDATA).free, 'serverStarted': False, 'aclModified': False}
    result['numericIdentity'] = uid_not_in_use()
    if require_access:
        require(result['access']['allRequiredParentsAndBinaryResourcesAccessible'],
                'Dedicated UID access blocked or protected ancestor writable: ' + json.dumps(result['access']))
    return result


def job_privacy():
    st = JOB.stat()
    require(st.st_uid == 0 and st.st_gid == 0 and stat.S_IMODE(st.st_mode) in (0o700, 0o710), 'Unsafe controller directory')
    if stat.S_IMODE(st.st_mode) == 0o710:
        r = subprocess.run(['/usr/bin/getfacl', '-c', '-p', '-n', str(JOB)], capture_output=True, text=True, timeout=5)
        lines = set(x.strip() for x in r.stdout.splitlines() if x.strip())
        require(r.returncode == 0 and lines == {'user::rwx', 'user:963:--x', 'group::---', 'mask::--x', 'other::---'},
                'JOB ACL must grant only exact dedicated UID execute traversal')


def phase(name, action):
    host_check()
    if not JOB.exists():
        JOB.mkdir(mode=0o700)
    no_symlink(JOB)
    job_privacy()
    intent = JOB / (name + '-intent.json')
    save_new(intent, {'phase': name, 'startedAtUtc': now(), 'noRetry': True, 'controllerSha256': sha(Path(__file__))})
    try:
        result = action()
        save_new(JOB / (name + '-result.json'), result)
        return result
    except BaseException as error:
        save_new(JOB / (name + '-failure.json'), {'failedAtUtc': now(), 'errorType': type(error).__name__,
                                                'error': str(error), 'retryAllowed': False})
        raise


def provision():
    # Account provisioning does not require pre-existing PG ancestor ACLs.
    baseline = preflight()
    account = baseline['account']
    commands = []
    if not account['exists']:
        for args in account['creationCommands']:
            uid_not_in_use()
            r = subprocess.run(args, capture_output=True, text=True, timeout=20, env={'PATH': '/usr/sbin:/usr/bin:/bin'})
            commands.append({'arguments': args, 'exitCode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
            require(r.returncode == 0, 'Account phase failed; retain partial state and do not retry')
    return {'account': account_plan(), 'commands': commands, 'databaseDataOrPermissionsChanged': False}


def chown_pgdata():
    before = preflight(require_access=True, expected_owner=(0, 0))
    require(before['account']['exists'], 'Dedicated account not provisioned')
    d = load_baseline()
    files, dirs = scan_tree(PGDATA)
    idle_check()
    targets = ownership_targets(files, dirs)
    for p in targets:
        st = p.lstat()
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if stat.S_ISDIR(st.st_mode):
            flags |= os.O_DIRECTORY
        fd = os.open(str(p), flags)
        try:
            got = os.fstat(fd)
            require((got.st_dev, got.st_ino, got.st_uid, got.st_gid) == (st.st_dev, st.st_ino, 0, 0),
                    'PG entry changed during bounded ownership migration')
            os.fchown(fd, UID, GID)
        finally:
            os.close(fd)
    after = verify_pg(d, (UID, GID))
    return {'before': before, 'after': after, 'onlyOwnershipChangedWithinExactPGDATA': True,
            'ancestorOwnershipOrModeChanged': False, 'postgresStarted': False, 'entriesChowned': len(targets)}


def ownership_targets(files, dirs):
    require(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in list(files) + list(dirs)),
            'Ownership target escaped fixed PGDATA')
    result = [PGDATA / n for n in sorted(files)] + [PGDATA / n for n in sorted(dirs, key=lambda n: (-len(Path(n).parts), n))]
    require(result and result[-1] == PGDATA, 'PGDATA root must be the last ownership target')
    require(all(p == PGDATA or PGDATA in p.parents for p in result), 'Ownership target escaped fixed PGDATA')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='preflight', choices=['preflight', 'provision-user', 'chown'])
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.action == 'preflight':
        require(not args.execute, 'Preflight is always read-only; omit --execute')
        result = preflight()
    else:
        require(args.execute, 'Mutation requires explicit --execute; no action taken')
        action = {'provision-user': provision, 'chown': chown_pgdata}[args.action]
        result = phase(args.action, action)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
