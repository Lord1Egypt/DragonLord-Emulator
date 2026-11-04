#!/usr/bin/env python3
"""Prepare fresh native recovery sources/commands; preserve all prior attempts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

PACKAGE=Path(__file__).resolve().parents[1]
EXPECTED_CLANG='dd3634f32c562c92a2dc11e115df029a5abc5373f2ee6d640b26e2f68d656c01'
EXPECTED_RENDERER='4a9f453d3fdde4bd267afbb2a7bb13a10113bfc6d32be8742ed59e46798aec11'


def win(p):
    return 'C:\\'+str(p.resolve().relative_to('/mnt/c')).replace('/','\\')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root',type=Path,required=True)
    p.add_argument('--tools-root',type=Path,required=True)
    p.add_argument('--commands',type=Path,required=True)
    p.add_argument('--repeats',type=int,default=1)
    a=p.parse_args()
    if a.commands.exists():p.error('Fresh command directory required')
    if not 1<=a.repeats<=30:p.error('Bounded repeats 1..30 required')
    clang=a.tools_root/'tools/clang+llvm-23.1.5-x86_64-pc-windows-msvc/bin/clang-cl.exe'
    renderer=a.tools_root/'build/gfxstream-native-3/Vulkan_unittests.exe'
    if digest(clang)!=EXPECTED_CLANG or digest(renderer)!=EXPECTED_RENDERER:
        p.error('Pinned native binary hash mismatch')
    a.commands.mkdir(parents=True)
    experiments=a.native_root/'experiments';experiments.mkdir(parents=True,exist_ok=True)
    rows=[]
    for kind,source in [('negative',PACKAGE/'evidence/source-snapshots/kernel-observer-before-recovery.cpp'),
                        ('recovered',PACKAGE/'experiments/kernel-observer.cpp')]:
        target=experiments/('kernel-observer-'+kind+'.cpp')
        if target.exists():raise ValueError('Refuse source overwrite: '+str(target))
        shutil.copyfile(source,target)
        rows.append({'path':str(target),'sha256':digest(target)})
        command={'executable':win(clang),'arguments':['/nologo','/std:c++17','/EHsc','/W4','/WX',win(target),
            '/Fo'+win(target.with_suffix('.obj')),'/Fe'+win(target.with_suffix('.exe')),'/link','gdi32.lib','dxgi.lib','psapi.lib'],
            'working_directory':win(experiments),'timeout_seconds':120,
            'scope':'Original deprecated-writer FAIL control' if kind=='negative' else 'Fixed writer compile only; GPU qualification separate'}
        (a.commands/(kind+'-build.json')).write_text(json.dumps(command,indent=2)+'\n')
    for mode in ['hardware','software']:
        old=json.loads((PACKAGE.parent/'gpu-recovery/evidence/commands'/('gfx-final-'+mode+'-command.json')).read_text())
        args='--gtest_filter=CompositorVkTest.EmptyCompositionShouldDrawABlackFrame:CompositorVkTest.SimpleComposition:CompositorVkTest.SolidColor --gtest_repeat='+str(a.repeats)
        trace=a.native_root/'results'/('recovery-smoke-'+mode)/'kernel.jsonl'
        command={'executable':win(experiments/'kernel-observer-recovered.exe'),
            'arguments':[win(renderer),args,'45',win(trace)],'working_directory':win(renderer.parent),
            'environment':old['environment'],'timeout_seconds':60,
            'scope':'Bounded trace-writer regression and unchanged Gfxstream pixel smoke; NOT independent GPU acceptance'}
        (a.commands/('smoke-'+mode+'.json')).write_text(json.dumps(command,indent=2)+'\n')
    (a.commands/'source-hashes.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Fresh sources/commands prepared; no execution PASS claimed')


if __name__=='__main__':main()
