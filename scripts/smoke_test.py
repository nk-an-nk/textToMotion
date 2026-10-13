#!/usr/bin/env python3
"""Functional API smoke; fixture checks do not count as trained model inference."""
import argparse
import json
import sys
import time
import urllib.request


def request(base,path,data=None):
    req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
                               headers={'Content-Type':'application/json'} if data is not None else {})
    with urllib.request.urlopen(req,timeout=30) as result:return json.load(result)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--model',help='Optional REAL-model inference; no fixture fallback.')
    parser.add_argument('--prompt',default='Raise your right hand and wave for three seconds.')
    parser.add_argument('--timeout',type=int,default=900)
    args=parser.parse_args()
    health=request(args.url,'/api/health')
    assert health['status']=='ok' and health['viewer_assets_present']
    if args.model:
        record=request(args.url,'/api/generate',{'model_name':args.model,'task_type':'instruction','text':args.prompt,'duration':3,'seed':0})
        deadline=time.monotonic()+args.timeout
        while record['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(1)
            record=request(args.url,'/api/experiments/'+record['id'])
        if record['status']!='succeeded':
            print(json.dumps(record,ensure_ascii=False,indent=2));sys.exit(1)
        assert record['artifacts'].get('original_motion_path') and record['artifacts'].get('normalized_motion_path')
        print('REAL official-model inference passed:',record['id'])
    else:
        record=request(args.url,'/api/viewer-fixture',{})
        motion=request(args.url,f"/api/experiments/{record['id']}/files/motion.json")
        assert motion['schema']=='motion-lab/v1' and len(motion['positions'])==120
        assert motion['metadata']['trained_model_output'] is False
        print('Application / viewer-fixture functional smoke passed. No pretrained inference executed.')
