#!/usr/bin/env python3
"""Build a small credential-free bootstrap; weights are transferred separately."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--normalization',type=Path,required=True,help='Official original HumanML3D Mean.npy and Std.npy directory')
    p.add_argument('--momask-archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Existing bootstrap is preserved.')
    root=Path(__file__).resolve().parents[1];assets=json.loads((root/'configs/masked_assets_20261016.json').read_text())
    digest=hashlib.sha256()
    with a.momask_archive.open('rb') as f:
        while chunk:=f.read(4*1024*1024):digest.update(chunk)
    if digest.hexdigest()!=assets['momask_archive_sha256']:raise ValueError('MoMask archive must match the verified experiment checkpoint bundle.')
    import numpy as np
    for name in ['Mean.npy','Std.npy']:
        values=np.load(a.normalization/name,allow_pickle=False)
        if values.shape!=(263,) or not np.isfinite(values).all() or (name=='Std.npy' and not (values>0).all()):raise ValueError('Invalid HumanML3D normalization.')
        if hashlib.sha256((a.normalization/name).read_bytes()).hexdigest()!=assets['molingo_normalization']['sha256'][name]:raise ValueError('Normalization differs from the verified original dataset statistics.')
    cache=a.output.parent/'t5-tokenizer';cache.mkdir(parents=True,exist_ok=True)
    for name in ['config.json','spiece.model','tokenizer.json']:
        dest=cache/name
        if not dest.exists():
            url='https://huggingface.co/google-t5/t5-large/resolve/150ebc2c4b72291e770f58e6057481c8d2ed331a/'+name
            with urllib.request.urlopen(url,timeout=60) as r:content=r.read()
            dest.write_bytes(content)
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=assets['t5_tokenizer']['sha256'][name]:raise ValueError('Pinned T5 tokenizer checksum mismatch.')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(a.output,'w:gz') as t:
        for name in ['benchmark_masked_models.py','resource_measurement.py']:t.add(root/'scripts'/name,arcname='project/scripts/'+name)
        t.add(root/'configs/masked_comparison_20261016.json',arcname='project/configs/masked_comparison_20261016.json')
        t.add(root/'configs/masked_assets_20261016.json',arcname='asset-manifest.json')
        t.add(root/'scripts/setup_masked_runtime.py',arcname='remote_setup.py')
        t.add(cache,arcname='assets/molingo/t5-tokenizer')
        t.add(a.normalization,arcname='assets/molingo/normalization')
    print(json.dumps({'bootstrap':str(a.output),'bytes':a.output.stat().st_size,'weights_included':False,'credentials_included':False}))


if __name__=='__main__':main()
