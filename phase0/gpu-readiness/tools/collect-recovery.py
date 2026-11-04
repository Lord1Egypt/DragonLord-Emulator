#!/usr/bin/env python3
"""Collect exact small native text artifacts, including separate JSONL traces, without overwrite."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Fresh output required')
    a.output.mkdir(parents=True)
    records=[]
    for run in sorted((a.native_root/'results').iterdir()):
        if not run.is_dir():continue
        for f in sorted(run.iterdir()):
            if not f.is_file() or f.suffix not in ('.json','.jsonl','.log','.cmd','.xml'):continue
            if f.stat().st_size>5*1024*1024:raise ValueError('Artifact too large; inspect before publication: '+str(f))
            target=a.output/run.name/f.name;target.parent.mkdir(exist_ok=True)
            shutil.copyfile(f,target);raw=target.read_bytes()
            records.append({'path':target.relative_to(a.output).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    (a.output/'collection.json').write_text(json.dumps({'scope':'Exact raw text/log/JSONL bytes; binaries excluded','files':records},indent=2)+'\n')
    print('Collected',len(records),'artifacts without altering originals')


if __name__=='__main__':main()
