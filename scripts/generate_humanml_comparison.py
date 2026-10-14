#!/usr/bin/env python3
"""Official masked generators under lab-sized resource budgets; no sample motion fallback."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
try:
    from scripts.resource_measurement import peak_ram_mib
except ModuleNotFoundError:
    from resource_measurement import peak_ram_mib


def json_file(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['momask', 'mmm', 'motionlcm'], required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--speech', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path('configs/segmented_english_lesson.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-threads', type=int, default=8)
    parser.add_argument('--vram-mib', type=int, default=12227)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    process_started = time.monotonic()
    if args.output.exists():
        raise ValueError('Existing outputs are preserved. Choose a new output directory.')
    plan = json.loads(args.config.read_text())
    args.repo = args.repo.resolve(); args.weights = args.weights.resolve()
    args.speech = args.speech.resolve(); args.output = args.output.resolve()
    os.environ.update({name: str(args.cpu_threads) for name in ['OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS']})
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[:args.cpu_threads]))
    import numpy as np
    # Older official quaternion/BVH modules used these aliases; retain their original scalar semantics.
    for alias, scalar in [('float', float), ('int', int), ('complex', complex), ('bool', bool)]:
        if alias not in np.__dict__:
            setattr(np, alias, scalar)
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; this comparison requires the actual GPU.')
    torch.set_num_threads(args.cpu_threads)
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, args.vram_mib * 1024**2 / total), 0)
    load = torch.load
    def official_load(filename, *a, **kw):
        # Only checkpoints obtained from the explicitly selected official archive may use legacy pickle metadata.
        if isinstance(filename, (str, Path)) and args.weights in Path(filename).resolve().parents:
            kw.setdefault('weights_only', False)
        return load(filename, *a, **kw)
    torch.load = official_load
    sys.path.insert(0, str(args.repo)); os.chdir(args.repo)
    if args.model != 'motionlcm':
        import clip
        from utils.motion_process import recover_from_ric
    if args.model == 'momask':
        from argparse import Namespace
        from utils.get_opt import get_opt
        from models.vq.model import RVQVAE
        from models.mask_transformer.transformer import MaskTransformer, ResidualTransformer
        model_name = 't2m_nlayer8_nhead6_ld384_ff1024_cdp0.1_rvq6ns'
        res_name = 'tres_nlayer8_ld384_ff1024_rvq6ns_cdp0.2_sw'
        model_opt = get_opt(str(args.weights/model_name/'opt.txt'), torch.device('cuda'))
        vq_opt = get_opt(str(args.weights/model_opt.vq_name/'opt.txt'), torch.device('cuda'))
        vq_opt.checkpoints_dir = str(args.weights.parent); vq_opt.dataset_name = args.weights.name
        # Use the official networks directly; the optional BVH/IK renderer is not part of VRM export.
        vq = RVQVAE(vq_opt, vq_opt.dim_pose, vq_opt.nb_code, vq_opt.code_dim,
                    vq_opt.output_emb_width, vq_opt.down_t, vq_opt.stride_t, vq_opt.width,
                    vq_opt.depth, vq_opt.dilation_growth_rate, vq_opt.vq_act, vq_opt.vq_norm)
        vq_state = torch.load(args.weights/vq_opt.name/'model/net_best_fid.tar', map_location='cpu')
        vq.load_state_dict(vq_state['vq_model'] if 'vq_model' in vq_state else vq_state['net'])
        model_opt.num_tokens = vq_opt.nb_code; model_opt.num_quantizers = vq_opt.num_quantizers
        model_opt.code_dim = vq_opt.code_dim
        model_opt.checkpoints_dir = str(args.weights.parent); model_opt.dataset_name = args.weights.name
        res_opt = get_opt(str(args.weights/res_name/'opt.txt'), torch.device('cuda'))
        res_opt.checkpoints_dir = str(args.weights.parent); res_opt.dataset_name = args.weights.name
        res_opt.num_quantizers = vq_opt.num_quantizers; res_opt.num_tokens = vq_opt.nb_code
        def transformer_options(value):
            return dict(code_dim=vq_opt.code_dim, cond_mode='text', latent_dim=value.latent_dim,
                        ff_size=value.ff_size, num_layers=value.n_layers, num_heads=value.n_heads,
                        dropout=value.dropout, clip_dim=512, cond_drop_prob=value.cond_drop_prob,
                        clip_version='ViT-B/32', opt=value)
        residual = ResidualTransformer(**transformer_options(res_opt), shared_codebook=vq_opt.shared_codebook,
                                       share_weight=res_opt.share_weight)
        masked = MaskTransformer(**transformer_options(model_opt))
        res_state = torch.load(args.weights/res_name/'model/net_best_fid.tar', map_location='cpu')
        mask_state = torch.load(args.weights/model_name/'model/latest.tar', map_location='cpu')
        for network, state in [(residual, res_state['res_transformer']),
                                (masked, mask_state['t2m_transformer'] if 't2m_transformer' in mask_state else mask_state['trans'])]:
            missing, unexpected = network.load_state_dict(state, strict=False)
            if unexpected or any(not name.startswith('clip_model.') for name in missing):
                raise RuntimeError('Official checkpoint does not match the selected network.')
            network.eval().cuda()
        vq.eval().cuda()
        mean = np.load(args.weights/vq_opt.name/'meta/mean.npy')
        std = np.load(args.weights/vq_opt.name/'meta/std.npy')
        def predict(text, frames):
            lens = torch.tensor([frames//4], device='cuda')
            codes = masked.generate([text], lens, timesteps=18, cond_scale=4,
                                    temperature=1, topk_filter_thres=.9, gsample=False)
            codes = residual.generate(codes, [text], lens, temperature=1, cond_scale=5)
            return vq.forward_decoder(codes)[0]
    elif args.model == 'mmm':
        import options.option_transformer as options
        argv = sys.argv; sys.argv = ['generate.py']
        try: opt = options.get_args_parser()
        finally: sys.argv = argv
        opt.resume_pth = str(args.weights/'2024-06-03-20-22-07_retrain/net_last.pth')
        opt.resume_trans = str(args.weights/'2024-06-04-09-29-20_trans_name_b128/net_last.pth')
        from generate import MMM
        model = MMM(opt).eval()
        mean = np.load(args.repo/'exit/t2m-mean.npy'); std = np.load(args.repo/'exit/t2m-std.npy')
        def predict(text, frames):
            return model([text], torch.tensor([frames], device='cuda'), rand_pos=False)[0, :frames]
    else:
        from omegaconf import OmegaConf
        from mld.config import get_module_config
        from mld.data.get_data import get_dataset
        from mld.models.modeltype.mld import MLD
        config = OmegaConf.load(args.repo/'configs/motionlcm_t2m.yaml')
        config = OmegaConf.merge(config, get_module_config(config.model, config.model.target, str(args.repo/'configs')))
        config.model.t5_path = str(args.weights/'sentence-t5-large')
        config.model.t2m_path = str(args.weights/'deps/t2m')
        config.DATASET.HUMANML3D.ROOT = str(args.weights/'datasets/humanml3d')
        config.DATASET.WINDOW_SIZE = 40
        config.output_dir = str(args.output)
        config.TEST.CHECKPOINTS = str(args.weights/'experiments_t2m/motionlcm_humanml/motionlcm_humanml.ckpt')
        state = torch.load(config.TEST.CHECKPOINTS, map_location='cpu')['state_dict']
        key = 'denoiser.time_embedding.cond_proj.weight'
        if key not in state:
            raise RuntimeError('The selected checkpoint is not MotionLCM.')
        config.model.denoiser.params.time_cond_proj_dim = state[key].shape[1]
        config.model.is_controlnet = False
        dataset = get_dataset(config, motion_only=True)
        model = MLD(config, dataset).eval().cuda()
        model.load_state_dict(state, strict=True)
        model.requires_grad_(False)
        def predict(text, frames):
            return model({'length':[frames], 'text':[text]})[0][0]
    torch.cuda.synchronize()
    loading_seconds = time.monotonic() - process_started
    args.output.mkdir(parents=True)
    source_names = ['pelvis','left_hip','right_hip','spine1','left_knee','right_knee','spine2',
             'left_ankle','right_ankle','spine3','left_toes','right_toes','neck',
             'left_collar','right_collar','head','left_shoulder','right_shoulder',
             'left_elbow','right_elbow','left_wrist','right_wrist']
    names = ['hips','leftUpperLeg','rightUpperLeg','spine','leftLowerLeg','rightLowerLeg','chest',
             'leftFoot','rightFoot','upperChest','leftToes','rightToes','neck',
             'leftShoulder','rightShoulder','head','leftUpperArm','rightUpperArm',
             'leftLowerArm','rightLowerArm','leftHand','rightHand']
    # HumanML3D's published 22-joint kinematic chain, independent of avatar dimensions.
    parents = [-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19]
    results = []
    for index, unit in enumerate(plan['segments']):
        started_at = datetime.now(timezone.utc).isoformat(); started = time.monotonic()
        text = unit['text']
        if args.model != 'motionlcm':
            clip.tokenize([text], truncate=False)  # Refuse silently truncated canonical input.
        speech = json.loads((args.speech/unit['id']/'voice.json').read_text())
        if speech['requested_text'] != text:
            raise ValueError('Speech and motion must use identical canonical text.')
        frames = min(196, max(40, math.ceil(speech['duration_seconds']*20/4)*4))
        torch.manual_seed(args.seed+index); torch.cuda.manual_seed_all(args.seed+index)
        torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():
            features = predict(text, frames)
            if args.model == 'motionlcm':
                joints = features.detach().cpu().numpy()
            else:
                values = features.detach().cpu().numpy() * std + mean
                joints = recover_from_ric(torch.from_numpy(values).float(), 22).numpy()
        torch.cuda.synchronize()
        if joints.shape != (frames,22,3) or not np.isfinite(joints).all():
            raise ValueError('Official decoder did not return finite HumanML3D joints.')
        directory = args.output/unit['id']; directory.mkdir()
        np.save(directory/'joints.npy', joints, allow_pickle=False)
        motion = {'schema':'motion-lab/v1','positions':joints.tolist(),'fps':20,
                  'joint_names':names,'parents':parents,'skeleton_type':'humanml3d:22',
                  'coordinate_system':{'up':'Y','handedness':'right','unit':'m'},
                  'source_coordinates':{'up':'Y','handedness':'right','unit':'m'},
                  'metadata':{'source_format':args.model+' decoded HumanML3D','trained_model_output':True,
                              'input_text':text,'seed':args.seed+index,'model':args.model,
                              'source_joint_names':source_names,'joint_label_mapping':'HumanML3D anatomy to VRM names; joint order unchanged'}}
        json_file(directory/'motion.json', motion)
        seconds = time.monotonic() - started
        receipt = {'id':unit['id'],'model':args.model,'original_text':text,'motion_prompt':text,
                   'input_submitted_at_utc':started_at,'skeleton_completed_at_utc':datetime.now(timezone.utc).isoformat(),
                   'input_to_skeleton_seconds':seconds,'skeleton_seconds':seconds,'seed':args.seed+index,
                   'cold_model_load_seconds':loading_seconds,'first_input_with_model_load_seconds':loading_seconds+seconds if index==0 else None,
                   'motion_sha256':hashlib.sha256((directory/'motion.json').read_bytes()).hexdigest(),
                   'native_frames':frames,'native_fps':20,'peak_torch_allocated_mib':torch.cuda.max_memory_allocated()/1024**2,
                   'peak_torch_reserved_mib':torch.cuda.max_memory_reserved()/1024**2,
                   'gpu_name':torch.cuda.get_device_name(0),'cpu_threads':args.cpu_threads,'torch_vram_allocator_limit_mib':args.vram_mib,
                   'process_peak_ram_mib':peak_ram_mib(),
                   'input_translation':False,'input_truncation':False,'new_gesture_generated':True}
        json_file(directory/'motion-generation.json', receipt); results.append(receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
    json_file(args.output/'timings.json', {'model':args.model,'segments':results,'model_load_seconds':loading_seconds})


if __name__ == '__main__':
    main()
