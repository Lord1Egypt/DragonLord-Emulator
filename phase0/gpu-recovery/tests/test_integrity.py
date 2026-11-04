import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "tools/verify-evidence.py"
spec = importlib.util.spec_from_file_location("verify_recovery_evidence", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IntegrityTests(unittest.TestCase):
    def fixture(self, root):
        p = Path(root)
        (p / "evidence").mkdir()
        (p / "evidence/log.txt").write_bytes(b"evidence\r\n")
        row = {"path": "evidence/log.txt", "bytes": 10, "sha256": hashlib.sha256(b"evidence\r\n").hexdigest()}
        self.manifest(p, [row])
        return p, row

    def manifest(self, root, rows):
        (root / "evidence/index.json").write_text(json.dumps({"files": rows}))

    def test_exact_bytes_pass(self):
        with tempfile.TemporaryDirectory() as t:
            p, _ = self.fixture(t)
            self.assertEqual(module.verify_index(p, False), 1)

    def test_line_ending_rewrite_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p, _ = self.fixture(t)
            (p / "evidence/log.txt").write_bytes(b"evidence\n")
            with self.assertRaises(ValueError):
                module.verify_index(p, False)

    def test_duplicate_path_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p, row = self.fixture(t)
            self.manifest(p, [row, row])
            with self.assertRaises(ValueError):
                module.verify_index(p, False)

    def test_parent_escape_fails(self):
        with tempfile.TemporaryDirectory() as t:
            p, row = self.fixture(t)
            row["path"] = "../private"
            self.manifest(p, [row])
            with self.assertRaises(ValueError):
                module.verify_index(p, False)


if __name__ == "__main__":
    unittest.main()
