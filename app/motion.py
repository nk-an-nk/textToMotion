"""Strict, explicit motion formats. Unknown pose parameters never become guessed skeletons."""
import json
import math
import re
import zipfile
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

MAX_FRAMES = 3600
MAX_JOINTS = 200
MAX_EXPANDED_BYTES = 256 * 1024 * 1024


class MotionError(ValueError):
    pass


def validate_motion(data):
    if data.get('schema') != 'motion-lab/v1':
        raise MotionError('Expected motion-lab/v1 schema.')
    try:
        positions = np.asarray(data['positions'], dtype=np.float32)
        fps = float(data['fps'])
        names = data['joint_names']
        parents = data['parents']
    except (KeyError, TypeError, ValueError) as error:
        raise MotionError('Missing or invalid positions, fps, names, or parents.') from error
    if positions.ndim != 3 or positions.shape[-1] != 3:
        raise MotionError('positions must have shape [frames, joints, 3].')
    frames, joints, _ = positions.shape
    if not 1 <= frames <= MAX_FRAMES or not 1 <= joints <= MAX_JOINTS:
        raise MotionError('Motion exceeds frame/joint limits or is empty.')
    if not np.isfinite(positions).all() or not math.isfinite(fps) or not 1 <= fps <= 240:
        raise MotionError('Coordinates must be finite and fps must be between 1 and 240.')
    if not isinstance(names, list) or not all(isinstance(n, str) and 0 < len(n) <= 128 for n in names):
        raise MotionError('Invalid joint names.')
    if len(names) != joints or len(set(names)) != joints:
        raise MotionError('Each joint needs a unique name.')
    if not isinstance(parents, list) or len(parents) != joints:
        raise MotionError('parents must match joint count.')
    for i, parent in enumerate(parents):
        if type(parent) is not int or not -1 <= parent < joints or parent == i:
            raise MotionError('Invalid parent index.')
        seen = {i}
        current = parent
        while current != -1:
            if current in seen:
                raise MotionError('Skeleton hierarchy contains a cycle.')
            seen.add(current)
            if type(parents[current]) is not int or not -1 <= parents[current] < joints:
                raise MotionError('Invalid parent index.')
            current = parents[current]
    if parents.count(-1) != 1:
        raise MotionError('Exactly one root joint is required.')
    if data.get('coordinate_system') != {'up': 'Y', 'handedness': 'right', 'unit': 'm'}:
        raise MotionError('Normalized coordinates must explicitly be right-handed, Y-up, in metres.')
    return data


def normalize(positions, fps, names, parents, *, skeleton_type, source_up, source_unit, metadata=None):
    if source_up not in ('Y', 'Z') or source_unit not in ('m', 'cm', 'mm'):
        raise MotionError('Specify supported source axes and units; no guessing is performed.')
    values = np.asarray(positions, dtype=np.float32).copy()
    if source_up == 'Z':
        # Proper rotation (determinant +1), preserving handedness.
        values = values[..., [0, 2, 1]]
        values[..., 2] *= -1
    values *= {'m': 1., 'cm': .01, 'mm': .001}[source_unit]
    data = {
        'schema': 'motion-lab/v1', 'positions': values.tolist(), 'fps': float(fps),
        'joint_names': list(names), 'parents': [int(p) for p in parents],
        'skeleton_type': skeleton_type,
        'coordinate_system': {'up': 'Y', 'handedness': 'right', 'unit': 'm'},
        'source_coordinates': {'up': source_up, 'handedness': 'right', 'unit': source_unit},
        'root_policy': 'original global trajectory preserved', 'metadata': metadata or {},
    }
    return validate_motion(data)


