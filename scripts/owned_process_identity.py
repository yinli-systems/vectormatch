"""Bounded /proc identity observations; signal ownership still requires pidfd checks.

One directory descriptor binds reads to one process instance. A second stat read
detects an exit during cmdline sampling. A live process with unprovable arguments
is refused, never treated as absent. No command-line bytes enter error messages.
"""
import hashlib
import os
from pathlib import Path
import time


class IdentityReadError(RuntimeError):
    pass


def _read_at(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
    try:
        chunks = []
        count = 0
        while True:
            chunk = os.read(fd, min(8192, maximum + 1 - count))
            if not chunk:
                return b"".join(chunks)
            count += len(chunk)
            if count > maximum:
                raise IdentityReadError("bounded " + name + " read exceeded")
            chunks.append(chunk)
    finally:
        os.close(fd)


def _stat_identity(body, pid, phase):
    opening, closing = body.find(b"("), body.rfind(b")")
    fields = body[closing + 2:].split() if closing >= 0 else []
    try:
        valid = opening > 0 and closing > opening and len(fields) > 19
        valid = valid and int(body[:opening].strip()) == pid
        start = int(fields[19]) if valid else 0
        state = fields[0].decode("ascii") if valid else "?"
        valid = valid and start > 0 and len(state) == 1
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise IdentityReadError("Incomplete process identity pid=%d phase=%s stat" % (pid, phase))
    return state, start


def read_identity(pid, proc_root=Path("/proc")):
    """Return exact PID/start/argv observation, None only on proven exit/absence.

    Permission failures and malformed live identities propagate. Two 1ms retries
    handle a bounded exec/exit transition; they never authorize signaling a PID.
    """
    if type(pid) is not int or pid <= 0:
        raise ValueError("positive integer PID required")
    directory = None
    last = None
    try:
        directory = os.open(Path(proc_root) / str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        for attempt in range(3):
            first = _stat_identity(_read_at(directory, "stat", 65536), pid, "before")
            if first[0] in ("Z", "X", "x"):
                return None
            arguments = _read_at(directory, "cmdline", 262144)
            second = _stat_identity(_read_at(directory, "stat", 65536), pid, "after")
            if first[1] != second[1]:
                raise IdentityReadError("Process identity changed pid=%d startTicks=%d->%d" % (pid, first[1], second[1]))
            if second[0] in ("Z", "X", "x"):
                return None
            if arguments.endswith(b"\0") and arguments.split(b"\0", 1)[0]:
                return dict(pid=pid, startTicks=first[1], commandSha256=hashlib.sha256(arguments).hexdigest(),
                            arguments=[os.fsdecode(value) for value in arguments[:-1].split(b"\0")])
            last = (first[0], second[0], first[1], len(arguments))
            if attempt < 2:
                time.sleep(0.001)
        raise IdentityReadError("Incomplete process identity pid=%d phase=cmdline state=%s/%s startTicks=%d argvBytes=%d" %
                                (pid, last[0], last[1], last[2], last[3]))
    except (FileNotFoundError, ProcessLookupError):
        return None
    except IdentityReadError as error:
        if "pid=" in str(error):
            raise
        raise IdentityReadError("Incomplete process identity pid=%d: %s" % (pid, error)) from error
    finally:
        if directory is not None:
            os.close(directory)
