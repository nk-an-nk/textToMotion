import importlib.util
import json
import sys
from pathlib import Path
from .base import ModelAdapter
from app import settings
from app.official_schema import normalize_kimodo_online


class KimodoAdapter(ModelAdapter):
    id = 'kimodo'
    tasks = ('instruction',)
    implemented = True

    def blockers(self):
        if self.config.get('backend')=='official_demo':
            reasons=[]
            if not self.repo.is_dir():reasons.append('公式の骨格定義ソースが未取得。')
            if not self.config.get('online_validated'):reasons.append('公式オンラインデモの推論と取得を未検証。')
            if not all(importlib.util.find_spec(name) for name in ('websockets','msgspec')):reasons.append('オンラインクライアントの依存関係が未導入。')
            return reasons
        reasons = super().blockers()
        if not self.config.get('checkpoint_cached', False):
            reasons.append('Kimodo の公開チェックポイントが未取得。')
        if not self.config.get('text_encoder_cached', False):
            reasons.append('LLM2Vec と gated Llama テキストエンコーダーが未取得。')
        return reasons

    def generate(self, request, output_dir):
        self.preflight(request)
        original = Path(output_dir) / 'original.npz'
        if self.config.get('backend')=='official_demo':
            if request.duration>10:raise ValueError('公式オンラインデモは10秒以内にしてください。')
            self.run([sys.executable,settings.ROOT/'scripts/kimodo_online.py',request.text,'--duration',str(request.duration),
                      '--seed',str(request.seed),'--output',original],output_dir,timeout=270)
            metadata=json.loads(original.with_suffix('.metadata.json').read_text())
            normalized=normalize_kimodo_online(original,Path(output_dir)/'motion.json',self.repo,metadata)
            return {'original_motion_path':original,'normalized_motion_path':normalized,'rendered_video_path':None,
                    'inference_time':metadata['inference_time'],'checkpoint':metadata['checkpoint'],
                    'device':metadata['device'],'metadata':metadata}
        env = self.environment()
        text_device=self.config.get('text_encoder_device','cpu')
        env.update({'TEXT_ENCODER_DEVICE': text_device, 'TEXT_ENCODER_MODE': 'local', 'LOCAL_CACHE': 'true',
                    'CHECKPOINT_DIR': str(self.data/self.config.get('checkpoint_dir','checkpoints/kimodo'))})
        self.ensure_requested_cuda(output_dir,env)
        elapsed = self.run([self.python, '-m', 'kimodo.scripts.generate', request.text,
                            '--model', self.config.get('model', 'kimodo-soma-rp-v1.1'), '--duration', str(request.duration),
                            '--seed', str(request.seed), '--no-postprocess', '--output', original], output_dir, env=env)
        return {'original_motion_path': original, 'normalized_motion_path': self.export_official(original, output_dir),
                'rendered_video_path': None, 'inference_time': elapsed, 'checkpoint': self.config.get('model'),
                'device': 'cuda' if self.cuda_available() else 'cpu', 'metadata': {'postprocess': False, 'text_encoder_device': text_device}}
