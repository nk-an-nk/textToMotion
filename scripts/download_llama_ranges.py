import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

import httpx
from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_url

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / '.motion-lab'
TOKEN = re.search(r'hf_[A-Za-z0-9]+', (ROOT / 'configs/huggingface.md').read_text(encoding='utf-8').replace('\\_', '_')).group()
REPO = 'meta-llama/Meta-Llama-3-8B-Instruct'
REV = HfApi(token=TOKEN).model_info(REPO).sha
BLOBS = DATA / 'hf-cache/hub/models--meta-llama--Meta-Llama-3-8B-Instruct/blobs'
WORK = DATA / 'range-downloads'
WORK.mkdir(exist_ok=True)
CHUNK = 1024 * 1024
OLD_HTTP_SUFFIXES = ('85cc2ebf', 'cf3a0a0c', 'f8c58d3e', 'da022610', 'faa24d35')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(4 * CHUNK), b''):
            h.update(b)
    return h.hexdigest()

for number in range(1, 5):
    name = f'model-{number:05d}-of-00004.safetensors'
    meta = get_hf_file_metadata(hf_hub_url(REPO, name, revision=REV), token=TOKEN)
    final = BLOBS / meta.etag
    if final.exists():
        if final.stat().st_size != meta.size or digest(final) != meta.etag:
            raise RuntimeError('Existing completed weight checksum mismatch: ' + name)
        print(name + ': existing official checksum verified', flush=True)
        continue
    part = WORK / (meta.etag + '.part')
    state = WORK / (meta.etag + '.json')
    completed = set(json.loads(state.read_text())['completed']) if state.exists() else set()
    if not part.exists():
        sources = [p for p in BLOBS.glob(meta.etag + '.*.incomplete')
                   if p.name.split('.')[-2] in OLD_HTTP_SUFFIXES]
        source = max(sources, key=lambda p: p.stat().st_size) if sources else None
        prefix = 0
        if source:
            shutil.copyfile(source, part)
            prefix = part.stat().st_size
        with part.open('ab') as f:
            f.truncate(meta.size)
        completed = set(range(prefix // CHUNK))
    count = (meta.size + CHUNK - 1) // CHUNK
    started = time.monotonic()
    previous = started
    with httpx.Client(timeout=40, limits=httpx.Limits(max_connections=24, max_keepalive_connections=24)) as client:
        def fetch(index):
            first = index * CHUNK
            last = min(meta.size, first + CHUNK) - 1
            for attempt in range(6):
                try:
                    response = client.get(meta.location, headers={'Range': f'bytes={first}-{last}', 'Accept-Encoding': 'identity'})
                    if response.status_code != 206 or response.headers.get('content-range') != f'bytes {first}-{last}/{meta.size}':
                        raise RuntimeError('Unexpected range response status ' + str(response.status_code))
                    if len(response.content) != last - first + 1:
                        raise RuntimeError('Incomplete range response')
                    return index, response.content
                except Exception:
                    if attempt == 5:
                        raise RuntimeError('Range download failed: ' + name + ' chunk ' + str(index)) from None
                    time.sleep(min(2 ** attempt, 10))
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool, part.open('r+b') as target:
            pending = iter(i for i in range(count) if i not in completed)
            futures = {}
            for _ in range(48):
                index = next(pending, None)
                if index is not None:
                    futures[pool.submit(fetch, index)] = index
            while futures:
                done, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    futures.pop(future)
                    index, content = future.result()
                    target.seek(index * CHUNK)
                    target.write(content)
                    completed.add(index)
                    next_index = next(pending, None)
                    if next_index is not None:
                        futures[pool.submit(fetch, next_index)] = next_index
                if time.monotonic() - previous >= 15 or not futures:
                    target.flush()
                    temporary = state.with_suffix('.tmp')
                    temporary.write_text(json.dumps({'revision': REV, 'completed': sorted(completed)}))
                    temporary.replace(state)
                    print(f'{name}: {len(completed)}/{count} MiB chunks verified received', flush=True)
                    previous = time.monotonic()
    if digest(part) != meta.etag:
        raise RuntimeError('Official SHA-256 mismatch: ' + name)
    part.replace(final)
    print(name + ': official SHA-256 verified; cached', flush=True)
print('All four weight shards downloaded and verified.', flush=True)
