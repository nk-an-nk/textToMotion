"""Read static hierarchy data from the inspected official source without importing its ML stack."""
import ast
import json
from pathlib import Path
import numpy as np
from app.motion import MotionError, normalize, save_motion


def normalize_kimodo_online(original, output, repo, metadata):
    with np.load(original,allow_pickle=False) as data:
        positions=data['posed_joints']
    if positions.ndim!=3 or positions.shape[-1]!=3:
        raise MotionError('Official online result must contain one [T,J,3] motion.')
    class_name={30:'SOMASkeleton30',77:'SOMASkeleton77',34:'G1Skeleton34'}.get(positions.shape[1])
    if not class_name:
        raise MotionError('Unknown official skeleton; retain the original NPZ rather than guessing.')
    definitions=Path(repo)/'kimodo/skeleton/definitions.py'
    tree=ast.parse(definitions.read_text())
    bones=None
    for node in tree.body:
        if isinstance(node,ast.ClassDef) and node.name==class_name:
            for item in node.body:
                if isinstance(item,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='bone_order_names_with_parents' for target in item.targets):
                    bones=ast.literal_eval(item.value)
    if bones is None or len(bones)!=positions.shape[1]:
        raise MotionError('Official hierarchy cannot be verified against the downloaded joint count.')
    names=[name for name,parent in bones]
    parents=[-1 if parent is None else names.index(parent) for name,parent in bones]
    if positions.shape[0]!=metadata['frames_requested']:
        raise MotionError('Official output frame count differs from the requested duration.')
    result=normalize(positions,metadata['fps'],names,parents,skeleton_type='Kimodo:'+class_name,
                     source_up='Y',source_unit='m',metadata={**metadata,'source_format':'official Kimodo Download NPZ',
                                                         'hierarchy_source':str(definitions.name) + ':' + class_name})
    save_motion(output,result)
    return Path(output)
