#!/usr/bin/env python3
"""Generate a per-job assets/config overlay and invoke the unchanged official v1 demo."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from omegaconf import OmegaConf

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for flag in ('repo', 'runtime', 'output', 'text', 'task', 'seed', 'duration'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--audio')
    args = parser.parse_args()
    repo, output = Path(args.repo), Path(args.output)
    config = json.loads(Path(args.runtime).read_text())['language_of_motion']
    assets = OmegaConf.load(config.get('cfg_assets', repo / 'configs/assets.yaml'))
    assets.FOLDER = str(output)
    assets.SEED_VALUE = int(args.seed)
    assets.TEST.FOLDER = str(output)
    assets.TEST.TEST_LENGTH = int(float(args.duration) * 30)
    overlay = output / 'lom_assets.yaml'
    OmegaConf.save(assets, overlay)
    cfg = config.get('cfg_audio' if args.task == 'cospeech' else 'cfg_text',
                     'configs/demo_cospeech.yaml' if args.task == 'cospeech' else 'configs/demo_text2motion.yaml')
    cfg_path = Path(cfg)
    if not cfg_path.is_absolute():
        cfg_path = repo / cfg_path
    experiment = OmegaConf.merge(OmegaConf.load(repo/'configs/default.yaml'),OmegaConf.load(cfg_path),assets)
    # Official demo.py falls back to random initialization when TEST.CHECKPOINTS is empty.
    # This adapter must never describe such output as pretrained inference.
    checkpoint = experiment.TEST.get('CHECKPOINTS')
    if not checkpoint:
        raise RuntimeError('LoM requires a real pretrained LM checkpoint; random initialization is rejected.')
    checkpoint_path = Path(checkpoint)
    if not checkpoint_path.is_absolute():
        checkpoint_path = repo / checkpoint_path
    if not checkpoint_path.is_file():
        raise FileNotFoundError('LoM pretrained checkpoint does not exist: ' + str(checkpoint_path))
    command = [sys.executable, 'demo.py', '--cfg', cfg, '--cfg_assets', str(overlay), '--task', args.task]
    command += ['--audio', args.audio] if args.audio else ['--text', args.text]
    subprocess.run(command, cwd=repo, check=True)
