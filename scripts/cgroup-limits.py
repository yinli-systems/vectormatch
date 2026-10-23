#!/usr/bin/env python3
"""Resolve the process cgroup and report every ancestor visible through its mounts.

Visible bounds are upper bounds, not a guarantee of dedicated CPU/RAM. A container
namespace or delegated mount can hide stricter ancestors outside this process's view.
"""
from pathlib import Path, PurePosixPath
import re


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def memberships(text):
    result = []
    for line in (text or "").splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3 or not parts[2].startswith("/"):
            continue
        result.append({"version": 2 if not parts[1] else 1,
                       "controllers": parts[1].split(",") if parts[1] else [],
                       "path": unescape(parts[2])})
    return result


def mounts(text):
    result = []
    for line in (text or "").splitlines():
        before, separator, after = line.partition(" - ")
        left, right = before.split(), after.split()
        if not separator or len(left) < 6 or len(right) < 3 or right[0] not in ("cgroup", "cgroup2"):
            continue
        result.append({"version": 2 if right[0] == "cgroup2" else 1,
                       "root": unescape(left[3]), "mountPoint": unescape(left[4]),
                       "controllers": right[2].split(",") if right[0] == "cgroup" else []})
    return result


def cpu_set(value):
    if not value:
        return None
    cpus = set()
    try:
        for group in value.split(","):
            ends = group.split("-")
            low, high = int(ends[0]), int(ends[-1])
            if len(ends) > 2 or low < 0 or high < low or high > 1_048_576:
                return None
            cpus.update(range(low, high + 1))
        return cpus
    except ValueError:
        return None


def positive(value):
    try:
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def nonnegative(value):
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def collect(cgroup_text=None, mountinfo_text=None, reader=read, affinity=None):
    if cgroup_text is None:
        cgroup_text = reader("/proc/self/cgroup")
    if mountinfo_text is None:
        mountinfo_text = reader("/proc/self/mountinfo")
    groups, available_mounts = memberships(cgroup_text), mounts(mountinfo_text)
    hierarchy_reports, unresolved, quotas, memories, cpusets = [], [], [], [], []
    for group in groups:
        candidates = []
        member = PurePosixPath(group["path"])
        for mount in available_mounts:
            if mount["version"] != group["version"]:
                continue
            if group["version"] == 1 and not set(group["controllers"]) & set(mount["controllers"]):
                continue
            root = PurePosixPath(mount["root"])
            try:
                relative = member.relative_to(root)
            except ValueError:
                continue
            if ".." in relative.parts:
                continue
            candidates.append((len(root.parts), mount, relative))
        if not candidates:
            unresolved.append({**group, "reason": "No visible cgroup mount maps this membership path; effective limits are unknown"})
            continue
        # Prefer the least-delegated view so that the most ancestors can be inspected.
        _, mount, relative = min(candidates, key=lambda candidate: candidate[0])
        mountpoint = Path(mount["mountPoint"])
        current = mountpoint / str(relative)
        process_directory = current
        rows = []
        if group["version"] == 2:
            files = ("cpu.max", "cpu.stat", "cpuset.cpus.effective", "cpuset.cpus",
                     "memory.max", "memory.current", "cgroup.controllers")
        else:
            controller_set = set(group["controllers"])
            files = []
            if "cpu" in controller_set:
                files += ["cpu.cfs_quota_us", "cpu.cfs_period_us", "cpu.stat"]
            if "memory" in controller_set:
                files += ["memory.limit_in_bytes", "memory.usage_in_bytes"]
            if "cpuset" in controller_set:
                files += ["cpuset.effective_cpus", "cpuset.cpus"]
        while True:
            values = {filename: reader(str(current / filename)) for filename in files}
            rows.append({"directory": str(current), "values": values,
                         "unavailableFiles": [key for key, value in values.items() if value is None]})
            if group["version"] == 2:
                maximum = (values.get("cpu.max") or "").split()
                if len(maximum) == 2:
                    quota, period = positive(maximum[0]), positive(maximum[1])
                    if quota is not None and period is not None:
                        quotas.append(quota / period)
                memory = nonnegative(values.get("memory.max"))
                selected = values.get("cpuset.cpus.effective") or values.get("cpuset.cpus")
            else:
                quota, period = positive(values.get("cpu.cfs_quota_us")), positive(values.get("cpu.cfs_period_us"))
                if quota is not None and period is not None:
                    quotas.append(quota / period)
                memory = nonnegative(values.get("memory.limit_in_bytes"))
                # Linux v1 uses a page-aligned LONG_MAX as its unlimited memory sentinel.
                if memory is not None and memory >= (1 << 63) - (1 << 20):
                    memory = None
                selected = values.get("cpuset.effective_cpus") or values.get("cpuset.cpus")
            if memory is not None:
                memories.append(memory)
            cpus = cpu_set(selected)
            if cpus is not None:
                cpusets.append(cpus)
            if current == mountpoint:
                break
            current = current.parent
        hierarchy_reports.append({**group, "mountRoot": mount["root"], "mountPoint": str(mountpoint),
                                  "processDirectory": str(process_directory), "ancestors": rows,
                                  "ancestorsOutsideMountNotVisible": mount["root"] != "/"})
    allowed = set(affinity) if affinity is not None else None
    for cpus in cpusets:
        allowed = cpus if allowed is None else allowed & cpus
    bounds = ([float(len(allowed))] if allowed is not None else []) + quotas
    return {
        "available": bool(groups and available_mounts),
        "hierarchies": hierarchy_reports, "unresolved": unresolved,
        "visibleCpuQuotaUpperBound": min(quotas) if quotas else None,
        "affinityAndVisibleCpusetCpuIds": sorted(allowed) if allowed is not None else None,
        "visibleCpuUpperBound": min(bounds) if bounds else None,
        "visibleMemoryUpperBoundBytes": min(memories) if memories else None,
        "scope": "Current process cgroups and all ancestors visible within resolved mounts. "
                 "Null means no finite readable visible limit, not proof of unlimited capacity. "
                 "Hidden namespace/host ancestors may impose stricter constraints; these are upper bounds, not dedicated resources.",
    }
