import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
spec = importlib.util.spec_from_file_location("phase0_validation", TOOLS / "validate-phase0.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class EvidenceIntegrityTests(unittest.TestCase):
    def write_boot(self, folder, console, argv=None, status="PASS"):
        (folder / "serial.log").write_text(console)
        (folder / "result.json").write_text(json.dumps({"status": status, "accelerator": "whpx",
            "argv": argv or ["-accel", "whpx"], "qemu_sha256": "diagnostic-only"}))

    def test_original_tcg_64bit_nonce_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nPHASE0_READY_" + "a" * 16 + "\nx86_64\n")
            self.assertEqual(validator.validate_boot(p, "whpx")["status"], "PASS")

    def test_original_windows_128bit_nonce_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nPHASE0_READY_" + "b" * 32 + "\nx86_64\n")
            self.assertEqual(validator.validate_boot(p, "whpx")["gpu"], "NOT TESTED")

    def test_command_echo_cannot_qualify_retained_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nroot# echo PHASE0_READY_" + "a" * 32 + "; uname -m\n")
            with self.assertRaises(ValueError): validator.validate_boot(p, "whpx")

    def test_fallback_cannot_qualify_retained_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nPHASE0_READY_" + "a" * 32 + "\nx86_64\n",
                            ["-accel", "whpx", "-accel", "tcg"])
            with self.assertRaises(ValueError): validator.validate_boot(p, "whpx")

    def test_wrong_returned_architecture_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nPHASE0_READY_" + "a" * 32 + "\naarch64\n")
            with self.assertRaises(ValueError): validator.validate_boot(p, "whpx")

    def test_blocked_record_is_not_upgraded_by_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            self.write_boot(p, "Linux version test\nPHASE0_READY_" + "a" * 32 + "\nx86_64\n", status="BLOCKED")
            with self.assertRaises(ValueError): validator.validate_boot(p, "whpx")

    def test_tampered_log_fails_hash_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "evidence").mkdir()
            f = p / "evidence/log.txt"
            f.write_text("original")
            (p / "evidence/index.json").write_text(json.dumps({"files": [{"path": "evidence/log.txt",
                "bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}]}))
            self.assertEqual(validator.validate_index(p), 1)
            f.write_text("tampered")
            with self.assertRaises(ValueError): validator.validate_index(p)

    def test_index_cannot_escape_evidence_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "evidence").mkdir()
            (p / "evidence/index.json").write_text(json.dumps({"files": [{"path": "../outside", "bytes": 0, "sha256": ""}]}))
            with self.assertRaises(ValueError): validator.validate_index(p)


if __name__ == "__main__": unittest.main()
