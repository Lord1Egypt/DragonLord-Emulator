#!/usr/bin/env python3
"""Relocate recorded native command JSON; execution/results remain separate."""
import argparse
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--native-root', required=True, help='Short native path, e.g. C:\\DLGPU\\replay')
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if not a.native_root.startswith('C:\\') or a.native_root.startswith('\\\\'):
    p.error('Expected short local C: workspace')
if a.output.exists():
    p.error('Fresh output directory required')
source = Path(__file__).resolve().parents[1]/'evidence/commands'


def replace(value):
    if isinstance(value,str):
        return value.replace('C:\\\\DLGPU\\\\p06-20261104',a.native_root).replace('C:\\DLGPU\\p06-20261104',a.native_root)
    if isinstance(value,list):
        return [replace(v) for v in value]
    if isinstance(value,dict):
        return {k:replace(v) for k,v in value.items()}
    return value


for file in source.rglob('*.json'):
    if file.name == 'source-hashes.json':
        continue
    target = a.output/file.relative_to(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(replace(json.loads(file.read_text())),indent=2)+'\n')
print('Commands prepared; select documented acceptance runs. Historical failure commands are retained as evidence, not recommended defaults.')
