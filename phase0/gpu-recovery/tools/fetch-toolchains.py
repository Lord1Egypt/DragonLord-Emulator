#!/usr/bin/env python3
"""Fetch pinned official portable tools and cryptographically verify LLVM in a private keyring."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

PACKAGE = Path(__file__).resolve().parents[1]
FINGERPRINT = 'FFB3368980F3E6BB5737145A316C56D064CACBA5'
LLVM = 'clang+llvm-23.1.5-x86_64-pc-windows-msvc.tar.zst'
RUST = 'rust-1.88.0-x86_64-pc-windows-msvc.tar.xz'
BASE = 'https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.5/'
PINS = {
    LLVM: (BASE + LLVM.replace('+', '%2B'), 'b2be33385ddc86e83511417a060de927ae8b09d1f3017cc3cdce5c73cd5029d7'),
    LLVM+'.sig': (BASE + LLVM.replace('+', '%2B')+'.sig', 'e452a33f38a471eed98b91ef6b01f1cee1f9e296e180066c1fdbd316717a635b'),
    'release-keys.asc': ('https://releases.llvm.org/release-keys.asc', 'f38bd19b7f2d22cafa755841e6ce9375b9a2e6d41f7b974e4953d6b084839001'),
    RUST: ('https://static.rust-lang.org/dist/2025-06-26/'+RUST, '4c5bafcfbb25a2a3b21cb5934d18c70d370b504b518c0119fda51aee7887e7c2'),
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def verify(directory):
    for name, (_, sha) in PINS.items():
        if digest(directory/name) != sha:
            raise ValueError('Checksum mismatch: '+name)
    with tempfile.TemporaryDirectory(prefix='dlgpu-gpg-') as home:
        subprocess.run(['gpg', '--homedir', home, '--batch', '--import', str(directory/'release-keys.asc')],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result = subprocess.run(['gpg', '--homedir', home, '--batch', '--status-fd', '1', '--verify',
                                 str(directory/(LLVM+'.sig')), str(directory/LLVM)], capture_output=True, text=True)
        if result.returncode or ('[GNUPG:] VALIDSIG '+FINGERPRINT+' ') not in result.stdout:
            raise ValueError('LLVM detached signature verification failed: '+result.stderr)
        return result.stdout+result.stderr


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, default=PACKAGE.parent/'.work/gpu-recovery/downloads')
    p.add_argument('--verify-only', action='store_true')
    a = p.parse_args()
    a.directory.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in PINS.items():
        path = a.directory/name
        if path.exists():
            if digest(path) != sha:
                raise ValueError('Existing download mismatch; refusing overwrite: '+name)
        elif a.verify_only:
            raise FileNotFoundError(path)
        else:
            temporary = path.with_name(name+'.partial')
            if temporary.exists():
                raise ValueError('Existing partial download; inspect before retry')
            with urllib.request.urlopen(url, timeout=120) as src, temporary.open('xb') as dst:
                for b in iter(lambda: src.read(1024*1024), b''):
                    dst.write(b)
            if digest(temporary) != sha:
                raise ValueError('Downloaded checksum mismatch: '+name)
            temporary.rename(path)
    signature = verify(a.directory)
    print(json.dumps({'status':'PASS','scope':'Archive checksums and LLVM detached signature, not native build or GPU',
                      'pins':PINS,'llvm_signature':signature,'rust_provenance':'SHA256 matches official pinned channel manifest; no independent Rust signature qualification'}, indent=2))


if __name__ == '__main__':
    main()