def load_npz(path, *, skeleton_type='custom', source_up='Y', source_unit='m'):
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise MotionError('Expanded NPZ exceeds memory limit.')
    except zipfile.BadZipFile as error:
        raise MotionError('Invalid NPZ archive.') from error
    with np.load(path, allow_pickle=False) as arrays:
        if 'posed_joints' not in arrays and 'positions' not in arrays:
            if 'poses' in arrays:
                raise MotionError('SMPL-X pose parameters require a licensed body model and forward kinematics. The original NPZ can be retained, but is not a joint-position array.')
            raise MotionError('NPZ must contain positions or posed_joints.')
        key = 'posed_joints' if 'posed_joints' in arrays else 'positions'
        if not all(k in arrays for k in ('joint_names', 'parents', 'fps')):
            raise MotionError('NPZ needs explicit joint_names, parents and fps. Use scripts/export_official.py for ARDY/Kimodo files.')
        return normalize(arrays[key], float(arrays['fps']), arrays['joint_names'].tolist(), arrays['parents'].tolist(),
                         skeleton_type=skeleton_type, source_up=source_up, source_unit=source_unit)


def load_bvh(path, *, source_up, source_unit):
    text = Path(path).read_text(encoding='utf-8-sig')
    if 'MOTION' not in text:
        raise MotionError('BVH is missing its MOTION section.')
    hierarchy, motion_text = text.split('MOTION', 1)
    tokens = re.findall(r'[{}]|[^\s{}]+', hierarchy)
    cursor = 0
    names, parents, offsets, channels = [], [], [], []

    def take(expected=None):
        nonlocal cursor
        if cursor >= len(tokens):
            raise MotionError('Truncated BVH hierarchy.')
        value = tokens[cursor]
        cursor += 1
        if expected is not None and value != expected:
            raise MotionError(f'Expected {expected}, found {value}.')
        return value

    def joint(parent, end=False):
        if len(names) >= MAX_JOINTS:
            raise MotionError('BVH contains too many joints.')
        if end:
            take('Site')
            name = f'{names[parent]}_End{len(names)}'
        else:
            name = take()
        index = len(names)
        names.append(name)
        parents.append(parent)
        channels.append([])
        take('{')
        take('OFFSET')
        offsets.append([float(take()) for _ in range(3)])
        if not end:
            take('CHANNELS')
            count = int(take())
            if count not in (3, 6):
                raise MotionError('Only 3-rotation or 6-position/rotation BVH channels are supported.')
            channels[index] = [take() for _ in range(count)]
            rotations = [c for c in channels[index] if c.endswith('rotation')]
            if sorted(rotations) != ['Xrotation', 'Yrotation', 'Zrotation']:
                raise MotionError('BVH rotation channels must describe each axis exactly once.')
            if count == 6 and (sorted(channels[index][:3]) != ['Xposition', 'Yposition', 'Zposition'] or channels[index][3:] != rotations):
                raise MotionError('Unsupported interleaved BVH translation/rotation channels.')
            if count == 3 and channels[index] != rotations:
                raise MotionError('Unsupported BVH channels.')
        while tokens[cursor] != '}':
            kind = take()
            if kind == 'JOINT':
                joint(index)
            elif kind == 'End':
                joint(index, end=True)
            else:
                raise MotionError(f'Unexpected hierarchy token: {kind}.')
        take('}')

    try:
        take('HIERARCHY')
        take('ROOT')
        joint(-1)
        if cursor != len(tokens):
            raise MotionError('Extra BVH hierarchy tokens.')
        match = re.fullmatch(r'\s*Frames:\s*(\d+)\s*Frame\s+Time:\s*([\d.eE+-]+)\s*(.*)', motion_text, re.S)
        if not match:
            raise MotionError('Invalid BVH frame header.')
        frames = int(match[1])
        interval = float(match[2])
        if not 1 <= frames <= MAX_FRAMES or not math.isfinite(interval) or interval <= 0:
            raise MotionError('Invalid BVH frame count/time.')
        width = sum(len(c) for c in channels)
        raw_values = match[3].split()
        if len(raw_values) != frames * width:
            raise MotionError('BVH motion values do not match its declared dimensions.')
        values = np.array([float(x) for x in raw_values]).reshape(frames, width)
        positions = np.zeros((frames, len(names), 3))
        global_rotations = np.zeros((frames, len(names), 3, 3))
        column = 0
        for index, channel_names in enumerate(channels):
            local_position = np.tile(offsets[index], (frames, 1))
            euler_values, order = [], ''
            for channel in channel_names:
                if channel.endswith('position'):
                    local_position[:, 'XYZ'.index(channel[0])] += values[:, column]
                else:
                    euler_values.append(values[:, column])
                    order += channel[0]
                column += 1
            local_rotation = Rotation.from_euler(order, np.stack(euler_values, axis=-1), degrees=True).as_matrix() if order else np.tile(np.eye(3), (frames, 1, 1))
            parent = parents[index]
            if parent == -1:
                positions[:, index] = local_position
                global_rotations[:, index] = local_rotation
            else:
                positions[:, index] = positions[:, parent] + np.einsum('tij,tj->ti', global_rotations[:, parent], local_position)
                global_rotations[:, index] = global_rotations[:, parent] @ local_rotation
        return normalize(positions, 1 / interval, names, parents, skeleton_type='BVH:' + names[0], source_up=source_up, source_unit=source_unit)
    except (IndexError, ValueError, OverflowError) as error:
        if isinstance(error, MotionError):
            raise
        raise MotionError('Invalid or unsupported BVH.') from error


