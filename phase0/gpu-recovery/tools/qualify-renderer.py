#!/usr/bin/env python3
"""Fail-closed qualification of captured Gfxstream runs; invalid PDH is never zero."""
import argparse
import json
from pathlib import Path
import re


def inspect(directory, vendor, device_type, expected_tests):
    result = json.loads((directory/'result.json').read_text(encoding='utf-8-sig'))
    log = (directory/'stdout.log').read_text()
    identities = re.findall(r'DLGPU_DEVICE name=(.*?) vendor=(\d+) device=(\d+) type=(\d+) api=(\d+) driver=(\d+) luidValid=(\d+) luid=([0-9a-f]{16})', log)
    passed = re.findall(r'^\[       OK \] (CompositorVkTest\.\w+) ', log, re.M)
    ok = result.get('exit_code') == 0 and not result.get('timed_out') and len(passed) == expected_tests
    ok = ok and len(identities) == expected_tests and all(int(d[1]) == vendor and int(d[3]) == device_type for d in identities)
    ok = ok and '[  SKIPPED ]' not in log and '[  FAILED  ]' not in log
    return result, {'pixel_workload': 'PASS' if ok else 'FAIL', 'completed_tests':len(passed),
                    'identities':sorted(set(identities)), 'pid':result.get('process_id')}


def qualify(hardware, software, expected_tests=90):
    h, hs = inspect(hardware, 0x10de, 2, expected_tests)
    s, ss = inspect(software, 0x1ae0, 4, expected_tests)
    hmods = [m['name'].lower() for m in h.get('modules',[])]
    smods = [m['name'].lower() for m in s.get('modules',[])]
    no_fallback = not any(any(bad in n for bad in ['swiftshader','warp','llvmpipe','lavapipe']) for n in hmods)
    hw_identity = hs['pixel_workload'] == 'PASS' and 'nvoglv64.dll' in hmods and 'vulkan-1.dll' in hmods and no_fallback
    sw_identity = ss['pixel_workload'] == 'PASS' and 'vk_swiftshader.dll' in smods
    positive = []
    for identity in hs['identities']:
        if identity[6] != '1':
            continue
        luid = int.from_bytes(bytes.fromhex(identity[7]),'little')
        prefix = f"pid_{h.get('process_id')}_luid_0x{luid>>32:08x}_0x{luid&0xffffffff:08x}_"
        positive += [g for sample in h.get('samples',[]) for g in sample['gpu']
                     if g['instance'].startswith(prefix) and g['status'] in (0,1) and g['value']>0]
    valid_software = [g for sample in s.get('samples',[]) for g in sample['gpu']
                      if g['instance'].startswith(f"pid_{s.get('process_id')}_") and g['status'] in (0,1)]
    # No sample / invalid samples cannot establish measured idle GPU execution.
    control = bool(valid_software) and all(g['value']==0 for g in valid_software)
    same_binary = h.get('executable_sha256') == s.get('executable_sha256') and bool(h.get('executable_sha256'))
    independent = hw_identity and sw_identity and bool(positive) and control and same_binary
    return {'scope':'Standalone Gfxstream compositor only; no guest API streaming/QEMU/Android validation',
            'hardware':hs,'software':ss,'same_binary':same_binary,'software_fallback_excluded_in_hardware':no_fallback,
            'hardware_selected_adapter_and_driver':'PASS' if hw_identity else 'FAIL',
            'software_selected_CPU_and_driver':'PASS' if sw_identity else 'FAIL',
            'matched_valid_positive_hardware_counter_samples':len(positive),
            'valid_software_counter_samples':len(valid_software),
            'vendor_DLL_also_loaded_in_software':'nvoglv64.dll' in smods,
            'software_counter_control':'PASS' if control else 'FAIL',
            'actual_hardware_rendering':'PASS' if hw_identity and positive else 'FAIL',
            'independent_gpu_verification':'PASS' if independent else 'FAIL',
            'reason':'Strict independent gate requires matched positive hardware telemetry and a valid measured software control; invalid/no data is never zero.',
            'ETW_hardware':h.get('etw'),'ETW_software':s.get('etw')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hardware',type=Path,required=True)
    p.add_argument('--software',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-tests',type=int,default=90)
    a = p.parse_args()
    if a.output.exists():
        p.error('Fresh output required')
    result = qualify(a.hardware,a.software,a.expected_tests)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['independent_gpu_verification']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
