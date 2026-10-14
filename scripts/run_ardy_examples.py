#!/usr/bin/env python3
"""Run utterances through the running local app queue; print timings and save CSV."""
import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.base import redact
from app.timing import csv_bytes,summary_row


def request(base,path,data=None):
    encoded=json.dumps(data).encode('utf-8') if data is not None else None
    headers={'Content-Type':'application/json'} if encoded is not None else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(base+path,data=encoded,headers=headers),timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(redact(error.read().decode('utf-8',errors='replace'))) from error


def run_batch(base,examples,directory,timeout=1800,models=None):
    models=models or ['ardy']
    health=request(base,'/api/health')
    if health.get('status')!='ok':raise RuntimeError('Start Motion Lab first.')
    catalog={item['id']:item for item in request(base,'/api/models')}
    for name in models:
        model=catalog.get(name)
        if not model or not model.get('can_generate') or model.get('backend')!='local':
            raise RuntimeError(f'Local text-conditioned {name} is not ready. Complete setup first; no fallback.')
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    rows=[]
    cases=[(example,model) for example in examples for model in models]
    for index,(example,model) in enumerate(cases,1):
        print(f"[{index}/{len(cases)}] {model}: {example['input_text']} -> {example['model_text']}",flush=True)
        record={'model_id':model,'input_text':example['input_text'],'model_text':example['model_text'],
                'status':'failed','duration_requested':example['duration'],'seed':example['seed']}
        video=''
        try:
            record=request(base,'/api/generate',{'model_name':model,'task_type':'instruction',
                           'text':example['input_text'],'translated_text':example['model_text'],
                           'duration':example['duration'],'seed':example['seed']})
            deadline=time.monotonic()+timeout
            while record['status'] in ('queued','running') and time.monotonic()<deadline:
                time.sleep(.3)
                record=request(base,'/api/experiments/'+record['id'])
            if record['status']!='succeeded':
                raise RuntimeError(record.get('error','Generation did not finish before the timeout.'))
            if record.get('device')!='cuda':
                raise RuntimeError('Expected CUDA motion generation; CPU output is not a successful lab GPU run.')
            request(base,f"/api/experiments/{record['id']}/render",{})
            record=request(base,'/api/experiments/'+record['id'])
            video=base+f"/api/experiments/{record['id']}/files/{record['artifacts']['rendered_video_path']}"
            values=record.get('timings',{})
            if any(values.get(key) is None for key in ('skeleton_seconds','mp4_render_seconds','total_seconds')):
                raise RuntimeError('Timing fields are missing. Restart the app using the current source.')
            print(f"  骨格まで: {values['skeleton_seconds']:.2f}秒 / MP4まで: {values['total_seconds']:.2f}秒 "
                  f"（書き出し: {values['mp4_render_seconds']:.2f}秒）",flush=True)
            print('  MP4: '+video,flush=True)
        except Exception as error:
            if record.get('id'):
                try:record=request(base,'/api/experiments/'+record['id'])
                except Exception:pass
            record={**record,'status':'failed','error':redact(str(error))}
            print('  失敗: '+record['error'],flush=True)
        row=summary_row(record,video)
        row['example_group']=example.get('group','')
        rows.append(row)
        # Save after each attempt, retaining prior successes if interrupted.
        (directory/'summary.csv').write_bytes(csv_bytes(rows))
        (directory/'records.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CSV: '+str((directory/'summary.csv').resolve()),flush=True)
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--examples',type=Path,default=ROOT/'configs/ardy-utterances.json')
    parser.add_argument('--group',choices=['all','short','medium'],default='all')
    parser.add_argument('--models',default='ardy')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'.motion-lab/batches')
    args=parser.parse_args()
    models=[name.strip() for name in args.models.split(',')]
    if len(models)!=len(set(models)) or any(name not in ('ardy','kimodo','text_to_vrma') for name in models):
        raise ValueError('models must select ardy, kimodo and/or text_to_vrma without duplicates.')
    examples=json.loads(args.examples.read_text(encoding='utf-8'))
    if args.group!='all':examples=[item for item in examples if item.get('group')==args.group]
    if not examples or not all(isinstance(item,dict) and item.get('input_text') and item.get('model_text')
                               and .5<=item.get('duration',0)<=20 and isinstance(item.get('seed'),int) for item in examples):
        raise ValueError('Each example requires input_text, model_text, duration, and seed.')
    stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y%m%d-%H%M%S')
    rows=run_batch(args.url.rstrip('/'),examples,args.output_dir/(stamp+'-'+uuid.uuid4().hex[:8]),models=models)
    return 0 if all(row['status']=='succeeded' for row in rows) else 1


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print(redact(str(error)),file=sys.stderr)
        sys.exit(1)
