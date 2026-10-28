import importlib.util
import io
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "pod-autopilot" / "pin_threads.py"
SPEC = importlib.util.spec_from_file_location("pin_threads", SOURCE)
pin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pin)

CASE = "ab-b1"
NODE_CPUS = [67, 71, 163, 167]
SOURCE_CPUS = [78, 95, 174, 191]
HOUSEKEEPING = [191]
CONFIG = {"cpuSets": [NODE_CPUS, [15, 31, 111, 127], [22, 61, 118, 157], SOURCE_CPUS], "housekeeping": HOUSEKEEPING}
NODE_CMD = "java -Xlog:gc:file=/x/experiments/%s/node0-g0/gc.log io.vectormatch.cluster.ReplicatedPathProbeNode MATCHING" % CASE
SOURCE_CMD = "java -Xlog:gc:file=/x/experiments/%s/node3-g0/gc.log io.vectormatch.cluster.ReplicatedPathProbe /x/evidence" % CASE


class FakeProc:
    """A /proc tree with comm, cmdline and task/<tid>/comm files."""

    def __init__(self, root):
        self.root = Path(root)

    def process(self, pid, cmdline, threads, comm="java"):
        d = self.root / str(pid)
        (d / "task").mkdir(parents=True, exist_ok=True)
        (d / "comm").write_text(comm + "\n")
        (d / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode() + b"\0")
        for tid, name in threads:
            self.thread(pid, tid, name)

    def thread(self, pid, tid, name):
        t = self.root / str(pid) / "task" / str(tid)
        t.mkdir(parents=True, exist_ok=True)
        (t / "comm").write_text(name + "\n")

    def exit_thread(self, pid, tid):
        t = self.root / str(pid) / "task" / str(tid)
        (t / "comm").unlink()
        t.rmdir()

    def exit_process(self, pid):
        shutil.rmtree(self.root / str(pid))


class Nice:
    def __init__(self):
        self.calls = []
        self.values = set()
        self.fail = {}

    def __call__(self, tid, value):
        if tid in self.fail:
            raise self.fail[tid]
        self.calls.append(tid)
        self.values.add(value)


class Affinity:
    def __init__(self):
        self.calls = []
        self.current = {}
        self.fail = {}

    def __call__(self, tid, cpus):
        if tid in self.fail:
            raise self.fail[tid]
        self.calls.append((tid, sorted(cpus)))
        self.current[tid] = sorted(cpus)


def source_threads(pid=500):
    # The thread set observed in the failed ab-b1 run's source JVM.
    return [(pid, "java"), (pid + 1, "java"), (pid + 20, "C2 CompilerThre"), (pid + 21, "GC Thread#0"),
            (pid + 25, "/opt/vectormatc"), (pid + 30, "probe-absolute-"), (pid + 31, "soak-jfr-stream")]


class ClassifyTest(unittest.TestCase):
    def test_primordial_launcher_thread_is_never_an_agent(self):
        self.assertEqual("other", pin.classify(3, 500, 500, "java"))
        self.assertEqual("agent", pin.classify(3, 500, 501, "java"))

    def test_node_and_source_agent_names(self):
        for name in ("archive-conduct", "consensus-modul", "clustered-servi", "/opt/vectormatc"):
            self.assertEqual("agent", pin.classify(0, 1, 2, name), name)
        self.assertEqual("other", pin.classify(0, 1, 2, "java"))
        self.assertEqual("agent", pin.classify(3, 1, 2, "probe-absolute-"))
        self.assertEqual("other", pin.classify(3, 1, 2, "archive-conduct"))

    def test_safepoint_threads_compilers_and_everything_else(self):
        self.assertEqual("stopped", pin.classify(0, 1, 2, "GC Thread#3"))
        self.assertEqual("stopped", pin.classify(3, 1, 2, "VM Thread"))
        self.assertEqual("compiler", pin.classify(0, 1, 2, "C2 CompilerThre"))
        self.assertEqual("compiler", pin.classify(3, 1, 2, "C1 CompilerThre"))
        for name in ("G1 Conc#0", "G1 Refine#0", "aeron-client", "soak-jfr-stream", "VM Periodic Tas"):
            self.assertEqual("other", pin.classify(0, 1, 2, name), name)


class RoleTest(unittest.TestCase):
    def test_roles_from_command_line(self):
        self.assertEqual(0, pin.role_of(NODE_CMD, CASE))
        self.assertEqual(3, pin.role_of(SOURCE_CMD, CASE))
        self.assertEqual(2, pin.role_of(NODE_CMD.replace("node0", "node2"), CASE))

    def test_other_cases_and_unknown_layouts_are_ignored(self):
        self.assertIsNone(pin.role_of(NODE_CMD, "ab-b2"))
        self.assertIsNone(pin.role_of(NODE_CMD.replace("node0", "node7"), CASE))
        self.assertIsNone(pin.role_of("java /x/experiments/%s/state" % CASE, CASE))


