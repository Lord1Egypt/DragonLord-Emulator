"""Mutate real captured fixtures to ensure missing/invalid evidence cannot become PASS."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('renderer_qualification',PACKAGE/'tools/qualify-renderer.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hardware = Path(self.tmp.name)/'hardware'
        self.software = Path(self.tmp.name)/'software'
        for name, target in [('gfx-final-hardware',self.hardware),('gfx-final-software',self.software)]:
            target.mkdir()
            for file in ['result.json','stdout.log']:
                shutil.copyfile(PACKAGE/'evidence/native'/name/file,target/file)

    def mutate(self, target, callback):
        p = target/'result.json'
        d = json.loads(p.read_text(encoding='utf-8-sig'))
        callback(d)
        p.write_text(json.dumps(d))

    def result(self):
        return module.qualify(self.hardware,self.software)

    def test_real_invalid_software_counters_never_count_as_zero(self):
        r = self.result()
        self.assertEqual(r['actual_hardware_rendering'],'PASS')
        self.assertEqual(r['valid_software_counter_samples'],0)
        self.assertEqual(r['independent_gpu_verification'],'FAIL')

    def test_wrong_pid_cannot_prove_hardware(self):
        self.mutate(self.hardware,lambda d:d.update(process_id=1))
        self.assertEqual(self.result()['actual_hardware_rendering'],'FAIL')

    def test_invalid_positive_counters_cannot_prove_hardware(self):
        def change(d):
            for sample in d['samples']:
                for g in sample['gpu']:
                    g['status'] = 0xc0000bc6
        self.mutate(self.hardware,change)
        self.assertEqual(self.result()['actual_hardware_rendering'],'FAIL')

    def test_software_module_in_hardware_run_blocks_qualification(self):
        self.mutate(self.hardware,lambda d:d['modules'].append({'name':'vk_swiftshader.dll'}))
        self.assertEqual(self.result()['actual_hardware_rendering'],'FAIL')

    def test_empty_test_selection_is_not_rendering(self):
        (self.hardware/'stdout.log').write_text('0 tests from 0 suites ran.\n')
        self.assertEqual(self.result()['actual_hardware_rendering'],'FAIL')


if __name__ == '__main__':
    unittest.main()
