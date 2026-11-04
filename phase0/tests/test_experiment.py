import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("experiment", TOOLS / "experiment.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)

class EvidenceGateTests(unittest.TestCase):
    def test_whpx_never_qualifies_under_wsl_or_linux(self):
        self.assertIsNotNone(experiment.accelerator_blocker("whpx", host="Linux"))

    def test_missing_kvm_blocks_instead_of_falling_back(self):
        self.assertIsNotNone(experiment.accelerator_blocker("kvm", host="Linux", kvm_access=False))

    def test_accessible_kvm_can_proceed_to_runtime_test(self):
        self.assertIsNone(experiment.accelerator_blocker("kvm", host="Linux", kvm_access=True))

    def test_hardware_command_has_one_accelerator_and_snapshot_disk(self):
        cmd = experiment.boot_argv("qemu", "whpx", "kernel", "disk", 19001, 19002, None)
        self.assertEqual(cmd.count("-accel"), 1)
        self.assertEqual(cmd[cmd.index("-accel") + 1], "whpx")
        self.assertNotIn("tcg", cmd)
        self.assertIn("snapshot=on", cmd[cmd.index("-drive") + 1])
        self.assertEqual(cmd[cmd.index("-nic") + 1], "none")

    def test_echoed_command_does_not_establish_guest_readiness(self):
        console = "Linux version 6 x86_64\ntuxtest login:\nprintf 'PHASE0_'; printf 'READY_abc\\n'; uname -m"
        self.assertFalse(experiment.ready_evidence(console, "PHASE0_READY_abc"))

    def test_marker_requires_returned_architecture(self):
        console = "Linux version 6 x86_64\ntuxtest login:\nPHASE0_READY_abc\naarch64\n"
        self.assertFalse(experiment.ready_evidence(console, "PHASE0_READY_abc"))

    def test_authenticated_command_response_can_qualify_diagnostic_only(self):
        console = "Linux version 6\ntuxtest login:\nPHASE0_READY_abc\r\nx86_64\r\n"
        self.assertTrue(experiment.ready_evidence(console, "PHASE0_READY_abc"))
        self.assertFalse(experiment.ready_evidence(console + "Kernel panic - not syncing", "PHASE0_READY_abc"))

    def test_bad_download_is_not_promoted_to_verified_artifact(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "artifact"
            with patch.object(experiment.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")):
                with self.assertRaises(ValueError):
                    experiment.verified_download("https://invalid.example/asset", "0" * 64, p)
            self.assertFalse(p.exists())
            self.assertFalse(p.with_name("artifact.part").exists())

    def test_blocked_smoke_cannot_claim_android_or_gpu_pass(self):
        import argparse
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(output=tmp, accel="whpx")
            with patch.object(experiment.platform, "system", return_value="Linux"):
                self.assertEqual(experiment.smoke(args), 2)
            result = json.loads((Path(tmp) / "result.json").read_text())
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["gpu"], "NOT_TESTED")
            self.assertEqual(result["android16"], "NOT_TESTED")

if __name__ == "__main__":
    unittest.main()
