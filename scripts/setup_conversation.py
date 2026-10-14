#!/usr/bin/env python3
"""Prepare conversation application only; model/CUDA setup and API opt-in are independent."""
import argparse
import os
from pathlib import Path
from setup_lab import ROOT, Runner, load_json, prepare_app, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=ROOT/'.motion-lab')
    args = parser.parse_args()
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    (data/'logs').mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', MOTION_LAB_NPM_CACHE=str(data/'npm-cache'),MPLCONFIGDIR=str(data/'matplotlib-cache'))
    path = data/'conversation-setup.json'
    state = load_json(path)
    prepare_app(Runner(data/'logs/conversation-setup.log', env), state, lambda: write_json(path, state))
    print('Application ready. Model readiness is separate. Run start-conversation.ps1.')


if __name__ == '__main__': main()
