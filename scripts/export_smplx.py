#!/usr/bin/env python3
"""Explicit SMPL-X FK with a user-supplied licensed body model. Never downloads body assets."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
import smplx
from smplx.joint_names import JOINT_NAMES

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--body-model', required=True)
    parser.add_argument('--flat-hand-mean', required=True, choices=['true','false'])
    args = parser.parse_args()
    if not Path(args.body_model).is_file():
        raise FileNotFoundError('Provide your licensed SMPL-X NPZ model; no substitute is supplied.')
    with np.load(args.input, allow_pickle=False) as data:
        poses = np.asarray(data['poses'], dtype=np.float32)
        trans = np.asarray(data['trans'], dtype=np.float32)
        betas = np.asarray(data['betas'], dtype=np.float32).reshape(-1)
        expressions = np.asarray(data['expressions'], dtype=np.float32)
        fps = float(data['mocap_frame_rate'])
    if poses.ndim != 2 or poses.shape[1] != 165 or trans.shape != (len(poses), 3):
        raise ValueError('Only explicit SMPL-X 55-joint axis-angle poses and matching trans are supported.')
    flat_hand_mean = args.flat_hand_mean == 'true'
    body = smplx.SMPLX(args.body_model, use_pca=False, flat_hand_mean=flat_hand_mean,
                      num_betas=len(betas), num_expression_coeffs=expressions.shape[1])
    joints = []
    with torch.inference_mode():
        for start in range(0, len(poses), 64):
            p = torch.from_numpy(poses[start:start+64])
            n = len(p)
            output = body(global_orient=p[:,:3], body_pose=p[:,3:66], jaw_pose=p[:,66:69],
                          leye_pose=p[:,69:72], reye_pose=p[:,72:75], left_hand_pose=p[:,75:120],
                          right_hand_pose=p[:,120:165], transl=torch.from_numpy(trans[start:start+n]),
                          betas=torch.from_numpy(betas).repeat(n,1), expression=torch.from_numpy(expressions[start:start+n]))
            joints.append(output.joints[:,:55].cpu().numpy())
    result = {'schema': 'motion-lab/v1', 'positions': np.concatenate(joints).tolist(), 'fps': fps,
              'joint_names': JOINT_NAMES[:55], 'parents': body.parents[:55].tolist(), 'skeleton_type': 'SMPL-X-55',
              'coordinate_system': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
              'source_coordinates': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
              'root_policy': 'original global trajectory preserved', 'metadata': {'conversion': 'licensed SMPL-X FK', 'flat_hand_mean': flat_hand_mean, 'source_format': 'SMPL-X NPZ'}}
    Path(args.output).write_text(json.dumps(result, allow_nan=False))
