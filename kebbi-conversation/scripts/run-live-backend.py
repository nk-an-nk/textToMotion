#!/usr/bin/env python3
"""Run the backend on localhost with a key read from an external file or env.

Install backend/requirements.txt in your chosen Python environment first.
No provider credentials are written to the repository or sent to the robot.
"""
import argparse
import os
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--model', default='gpt-4.1-mini-2025-04-14')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    key = os.environ.get('LLM_API_KEY', '').strip()
    if args.key_file:
        keys = re.findall(r'sk-[A-Za-z0-9_-]+', args.key_file.read_text().strip())
        if len(keys) != 1:
            parser.error('The key file must contain exactly one API key.')
        key = keys[0]
    if not key:
        parser.error('Supply --key-file or LLM_API_KEY.')
    os.environ.update(LLM_PROVIDER='openai', LLM_API_KEY=key, LLM_MODEL=args.model,
                      LLM_BASE_URL='https://api.openai.com/v1', LLM_JSON_MODE='true',
                      LOG_CONTENT='false')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    import uvicorn
    print(f'Kebbi backend: OpenAI / {args.model} / localhost:{args.port}', flush=True)
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
