#!/usr/bin/env python3
"""Render the two prepared demo formats per model, with bounded CPU concurrency."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('reports/masked-models-20261016'))
    p.add_argument('--profile',choices=['lab_proxy','b300'],required=True)
    p.add_argument('--avatar',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);p.add_argument('--resume',action='store_true')
    p.add_argument('--wait-for-plans-seconds',type=float,default=0)
    a=p.parse_args()
    if not 1<=a.jobs<=4:raise ValueError('Use one to four render jobs.')
    base=a.root/a.profile;logs=base/'render-logs';logs.mkdir(parents=True,exist_ok=True)
    def render(model,kind):
        folder=base/(kind+'-video')/model;video=folder/('combined.mp4' if kind=='common' else 'dialogue.mp4')
        plan=folder/('manifest.json' if kind=='common' else 'plan.json');deadline=time.monotonic()+a.wait_for_plans_seconds
        while not plan.exists() and time.monotonic()<deadline:time.sleep(2)
        if not plan.exists():raise ValueError('Missing render plan: '+str(plan))
        receipt=video.with_suffix('.json')
        if video.exists() or receipt.exists():
            if a.resume and video.exists() and receipt.exists():
                m=json.loads(receipt.read_text())
                if hashlib.sha256(video.read_bytes()).hexdigest()==m['video_sha256']:
                    return {'model':model,'kind':kind,'status':'verified existing video','video':str(video)}
            raise RuntimeError('Existing output preserved: '+str(video))
        if kind=='common':
            cmd=['node','scripts/export_segmented_dialogue.cjs','--manifest',str(folder/'manifest.json'),'--avatar',str(a.avatar),'--output',str(video),'--upper-body']
        else:
            cmd=['node','scripts/export_upper_body_dialogue.cjs','--plan',str(folder/'plan.json'),'--avatar',str(a.avatar),'--output',str(video)]
        started=time.monotonic();log=logs/(model+'-'+kind+'.log')
        with log.open('x') as f:result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(str(log)+': '+log.read_text()[-2000:])
        return {'model':model,'kind':kind,'status':'rendered','seconds':time.monotonic()-started,'video':str(video)}
    results=[]
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures=[pool.submit(render,m,k) for m in ['momask','remomask2','molingo'] for k in ['dialogue','common']]
        for f in as_completed(futures):
            result=f.result();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    (base/'render-summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
