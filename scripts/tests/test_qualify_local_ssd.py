"""Negative and positive proofs for the fail-closed SSD candidate preflight."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "qualify-local-ssd.py"
spec = importlib.util.spec_from_file_location("qualify_local_ssd_test", SCRIPT)
ssd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ssd)


def mount(source="/dev/nvme0n1p1", fstype="ext4", options="rw,relatime"):
    return {"filesystems": [{"target": "/mnt/bench", "source": source,
                             "fstype": fstype, "options": options,
                             "maj:min": "259:0" if source == "/dev/nvme0n1" else "259:1"}]}


def devices(model="Samsung SSD 990 PRO", transport="nvme", rotational=False):
    return {"blockdevices": [
        {"name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "pkname": None,
         "tran": transport, "rota": rotational, "model": model, "maj:min": "259:0"},
        {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "type": "part", "pkname": "nvme0n1",
         "tran": None, "rota": rotational, "model": None, "maj:min": "259:1"},
    ]}


def check(mount_info=None, devices_info=None, free=5_000_000_000, growth=1_000_000_000, reserve=1_000_000_000):
    actual_mount = mount() if mount_info is None else mount_info
    return ssd.classify(actual_mount,
                        devices() if devices_info is None else devices_info,
                        free, growth, reserve,
                        actual_mount.get("filesystems", [{}])[0].get("maj:min", "invalid"))


class LocalSsdCandidateTest(unittest.TestCase):
    def test_positive_case_is_only_a_candidate_never_physical_durability_proof(self):
        report = check()
        self.assertTrue(report["candidateForDiskBackedExperiment"])
        self.assertFalse(report["strictPhysicalDurabilityProven"])
        self.assertTrue(report["operatorAndProviderPhysicalLocalityAttestationRequired"])
        self.assertTrue(report["powerLossOrDeviceFlushProofRequired"])
        self.assertEqual([], report["rejectionReasons"])

    def test_xfs_direct_disk_is_supported(self):
        block = devices()
        block["blockdevices"].pop()
        self.assertTrue(check(mount_info=mount(source="/dev/nvme0n1", fstype="xfs"), devices_info=block)
                        ["candidateForDiskBackedExperiment"])

    def test_non_disk_backed_mounts_never_qualify(self):
        for fstype, source in (("fuse.mfs", "mfs#eur-is-1.runpod.net:9421"),
                               ("tmpfs", "tmpfs"), ("overlay", "overlay"),
                               ("nfs4", "10.0.0.1:/exports/bench")):
            with self.subTest(fstype=fstype):
                report = check(mount_info=mount(source=source, fstype=fstype))
                self.assertFalse(report["candidateForDiskBackedExperiment"])
                self.assertFalse(report["strictPhysicalDurabilityProven"])

    def test_ext4_label_is_insufficient_if_backed_by_ebs_nvme(self):
        for model in ("Amazon Elastic Block Store", "Google Persistent Disk", "VirtIO Block Device"):
            with self.subTest(model=model):
                report = check(devices_info=devices(model=model))
                self.assertFalse(report["candidateForDiskBackedExperiment"])
                self.assertIn("disk model suggests remote/virtualized backing", report["rejectionReasons"])

    def test_mapped_device_cannot_impersonate_direct_nvme(self):
        for source in ("/dev/mapper/vg0-data", "/dev/nvme0n1p1[/var/lib/container]", "UUID=abc"):
            with self.subTest(source=source):
                self.assertFalse(check(mount_info=mount(source=source))["candidateForDiskBackedExperiment"])

    def test_drive_and_mount_properties_are_strict(self):
        cases = ((mount(options="ro,noatime"), devices()),
                 (mount(), devices(transport="sata")),
                 (mount(), devices(rotational=True)),
                 (mount(), devices(model="")),
                 (mount(), {"blockdevices": []}))
        for mount_info, devices_info in cases:
            with self.subTest(source=mount_info, devices=devices_info):
                self.assertFalse(check(mount_info, devices_info)["candidateForDiskBackedExperiment"])

    def test_device_identity_must_match_mount_lsblk_and_real_path(self):
        bad_lsblk = devices()
        bad_lsblk["blockdevices"][1]["maj:min"] = "259:17"
        self.assertFalse(check(devices_info=bad_lsblk)["candidateForDiskBackedExperiment"])
        self.assertFalse(ssd.classify(mount(), devices(), 5_000_000_000,
                                      1_000_000_000, 1_000_000_000, "259:17")
                         ["candidateForDiskBackedExperiment"])
        bad_findmnt = mount()
        bad_findmnt["filesystems"][0]["maj:min"] = "abc"
        self.assertFalse(check(mount_info=bad_findmnt)["candidateForDiskBackedExperiment"])

    def test_budget_must_fit_with_reserve_and_must_be_positive(self):
        self.assertTrue(check(free=2_000_000_000)["candidateForDiskBackedExperiment"])
        for values in ((1_999_999_999, 1_000_000_000, 1_000_000_000),
                       (5_000_000_000, 0, 1_000_000_000),
                       (5_000_000_000, 1_000_000_000, -1),
                       (True, 1_000_000_000, 1_000_000_000)):
            with self.subTest(values=values):
                self.assertFalse(check(free=values[0], growth=values[1], reserve=values[2])
                                 ["candidateForDiskBackedExperiment"])

    def test_ambiguous_inventory_ancestry_and_input_fail_closed(self):
        faulty = devices()
        faulty["blockdevices"][0]["pkname"] = "nvme0n1p1"
        self.assertFalse(check(devices_info=faulty)["candidateForDiskBackedExperiment"])
        for mount_info, device_info in (({}, devices()),
                                        (mount(), {}),
                                        ({"filesystems": [{}, {}]}, devices())):
            with self.subTest(mount_info=mount_info):
                self.assertFalse(check(mount_info, device_info)["candidateForDiskBackedExperiment"])

    def test_probe_errors_and_non_json_are_not_silent_successes(self):
        with patch.object(ssd.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
            with self.assertRaisesRegex(ValueError, "probe failed"):
                ssd.command_json(["findmnt"])
        with patch.object(ssd.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "not-json", "")):
            with self.assertRaisesRegex(ValueError, "non-JSON"):
                ssd.command_json(["lsblk"])

    def test_real_cli_refuses_current_workspace_without_falsely_claiming_durability(self):
        if sys.platform != "linux":
            self.skipTest("Linux-specific CLI gate")
        result = subprocess.run([sys.executable, str(SCRIPT), "--path", str(SCRIPT.parent),
                                 "--required-growth-bytes", "1000000000",
                                 "--minimum-reserve-bytes", "1000000000"],
                                capture_output=True, text=True, timeout=10)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["strictPhysicalDurabilityProven"])
        self.assertEqual(result.returncode == 0, report["candidateForDiskBackedExperiment"])


if __name__ == "__main__":
    unittest.main()
