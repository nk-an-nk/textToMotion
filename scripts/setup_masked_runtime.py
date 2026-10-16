#!/usr/bin/env python3
"""Run inside the owned CUDA Pod; retain assets and an environment archive on its volume.

Requires /workspace/retained/bootstrap from prepare_masked_bootstrap.py and the
verified MoMask archive at /workspace/retained/assets/momask-weights.tar.gz.
No OpenAI, Hugging Face or RunPod credential is used on the GPU machine.
"""
import concurrent.futures,hashlib,json,os,shutil,subprocess,sys,tarfile,time,urllib.request,zipfile
from pathlib import Path
BASE=Path('/tmp/masked_runtime');KEEP=Path('/workspace/retained');BASE.mkdir(exist_ok=True);KEEP.mkdir(exist_ok=True)
meta=json.loads((KEEP/'bootstrap/asset-manifest.json').read_text())
def run(args,cwd=None):
 subprocess.run([str(x) for x in args],cwd=cwd,check=True)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(16*1024*1024):h.update(b)
 return h.hexdigest()
def download(url,path,size=None,sha=None):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and (not size or path.stat().st_size==size) and (not sha or digest(path)==sha):return
 temp=path.with_name(path.name+'.partial')
 for attempt in range(3):
  try:
   with urllib.request.urlopen(url,timeout=120) as r,temp.open('wb') as f:
    while b:=r.read(4*1024*1024):f.write(b)
   if size and temp.stat().st_size!=size:raise ValueError('Size mismatch: '+path.name)
   if sha and digest(temp)!=sha:raise ValueError('Hash mismatch: '+path.name)
   temp.replace(path);return
  except Exception:
   if attempt==2:raise
 print('download_complete',path.name,flush=True)
def range_download(url,path,size,sha):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists() and path.stat().st_size==size and digest(path)==sha:return
 chunk=32*1024*1024;count=(size+chunk-1)//chunk
 def piece(i):
  start=i*chunk;end=min(size,(i+1)*chunk)-1;p=path.with_name(path.name+f'.part{i:04d}')
  if p.exists() and p.stat().st_size==end-start+1:return
  for attempt in range(3):
   try:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'}),timeout=90) as r,p.open('wb') as f:
     if r.status!=206:raise ValueError('Expected ranged download')
     while b:=r.read(4*1024*1024):f.write(b)
    if p.stat().st_size!=end-start+1:raise ValueError('Incomplete range')
    return
   except Exception:
    if attempt==2:raise
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(piece,range(count)))
 temp=path.with_name(path.name+'.partial')
 with temp.open('wb') as f:
  for i in range(count):
   p=path.with_name(path.name+f'.part{i:04d}')
   with p.open('rb') as src:shutil.copyfileobj(src,f,4*1024*1024)
   p.unlink()
 if temp.stat().st_size!=size or digest(temp)!=sha:raise ValueError('Archive hash mismatch')
 temp.replace(path)
print('SETUP_START',flush=True)
venv=BASE/'venv'
if not (venv/'bin/python').exists():run([sys.executable,'-m','venv','--system-site-packages',venv])
py=venv/'bin/python'
os.environ.update(PIP_CACHE_DIR='/workspace/cache/pip',MPLCONFIGDIR='/tmp/masked_runtime/mpl',HF_HOME='/workspace/cache/hf')
run([py,'-m','pip','install','--progress-bar','off','setuptools==69.5.1','wheel','numpy==1.26.4','scipy==1.13.1','transformers==4.51.3','huggingface-hub==0.33.1','sentencepiece==0.2.0','protobuf','einops==0.8.1','ftfy','regex','psutil==7.0.0','matplotlib==3.9.4','tensorboard==2.19.0','hydra-core==1.3.2','omegaconf==2.3.0'])
run([py,'-m','pip','install','--no-deps','--no-build-isolation','git+https://github.com/openai/CLIP.git@dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1'])
run([py,'-c','import torch,torchvision; assert torch.cuda.is_available(); x=torch.randn(32,32,device="cuda"); assert torch.isfinite(x@x).all();torch.cuda.synchronize();print(torch.__version__,torch.version.cuda,torch.cuda.get_device_name(0))'])
for name,url,rev in meta['sources']:
 repo=BASE/'upstreams'/name
 if not repo.exists():run(['git','clone','--quiet','--depth','1',url,repo])
 head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
 if head!=rev:run(['git','-C',repo,'fetch','--quiet','--depth','1','origin',rev]);run(['git','-C',repo,'checkout','--quiet','--detach',rev])
