#!/usr/bin/env python3
"""Strict trace-format validation. Parse PASS never qualifies hardware or lifetime safety."""
import argparse
import json
from pathlib import Path


def parse(path):
    events=[]
    for number,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.startswith('DLK '):
            raise ValueError(f'Unexpected trace content at source line {number}')
        event=json.loads(line[4:])
        if not isinstance(event,dict) or not isinstance(event.get('event'),str):
            raise ValueError(f'Missing event identity at source line {number}')
        events.append(event)
    children=[e for e in events if e['event']=='child']
    exits=[e for e in events if e['event']=='exit']
    samples=[e for e in events if e['event']=='sample']
    if len(children)!=1 or len(exits)!=1 or not samples:
        raise ValueError('Incomplete trace; require one child, one exit and samples')
    pid=children[0]['pid']
    if pid<=0 or any(s['pid']!=pid for s in samples) or exits[0]['pid']!=pid:
        raise ValueError('Trace PID mismatch')
    if exits[0]['code']!=0 or exits[0]['timeout']:
        raise ValueError('Child failed or timed out')
    valid=[s for s in samples if s['status']==0]
    if any(s['running_time_raw']<0 for s in valid):
        raise ValueError('Successful kernel sample carries invalid sentinel')
    return {'scope':'Trace format/completion only; no hardware qualification or timing-unit inference',
            'status':'PASS','pid':pid,'samples':len(samples),'valid_samples':len(valid),
            'invalid_samples':len(samples)-len(valid),
            'observed_adapters':[e for e in events if e['event']=='adapter'],
            'modules':[e['path'] for e in events if e['event']=='module'],
            'max_running_time_raw':max((s['running_time_raw'] for s in valid),default=None)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Fresh output required')
    try: result=parse(a.trace)
    except (ValueError,KeyError,OSError) as e:
        result={'status':'FAIL','scope':'Trace format/completion only','reason':str(e)}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
