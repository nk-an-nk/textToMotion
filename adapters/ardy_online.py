"""Explicit optional public service; the existing local ARDY adapter stays unchanged."""
import json
import os
from pathlib import Path

from adapters.ardy import ArdyAdapter
from adapters.base import ModelAdapter
from app import settings
from scripts.ardy_online import check_service, native_duration


class ArdyOnlineAdapter(ArdyAdapter):
    def __init__(self, data_dir=None):
        super().__init__(data_dir)
        self.config={**self.config, 'backend':'community_demo', 'model':'core40'}

    def blockers(self):
        reasons=ModelAdapter.blockers(self)
        if not os.environ.get('HF_TOKEN'):
            reasons.append('公開ARDYサービスの利用にはHF_TOKENが必要です。クラウド設定で保存・Publishしてください。')
        return reasons

    def check_service(self):
        return check_service()

    def native_duration(self, seconds):
        return native_duration(seconds)

    def generate(self, request, output_dir):
        self.preflight(request)
        original=Path(output_dir)/'original.npz'
        self.run([self.python, settings.ROOT/'scripts/ardy_online.py', request.text, '--duration', str(request.duration),
                  '--seed', str(request.seed), '--output', original], output_dir, timeout=210)
        metadata=json.loads(original.with_suffix('.metadata.json').read_text(encoding='utf-8'))
        normalized=self.export_official(original, output_dir)
        motion=json.loads(normalized.read_text(encoding='utf-8')); motion['metadata'].update(metadata)
        normalized.write_text(json.dumps(motion, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        return {'original_motion_path':original, 'normalized_motion_path':normalized, 'rendered_video_path':None,
                'inference_time':metadata['inference_time'], 'checkpoint':metadata['checkpoint'],
                'device':metadata['device'], 'metadata':metadata}
