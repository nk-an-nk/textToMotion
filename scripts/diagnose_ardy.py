#!/usr/bin/env python3
"""Real pretrained ARDY unconditional diagnostic, NOT text-to-motion or co-speech validation.

Uses the public precomputed-text-feature API with the official empty-prompt representation:
zero features, false text mask, and zero text/constraint guidance. No fabricated text embedding.
Run with the isolated ARDY Python. The official source and weights are unchanged.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import torch
from ardy.model import load_model
from ardy.tools import seed_everything, to_numpy

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--checkpoints-dir',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--duration',type=float,default=3)
    args=parser.parse_args()
    if not .5 <= args.duration <= 10:
        parser.error('Diagnostic duration must be 0.5–10 seconds.')
    torch.set_num_threads(4)
    seed_everything(args.seed)
    started=time.monotonic()
    model=load_model('core8',device='cpu',checkpoints_dir=args.checkpoints_dir,text_encoder=False)
    load_time=time.monotonic()-started
    fps=float(model.motion_rep.fps);frames=int(args.duration*fps)
    feature_size=model.denoiser.llm_shape[-1]
    features=torch.zeros(1,1,feature_size,device='cpu')
    text_mask=torch.zeros(1,1,dtype=torch.bool,device='cpu')
    generation_started=time.monotonic()
    with torch.inference_mode():
        motion=model(texts=[''],num_frames=frames,num_denoising_steps=int(model.diffusion.num_base_steps),
                     pad_mask=torch.ones(1,frames,dtype=torch.bool),first_heading_angle=torch.zeros(1),
                     motion_mask=None,observed_motion=None,cfg_weight=(0.,0.),
                     text_feat=features,text_pad_mask=text_mask,crop_history_length=int(10*fps)-model.gen_horizon_len)
        output=to_numpy(model.motion_rep.inverse(motion,is_normalized=True))
    elapsed=time.monotonic()-generation_started
    sample={key:np.asarray(value[0] if hasattr(value,'shape') and value.ndim>0 and value.shape[0]==1 else value) for key,value in output.items()}
    assert sample['posed_joints'].shape==(frames,27,3)
    assert np.isfinite(sample['posed_joints']).all()
    assert float(np.max(np.abs(np.diff(sample['posed_joints'],axis=0))))>1e-6
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    np.savez(path,**sample,fps=np.asarray(fps),text=np.asarray(''))
    metadata={'task_type':'unconditional_diagnostic','trained_model_output':True,'text_conditioned':False,
              'audio_conditioned':False,'prompt':None,'seed':args.seed,'model_id':'ardy','device':'cpu',
              'checkpoint':'nvidia/ARDY-Core-RP-20FPS-Horizon8','checkpoint_revision':'257a0843a10bf5201065963d7bca2791e9393a7a',
              'load_time':load_time,'inference_time':elapsed,'time_to_first_result':time.monotonic()-started,
              'fps':fps,'frames':frames,'duration':frames/fps,'diffusion_steps':int(model.diffusion.num_base_steps),
              'text_guidance':0,'constraint_guidance':0,'postprocess':False,
              'notice':'実学習済みモデルの無条件CPU診断。テキスト・音声条件付き生成の成功ではありません。'}
    path.with_suffix('.metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(json.dumps(metadata,ensure_ascii=False))
