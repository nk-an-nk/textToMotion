from pathlib import Path
from .base import ModelAdapter


class LanguageOfMotionAdapter(ModelAdapter):
    id = 'language_of_motion'
    tasks = ('instruction', 'audio')
    implemented = True
    needs_cuda = True

    def blockers(self):
        reasons = super().blockers()
        if not self.config.get('assets_confirmed'):
            reasons.append('v1 LM/VQ/T5/HuBERT および許諾済み SMPL-X/FLAME 資産が未確認。')
        if not Path(self.config.get('smplx_model', '/nonexistent')).is_file():
            reasons.append('runtime.json に許諾済み SMPL-X body model のパスが必要。')
        return reasons

    def generate(self, request, output_dir):
        self.preflight(request)
        output_dir = Path(output_dir)
        prompt = output_dir / 'prompt.txt'
        prompt.write_text(request.text + '\n')
        elapsed = self.run([self.python, Path(__file__).resolve().parents[1] / 'scripts/run_lom.py',
                            '--repo', self.repo, '--runtime', self.data / 'runtime.json', '--output', output_dir,
                            '--text', prompt, '--task', 'cospeech' if request.task_type == 'audio' else 'text2motion',
                            '--seed', request.seed, '--duration', request.duration,
                            *(['--audio', request.audio_path] if request.audio_path else [])], output_dir)
        candidates = list(output_dir.rglob('*.npz'))
        if len(candidates) != 1:
            raise RuntimeError('LoM の出力 NPZ を一意に特定できません。公式ログを確認してください。')
        original = candidates[0]
        return {'original_motion_path': original, 'normalized_motion_path': self.export_smplx(original, output_dir, self.config['smplx_model'], flat_hand_mean=False),
                'rendered_video_path': None, 'inference_time': elapsed, 'checkpoint': 'LoM v1', 'device': 'cuda',
                'metadata': {'variant': 'v1', 'v2_checkpoint_compatible': False}}
