import json
from pathlib import Path
from .base import ModelAdapter
from .base import UnavailableError
from app import settings


class ArdyAdapter(ModelAdapter):
    id = 'ardy'
    tasks = ('instruction',)
    implemented = True

    def diagnostic_blockers(self):
        reasons = super().blockers()
        folder = self.data / self.config.get('checkpoint_dir', 'checkpoints/ardy') / 'ARDY-Core-RP-20FPS-Horizon8'
        for filename in ('config.yaml','denoiser.safetensors','tokenizer.safetensors','motion-lab-download.json'):
            if not (folder/filename).is_file():
                reasons.append('検証済み ARDY-Core-RP-20FPS-Horizon8 重みが未取得。')
                break
        return reasons

    def diagnose(self,request,output_dir):
        reasons=self.diagnostic_blockers()
        if reasons:raise UnavailableError(' / '.join(reasons))
        original=Path(output_dir)/'original.npz'
        self.run([self.python,settings.ROOT/'scripts/diagnose_ardy.py','--checkpoints-dir',
                  self.data/self.config.get('checkpoint_dir','checkpoints/ardy'),'--duration',str(request.duration),
                  '--seed',str(request.seed),'--output',original],output_dir)
        metadata=json.loads(original.with_suffix('.metadata.json').read_text())
        normalized=self.export_official(original,output_dir)
        motion=json.loads(normalized.read_text());motion['metadata'].update(metadata)
        normalized.write_text(json.dumps(motion,ensure_ascii=False,allow_nan=False))
        return {'original_motion_path':original,'normalized_motion_path':normalized,'rendered_video_path':None,
                'inference_time':metadata['inference_time'],'checkpoint':metadata['checkpoint'],
                'device':'cpu','metadata':metadata}

    def blockers(self):
        reasons = super().blockers()
        folder = self.data / self.config.get('checkpoint_dir', 'checkpoints/ardy')
        if not list(folder.glob('*/config.yaml')):
            reasons.append('ARDY の公開チェックポイントが未取得。')
        if not self.config.get('text_encoder_cached', False):
            reasons.append('LLM2Vec と gated Meta-Llama-3-8B-Instruct の利用権・取得が未確認。')
        return reasons

    def generate(self, request, output_dir):
        if request.task_type=='unconditional_diagnostic':
            return self.diagnose(request,output_dir)
        self.preflight(request)
        output_dir = Path(output_dir)
        env = self.environment()
        env.update({'TEXT_ENCODER_MODE': 'local', 'TEXT_ENCODER_DEVICE': 'cpu' if not self.cuda_available() else 'cuda'})
        original = output_dir / 'original.npz'
        elapsed = self.run([self.python, 'scripts/generate.py', request.text, '--model', self.config.get('model', 'core8'),
                            '--duration', str(request.duration), '--seed', str(request.seed), '--no-postprocess',
                            '--checkpoints_dir', self.data / self.config.get('checkpoint_dir', 'checkpoints/ardy'),
                            '--output', original], output_dir, env=env)
        return {'original_motion_path': original, 'normalized_motion_path': self.export_official(original, output_dir),
                'rendered_video_path': None, 'inference_time': elapsed, 'checkpoint': self.config.get('model', 'core8'),
                'device': 'cuda' if self.cuda_available() else 'cpu', 'metadata': {'postprocess': False}}
