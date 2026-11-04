#!/usr/bin/env python3
"""Apply the reviewed one-line printf safety correction only to the isolated copy."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--native-root', type=Path, required=True)
a = p.parse_args()
package = Path(__file__).resolve().parents[1]
m = json.loads((package/'evidence/gfxstream-source-overlay.json').read_text())
f = a.native_root/'src/hardware/google/gfxstream'/m['files'][0]['path']
raw = f.read_bytes()
if hashlib.sha256(raw).hexdigest() != m['files'][0]['original_sha256']:
    raise SystemExit('Pristine input hash mismatch; refusing overwrite')
s = raw.decode(); after = s.replace('mFeatures.VulkanAllocateHostMemory.getReason());', 'mFeatures.VulkanAllocateHostMemory.getReason().c_str());')
patch = ''.join(difflib.unified_diff(s.splitlines(True), after.splitlines(True), fromfile='a/'+m['files'][0]['path'], tofile='b/'+m['files'][0]['path']))
if patch != (package/'gfxstream-printf-argument.patch').read_text() or hashlib.sha256(after.encode()).hexdigest() != m['files'][0]['patched_sha256']:
    raise SystemExit('Overlay content mismatch')
f.write_bytes(after.encode())
(a.native_root/'gfxstream-source-overlay.json').write_text(json.dumps(m,indent=2)+'\n')
print('Isolated build correction applied; no build or rendering result claimed')
