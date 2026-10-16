#!/usr/bin/env python3
"""Bounded experiment Pods: STOP at the deadline; retain data for 24 hours.

The local watcher is best effort and must be restarted after this environment is
replaced. Never treats a provider stop request as confirmed deletion/termination.
API credentials remain on the controlling cloud machine, never inside GPU Pods.
"""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.runpod_trial import api,save,owned_pod
from scripts.runpod_plan import graphql


def account():
    return graphql('query { myself { clientBalance currentSpendPerHr } }',authenticated=True)['myself']


def stop(path,reason):
    state=json.loads(path.read_text());pod=owned_pod(state)
    if not pod:raise RuntimeError('Owned Pod not found; retained data cannot be confirmed.')
    if state.get('stop_confirmed') and pod.get('desiredStatus') in ['EXITED','STOPPED']:return state
    if pod.get('desiredStatus') not in ['EXITED','STOPPED']:
        api('POST','/pods/'+state['pod_id']+'/stop')
    for _ in range(12):
        pod=owned_pod(state)
        if pod and pod.get('desiredStatus') in ['EXITED','STOPPED']:
            at=time.time();state.update(stopped_at_utc=datetime.now(timezone.utc).isoformat(),
                stopped_epoch=at,stop_confirmed=True,stop_reason=reason,
                retention_until_epoch=at+state['retention_hours']*3600,
                retention_until_utc=datetime.fromtimestamp(at+state['retention_hours']*3600,timezone.utc).isoformat())
            save(path,state);return state
        time.sleep(2)
    raise RuntimeError('Stop is requested but not confirmed; inspect the Pod.')


def tick(root):
        config=json.loads((root/'credit-budget-private.json').read_text())
        states=list(root.glob('*/state.json'))
        running=[]
        for path in states:
            state=json.loads(path.read_text())
            if not state.get('pod_id') or state.get('deleted_at_utc'):continue
            if state.get('stop_confirmed'):
                if time.time()>=state['retention_until_epoch']:
                    pod=owned_pod(state)
                    if pod:api('DELETE','/pods/'+state['pod_id'])
                    if owned_pod(state):raise RuntimeError('Retention cleanup is not confirmed.')
                    state.update(deleted_at_utc=datetime.now(timezone.utc).isoformat(),deletion_confirmed=True)
                    save(path,state);print('Expired retained experiment Pod removed.',flush=True)
            else:running.append((path,state))
        if running:
            remaining=account().get('clientBalance')
            for path,state in running:
                if time.time()>=state['deadline_epoch'] or remaining is None or remaining<=config['retained_storage_reserve_usd']+.25:
                    stop(path,'compute deadline or reserved remaining-credit threshold')
                    print('Owned experiment Pod stopped; persistent volume retained.',flush=True)


def watch(root):
    while True:
        try:tick(root)
        except Exception as error:
            print(datetime.now(timezone.utc).isoformat()+' watcher retry: '+type(error).__name__,flush=True)
        time.sleep(20)


def create(root,profile,minutes):
    if not math.isfinite(minutes) or minutes<=0:raise ValueError('Positive finite compute minutes required.')
    folder=root/profile;folder.mkdir(parents=True,exist_ok=True);path=folder/'state.json'
    if path.exists():raise RuntimeError('Existing experiment state is preserved.')
    config=json.loads((root/'credit-budget-private.json').read_text());balance=account()['clientBalance']
    gpu='NVIDIA GeForce RTX 4090' if profile=='lab_proxy' else 'NVIDIA B300 SXM6 AC'
    hourly=.89 if profile=='lab_proxy' else 8.99
    reserve=config['retained_storage_reserve_usd']+.25
    if balance<=reserve or hourly*minutes/60+reserve>balance:
        raise RuntimeError('Requested runtime cannot fit remaining credit and 24h storage reserve.')
    token=secrets.token_urlsafe(32);auth=folder/'auth.json';auth.write_text(json.dumps({'token':token}));auth.chmod(0o600)
    name='motion-masked-'+profile.replace('_','-')+'-'+uuid.uuid4().hex[:8]
    state={'schema':'motion-lab/retained-runpod-v1','pod_name':name,'pod_id':None,'profile':profile,
           'started_at_utc':datetime.now(timezone.utc).isoformat(),'started_epoch':time.time(),
           'deadline_epoch':time.time()+minutes*60,'max_minutes':minutes,'retention_hours':24,
           'stop_confirmed':False,'no_automatic_deposit':True}
    save(path,state)
    command='exec python -m jupyter lab --allow-root --no-browser --ip=0.0.0.0 --port=8888 --IdentityProvider.token="$JUPYTER_PASSWORD" --ServerApp.root_dir=/'
    body={'name':name,'cloudType':'SECURE','computeType':'GPU','gpuTypeIds':[gpu],'gpuTypePriority':'custom',
          'gpuCount':1,'imageName':'runpod/pytorch:1.4.0-cu1290-torch280-ubuntu2404',
          'dockerEntrypoint':['/bin/bash','-lc'],'dockerStartCmd':[command],
          'containerDiskInGb':40,'volumeInGb':40,'volumeMountPath':'/workspace','ports':['8888/http'],
          'supportPublicIp':True,'interruptible':False,'minVCPUPerGPU':8,'minRAMPerGPU':32,
          'env':{'JUPYTER_PASSWORD':token,'NVIDIA_DRIVER_CAPABILITIES':'compute,utility'}}
    try:pod=api('POST','/pods',body)
    except Exception:
        found=[p for p in api('GET','/pods') if p.get('name')==name]
        if len(found)!=1:raise
        pod=found[0]
    actual=float(pod['costPerHr'])
    state.update(pod_id=pod['id'],cost_per_hour_usd=actual,image=body['imageName'],container_disk_gb=40,
                 volume_gb=40,gpu=gpu,allocated_vcpu=pod.get('vcpuCount'),allocated_ram_gb=pod.get('memoryInGb'))
    save(path,state)
    if actual>hourly+.001 or actual*minutes/60+reserve>balance:
        stop(path,'unexpected quote exceeds reserved budget');raise RuntimeError('Quote mismatch; Pod stopped.')
    return {k:state[k] for k in ['pod_id','profile','cost_per_hour_usd','max_minutes','retention_hours']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('create');c.add_argument('--profile',choices=['lab_proxy','b300'],required=True);c.add_argument('--minutes',type=float,required=True)
    s=sub.add_parser('stop');s.add_argument('--profile',choices=['lab_proxy','b300'],required=True)
    sub.add_parser('watch');a=p.parse_args();root=a.root.resolve()
    if a.action=='watch':watch(root)
    elif a.action=='create':print(json.dumps(create(root,a.profile,a.minutes)))
    else:
        d=stop(root/a.profile/'state.json','experiment completed; retain data 24 hours')
        print(json.dumps({k:d[k] for k in ['pod_id','stop_confirmed','retention_until_utc']}))
