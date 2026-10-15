#!/usr/bin/env python3
"""Measure real resident Kimodo text-to-skeleton inference on one CUDA GPU.

Weights and text embeddings are never replaced with fixtures. Every timed call
encodes its original text again. CPU transfer and upper-body JSON serialization
are included in bone_ready_seconds; startup, network and video export are not.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--serve', action='store_true', help='Keep this measured model resident on loopback port 8766.')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Existing benchmark output is preserved.')
    config = json.loads(args.config.read_text())
    args.output.mkdir(parents=True)
    os.environ.update(TEXT_ENCODER_MODE='local', TEXT_ENCODER_DEVICE='cuda', LOCAL_CACHE='true',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import numpy as np
    import torch
    from kimodo import load_model
    from kimodo.skeleton.definitions import SOMASkeleton77
    if not torch.cuda.is_available():
        raise RuntimeError('A real CUDA GPU is required.')
    torch.set_num_threads(config.get('cpu_threads', 8))
    torch.cuda.init()
    torch.cuda.synchronize()
    info = {
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'gpu_name': torch.cuda.get_device_name(),
        'gpu_vram_mib': torch.cuda.get_device_properties(0).total_memory / 1024**2,
        'compute_capability': list(torch.cuda.get_device_capability()),
        'torch': torch.__version__, 'cuda_runtime': torch.version.cuda,
        'python': platform.python_version(), 'platform': platform.platform(),
        'cpu_threads': torch.get_num_threads(), 'cpu_count': os.cpu_count(),
        'source_commit': config['source_commit'], 'checkpoint': config['checkpoint'],
        'checkpoint_revision': config['checkpoint_revision'],
        'batch_size': 1, 'post_processing': False, 'text_encoder_device': 'cuda',
        'motion_precision': 'float32', 'text_encoder_precision': 'bfloat16',
        'embedding_cache': False, 'torch_compile': False,
        'timing_note': 'Resident process; original text encoding, CUDA motion generation, CPU transfer and upper-body JSON serialization. No network/startup/rendering.',
    }
    try:
        info['nvidia_smi'] = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,driver_version,memory.total,power.limit',
             '--format=csv,noheader'], text=True).strip()
    except (OSError, subprocess.SubprocessError):
        info['nvidia_smi'] = None
    write_json(args.output/'hardware.json', info)
    load_start = time.perf_counter()
    # Transformers 5 may auto-load the first PEFT adapter while the official
    # wrapper also loads it explicitly. Build the same two-adapter pipeline
    # explicitly and verify every LoRA tensor before using the text encoder.
    from kimodo.model.llm2vec.llm2vec import LLM2Vec
    from kimodo.model.llm2vec.llm2vec_wrapper import LLM2VecEncoder
    from peft import PeftModel
    from safetensors.torch import load_file
    cache = Path(os.environ['HF_HOME'])/'hub'
    def snapshot(repo):
        folder = cache/('models--'+repo.replace('/', '--'))
        return folder/'snapshots'/(folder/'refs/main').read_text().strip()
    base = snapshot('meta-llama/Meta-Llama-3-8B-Instruct')
    mntp = snapshot('McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp')
    supervised = snapshot('McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised')
    plain = args.output/'plain-llama-base'
    plain.mkdir()
    for source in list(base.iterdir())+[mntp/name for name in ['tokenizer.json','tokenizer_config.json','special_tokens_map.json']]:
        if source.is_file() and not (plain/source.name).exists():
            (plain/source.name).symlink_to(source.resolve())
    def verify_adapter(module, folder):
        def key(value):
            value = value.replace('.default.', '.')
            while value.startswith('base_model.model.'):
                value = value[len('base_model.model.'):]
            while value.startswith('model.'):
                value = value[len('model.'):]
            return value
        actual = {key(k): v for k,v in module.state_dict().items() if '.lora_' in k}
        expected = {key(k):v for k,v in load_file(str(folder/'adapter_model.safetensors')).items()}
        if set(actual) != set(expected) or not all(torch.equal(actual[k].detach().cpu(),v) for k,v in expected.items()):
            raise RuntimeError('Text encoder adapter tensors differ from the official checkpoint.')
        return len(expected)
    embedding = LLM2Vec.from_pretrained(str(plain), peft_model_name_or_path=str(mntp),
                                       merge_peft=False, torch_dtype=torch.bfloat16)
    verified_mntp = verify_adapter(embedding.model, mntp)
    embedding.model = embedding.model.merge_and_unload()
    embedding.model = PeftModel.from_pretrained(embedding.model, str(supervised))
    verified_supervised = verify_adapter(embedding.model, supervised)
    encoder = LLM2VecEncoder.__new__(LLM2VecEncoder)
    encoder.model = embedding.to('cuda').eval()
    encoder.llm_dim = 4096
    encoder._device = 'cuda'
    for parameter in encoder.model.parameters():
        parameter.requires_grad_(False)
    info['verified_lora_tensor_counts'] = {'mntp':verified_mntp,'supervised':verified_supervised}
    model = load_model(config['checkpoint'], device='cuda', text_encoder=encoder)
    torch.cuda.synchronize()
    info['model_load_seconds'] = time.perf_counter() - load_start
    actual_encoder = model.text_encoder

    class TimedEncoder:
        last_seconds = None

        def __call__(self, text):
            torch.cuda.synchronize()
            started = time.perf_counter()
            value = actual_encoder(text)
            torch.cuda.synchronize()
            self.last_seconds = time.perf_counter() - started
            return value

    timer = TimedEncoder()
    model.text_encoder = timer
    bones = SOMASkeleton77.bone_order_names_with_parents
    names = [name for name, _ in bones]
    # Retain Hips solely as the upper-body coordinate reference, not as a
    # locomotion command. All leg/foot/toe branches are excluded from this JSON.
    excluded = ('Leg', 'Shin', 'Foot', 'Toe')
    upper_indices = [i for i, name in enumerate(names) if not any(x in name for x in excluded)]
    upper_names = [names[i] for i in upper_indices]
    upper_parents = [-1 if bones[i][1] is None else upper_names.index(bones[i][1]) for i in upper_indices]
    results = []

    def run(unit, mode, trial, warmup=False):
        torch.set_float32_matmul_precision(mode['matmul_precision'])
        torch.backends.cudnn.allow_tf32 = mode['matmul_precision'] != 'highest'
        seed = config['seed'] + max(trial, 0)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            output = model(unit['text'], unit['frames'], num_denoising_steps=mode['steps'],
                           cfg_weight=[2.0, 2.0], post_processing=False,
                           return_numpy=False, progress_bar=lambda values: values)
        torch.cuda.synchronize()
        generation_seconds = time.perf_counter() - started
        positions = output['posed_joints'].detach().float().cpu().numpy()
        if positions.shape != (unit['frames'], 77, 3) or not np.isfinite(positions).all():
            raise ValueError('Official model returned an invalid skeleton.')
        upper = {'schema': 'motion-lab/v1', 'fps': float(model.fps),
                 'positions': positions[:, upper_indices].tolist(),
                 'joint_names': upper_names, 'parents': upper_parents,
                 'metadata': {'trained_model_output': True, 'input_text': unit['text'],
                              'upper_body_only': True, 'generation_scope': 'full_body_then_select_upper_body',
                              'hips_role': 'coordinate_reference', 'mode': mode['id']}}
        payload = json.dumps(upper, ensure_ascii=False, separators=(',', ':')).encode()
        bone_seconds = time.perf_counter() - started
        receipt = {'unit': unit['id'], 'text': unit['text'], 'mode': mode['id'], 'trial': trial,
                   'warmup': warmup, 'seed': seed, 'frames': unit['frames'], 'fps': float(model.fps),
                   'duration_seconds': unit['frames']/float(model.fps), 'denoising_steps': mode['steps'],
                   'matmul_precision': mode['matmul_precision'], 'text_encoding_seconds': timer.last_seconds,
                   'generation_seconds': generation_seconds,
                   'motion_and_decode_seconds': generation_seconds - timer.last_seconds,
                   'bone_ready_seconds': bone_seconds,
                   'upper_body_transfer_and_serialization_seconds': bone_seconds-generation_seconds,
                   'peak_torch_allocated_mib': torch.cuda.max_memory_allocated()/1024**2,
                   'upper_json_sha256': hashlib.sha256(payload).hexdigest()}
        if trial == 0 and not warmup:
            directory = args.output/mode['id']/unit['id']
            directory.mkdir(parents=True)
            (directory/'upper-motion.json').write_bytes(payload)
            np.savez_compressed(directory/'original.npz',
                                **{k: v.detach().cpu().numpy() for k, v in output.items() if torch.is_tensor(v)})
            write_json(directory/'receipt.json', receipt)
        results.append(receipt)
        with (args.output/'measurements.jsonl').open('a') as f:
            f.write(json.dumps(receipt, ensure_ascii=False)+'\n')
        print(json.dumps(receipt, ensure_ascii=False), flush=True)

    for mode in config['modes']:
        # Warm up each sequence length explicitly; record rather than hide its cost.
        for unit in config['units']:
            run(unit, mode, -1, warmup=True)
        for trial in range(config['repeats']):
            for unit in config['units']:
                run(unit, mode, trial)
    summary = []
    for mode in config['modes']:
        for unit in config['units']:
            rows = [r for r in results if r['mode'] == mode['id'] and r['unit'] == unit['id'] and not r['warmup']]
            summary.append({'mode': mode['id'], 'unit': unit['id'], 'text': unit['text'],
                            'frames': unit['frames'], 'repeats': len(rows),
                            **{key: statistics.median(r[key] for r in rows)
                               for key in ['bone_ready_seconds','generation_seconds','text_encoding_seconds','motion_and_decode_seconds']},
                            'min_bone_ready_seconds': min(r['bone_ready_seconds'] for r in rows),
                            'max_bone_ready_seconds': max(r['bone_ready_seconds'] for r in rows)})
    write_json(args.output/'summary.json', summary)
    write_json(args.output/'hardware.json', info)
    write_json(args.output/'config.json', config)
    (args.output/'DONE').write_text(datetime.now(timezone.utc).isoformat())
    if args.serve:
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *unused):
                pass

            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                if self.path != '/generate' or not 0 < length < 8192:
                    self.send_error(400)
                    return
                request = json.loads(self.rfile.read(length))
                if not request['id'].replace('-', '').isalnum() or not 1 <= request['frames'] <= 600:
                    self.send_error(400)
                    return
                mode = next(m for m in config['modes'] if m['id'] == request['mode'])
                unit = {'id': request['id'], 'text': request['text'], 'frames': request['frames']}
                try:
                    run(unit, mode, 0)
                    receipt = results[-1]
                    import base64
                    directory = args.output/mode['id']/unit['id']
                    payload = json.dumps({'receipt': receipt,
                        'upper_motion': json.loads((directory/'upper-motion.json').read_text()),
                        'original_base64': base64.b64encode((directory/'original.npz').read_bytes()).decode()},
                        ensure_ascii=False).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as error:
                    self.send_error(500, type(error).__name__)

        print('RESIDENT_SERVICE_READY', flush=True)
        HTTPServer(('127.0.0.1', 8766), Handler).serve_forever()


if __name__ == '__main__':
    main()
