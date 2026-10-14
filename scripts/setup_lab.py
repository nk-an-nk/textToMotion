#!/usr/bin/env python3
"""Resumable user-owned local GPU setup; invoked by the Windows PowerShell entry point."""
import argparse
import datetime
import getpass
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.base import redact

CATALOG={item['id']:item for item in json.loads((ROOT/'configs/models.json').read_text(encoding='utf-8'))}
TORCH_PROBE=(
    'import json,torch; assert torch.cuda.is_available(), "CUDA unavailable; update the Windows NVIDIA driver"; '
    'x=torch.randn((64,64),device="cuda"); y=x@x; torch.cuda.synchronize(); '
    'assert torch.isfinite(y).all(); '
    'print(json.dumps({"torch":torch.__version__,"cuda":torch.version.cuda,'
    '"gpu":torch.cuda.get_device_name(0),"capability":torch.cuda.get_device_capability(0)}))'
)


def load_json(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else (default or {})


def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def interpreter(folder):
    return Path(folder)/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def fingerprint(files,options):
    value=hashlib.sha256(json.dumps(options,sort_keys=True).encode())
    for file in files:
        value.update(Path(file).read_bytes())
    return value.hexdigest()


def validate_profile(profile):
    models=profile.get('models')
    if not models or len(models)!=len(set(models)) or any(model not in ('kimodo','ardy','text_to_vrma') for model in models):
        raise ValueError('models must select kimodo, ardy and/or text_to_vrma without duplicates.')
    if 'text_to_vrma' in models and ('ardy' not in models or models.index('ardy')>models.index('text_to_vrma')):
        raise ValueError('Select ardy before text_to_vrma: it shares the verified ARDY environment and weights.')
    if profile.get('cuda_build') not in ('cu126','cu128'):
        raise ValueError('Unsupported CUDA build.')
    if profile.get('text_encoder_device')!='cpu':
        raise ValueError('The 12GB lab profile requires text_encoder_device=cpu.')
    if not isinstance(profile.get('port'),int) or not 1024<=profile['port']<=65535:
        raise ValueError('port must be 1024–65535.')
    if not isinstance(profile.get('min_free_gib'),(int,float)) or profile['min_free_gib']<1:
        raise ValueError('min_free_gib must be positive.')


def preflight():
    checks={'python':platform.python_version(),'platform':platform.platform(),
            'commands':{name:bool(shutil.which(name)) for name in ('git','node','npm','ffmpeg','nvidia-smi')}}
    if checks['commands']['nvidia-smi']:
        result=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version',
                               '--format=csv,noheader,nounits'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        checks['gpu_query_exit_code']=result.returncode
        checks['gpu']=result.stdout.strip() if result.returncode==0 else 'NVIDIA GPU query failed.'
    return checks


class Runner:
    def __init__(self,log,env):
        self.log=Path(log)
        self.env=env

    def run(self,command,*,cwd=ROOT,capture=False):
        # No shell interpolation and no environment dump. HF input stays hidden.
        collected=[]
        with self.log.open('a',encoding='utf-8') as log:
            with subprocess.Popen([str(arg) for arg in command],cwd=cwd,env=self.env,
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,encoding='utf-8',errors='replace') as process:
                for line in process.stdout:
                    safe=redact(line)
                    log.write(safe)
                    if capture:collected.append(safe)
                    else:print(safe,end='',flush=True)
                code=process.wait()
        if code:
            raise RuntimeError(f'Command failed (exit {code}); see {self.log}. Rerun setup to resume.')
        return ''.join(collected)


def checkpoint_valid(data,model):
    folder=Path(data)/'checkpoints'/model/CATALOG[model]['checkpoint'].split('/')[-1]
    manifest=load_json(folder/'motion-lab-download.json')
    if manifest.get('repo')!=CATALOG[model]['checkpoint'] or not manifest.get('sha256'):
        return False
    for name,expected in manifest['sha256'].items():
        path=folder/name
        if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file():return False
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(4*1024*1024),b''):digest.update(chunk)
        if digest.hexdigest()!=expected:
            raise RuntimeError(f'Existing checkpoint changed: {path}. Inspect it before replacing anything.')
    return True


def result_valid(data,result):
    if result.get('status')!='succeeded' or result.get('device')!='cuda':return False
    identifier=result.get('experiment_id','')
    if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):return False
    directory=Path(data)/'outputs'/identifier
    record=load_json(directory/'experiment.json')
    original='original.vrma' if result.get('model')=='text_to_vrma' else 'original.npz'
    if not (record.get('status')=='succeeded' and record.get('task_type')=='instruction'
            and record.get('model_id')==result.get('model') and record.get('device')=='cuda'
            and all((directory/name).is_file() for name in (original,'motion.json','video.mp4'))):return False
    motion=load_json(directory/'motion.json')
    return motion.get('metadata',{}).get('trained_model_output') is True


