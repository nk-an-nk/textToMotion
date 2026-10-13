#!/usr/bin/env python3
"""Pinned source/dependency setup, explicit license/capacity checks, no paid cloud provisioning."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CATALOG = {m['id']:m for m in json.loads((ROOT/'configs/models.json').read_text())}


def run(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


def get_json(url):
    request = urllib.request.Request(url)
    # Credentials only in a supported Authorization header, never in a URL, log, or saved file.
    token = os.environ.get('HF_TOKEN')
    if token:
        request.add_header('Authorization','Bearer ' + token)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def clone(model, data):
    target = data/'upstreams'/model['id']
    if target.exists():
        result = subprocess.run(['git','-C',str(target),'rev-parse','HEAD'],capture_output=True,text=True,check=True)
        if result.stdout.strip() != model['commit']:
            raise RuntimeError(f"{target}: commit differs. Preserve local work and inspect it; this script never resets it.")
        return target
    target.parent.mkdir(parents=True,exist_ok=True)
    run(['git','init',target])
    run(['git','-C',target,'remote','add','origin','https://github.com/'+model['repo']+'.git'])
    run(['git','-C',target,'fetch','--depth','1','origin',model['commit']])
    env=os.environ.copy();env['GIT_LFS_SKIP_SMUDGE']='1'
    run(['git','-C',target,'checkout','--detach','FETCH_HEAD'],env=env)
    return target


def install(model_id, data, device, demo):
    if model_id not in ('ardy','kimodo'):
        raise RuntimeError('Automated installer currently supports ARDY and Kimodo only. See official commands in docs/gpu_setup.md for other models.')
    source=clone(CATALOG[model_id],data)
    environment=data/'envs'/model_id
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    interpreter=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not interpreter.is_file():
        raise RuntimeError('Existing model environment is invalid; inspect before replacing it.')
    env=os.environ.copy();env['PATH']=str(interpreter.parent)+os.pathsep+env.get('PATH','')
    if device=='cuda':
        run([interpreter,'-m','pip','install','--no-cache-dir','torch==2.9.0+cu126','--index-url','https://download.pytorch.org/whl/cu126'],env=env)
    else:
        run([interpreter,'-m','pip','install','--no-cache-dir','torch==2.9.0+cpu','--index-url','https://download.pytorch.org/whl/cpu'],env=env)
    run([interpreter,'-m','pip','install','--no-cache-dir','cmake==3.31.6','setuptools==78.1.0','wheel==0.45.1'],env=env)
    locked=ROOT/'configs'/f'requirements-{model_id}-{device}.lock'
    if locked.exists():
        # PyTorch was selected explicitly above; prevent registry defaults from replacing it.
        run([interpreter,'-m','pip','install','--no-cache-dir','-r',locked],env=env)
        run([interpreter,'-m','pip','install','--no-cache-dir','--no-build-isolation','--no-deps',source],env=env)
    else:
        run([interpreter,'-m','pip','install','--no-cache-dir','--no-build-isolation',source],env=env)
    if demo:
        run([interpreter,'-m','pip','install','--no-cache-dir',model_id+'[demo]'],env=env)
    run([interpreter,'-m','pip','check'],env=env)
    logs=data/'logs';logs.mkdir(parents=True,exist_ok=True)
    versions=subprocess.run([interpreter,'-m','pip','freeze'],capture_output=True,text=True,check=True)
    (logs/(model_id+'-'+device+'-versions.txt')).write_text(versions.stdout)
    command=[interpreter,'scripts/generate.py','--help'] if model_id=='ardy' else [interpreter,'-m','kimodo.scripts.generate','--help']
    run(command,cwd=source,env=env)


def download(model_id,data,max_gb,accepted):
    if not accepted:
        raise RuntimeError('Read the official model license first and pass --accept-model-license. This does not accept gated Llama/SMPL-X terms on your behalf.')
    model=CATALOG[model_id]
    if model_id not in ('ardy','kimodo','language_of_motion','streamtalk'):
        raise RuntimeError('No verified checkpoint download mapping for this model.')
    repo=model['checkpoint']
    metadata=get_json('https://huggingface.co/api/models/'+repo+'?blobs=true')
    total=sum(item.get('size',0) for item in metadata['siblings'])
    free=shutil.disk_usage(data).free
    print(json.dumps({'repo':repo,'revision':metadata['sha'],'download_bytes':total,'free_bytes':free,'license':metadata.get('cardData',{}).get('license')}))
    if total > max_gb*2**30 or free < total*1.3+2**30:
        raise RuntimeError('Download exceeds the explicit budget or leaves insufficient free disk space.')
    interpreter=data/'envs'/model_id/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not interpreter.is_file():
        raise RuntimeError('Install the isolated model environment (with huggingface_hub) first.')
    destination=data/'checkpoints'/model_id/(repo.split('/')[-1])
    destination.mkdir(parents=True,exist_ok=True)
    worker="from huggingface_hub import snapshot_download; import sys; snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_dir=sys.argv[3])"
    env=os.environ.copy();env.update(HF_HOME=str(data/'hf-cache'),HF_HUB_DISABLE_XET='1')
    run([interpreter,'-c',worker,repo,metadata['sha'],destination],env=env)
    checksums={}
    for file in metadata['siblings']:
        path=destination/file['rfilename']
        if not path.is_file() or path.stat().st_size!=file.get('size',path.stat().st_size):
            raise RuntimeError('Downloaded artifact size mismatch: '+file['rfilename'])
        hasher=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):hasher.update(chunk)
        value=hasher.hexdigest()
        expected=file.get('lfs',{}).get('sha256')
        if expected and value!=expected:
            raise RuntimeError('Official LFS SHA256 verification failed: '+file['rfilename'])
        checksums[file['rfilename']]=value
    (destination/'motion-lab-download.json').write_text(json.dumps({'repo':repo,'revision':metadata['sha'],'license':metadata.get('cardData',{}).get('license'),'sha256':checksums},indent=2))
    print('Weights downloaded and verified. Configure the separate text encoder / licensed body assets before inference.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',nargs='+',choices=CATALOG,default=['ardy'])
    parser.add_argument('--data-dir',default=os.environ.get('MOTION_LAB_DATA',ROOT/'.motion-lab'))
    parser.add_argument('--clone',action='store_true')
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--accept-model-license',action='store_true')
    parser.add_argument('--max-download-gb',type=float,default=2)
    args=parser.parse_args();data=Path(args.data_dir).resolve();data.mkdir(parents=True,exist_ok=True)
    failures=[]
    for model_id in args.models:
        try:
            if args.clone:clone(CATALOG[model_id],data)
            if args.install:install(model_id,data,args.device,args.demo)
            if args.download:download(model_id,data,args.max_download_gb,args.accept_model_license)
            if not any([args.clone,args.install,args.download]):print(model_id, 'Select --clone, --install, or --download.')
        except Exception as error:
            from adapters.base import redact
            failures.append(model_id);print(model_id+': '+redact(str(error)),file=sys.stderr)
    sys.exit(bool(failures))
