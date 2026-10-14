#!/usr/bin/env python3
"""One official text-to-vrma ARDY engine per job, sharing the verified ARDY env/cache."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.base import redact

def stop_engine(process):
    if process.poll() is not None:
        return
    if os.name=='nt':
        # Windows venv launchers spawn the real interpreter. Stop that child too
        # so it releases the capture file and its GPU memory before cleanup.
        result=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode!=0 and process.poll() is None:
            process.terminate()
    else:
        process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

def remove_temporary(path):
    # Windows can retain inherited file handles briefly after process exit.
    for attempt in range(20):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt==19:
                print(f'Temporary diagnostic retained while locked: {path.name}',flush=True)
                return
            time.sleep(.25)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--prompt',required=True)
    parser.add_argument('--duration',type=float,required=True)
    parser.add_argument('--seed',type=int,required=True)
    args=parser.parse_args()
    if not args.prompt.strip() or not .5<=args.duration<=20 or not 0<=args.seed<=4294967295:
        parser.error('Invalid prompt, duration, or seed.')
    data=args.data_dir.resolve();output=args.output_dir.resolve()
    source=data/'upstreams/text_to_vrma'
    python=data/'envs/ardy'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    node=shutil.which('node')
    if not python.is_file() or not node:raise RuntimeError('The verified ARDY env and Node.js are required.')
    output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=os.environ.copy()
    env.update(HF_HOME=str(data/'hf-cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
               CHECKPOINTS_DIR=str(data/'checkpoints/ardy'),TEXT_ENCODER_MODE='local',TEXT_ENCODER_DEVICE='cpu',
               PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    # ARDY-only comparison never activates optional paid planners or Jev.
    for name in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','JEV_API_KEY'):
        env.pop(name,None)
    capture=output/'.text-vrma-engine-capture'
    configuration=output/'.text-vrma-request.json'
    started=time.monotonic()
    with capture.open('w',encoding='utf-8') as log:
        process=subprocess.Popen([str(python),str(source/'tools/ardy-engine/server.py'),
                                  '--model','core8','--no-translate','--port',str(port)],
                                 cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+600
            info=None
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('The official text-to-vrma ARDY engine exited during boot.')
                try:
                    with urllib.request.urlopen(base+'/health',timeout=2) as response:info=json.load(response)
                except (OSError,ValueError):time.sleep(.25);continue
                if info.get('boot',{}).get('error') or info.get('error'):
                    raise RuntimeError('Engine boot failed: '+str(info.get('boot',{}).get('error') or info.get('error')))
                if info.get('status')=='ok':
                    if info.get('model')!='core8':raise RuntimeError('Unexpected ARDY checkpoint in engine health.')
                    if not str(info.get('device','')).startswith('cuda'):
                        raise RuntimeError('The official engine is not on CUDA; no CPU fallback.')
                    break
                time.sleep(.25)
            else:raise RuntimeError('Official ARDY engine boot timed out.')
            configuration.write_text(json.dumps({'source':str(source),'engine_url':base,
                                       'prompt':args.prompt,'duration':args.duration,'seed':args.seed,
                                       'spec_path':str(output/'original.spec.json'),
                                       'vrma_path':str(output/'original.vrma')}),encoding='utf-8')
            subprocess.run([node,str(ROOT/'scripts/text_to_vrma_bridge.mjs'),str(configuration)],
                           cwd=source,env=env,check=True,timeout=950)
            elapsed=time.monotonic()-started
            checkpoint=json.loads((data/'checkpoints/ardy/ARDY-Core-RP-20FPS-Horizon8/motion-lab-download.json').read_text(encoding='utf-8'))
            metadata={'model_id':'text_to_vrma','engine':'ardy','planner':'none','use_jev':False,
                      'trained_model_output':True,'text_conditioned':True,'audio_conditioned':False,
                      'prompt':args.prompt,'seed':args.seed,'seed_enforced':True,'device':'cuda',
                      'text_encoder_device':'cpu','checkpoint':'nvidia/ARDY-Core-RP-20FPS-Horizon8',
                      'checkpoint_revision':checkpoint['revision'],'native_fps':info['fps'],
                      'shares_ardy_weights':True,'upstream_postprocessing':True,'native_engine_history_frames':40,
                      'native_engine_arm_spread_degrees':6,'native_engine_cfg':3.0,'inference_time':elapsed,
                      'timing_note':'Includes engine boot, CPU text encoding, CUDA generation, retargeting and VRMA export.'}
            (output/'original.metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        finally:
            stop_engine(process)
    # Keep redacted source-engine diagnostics and remove temporary request/capture.


if __name__=='__main__':
    # The adapter's outer capture also redacts errors; retain engine logs on failure.
    output=None
    try:
        position=sys.argv.index('--output-dir')+1
        output=Path(sys.argv[position])
        main()
    finally:
        if output:
            capture=output/'.text-vrma-engine-capture'
            if capture.is_file():
                (output/'text-vrma-engine.log').write_text(redact(capture.read_text(encoding='utf-8',errors='replace')),encoding='utf-8')
                remove_temporary(capture)
            remove_temporary(output/'.text-vrma-request.json')
