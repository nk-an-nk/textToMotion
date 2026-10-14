#!/usr/bin/env python3
"""Official ARDY API with CPU text encoder and CUDA motion model; no upstream edits."""
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('prompt')
    parser.add_argument('--model',default='core8')
    parser.add_argument('--duration',type=float,default=3)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--text-device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--require-cuda',action='store_true')
    parser.add_argument('--checkpoints_dir',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--no-postprocess',action='store_true',required=True)
    args=parser.parse_args()
    if not args.prompt.strip() or not .5<=args.duration<=20:
        parser.error('A nonempty prompt and a duration of 0.5–20 seconds are required.')
    import numpy as np
    import torch
    from ardy.model.load_model import load_model,load_text_encoder
    from ardy.tools import seed_everything,to_numpy
    if args.require_cuda and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; no CPU fallback.')
    device='cuda' if torch.cuda.is_available() else 'cpu'
    torch.set_num_threads(4)
    seed_everything(args.seed)
    # Passing an existing encoder avoids load_model moving it to the motion GPU.
    encoder=load_text_encoder(mode='local',device=args.text_device)
    model=load_model(args.model,device=device,checkpoints_dir=args.checkpoints_dir,text_encoder=encoder)
    fps=float(model.motion_rep.fps)
    frames=int(args.duration*fps)
    patch=int(model.num_frames_per_token)
    history=((int(10*fps)//patch)*patch-int(model.gen_horizon_len))//patch*patch
    with torch.inference_mode():
        motion=model([args.prompt.strip()],frames,num_denoising_steps=int(model.diffusion.num_base_steps),
                     pad_mask=torch.ones(1,frames,dtype=torch.bool,device=device),
                     first_heading_angle=torch.zeros(1,device=device),motion_mask=None,observed_motion=None,
                     cfg_weight=(2.,2.),crop_history_length=history)
        output=to_numpy(model.motion_rep.inverse(motion,is_normalized=True))
    sample={key:np.asarray(value[0] if hasattr(value,'shape') and value.ndim>0 and value.shape[0]==1 else value)
            for key,value in output.items()}
    joints=sample['posed_joints']
    if joints.shape[0]!=frames or not np.isfinite(joints).all():
        raise ValueError('Invalid official model output.')
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    np.savez(target,**sample,fps=np.asarray(fps),text=np.asarray(args.prompt.strip()))
    print(f'Generated real ARDY output: device={device}, text_device={args.text_device}, frames={frames}')


if __name__=='__main__':
    main()