def read_motion(path, *, source_up='Y', source_unit='m'):
    path = Path(path)
    if path.suffix.lower() == '.json':
        return validate_motion(json.loads(path.read_text()))
    if path.suffix.lower() == '.bvh':
        return load_bvh(path, source_up=source_up, source_unit=source_unit)
    if path.suffix.lower() == '.npz':
        return load_npz(path, source_up=source_up, source_unit=source_unit)
    raise MotionError('Supported motion imports: JSON, BVH, NPZ.')


def save_motion(path, data):
    validate_motion(data)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')))


def metrics(data):
    positions = np.asarray(data['positions'])
    fps = data['fps']
    # This is a kinematic diagnostic, not a semantic/naturalness evaluation.
    acceleration = np.diff(positions, n=2, axis=0) * fps**2
    return {'frames': len(positions), 'fps': fps, 'duration': len(positions) / fps,
            'acceleration_rms_m_s2': float(np.sqrt(np.mean(acceleration**2))) if acceleration.size else None,
            'semantic_alignment': None, 'naturalness': None,
            'evaluation_note': '意味的一致・自然さは未評価。主観評価が必要。足接地の真値なしに足滑りを採点しません。'}


def viewer_fixture():
    """Explicitly synthetic animation for viewer tests; never a trained model output."""
    names = ['pelvis', 'spine', 'neck', 'head', 'left_shoulder', 'left_elbow', 'left_hand',
             'right_shoulder', 'right_elbow', 'right_hand', 'left_hip', 'left_knee', 'left_foot',
             'right_hip', 'right_knee', 'right_foot']
    parents = [-1,0,1,2,2,4,5,2,7,8,0,10,11,0,13,14]
    pose = np.array([[0,1,0],[0,1.3,0],[0,1.6,0],[0,1.8,0],[-.22,1.55,0],[-.45,1.3,0],[-.55,1.08,0],
                     [.22,1.55,0],[.45,1.3,0],[.55,1.08,0],[-.15,.95,0],[-.15,.5,0],[-.15,.08,.1],
                     [.15,.95,0],[.15,.5,0],[.15,.08,.1]])
    positions = np.tile(pose, (120,1,1))
    phase = np.arange(120) / 30 * np.pi
    positions[:,9,1] += .25 * np.sin(phase)
    positions[:,6,2] += .12 * np.sin(phase)
    return normalize(positions, 30, names, parents, skeleton_type='synthetic-16', source_up='Y', source_unit='m',
                     metadata={'provenance': 'synthetic_viewer_fixture', 'trained_model_output': False,
                               'notice': 'ビューアー検証用の人工アニメーション。学習済みモデルの推論結果ではありません。'})