print('DEPENDENCIES_AND_SOURCE_READY',flush=True)
# Archives remain on the persistent volume. Runtime weights use local /tmp IO.
for row in meta['molingo_archives']:
 path=KEEP/'assets/molingo'/row['name'];range_download(row['url'],path,row['bytes'],row['sha256'])
 dest=BASE/'weights/molingo';dest.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(path) as z:
  for member in z.infolist():
   p=Path(member.filename)
   if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe model zip')
   if not (dest/p).exists():z.extract(member,dest)
 print('MOLINGO_ARCHIVE_READY',row['name'],flush=True)
for folder in ['normalization','t5-tokenizer']:
 shutil.copytree(KEEP/'bootstrap/assets/molingo'/folder,BASE/'weights/molingo'/folder,dirs_exist_ok=True)
print('MOLINGO_READY',flush=True)
rem=KEEP/'assets/remomask2';rem.mkdir(parents=True,exist_ok=True)
rows=[x for x in meta['remomask_files'] if x.get('type')=='file' and not x['path'].startswith('.') and x['path']!='README.md']
def rem_file(row):
 name=row['path'];download('https://huggingface.co/AIGeeksGroup/ReMoMask-2/resolve/cee377d8361177f0eba1aff57161a20e01ca742e/'+name+'?download=true',rem/name,row['size'],row.get('lfs',{}).get('oid'))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(rem_file,rows))
layout={'net_best_fid_ep0309.tar':'logs/humanml3d/v2_mtrans_vgate/model/net_best_fid_ep0309.tar','model_opt.txt':'logs/humanml3d/v2_mtrans_vgate/opt.txt','vq.tar':'logs/humanml3d/pretrain_vq/model/net_best_fid.tar','vq_opt.txt':'logs/humanml3d/pretrain_vq/opt.txt','mean.npy':'logs/humanml3d/pretrain_vq/meta/mean.npy','std.npy':'logs/humanml3d/pretrain_vq/meta/std.npy','encoded_motions.npy':'database_ze/encoded_motions.npy','encoded_texts_clip.npy':'database_ze/encoded_texts_clip.npy','motion_ids.npy':'database_ze/motion_ids.npy','all_captions.npy':'database_ze/all_captions.npy','query_projector.pt':'query_projector.pt'}
for name,rel in layout.items():
 dst=BASE/'weights/remomask2'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(rem/name,dst)
archive=KEEP/'assets/momask-weights.tar.gz'
if digest(archive)!=meta['momask_archive_sha256']:raise ValueError('MoMask archive hash mismatch')
with tarfile.open(archive) as t:t.extractall(BASE,filter='data')
print('REMOMASK_AND_MOMASK_READY',flush=True)
run([py,'-c','import clip;clip.load("ViT-B/32",device="cpu",download_root="/workspace/cache/clip");print("CLIP_READY")'])
shutil.copytree(KEEP/'bootstrap/project',BASE/'project',dirs_exist_ok=True)
versions=subprocess.check_output([str(py),'-m','pip','freeze'],text=True);(KEEP/'versions.txt').write_text(versions)
(KEEP/'resume.sh').write_text('#!/bin/bash\nset -e\npython /workspace/retained/bootstrap/remote_setup.py\n')
# Preserve installed environment and exact source, not only a package list.
with tarfile.open(KEEP/'runtime-environment.tar.gz','w:gz',compresslevel=1) as t:
 t.add(venv,arcname='venv')
 t.add(BASE/'upstreams',arcname='upstreams',filter=lambda i: None if '/mogen/body_models/' in i.name else i)
 t.add(BASE/'project',arcname='project')
(KEEP/'SETUP_DONE').write_text('ready\n');print('SETUP_DONE',flush=True)
