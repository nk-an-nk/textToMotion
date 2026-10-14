#!/usr/bin/env python3
"""Install pinned comparison models in dedicated Windows/Linux CUDA environments."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.setup_models import clone,CATALOG

CLIP='git+https://github.com/openai/CLIP.git@a1d071733d7111c9c014f024669f959182114e33'
ARCHIVES={
 'momask':[('1vXS7SHJBgWPt59wupQ5UUzhFObrnGkQ0','momask.zip','t2m')],
 'mmm':[('1y7N6GgnwLe9HF02-FplXVA7TZ6zJZRUV','mmm.zip','')],
 'motionlcm':[('1U7homKobR2gaDLfL5flS3N0g7e0a_AQd','models.zip',''),
              ('16hyR4XlEyksVyNVjhIWK684Lrm_7_pvX','eval.zip','deps/t2m'),
              ('1Mg_3RnWmRt0tk_lyLRRiOZg1W-Fu4wLL','tiny.zip','datasets')],
 'reactmotion':[('1tOw9wiu6jkzBy-bLe2iy47KAjE50DgjP','vqvae.zip',''),
                ('1FIiqtkt4F-GVWmnBgtZnv9W3cPWS-oM-','t2m.zip','')],
 'maai':[]}


def run(cmd,env,cwd=None):subprocess.run([str(v) for v in cmd],env=env,cwd=cwd,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',nargs='+',choices=list(ARCHIVES),default=list(ARCHIVES))
    p.add_argument('--data-dir',type=Path,default=ROOT/'.motion-lab')
    p.add_argument('--download',action='store_true');p.add_argument('--accept-model-license',action='store_true')
    a=p.parse_args();data=a.data_dir.resolve();data.mkdir(parents=True,exist_ok=True)
    if a.download and not a.accept_model_license:p.error('Read upstream model and dataset terms, then use --accept-model-license.')
    for model in a.models:
        repo=clone(CATALOG[model],data);folder=data/'envs'/model
        if not folder.exists():venv.EnvBuilder(with_pip=True).create(folder)
        python=folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        env=os.environ.copy();env.update(HF_HOME=str(data/'hf-cache'),HF_HUB_ENABLE_HF_TRANSFER='0',HF_HUB_DISABLE_XET='1')
        run([python,'-m','pip','install','torch==2.8.0','torchaudio==2.8.0','--index-url','https://download.pytorch.org/whl/cu128'],env)
        constraint=folder/'torch-constraint.txt';constraint.write_text('torch==2.8.0\ntorchaudio==2.8.0\nnumpy==1.26.4\n')
        env['PIP_CONSTRAINT']=str(constraint)
        common=['numpy==1.26.4','scipy==1.13.1','matplotlib==3.9.4','gdown==6.1.0','einops==0.8.1','PyYAML==6.0.2','tqdm','ftfy','psutil==7.0.0']
        if model in ['momask','mmm']:
            run([python,'-m','pip','install','setuptools==69.5.1','wheel'],env)
            common += ['plotly==5.24.1']
        elif model=='motionlcm':common+=['transformers==4.38.0','sentence-transformers==2.2.2','diffusers==0.24.0',
            'huggingface-hub==0.25.2','torchmetrics==1.3.2','tensorboard==2.15.1','omegaconf','hydra-core','rich','spacy']
        elif model=='reactmotion':common+=['transformers==4.51.3','huggingface-hub==0.30.2','sentencepiece==0.2.0','imageio==2.37.0','pandas==2.2.3']
        else:common+=['transformers==5.5.3','huggingface-hub','soundfile','onnxruntime-gpu','pygame','pydub','pyaudio',
            'PyQt5==5.15.11','PyQt5-Qt5==5.15.19','PyQt5-sip==12.17.0','pyqtgraph==0.14.0','seaborn']
        run([python,'-m','pip','install',*common],env)
        if model in ['momask','mmm']:run([python,'-m','pip','install','--no-build-isolation',CLIP],env)
        if model=='maai':run([python,'-m','pip','install','--no-deps','-e',repo],env)
        run([python,'-c','import torch;assert torch.cuda.is_available();x=torch.ones(32,32,device="cuda");assert torch.isfinite(x@x).all();torch.cuda.synchronize();print(torch.cuda.get_device_name(0))'],env)
        if a.download:
            downloads=data/'downloads'/model;downloads.mkdir(parents=True,exist_ok=True)
            weights=data/'checkpoints'/model;weights.mkdir(parents=True,exist_ok=True)
            receipts=[]
            for driveid,name,subdir in ARCHIVES[model]:
                archive=downloads/name
                if not archive.exists():run([python,'-m','gdown',driveid,'-O',archive],env)
                with zipfile.ZipFile(archive) as z:
                    for member in z.infolist():
                        path=Path(member.filename)
                        if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe model archive member.')
                        target=weights/subdir/path
                        if target.exists():continue
                        z.extract(member,weights/subdir)
                receipts.append({'google_drive_file_id':driveid,'filename':name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()})
            if model in ['motionlcm','reactmotion']:
                hf_repo,revision,dest=('sentence-transformers/sentence-t5-large',None,'sentence-t5-large') if model=='motionlcm' else ('awakening-ai/ReactMotion1.0','f00075813798ff957a4768fbe393283e4c36560e','generator')
                code='from huggingface_hub import snapshot_download;snapshot_download(repo_id='+repr(hf_repo)+',revision='+repr(revision)+',local_dir='+repr(str(weights/dest))+')'
                run([python,'-c',code],env)
            (weights/'download-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
        log=data/'logs';log.mkdir(exist_ok=True)
        freeze=subprocess.run([str(python),'-m','pip','freeze'],env=env,capture_output=True,text=True,check=True)
        (log/(model+'-versions.txt')).write_text(freeze.stdout)
        print(json.dumps({'model':model,'python':str(python),'ready_environment':True,'inference_verified':False}))


if __name__=='__main__':main()
