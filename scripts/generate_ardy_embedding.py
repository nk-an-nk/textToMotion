#!/usr/bin/env python3
"""Official ARDY CUDA generation using real locally encoded LLM2Vec features."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['embeddings','config','speech','weights','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();start=time.monotonic()
    if a.output.exists():raise ValueError('Existing ARDY outputs are preserved.')
    import numpy as np
    import torch
    from ardy.model import load_model
    from ardy.tools import seed_everything,to_numpy
    if not torch.cuda.is_available():raise RuntimeError('CUDA required; no CPU motion fallback.')
    torch.set_num_threads(8)
    torch.cuda.set_per_process_memory_fraction(min(1,12227*1024**2/torch.cuda.get_device_properties(0).total_memory))
    embedding_receipts={s['id']:s for s in json.loads((a.embeddings/'timings.json').read_text())['segments']}
    model=load_model('core8',device='cuda',checkpoints_dir=str(a.weights),text_encoder=False)
    torch.cuda.synchronize();load=time.monotonic()-start;a.output.mkdir(parents=True);results=[]
    for i,u in enumerate(json.loads(a.config.read_text())['segments']):
        encoder=embedding_receipts[u['id']]
        if encoder['text']!=u['text']:raise ValueError('Actual text embedding differs from canonical model input.')
        began=time.monotonic();utc=datetime.now(timezone.utc).isoformat();seed_everything(i);torch.cuda.reset_peak_memory_stats()
        data=np.load(a.embeddings/(u['id']+'.npz'),allow_pickle=False)
        features=torch.from_numpy(data['embedding']).to(device='cuda',dtype=next(model.parameters()).dtype)
        if features.shape!=(1,1,4096) or not torch.isfinite(features).all():raise ValueError('Invalid learned LLM2Vec features.')
        voice=json.loads((a.speech/u['id']/'voice.json').read_text());fps=float(model.motion_rep.fps)
        frames=math.ceil(voice['duration_seconds']*fps);patch=int(model.num_frames_per_token)
        history=((int(10*fps)//patch)*patch-int(model.gen_horizon_len))//patch*patch
        with torch.inference_mode():
            out=model(texts=[u['text']],num_frames=frames,num_denoising_steps=int(model.diffusion.num_base_steps),
                pad_mask=torch.ones(1,frames,dtype=torch.bool,device='cuda'),first_heading_angle=torch.zeros(1,device='cuda'),
                motion_mask=None,observed_motion=None,cfg_weight=(2.,2.),text_feat=features,
                text_pad_mask=torch.ones(1,1,dtype=torch.bool,device='cuda'),crop_history_length=history)
            output=to_numpy(model.motion_rep.inverse(out,is_normalized=True))
        torch.cuda.synchronize();folder=a.output/u['id'];folder.mkdir()
        sample={k:np.asarray(v[0] if hasattr(v,'shape') and v.ndim>0 and v.shape[0]==1 else v) for k,v in output.items()}
        np.savez(folder/'original.npz',**sample,fps=np.asarray(fps),text=np.asarray(u['text']))
        import sys
        subprocess.run([sys.executable,str(Path(__file__).resolve().parent/'export_official.py'),
            '--family','ardy','--input',str(folder/'original.npz'),'--output',str(folder/'motion.json')],check=True)
        motion=json.loads((folder/'motion.json').read_text());motion['metadata'].update(trained_model_output=True,input_text=u['text'],
            text_conditioned=True,text_embedding_source='official LLM2Vec CPU encoder',text_guidance=2,constraint_guidance=2)
        (folder/'motion.json').write_text(json.dumps(motion,ensure_ascii=False,allow_nan=False)+'\n')
        seconds=time.monotonic()-began
        receipt={'id':u['id'],'model':'ardy','original_text':u['text'],'motion_prompt':u['text'],'seed':i,
            'input_submitted_at_utc':utc,'skeleton_completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'input_to_skeleton_seconds':seconds+encoder['embedding_seconds'],'skeleton_seconds':seconds+encoder['embedding_seconds'],
            'motion_cuda_seconds':seconds,'text_encoder_cpu_seconds':encoder['embedding_seconds'],
            'cold_model_load_seconds':load,'text_encoder_model_load_seconds':encoder['model_load_seconds'],
            'motion_sha256':hashlib.sha256((folder/'motion.json').read_bytes()).hexdigest(),
            'gpu_name':torch.cuda.get_device_name(0),'torch_vram_allocator_limit_mib':12227,'cpu_threads':8,
            'peak_torch_allocated_mib':torch.cuda.max_memory_allocated()/1024**2,
            'peak_torch_reserved_mib':torch.cuda.max_memory_reserved()/1024**2,
            'text_encoder_peak_ram_mib':encoder['peak_ram_mib'],'new_gesture_generated':True,
            'checkpoint':'nvidia/ARDY-Core-RP-20FPS-Horizon8','text_encoder_device':'cpu','motion_device':'cuda',
            'text_embedding_precomputed':True,'input_translation':False,'input_truncation':False}
        (folder/'motion-generation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');results.append(receipt)
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    (a.output/'timings.json').write_text(json.dumps({'segments':results,'model_load_seconds':load},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
