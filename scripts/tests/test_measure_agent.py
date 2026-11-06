"""Memória do cgroup real, sem depender do layout de cgroup do executor de CI."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure_agent  # noqa: E402


class ContainerMemoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.proc = self.root / "proc"
        (self.proc / "self").mkdir(parents=True)

    def layout(self, membership, version="v2", mount_root="/", value="3073\n"):
        mount = self.root / "cgroup space"
        mount.mkdir(exist_ok=True)
        escaped_mount = str(mount).replace(" ", r"\040")
        filesystem = "cgroup2 cgroup rw" if version == "v2" else "cgroup cgroup rw,memory"
        (self.proc / "self/mountinfo").write_text(f"42 20 0:28 {mount_root} {escaped_mount} rw - {filesystem}\n")
        controllers = "" if version == "v2" else "cpu,memory"
        (self.proc / "self/cgroup").write_text(f"0:{controllers}:{membership}\n")
        relative = membership.removeprefix(mount_root).lstrip("/")
        counter = mount / relative / ("memory.current" if version == "v2" else "memory.usage_in_bytes")
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text(value)
        return counter

    def test_v2_uses_own_nested_cgroup_instead_of_mount_aggregate(self):
        counter = self.layout("/demo/agent")
        (self.root / "cgroup space/memory.current").write_text("999999999\n")
        result = measure_agent.container_memory(self.proc)
        self.assertEqual(result["container_memory_kib"], 3)
        self.assertEqual(result["container_memory_source"], str(counter))
        self.assertIsNone(result["container_memory_unavailable_reason"])

    def test_v1_uses_memory_controller_and_respects_subtree_mount(self):
        counter = self.layout("/docker/agent", "v1", "/docker", "8192\n")
        result = measure_agent.container_memory(self.proc)
        self.assertEqual(result["container_memory_kib"], 8)
        self.assertEqual(result["container_memory_source"], str(counter))

    def test_namespaced_membership_at_mount_root_is_supported(self):
        counter = self.layout("/", "v1", "/docker/agent", "0\n")
        result = measure_agent.container_memory(self.proc)
        self.assertEqual(result["container_memory_kib"], 0)
        self.assertEqual(result["container_memory_source"], str(counter))

    def test_unrelated_mount_does_not_report_host_memory(self):
        self.layout("/other/agent", "v1", "/docker")
        result = measure_agent.container_memory(self.proc)
        self.assertIsNone(result["container_memory_kib"])
        self.assertIsNone(result["container_memory_source"])
        self.assertEqual(result["container_memory_unavailable_reason"], "no_matching_memory_cgroup")

    def test_missing_metadata_is_explicit(self):
        result = measure_agent.container_memory(self.proc)
        self.assertIsNone(result["container_memory_kib"])
        self.assertEqual(result["container_memory_unavailable_reason"], "metadata_unreadable")

    def test_missing_counter_is_not_zero(self):
        counter = self.layout("/", value="0")
        counter.unlink()
        result = measure_agent.container_memory(self.proc)
        self.assertIsNone(result["container_memory_kib"])
        self.assertEqual(result["container_memory_source"], str(counter))
        self.assertEqual(result["container_memory_unavailable_reason"], "counter_unreadable")

    def test_unreadable_counter_does_not_interrupt_process_measurement(self):
        counter = self.layout("/")
        counter.unlink()
        counter.mkdir()
        result = measure_agent.container_memory(self.proc)
        self.assertIsNone(result["container_memory_kib"])
        self.assertEqual(result["container_memory_unavailable_reason"], "counter_unreadable")

    def test_invalid_or_negative_counter_is_not_memory_evidence(self):
        for value in ("invalid", "-1024", ""):
            with self.subTest(value=value):
                self.layout("/", value=value)
                result = measure_agent.container_memory(self.proc)
                self.assertIsNone(result["container_memory_kib"])
                self.assertEqual(result["container_memory_unavailable_reason"], "counter_invalid")

    def test_peak_retains_available_samples_and_marks_missing_samples(self):
        counter = self.layout("/", value="4096")
        # O pico usa as mesmas amostras que vão ao JSON, incluindo falhas transitórias.
        samples = [{"processes": 1, "mcp_processes": 0, "rss_kib": 20, **measure_agent.container_memory(self.proc)}]
        counter.unlink()
        samples.append({"processes": 3, "mcp_processes": 2, "rss_kib": 30, **measure_agent.container_memory(self.proc)})
        peak = measure_agent.peak_snapshot(samples)
        self.assertEqual(peak["container_memory_kib"], 4)
        self.assertEqual(peak["container_memory_sources"], [str(counter)])
        self.assertEqual(peak["container_memory_unavailable_samples"], 1)
        self.assertEqual(peak["mcp_processes"], 2)
        unavailable = measure_agent.peak_snapshot(samples[1:])
        self.assertIsNone(unavailable["container_memory_kib"])
        self.assertEqual(unavailable["container_memory_unavailable_samples"], 1)


if __name__ == "__main__":
    unittest.main()
