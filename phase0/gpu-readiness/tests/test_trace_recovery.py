"""Fail-closed trace regressions using actual preserved broken and recovered records."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PACKAGE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('trace_recovery',PACKAGE/'tools/parse-kernel-trace.py')
parser=importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
FIXTURE=PACKAGE/'evidence/recovered-native/recovery-smoke-hardware/kernel.jsonl'


class TraceRecoveryTests(unittest.TestCase):
    def mutate(self, transform):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        events=[json.loads(line[4:]) for line in FIXTURE.read_text().splitlines()]
        events=transform(events)
        p=Path(temporary.name)/'trace.jsonl'
        p.write_text(''.join('DLK '+json.dumps(e)+'\n' for e in events))
        return p

    def test_actual_recovered_trace_parses(self):
        result=parser.parse(FIXTURE)
        self.assertEqual(result['status'],'PASS')
        self.assertGreater(result['samples'],0)
        self.assertIn('no hardware qualification',result['scope'])

    def test_actual_interleaved_record_still_fails_at_column_108(self):
        data=json.loads((PACKAGE/'evidence/json-diagnosis/result.json').read_text())
        line=data['runs'][0]['first_errors'][0]['raw_line']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'broken.jsonl';p.write_text(line+'\n')
            with self.assertRaises(json.JSONDecodeError) as caught:parser.parse(p)
        self.assertEqual(caught.exception.colno,108)

    def test_truncated_trace_fails(self):
        p=self.mutate(lambda events:[e for e in events if e['event']!='exit'])
        with self.assertRaisesRegex(ValueError,'Incomplete'):parser.parse(p)

    def test_wrong_process_samples_fail(self):
        def change(events):
            next(e for e in events if e['event']=='sample')['pid']=1
            return events
        with self.assertRaisesRegex(ValueError,'PID mismatch'):parser.parse(self.mutate(change))

    def test_invalid_numeric_zero_is_not_a_valid_kernel_sample(self):
        def change(events):
            for e in events:
                if e['event']=='sample':e.update(status=0xc0000bc6,running_time_raw=0)
            return events
        result=parser.parse(self.mutate(change))
        self.assertEqual(result['valid_samples'],0)
        self.assertEqual(result['invalid_samples'],result['samples'])
        self.assertIsNone(result['max_running_time_raw'])


if __name__=='__main__':unittest.main()
