#!/usr/bin/env python3
"""Encode canonical text locally; gated Hugging Face credentials never leave this machine."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
try:
    from scripts.resource_measurement import peak_ram_mib
except ModuleNotFoundError:
    from resource_measurement import peak_ram_mib


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Existing embeddings are preserved.')
    os.environ.update(TEXT_ENCODER_DEVICE='cpu',HF_HUB_ENABLE_HF_TRANSFER='0',HF_HUB_DISABLE_XET='1')
    os.environ.setdefault('HF_HOME',str(Path('/workspace/shared/motion-lab/huggingface')))
    import torch
    from ardy.model.load_model import load_text_encoder
    torch.set_num_threads(8);start=time.monotonic()
    encoder=load_text_encoder(mode='local',device='cpu')
    load=time.monotonic()-start;a.output.mkdir(parents=True)
    receipts=[]
    for unit in json.loads(a.config.read_text())['segments']:
        t=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
        with torch.inference_mode():embedding,length=encoder([unit['text']])
        import numpy as np
        np.savez(a.output/(unit['id']+'.npz'),embedding=embedding.float().cpu().numpy(),length=np.asarray(length))
        receipts.append({'id':unit['id'],'text':unit['text'],'input_submitted_at_utc':utc,
            'embedding_seconds':time.monotonic()-t,'model_load_seconds':load,
            'cpu_threads':8,'peak_ram_mib':peak_ram_mib()})
        print(json.dumps(receipts[-1],ensure_ascii=False),flush=True)
    (a.output/'timings.json').write_text(json.dumps({'segments':receipts,'model_load_seconds':load},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    try:main()
    except Exception as e:
        # Library exceptions can contain authenticated URLs. Keep only the class.
        print('ARDY text encoder failed: '+type(e).__name__,flush=True);raise SystemExit(1)
