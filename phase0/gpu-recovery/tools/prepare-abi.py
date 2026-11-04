#!/usr/bin/env python3
"""Prepare native C-header negative controls and actual Rust/DLL boundary tests."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

PACKAGE = Path(__file__).resolve().parents[1]


def win(path):
    relative = path.resolve().relative_to('/mnt/c')
    return 'C:\\' + str(relative).replace('/', '\\')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root', type=Path, required=True)
    p.add_argument('--command-directory', type=Path, required=True)
    args = p.parse_args()
    root = args.native_root
    args.command_directory.mkdir(parents=True, exist_ok=True)
    experiments = root / 'experiments'
    helper = experiments / 'boundary'
    (helper / 'src').mkdir(parents=True, exist_ok=True)
    shutil.copy2(PACKAGE / 'experiments/boundary/Cargo.toml', helper / 'Cargo.toml')
    shutil.copy2(PACKAGE / 'experiments/boundary/src/lib.rs', helper / 'src/lib.rs')
    shutil.copy2(PACKAGE / 'experiments/abi_probe.c', experiments / 'abi_probe.c')
    original_dir = root / 'src/rutabaga/ffi/src/include'
    original = original_dir / 'rutabaga_gfx_ffi.h'
    before = original.read_text()
    old = '    uint32_t ctx_id;\n    uint32_t ring_idx;'
    new = '    uint32_t ctx_id;\n    uint8_t ring_idx;'
    if before.count(old) != 1:
        raise SystemExit('Unexpected original fence definition')
    fixed_dir = experiments / 'abi-fixed-include'
    fixed_dir.mkdir(exist_ok=True)
    fixed = fixed_dir / original.name
    fixed.write_text(before.replace(old, new))
    patch = ''.join(difflib.unified_diff(before.splitlines(keepends=True), fixed.read_text().splitlines(keepends=True),
                    fromfile='a/ffi/src/include/rutabaga_gfx_ffi.h', tofile='b/ffi/src/include/rutabaga_gfx_ffi.h'))
    if patch != (PACKAGE / 'rutabaga-ring-width.patch').read_text():
        raise SystemExit('Header overlay differs from reviewable patch')
    clang = root / 'tools/clang+llvm-23.1.5-x86_64-pc-windows-msvc/bin/clang-cl.exe'
    dll_dir = root / 'build/rutabaga-ffi-core/x86_64-pc-windows-msvc/release'
    for name, include, observe in [('abi-original-assert', original_dir, False),
                                   ('abi-original-observe', original_dir, True),
                                   ('abi-corrected', fixed_dir, False)]:
        executable = experiments / (name + '.exe')
        command = {'executable': win(clang), 'arguments': ['/nologo', '/TC', '/std:c11', '/W3', '/WX',
            '/I' + win(include), win(experiments / 'abi_probe.c'), '/Fo' + win(experiments / (name + '.obj')),
            '/Fe' + win(executable)], 'working_directory': win(experiments), 'timeout_seconds': 120,
            'scope': 'C ABI compile assertion; original header is an explicit negative control'}
        if observe:
            command['arguments'].insert(1, '/DOBSERVE_UNCORRECTED_HEADER')
        (args.command_directory / (name + '-compile.json')).write_text(json.dumps(command, indent=2) + '\n')
        if observe or name == 'abi-corrected':
            run = {'executable': win(executable), 'arguments': [win(dll_dir / 'dragonlord_boundary_probe.dll'),
                    win(dll_dir / 'rutabaga_gfx_ffi.dll')], 'working_directory': win(experiments), 'timeout_seconds': 60,
                   'scope': 'Actual native C/Rust ABI, HANDLE and FFI core/CPU transfer; GPU NOT TESTED'}
            (args.command_directory / (name + '-run.json')).write_text(json.dumps(run, indent=2) + '\n')
    hashes = {str(p.relative_to(experiments)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [helper / 'Cargo.toml', helper / 'src/lib.rs', experiments / 'abi_probe.c', fixed]}
    (args.command_directory / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print('Prepared original FAIL controls and corrected native ABI/FFI commands; no test execution claimed')


if __name__ == '__main__':
    main()
