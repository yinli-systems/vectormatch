"""Write 4 KiB at an advancing offset and force it, like an append-only log; report force latency percentiles."""
import os, sys, time
path, n = sys.argv[1], int(sys.argv[2])
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
buf = b'\x5a' * 4096
for name, force in (('fdatasync', os.fdatasync), ('fsync', os.fsync)):
    lat = []
    for i in range(n):
        os.pwrite(fd, buf, (len(lat) + (0 if name == 'fdatasync' else n)) * 4096)
        t = time.perf_counter_ns(); force(fd); lat.append(time.perf_counter_ns() - t)
    lat.sort(); q = lambda p: lat[min(n - 1, int(p * n))] / 1000
    print('FS %s n=%d p50=%.1fus p99=%.1fus p999=%.1fus max=%.1fus' % (name, n, q(.5), q(.99), q(.999), lat[-1] / 1000))
os.close(fd); os.unlink(path)
