#!/usr/bin/env python3
"""Copy only text/log evidence from an isolated build; compress full large logs losslessly."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--native-root', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--runs', nargs='+', required=True)
a = p.parse_args()
for name in a.runs:
    if Path(name).name != name:
        raise ValueError('Run must be a single directory name')
    source = a.native_root/'results'/name
    if not (source/'result.json').is_file():
        raise ValueError('Incomplete run: '+name)
    dest = a.output/name
    if dest.exists():
        raise ValueError('Refusing overwrite: '+name)
    dest.mkdir(parents=True)
    manifest = []
    for file in sorted(source.iterdir()):
        if file.suffix not in ('.log', '.json', '.xml', '.cmd'):
            continue  # Never copy binaries, dumps, archives or unreviewed files.
        raw = file.read_bytes()
        target = dest/file.name
        if len(raw)>2*1024*1024:
            target = target.with_name(target.name+'.gz')
            target.write_bytes(gzip.compress(raw,mtime=0))
        else:
            shutil.copyfile(file,target)
        manifest.append({'file':file.name,'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                         'stored_as':target.name,'stored_sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    (dest/'collection.json').write_text(json.dumps({'scope':'Exact raw log bytes, lossless gzip when large; no binaries or ETL copied',
        'files':manifest},indent=2)+'\n')
    print(name, 'collected',len(manifest),'files')
