#!/usr/bin/env python3
"""Relink existing pinned QEMU core objects with an ASan-instrumented host-unit main.

Does not change source/build objects or execute a VM guest. Renderer/device/virtqueue
fixtures are explicit; memory/QOM/RCU/Aio implementations are real QEMU objects.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT/'phase0/gpu-readiness'
QEMU = ROOT/'phase0/.work/qemu-11.1.3'
PIN = '005c61c0ef6f6ae615283440b4bb7be51b2c6ddd'


def function(source, name):
    # Reviewed pinned functions have no braces inside string literals.
    pos = source.index(name+'(')
    start = source.rfind('\nstatic ',0,pos)
    if start < 0 or '\n}' in source[start:pos]:
        start = source.rfind('\nvoid ',0,pos)
    start += 1
    brace = source.index('{',pos);depth=1;end=brace+1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'phase0/.work/qemu-build-linux')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Fresh output required')
    a.output.mkdir(parents=True)
    work=ROOT/'phase0/.work/gpu-readiness/core';work.mkdir(parents=True,exist_ok=True)
    assert subprocess.check_output(['git','-C',str(QEMU),'rev-parse','HEAD'],text=True).strip()==PIN
    assert not subprocess.check_output(['git','-C',str(QEMU),'diff','HEAD','--name-only'],text=True).strip()
    commands=json.loads((a.build/'compile_commands.json').read_text())
    record=next(r for r in commands if r['file'].endswith('/system/main.c'))
    argv=shlex.split(record['command']); old_obj=record['output']
    argv=argv[:argv.index('-MD')]
    source=work/'core_probe.c';binary=work/'core_probe';obj=work/'core_probe.o'
    source.write_text((PACKAGE/'experiments/core_probe.c.in').read_text())
    argv += ['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(obj),'-c',str(source)]
    result={'scope':'Actual pinned QEMU core with instrumented test main; not a VM/GPU/WHPX test','qemu_pin':PIN,'commands':[], 'status':'FAIL'}
    def run(command,name):
        r=subprocess.run(command,cwd=a.build,capture_output=True,timeout=120)
        (a.output/(name+'.stdout.log')).write_bytes(r.stdout);(a.output/(name+'.stderr.log')).write_bytes(r.stderr)
        result['commands'].append({'argv':command,'cwd':str(a.build),'exit_code':r.returncode})
        return r
    r=run(argv,'compile')
    if r.returncode==0:
        ninja=ROOT/'phase0/.work/build-venv/bin/ninja'
        db=json.loads(subprocess.check_output([str(ninja),'-C',str(a.build),'-t','compdb','-x']))
        link=shlex.split(next(r for r in db if r.get('output')=='qemu-system-x86_64')['command'])
        assert old_obj in link
        link[link.index(old_obj)]=str(obj);link[link.index('-o')+1]=str(binary)
        link += ['-fsanitize=address,undefined']
        r=run(link,'link')
        if r.returncode==0:
            result.update(status='PASS',binary=str(binary),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    result['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