class PlanTest(unittest.TestCase):
    def test_failed_run_layout_keeps_every_agent_off_housekeeping(self):
        wanted, agents, overflow = pin.plan(3, 500, source_threads(), SOURCE_CPUS, HOUSEKEEPING, {})
        self.assertEqual([], overflow)
        self.assertEqual({501: 78, 525: 95, 530: 174}, agents)
        self.assertEqual(frozenset({174}), wanted[530])
        self.assertEqual(frozenset(HOUSEKEEPING), wanted[500])
        self.assertEqual(frozenset(HOUSEKEEPING), wanted[520])
        self.assertEqual(frozenset(SOURCE_CPUS), wanted[521])
        self.assertNotIn(191, agents.values())

    def test_assignments_are_sticky_and_late_agents_overflow_to_housekeeping(self):
        _, agents, _ = pin.plan(3, 500, source_threads(), SOURCE_CPUS, HOUSEKEEPING, {})
        later = source_threads() + [(540, "/opt/vectormatc")]
        wanted, again, overflow = pin.plan(3, 500, later, SOURCE_CPUS, HOUSEKEEPING, agents)
        self.assertEqual(agents, again)
        self.assertEqual([(540, "/opt/vectormatc")], overflow)
        self.assertEqual(frozenset(HOUSEKEEPING), wanted[540])

    def test_cpu_of_an_exited_agent_is_reused(self):
        _, agents, _ = pin.plan(3, 500, source_threads(), SOURCE_CPUS, HOUSEKEEPING, {})
        without_arrival = [t for t in source_threads() if t[0] != 530] + [(540, "/opt/vectormatc")]
        _, again, overflow = pin.plan(3, 500, without_arrival, SOURCE_CPUS, HOUSEKEEPING, agents)
        self.assertEqual([], overflow)
        self.assertEqual(174, again[540])
        self.assertEqual(agents[525], again[525])

    def test_previous_cpu_outside_the_agent_set_is_reassigned(self):
        _, agents, _ = pin.plan(3, 500, source_threads(), SOURCE_CPUS, HOUSEKEEPING, {501: 191, 525: 999})
        self.assertNotIn(191, agents.values())
        self.assertEqual(sorted(agents.values()), [78, 95, 174])

    def test_node_with_four_agents_uses_all_four_cpus(self):
        threads = [(100, "java"), (101, "java"), (110, "/opt/vectormatc"), (111, "archive-conduct"),
                   (112, "consensus-modul"), (113, "clustered-servi"), (120, "GC Thread#0")]
        wanted, agents, overflow = pin.plan(0, 100, threads, NODE_CPUS, HOUSEKEEPING, {})
        self.assertEqual([], overflow)
        self.assertEqual(sorted(NODE_CPUS), sorted(agents.values()))
        self.assertEqual(frozenset(HOUSEKEEPING), wanted[101])


class GovernorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.proc = FakeProc(self.temporary.name)
        self.affinity = Affinity()
        self.nice = Nice()
        self.log = io.StringIO()

    def governor(self, config=CONFIG):
        return pin.Governor(Path("/x/experiments") / CASE, config, proc=self.proc.root, set_affinity=self.affinity,
                            set_nice=self.nice, log=self.log)

    def events(self):
        return [json.loads(line) for line in self.log.getvalue().splitlines()]

    def test_pins_every_thread_once_and_is_idempotent(self):
        self.proc.process(500, SOURCE_CMD, source_threads())
        g = self.governor()
        self.assertEqual(len(source_threads()), g.step())
        self.assertEqual([174], self.affinity.current[530])
        self.assertEqual(0, g.step())
        self.assertEqual(2, g.counts["passes"])

    def test_compilers_keep_their_priority_by_default(self):
        self.proc.process(500, SOURCE_CMD, source_threads())
        g = self.governor()
        g.step()
        self.assertEqual([], self.nice.calls)
        self.assertEqual(HOUSEKEEPING, self.affinity.current[520])
        self.assertEqual(0, g.counts["nicedCompilers"])

    def test_vm_thread_uses_the_jvm_set_and_compilers_are_reniced_once_when_asked(self):
        self.proc.process(500, SOURCE_CMD, source_threads() + [(510, "VM Thread"), (522, "C1 CompilerThre")])
        g = self.governor(dict(CONFIG, compilerNice=19))
        g.step()
        g.step()
        self.assertEqual(sorted(SOURCE_CPUS), self.affinity.current[510])
        self.assertEqual(HOUSEKEEPING, self.affinity.current[520])
        self.assertEqual([520, 522], self.nice.calls)
        self.assertEqual({19}, self.nice.values)
        self.assertEqual(2, g.counts["nicedCompilers"])

    def test_renice_failure_is_reported_once_and_retried(self):
        self.proc.process(500, SOURCE_CMD, source_threads())
        self.nice.fail = {520: PermissionError("denied")}
        g = self.governor(dict(CONFIG, compilerNice=19))
        g.step()
        g.step()
        errors = [e["error"] for e in self.events() if "error" in e]
        self.assertEqual(1, len(errors))
        self.assertTrue(errors[0].startswith("setpriority(520, 19)"), errors[0])
        self.nice.fail = {}
        g.step()
        self.assertEqual([520], self.nice.calls)

    def test_ignores_other_cases_and_non_java_processes(self):
        self.proc.process(600, NODE_CMD.replace(CASE, "ab-a1"), [(601, "archive-conduct")])
        self.proc.process(700, NODE_CMD, [(701, "archive-conduct")], comm="python3")
        (self.proc.root / "self").mkdir()
        self.assertEqual(0, self.governor().step())

    def test_reused_tid_with_a_new_name_is_pinned_again(self):
        self.proc.process(100, NODE_CMD, [(100, "java"), (110, "archive-conduct")])
        g = self.governor()
        g.step()
        self.proc.exit_thread(100, 110)
        self.proc.thread(100, 110, "C2 CompilerThre")
        self.assertEqual(1, g.step())
        self.assertEqual(HOUSEKEEPING, self.affinity.current[110])

    def test_vanished_thread_is_skipped_and_other_failures_reported_once(self):
        self.proc.process(100, NODE_CMD, [(100, "java"), (110, "archive-conduct"), (111, "consensus-modul")])
        self.affinity.fail = {110: ProcessLookupError(), 111: PermissionError("denied")}
        g = self.governor()
        g.step()
        g.step()
        errors = [e for e in self.events() if "error" in e]
        self.assertEqual(1, len(errors))
        self.assertIn("sched_setaffinity(111", errors[0]["error"])

    def test_simultaneous_extra_agent_is_the_newest_and_drift_is_reported(self):
        self.proc.process(500, SOURCE_CMD, source_threads() + [(540, "/opt/vectormatc")])
        g = self.governor(dict(CONFIG, expectedAgents={"source": 3}))
        g.step()
        g.step()
        errors = sorted(e["error"] for e in self.events() if "error" in e)
        self.assertEqual(["agent /opt/vectormatc (540) has no free CPU; confined to housekeeping",
                          "expected 3 agents, found 4"], errors)
        self.assertEqual(1, g.counts["overflowAgents"])
        self.assertEqual(HOUSEKEEPING, self.affinity.current[540])
        self.assertEqual([{"pid": 500, "role": 3, "expected": 3, "peak": 4}], g.drift())

    def test_startup_ramp_is_neither_an_error_nor_drift(self):
        threads = source_threads()
        self.proc.process(500, SOURCE_CMD, [t for t in threads if t[1] != "/opt/vectormatc" and t[1] != "probe-absolute-"])
        g = self.governor(dict(CONFIG, expectedAgents={"source": 3}))
        g.step()
        self.proc.thread(500, 525, "/opt/vectormatc")
        g.step()
        self.proc.thread(500, 530, "probe-absolute-")
        g.step()
        self.assertEqual([], [e for e in self.events() if "error" in e])
        self.assertEqual([], g.drift())
        self.assertEqual({"501": ["java", 78], "525": ["/opt/vectormatc", 95], "530": ["probe-absolute-", 174]},
                         g.summary(CONFIG)["agentHistory"]["500"]["agents"])

    def test_agent_that_never_appears_is_drift(self):
        self.proc.process(100, NODE_CMD, [(100, "java"), (110, "/opt/vectormatc"), (111, "archive-conduct"),
                                          (112, "consensus-modul")])
        g = self.governor(dict(CONFIG, expectedAgents={"node": 4}))
        g.step()
        self.assertEqual([{"pid": 100, "role": 0, "expected": 4, "peak": 3}], g.drift())
        self.assertEqual(0, g.counts["errors"])

    def test_assignment_of_an_exited_jvm_stays_in_the_summary(self):
        self.proc.process(500, SOURCE_CMD, source_threads())
        g = self.governor()
        g.step()
        self.proc.exit_process(500)
        g.step()
        summary = g.summary(CONFIG)
        self.assertEqual(3, summary["agentHistory"]["500"]["role"])
        self.assertEqual(["probe-absolute-", 174], summary["agentHistory"]["500"]["agents"]["530"])
        self.assertEqual(0, summary["pinnedThreads"])

    def test_configuration_is_validated(self):
        with self.assertRaises(pin.PinningError):
            self.governor(dict(CONFIG, cpuSets=CONFIG["cpuSets"][:3]))
        with self.assertRaises(pin.PinningError):
            self.governor(dict(CONFIG, housekeeping=[]))


@unittest.skipUnless(Path("/proc/self/task").is_dir(), "requires Linux /proc")
class MainTest(unittest.TestCase):
    def test_sigterm_writes_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / CASE
            case.mkdir()
            process = subprocess.Popen([sys.executable, str(SOURCE), str(case), json.dumps(CONFIG)])
            time.sleep(1.2)
            process.send_signal(signal.SIGTERM)
            self.assertEqual(0, process.wait(timeout=10))
            summary = json.loads((case / "thread-pinning-summary.json").read_text())
            self.assertGreaterEqual(summary["passes"], 1)
            self.assertEqual(0, summary["errors"])
            self.assertEqual(CONFIG, summary["config"])


if __name__ == "__main__":
    unittest.main()
