#!/usr/bin/env python3
"""Local development launcher. Explicit opt-in; key stays in child process, never a file."""
import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable-realtime', action='store_true')
    parser.add_argument('--budget-usd', type=float, default=0)
    parser.add_argument('--text-first', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'.motion-lab')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024–65535')
    env = os.environ.copy()
    if args.enable_realtime:
        if args.budget_usd < 1: parser.error('--budget-usd >= 1 is required to authorize API allowances')
        if not env.get('OPENAI_API_KEY'):
            env['OPENAI_API_KEY'] = env.get('MOTION_LAB_OPENAI_API_KEY') or env.get('realtime', '')
        if not env.get('OPENAI_API_KEY'):
            env['OPENAI_API_KEY'] = getpass.getpass('OpenAI API key (hidden; child process only): ').strip()
        if not env['OPENAI_API_KEY']: parser.error('API key was not provided')
    env.update(OPENAI_REALTIME_ENABLED='1' if args.enable_realtime else '0',
               OPENAI_API_BUDGET_USD=str(args.budget_usd),
               OPENAI_TEXT_FIRST_ENABLED='1' if args.text_first else '0',
               MOTION_LAB_DATA=str(args.data_dir.resolve()), MOTION_LAB_OUTPUTS=str(args.data_dir.resolve()/'outputs'),
               HF_HOME=str(args.data_dir.resolve()/'hf-cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',MPLCONFIGDIR=str(args.data_dir.resolve()/'matplotlib-cache'))
    print(f'Conversation: http://127.0.0.1:{args.port}/conversation')
    subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
                    '--port',str(args.port)],cwd=ROOT,env=env,check=True)


if __name__ == '__main__': main()