def prepare_app(runner,state,save):
    folder=ROOT/'.venv'
    python=interpreter(folder)
    signature=fingerprint([ROOT/'requirements-app.lock',ROOT/'package-lock.json',ROOT/'pyproject.toml'],
                          {'python':platform.python_version()})
    if folder.exists() and not python.is_file():
        raise RuntimeError('Existing .venv is invalid; inspect it. Setup never deletes environments.')
    if state.get('app')!=signature or not (ROOT/'node_modules/three/package.json').is_file():
        if not folder.exists():venv.EnvBuilder(with_pip=True).create(folder)
        runner.run([python,'-m','pip','install','--no-cache-dir','-r',ROOT/'requirements-app.lock'])
        runner.run([python,'-m','pip','install','--no-deps','-e',ROOT])
        runner.run([shutil.which('npm'),'ci','--cache',runner.env['MOTION_LAB_NPM_CACHE']])
        state['app']=signature
        save()
    runner.run([python,'-m','pip','check'])
    runner.run([python,'-c','import fastapi,numpy,scipy,matplotlib; print("Application imports OK")'])
    return python


def setup(args,profile):
    if not args.accept_model_license:
        raise RuntimeError('Read reports/licenses.md and the NVIDIA model agreement; then use -AcceptModelLicense. Llama approval is separate.')
    if sys.version_info[:2]!=(3,12):
        raise RuntimeError('This Windows profile uses Python 3.12 x64.')
    checks=preflight()
    missing=[name for name,present in checks['commands'].items() if not present]
    if missing or checks.get('gpu_query_exit_code')!=0:
        raise RuntimeError(f'Missing prerequisites: {missing}; GPU query must succeed. Run setup-windows.ps1 -CheckOnly.')
    data=args.data_dir.resolve()
    data.mkdir(parents=True,exist_ok=True)
    state_path=data/'lab-setup.json'
    state=load_json(state_path)
    required_space=2 if state else profile['min_free_gib']
    if shutil.disk_usage(data).free<required_space*2**30:
        raise RuntimeError(f'At least {required_space} GiB free space is required on the data drive.')
    env=os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',MOTION_LAB_DATA=str(data),
               MOTION_LAB_OUTPUTS=str(data/'outputs'),HF_HOME=str(data/'hf-cache'),
               HF_HUB_DISABLE_XET='1',TEXT_ENCODER_MODE='local',TEXT_ENCODER_DEVICE='cpu',
               MOTION_LAB_NPM_CACHE=str(data/'npm-cache'),MPLCONFIGDIR=str(data/'matplotlib-cache'))
    env.pop('HF_HUB_OFFLINE',None)
    env.pop('TRANSFORMERS_OFFLINE',None)
    log=data/'logs/lab-setup.log'
    log.parent.mkdir(parents=True,exist_ok=True)
    runner=Runner(log,env)
    def save():write_json(state_path,state)
    app_python=prepare_app(runner,state,save)
    runtime_path=data/'runtime.json'
    runtime=load_json(runtime_path)
    model_signatures={}
    for model in profile['models']:
        model_python=interpreter(data/'envs'/model)
        signature=fingerprint([ROOT/'scripts/setup_models.py'],
                              {'model':model,'commit':CATALOG[model]['commit'],
                               'cuda':profile['cuda_build'],'python':platform.python_version()})
        runner.run([app_python,ROOT/'scripts/setup_models.py','--models',model,'--clone','--data-dir',data])
        if model=='text_to_vrma':
            if (state.get('environments',{}).get(model)!=signature
                    or not (data/'upstreams/text_to_vrma/node_modules/three/package.json').is_file()):
                runner.run([app_python,ROOT/'scripts/setup_models.py','--models',model,'--install','--data-dir',data])
                state.setdefault('environments',{})[model]=signature
                save()
            model_signatures[model]=fingerprint([ROOT/'scripts/generate_text_to_vrma.py',ROOT/'scripts/text_to_vrma_bridge.mjs',
                                               ROOT/'app/vrma.py',ROOT/'adapters/text_to_vrma.py',ROOT/'scripts/verify_lab_model.py'],
                                              {'environment':signature})
            runtime[model]={**runtime.get(model,{}),'engine':'ardy','backend':'local','enabled':False}
            continue
        if state.get('environments',{}).get(model)!=signature or not model_python.is_file():
            runner.run([app_python,ROOT/'scripts/setup_models.py','--models',model,'--install',
                        '--device','cuda','--cuda-build',profile['cuda_build'],'--data-dir',data])
            state.setdefault('environments',{})[model]=signature
            save()
        probe=json.loads(runner.run([model_python,'-c',TORCH_PROBE],capture=True).strip().splitlines()[-1])
        if probe['torch']!='2.9.0+'+profile['cuda_build']:
            raise RuntimeError('The model environment has a different PyTorch build; inspect before reinstalling.')
        write_json(data/'logs'/f'{model}-gpu.json',probe)
        runner.run([model_python,'-m','pip','check'])
        if not checkpoint_valid(data,model):
            runner.run([app_python,ROOT/'scripts/setup_models.py','--models',model,'--download',
                        '--accept-model-license','--max-download-gb','2','--data-dir',data])
        model_signatures[model]=fingerprint([ROOT/'scripts/verify_lab_model.py',ROOT/'scripts/generate_ardy_local.py',
                                            ROOT/'adapters'/f'{model}.py',ROOT/'adapters/base.py'],
                                           {'environment':signature,'text_device':'cpu'})
        runtime[model]={**runtime.get(model,{}),'backend':'local','checkpoint_dir':f'checkpoints/{model}',
                        'model':'core8' if model=='ardy' else 'kimodo-soma-rp-v1.1',
                        'text_encoder_device':'cpu','require_cuda':True,
                        'checkpoint_cached':True,'text_encoder_cached':False}
    write_json(runtime_path,runtime)
    text_python=interpreter(data/'envs'/profile['models'][0])
    text_manifest=data/'text-encoder-manifest.json'
    if not text_manifest.is_file() and not env.get('HF_TOKEN'):
        print('Llama access must already be approved for your Hugging Face account.')
        token=getpass.getpass('Hugging Face read token (hidden; kept only in this process): ').strip()
        if not token:raise RuntimeError('No token supplied. Access approval cannot be automated; rerun after approval.')
        env['HF_TOKEN']=token
    runner.run([text_python,ROOT/'scripts/prepare_lab_text.py','--manifest',text_manifest])
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    for model in profile['models']:
        result_path=data/'lab-verification'/f'{model}.json'
        result=load_json(result_path)
        if (state.get('verified',{}).get(model)!=model_signatures[model]
                or not result_valid(data,result)):
            runner.run([app_python,ROOT/'scripts/verify_lab_model.py','--model',model,
                        '--data-dir',data,'--result',result_path])
            result=load_json(result_path)
            if not result_valid(data,result):raise RuntimeError('Verification did not produce a real CUDA MP4.')
            state.setdefault('verified',{})[model]=model_signatures[model]
            save()
        runtime[model]['text_encoder_cached']=True
        if model=='text_to_vrma':runtime[model]['enabled']=True
        write_json(runtime_path,runtime)
        print(f"{model}: verified CUDA generation; MP4: {result['video']}")
    state['completed_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    state['port']=profile['port']
    state['cuda_build']=profile['cuda_build']
    save()
    print('Setup complete. Run start-windows.ps1 and open http://127.0.0.1:'+str(profile['port']))


def start(args,profile):
    data=args.data_dir.resolve()
    state=load_json(data/'lab-setup.json')
    runtime=load_json(data/'runtime.json')
    if state.get('cuda_build')!=profile['cuda_build']:
        raise RuntimeError('CUDA profile changed or setup is incomplete. Rerun setup-windows.ps1.')
    for model in profile['models']:
        if not state.get('verified',{}).get(model) or not runtime.get(model,{}).get('text_encoder_cached'):
            raise RuntimeError('Setup has not verified all selected models. Rerun setup-windows.ps1.')
        if not result_valid(data,load_json(data/'lab-verification'/f'{model}.json')):
            raise RuntimeError('Verification outputs are missing; rerun setup.')
    os.environ.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',MOTION_LAB_DATA=str(data),
                      MOTION_LAB_OUTPUTS=str(data/'outputs'),HF_HOME=str(data/'hf-cache'),
                      HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                      MPLCONFIGDIR=str(data/'matplotlib-cache'))
    python=interpreter(ROOT/'.venv')
    print(f"Open http://127.0.0.1:{profile['port']} in this PC's browser. Ctrl+C stops the app.")
    subprocess.run([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1',
                    '--port',str(profile['port'])],cwd=ROOT,check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['check','setup','start'])
    parser.add_argument('--profile',type=Path,default=ROOT/'configs/lab-windows.json')
    parser.add_argument('--data-dir',type=Path,default=ROOT/'.motion-lab')
    parser.add_argument('--accept-model-license',action='store_true')
    args=parser.parse_args()
    profile=load_json(args.profile)
    validate_profile(profile)
    if args.action=='check':
        print(json.dumps(preflight(),ensure_ascii=False,indent=2))
    elif args.action=='setup':setup(args,profile)
    else:start(args,profile)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(redact(str(error)),file=sys.stderr)
        sys.exit(1)
