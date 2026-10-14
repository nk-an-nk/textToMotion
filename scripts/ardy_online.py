#!/usr/bin/env python3
"""Pinned community ARDY inference. Never substitute examples or evade provider limits."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.request

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.base import redact

SPACE='hugging-apps/ardy-human-motion'
ENDPOINT='https://hugging-apps-ardy-human-motion.hf.space'
REVISION='344cab081ed29a48879683c0a78f80918b5a1681'
APP_SHA256='54d625cd8984c6980abc54a7fe953718205a44bfb53f651115ca68b47754d828'
CHECKPOINT='nvidia/ARDY-Core-RP-20FPS-Horizon40'


def native_duration(seconds):
    # The community UI enforces 1s; ARDY's native frames are 20fps.
    return max(1, math.ceil(seconds*20-1e-5)/20)


def check_service():
    with urllib.request.urlopen('https://huggingface.co/api/spaces/'+SPACE, timeout=20) as response:
        info=json.load(response)
    if info.get('runtime', {}).get('stage') != 'RUNNING':
        raise RuntimeError('The public ARDY service is not running; no GPU start/resume is performed.')
    if info['sha'] != REVISION:
        raise RuntimeError('Public ARDY source changed; review it before requesting inference.')
    with urllib.request.urlopen(f'https://huggingface.co/spaces/{SPACE}/resolve/{REVISION}/app.py', timeout=20) as response:
        source=response.read(256*1024)
    if hashlib.sha256(source).hexdigest() != APP_SHA256:
        raise RuntimeError('Reviewed public ARDY source hash does not match.')
    return info


def validate_result(payload, original, *, prompt, seed, frames):
    if (payload.get('prompt') != prompt or payload.get('seed') != seed or payload.get('fps') != 20
            or payload.get('num_frames') != frames or payload.get('num_joints') != 27):
        raise ValueError('Provider result does not match the requested prompt, seed or native skeleton.')
    if not Path(original).is_file() or Path(original).stat().st_size > 32*1024*1024:
        raise ValueError('Expected a bounded NPZ download.')
    with np.load(original, allow_pickle=False) as data:
        joints=data['posed_joints']
        if str(data['text'].item()) != prompt or float(data['fps']) != 20:
            raise ValueError('NPZ text/FPS does not match the request.')
        if joints.shape != (frames, 27, 3) or not np.isfinite(joints).all():
            raise ValueError('Invalid native ARDY joint positions.')
        if not np.allclose(joints[:, 0], np.asarray(payload['root']), atol=.00011):
            raise ValueError('NPZ and provider viewer payload do not describe the same motion.')


def generate(prompt, seconds, seed, output):
    from gradio_client import Client
    from huggingface_hub import get_token
    token=get_token()
    if not token:
        raise RuntimeError('HF_TOKEN is required for this ZeroGPU inference service. Never paste it into chat.')
    output=Path(output)
    if output.exists() or output.with_suffix('.metadata.json').exists():
        raise ValueError('Existing model output is preserved. Use a new filename.')
    info=check_service(); duration=native_duration(seconds); frames=round(duration*20); began=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='ardy-download-') as temporary:
        client=Client(ENDPOINT, hf_token=token, download_files=temporary, verbose=False)
        job=client.submit(prompt=prompt, duration=min(10, duration+1e-7), waypoints='', diffusion_steps=10,
                          cfg_text=2., cfg_constraint=2., postprocess=False, seed=seed, randomize_seed=False,
                          api_name='/generate')
        try:
            result=job.result(timeout=150)
        except Exception as error:
            job.cancel()
            raise RuntimeError('Public ARDY inference failed: '+redact(str(error))) from None
        payload=json.loads(result[0])
        if result[2] != seed:
            raise ValueError('Provider randomized the requested seed.')
        validate_result(payload, result[1], prompt=prompt, seed=seed, frames=frames)
        output.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(result[1], output)
    metadata={'model_id':'ardy', 'task_type':'instruction', 'trained_model_output':True,
              'backend':'community_online_demo', 'provider':'hugging-apps (community, not NVIDIA-hosted)',
              'endpoint':ENDPOINT, 'space_repository':SPACE, 'space_commit':REVISION, 'app_sha256':APP_SHA256,
              'checkpoint':CHECKPOINT, 'checkpoint_sha256':None, 'text_encoder':'LLM2Vec-Llama-3-8B (provider)',
              'text_conditioned':True, 'audio_conditioned':False, 'prompt':prompt, 'seed':seed,
              'fps':20, 'frames_requested':frames, 'duration_requested':duration, 'diffusion_steps':10,
              'text_guidance':2., 'constraint_guidance':2., 'postprocess':False,
              'device':'remote: '+str(info.get('runtime', {}).get('hardware', {}).get('current'))+' (provider-reported)',
              'inference_time':time.monotonic()-began, 'timing_note':'Remote wall time includes queue, text encoding and transfer.',
              'download_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
              'provider_result':{key:payload[key] for key in ('fps','num_frames','num_joints','prompt','seed')}}
    output.with_suffix('.metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prompt'); parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--seed', type=int, default=0); parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if not args.prompt.strip() or len(args.prompt)>4000 or not math.isfinite(args.duration) or not .5<=args.duration<=10 or not 0<=args.seed<2**31:
        parser.error('Use a nonempty prompt, 0.5–10 seconds and a valid seed.')
    try:
        print(json.dumps(generate(args.prompt, args.duration, args.seed, args.output), ensure_ascii=False))
    except Exception as error:
        print(redact(str(error)), file=sys.stderr); sys.exit(1)
