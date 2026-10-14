#!/usr/bin/env python3
"""Download only the official encoder files; record revisions and verify existing files."""
import argparse
import hashlib
import json
import os
from pathlib import Path

REPOSITORIES=[
    'meta-llama/Meta-Llama-3-8B-Instruct',
    'McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp',
    'McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised',
]
PATTERNS=['*.json','*.safetensors','*.model','*.txt','*.tiktoken','*.md','LICENSE*']


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(4*1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def valid_record(record):
    return bool(record.get('sha256')) and all(
        (Path(record['path'])/name).is_file() and digest(Path(record['path'])/name)==sha
        for name,sha in record.get('sha256',{}).items())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    records=json.loads(args.manifest.read_text(encoding='utf-8')) if args.manifest.is_file() else {}
    complete=all(repo in records and valid_record(records[repo]) for repo in REPOSITORIES)
    if args.check:
        if not complete:
            raise RuntimeError('Encoder assets are missing or their checksums changed.')
        print('All encoder assets verified; no downloads.')
        return
    from huggingface_hub import HfApi,snapshot_download
    api=HfApi()
    for repo in REPOSITORIES:
        if repo in records:
            if not valid_record(records[repo]):
                raise RuntimeError(f'Existing encoder files changed: {repo}. Inspect them before replacing anything.')
            continue
        info=api.model_info(repo)
        # Branch resolution creates refs/main needed by the official PEFT backbone loader.
        # Check against the revision observed before downloading to catch a moving branch.
        path=Path(snapshot_download(repo_id=repo,revision='main',allow_patterns=PATTERNS))
        if path.name!=info.sha:
            raise RuntimeError(f'{repo}: revision changed during download; rerun to record a consistent revision.')
        files=[file for file in path.rglob('*') if file.is_file()]
        if not any(file.suffix=='.safetensors' for file in files):
            raise RuntimeError(f'{repo}: no safetensors weights obtained.')
        records[repo]={'revision':info.sha,'path':str(path),
                       'sha256':{file.relative_to(path).as_posix():digest(file) for file in files}}
        args.manifest.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.manifest.with_suffix('.tmp')
        temporary.write_text(json.dumps(records,indent=2),encoding='utf-8')
        temporary.replace(args.manifest)
        print(f'Encoder downloaded and SHA-256 recorded: {repo} @ {info.sha}')


if __name__=='__main__':
    main()
