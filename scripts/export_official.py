#!/usr/bin/env python3
"""Execute in the model venv; obtain hierarchy from its own official skeleton implementation."""
import argparse
import importlib
import json
from pathlib import Path
import numpy as np

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', required=True, choices=['ardy', 'kimodo'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as data:
        positions = data['posed_joints']
        if positions.ndim == 4 and positions.shape[0] == 1:
            positions = positions[0]
        if positions.ndim != 3 or positions.shape[2] != 3 or not np.isfinite(positions).all():
            raise ValueError('Expected finite single-sample [T,J,3] official world-space posed_joints.')
        skeleton = importlib.import_module(args.family + '.skeleton.registry').build_skeleton(positions.shape[1])
        fps = float(data['fps'])
        result = {'schema': 'motion-lab/v1', 'positions': positions.tolist(), 'fps': fps,
                  'joint_names': skeleton.bone_order_names, 'parents': skeleton.joint_parents.cpu().tolist(),
                  'skeleton_type': args.family + ':' + skeleton.name,
                  'coordinate_system': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
                  'source_coordinates': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
                  'root_policy': 'original global trajectory preserved',
                  'metadata': {'source_format': args.family + ' NPZ', 'hierarchy_source': args.family + '.skeleton.registry', 'trained_model_output': True}}
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
