#!/usr/bin/env python3
"""Hold one repository launcher lock across exec and its supervised descendants."""
import fcntl
import os
from pathlib import Path
import stat
import sys


def validate(fd, path):
    """An inherited descriptor must reference the expected file and own its flock."""
    actual, expected = os.fstat(fd), os.stat(path)
    if not stat.S_ISREG(actual.st_mode) or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
        raise RuntimeError("Launcher inherited the wrong lock descriptor")
    # flock is associated with the shared open-file description, so this succeeds for
    # our inherited descriptor and fails if another description owns the lock.
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--validate":
        validate(int(sys.argv[2]), sys.argv[3])
        return
    if len(sys.argv) >= 4 and sys.argv[1] == "--without-lock":
        # Persistent infrastructure/daemons must not retain the foreground launcher's lock.
        os.close(int(sys.argv[2]))
        os.execvpe(sys.argv[3], sys.argv[3:], os.environ.copy())
    if len(sys.argv) < 3:
        raise RuntimeError("Usage: launcher-lock.py <lock-file> <command> [args...]")
    path = Path(sys.argv[1]).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        validate(fd, path)
    except BlockingIOError:
        os.close(fd)
        print("Another replicated launcher or supervised service still holds this repository's lock. "
              "Stop the existing services before restarting; no drivers were touched.", file=sys.stderr)
        sys.exit(75)
    os.ftruncate(fd, 0)
    os.write(fd, (str(os.getpid()) + "\n").encode())
    os.set_inheritable(fd, True)
    env = os.environ.copy()
    env["VM_REPLICATED_LOCK_PID"] = str(os.getpid())
    env["VM_REPLICATED_LOCK_FD"] = str(fd)
    # Never unlink the lock file: replacing its inode would allow parallel owners.
    os.execvpe(sys.argv[2], sys.argv[2:], env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print("Launcher lock failed: " + str(error), file=sys.stderr)
        sys.exit(1)
