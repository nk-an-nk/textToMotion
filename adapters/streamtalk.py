import os
from pathlib import Path
from .base import ModelAdapter


class StreamTalkAdapter(ModelAdapter):
    id = 'streamtalk'
    tasks = ('audio',)
    implemented = True
    needs_cuda = True

    def blockers(self):
        reasons = super().blockers()
        for key in ('checkpoint', 'example_motion_npz', 'smplx_model', 'retrieval_data_folder', 'retrieval_csv_file'):
            if not self.config.get(key) or not Path(self.config[key]).exists():
                reasons.append(f'StreamTalk 資産 {key} が未設定または存在しません。')
        return reasons

    def generate(self, request, output_dir):
        self.preflight(request)
        original = Path(output_dir) / 'original.npz'
        command = [self.python, 'TestFixedExpressions_keyposes.py', request.audio_path, self.config['checkpoint'],
                   '--pid', self.config.get('pid', '2_scott_0'), '--output_file', original,
                   '--wavlm_model', self.config.get('wavlm_model', 'patrickvonplaten/wavlm-libri-clean-100h-large'),
                   '--cfg_scale', '3', '--seed', str(request.seed)]
        for name in ('example_motion_npz', 'smplx_model', 'retrieval_data_folder', 'retrieval_csv_file'):
            command += ['--' + name, self.config[name]]
        env = self.environment()
        env['PYTHONPATH'] = str(self.repo / 'Scripts') + os.pathsep + env.get('PYTHONPATH', '')
        elapsed = self.run(command, output_dir, cwd=self.repo / 'Scripts/FM', env=env)
        return {'original_motion_path': original, 'normalized_motion_path': self.export_smplx(original, output_dir, self.config['smplx_model'], flat_hand_mean=True),
                'rendered_video_path': None, 'inference_time': elapsed, 'checkpoint': self.config['checkpoint'],
                'device': 'cuda', 'metadata': {'cfg_scale': 3, 'audio_conditioned': True}}
