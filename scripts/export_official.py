#!/usr/bin/env python3
"""Execute in the model venv; obtain hierarchy from its own official skeleton implementation."""
import argparse
import importlib
import json
from pathlib import Path
import numpy as np

def official_fps(data, family, model=None, checkpoint_dir=None):
    if 'fps' in data:
        fps=float(data['fps'])
    elif family=='kimodo' and model and checkpoint_dir:
        from kimodo.model.registry import get_model_info,resolve_model_name
        from omegaconf import OmegaConf
        info=get_model_info(model) or get_model_info(resolve_model_name(model,'Kimodo'))
        if info is None:
            raise ValueError('Unknown official Kimodo checkpoint.')
        folder=Path(checkpoint_dir)/info.display_name
        if not folder.is_dir():
            folder=Path(checkpoint_dir)/model
        config=OmegaConf.load(folder/'config.yaml')
        fps=float(config.denoiser.motion_rep.fps)
    else:
        raise ValueError('Official output has no fps; provide the source model and checkpoint directory.')
    if not np.isfinite(fps) or fps<=0:
        raise ValueError('Official fps must be finite and positive.')
    return fps

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', required=True, choices=['ardy', 'kimodo'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model')
    parser.add_argument('--checkpoint-dir')
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as data:
        positions = data['posed_joints']
        if positions.ndim == 4 and positions.shape[0] == 1:
            positions = positions[0]
        if positions.ndim != 3 or positions.shape[2] != 3 or not np.isfinite(positions).all():
            raise ValueError('Expected finite single-sample [T,J,3] official world-space posed_joints.')
        skeleton = importlib.import_module(args.family + '.skeleton.registry').build_skeleton(positions.shape[1])
        fps = official_fps(data,args.family,args.model,args.checkpoint_dir)
        result = {'schema': 'motion-lab/v1', 'positions': positions.tolist(), 'fps': fps,
                  'joint_names': skeleton.bone_order_names, 'parents': skeleton.joint_parents.cpu().tolist(),
                  'skeleton_type': args.family + ':' + skeleton.name,
                  'coordinate_system': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
                  'source_coordinates': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
                  'root_policy': 'original global trajectory preserved',
                  'metadata': {'source_format': args.family + ' NPZ', 'hierarchy_source': args.family + '.skeleton.registry', 'trained_model_output': True}}
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False),encoding='utf-8')
