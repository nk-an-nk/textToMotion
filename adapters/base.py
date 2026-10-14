import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app import settings


class UnavailableError(RuntimeError):
    pass


def redact(text):
    text = re.sub(r'hf_[A-Za-z0-9]{10,}', '[REDACTED_TOKEN]', text)
    text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,]+', r'\1[REDACTED]', text)
    return re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[REDACTED_QUERY]', text)


@dataclass
class MotionInput:
    task_type: str
    text: str
    audio_path: Path | None
    duration: float
    seed: int
    model_name: str
    original_text: str = ''


class ModelAdapter:
    id = ''
    tasks = ()
    implemented = False
    needs_cuda = False

    def __init__(self, data_dir=None):
        self.data = Path(data_dir or settings.DATA)
        self.repo = self.data / 'upstreams' / self.id
        self.python = self.data / 'envs' / self.id / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        config_file = self.data / 'runtime.json'
        self.config = json.loads(config_file.read_text()).get(self.id, {}) if config_file.exists() else {}

    def cuda_available(self):
        executable = shutil.which('nvidia-smi')
        if not executable:
            return False
        probe = subprocess.run([executable, '-L'], capture_output=True, text=True, timeout=10)
        return probe.returncode == 0 and 'GPU' in probe.stdout

    def blockers(self):
        reasons = []
        if not self.implemented:
            reasons.append('実行アダプター未実装。公式ソースの調査のみ完了。')
        if not self.repo.is_dir():
            reasons.append('公式ソースが未取得。scripts/setup_models.py --clone を実行してください。')
        if not self.python.is_file():
            reasons.append('モデル専用仮想環境が未構築。')
        if self.needs_cuda and not self.cuda_available():
            reasons.append('この公式推論経路には NVIDIA CUDA GPU が必要です。')
        return reasons

    def preflight(self, request):
        if request.task_type not in self.tasks:
            raise UnavailableError(f'{self.id} は {request.task_type} 入力に対応していません。')
        reasons = self.blockers()
        if reasons:
            raise UnavailableError(' / '.join(reasons))

    def environment(self):
        env = os.environ.copy()
        env.update({'HF_HOME': str(self.data / 'hf-cache'), 'OMP_NUM_THREADS': '4',
                    'MKL_NUM_THREADS': '4', 'PYTHONUNBUFFERED': '1', 'HF_HUB_DISABLE_XET': '1',
                    'PATH': str(self.python.parent) + os.pathsep + env.get('PATH', '')})
        return env

    def run(self, argv, output_dir, *, cwd=None, env=None, timeout=900):
        started = time.monotonic()
        log = Path(output_dir) / 'inference.log'
        # Pipe through a temporary private capture; only a redacted log is retained.
        capture = Path(output_dir) / '.process-capture'
        try:
            with capture.open('w') as handle:
                result = subprocess.run([str(x) for x in argv], cwd=cwd or self.repo,
                                        env=env or self.environment(), stdout=handle,
                                        stderr=subprocess.STDOUT, timeout=timeout)
            content = redact(capture.read_text(errors='replace'))
            with log.open('a') as handle:
                handle.write(content)
            if result.returncode:
                raise RuntimeError(f'公式コマンドが exit {result.returncode} で失敗しました。\n' + content[-2500:])
        except subprocess.TimeoutExpired as error:
            if capture.exists():
                log.write_text(redact(capture.read_text(errors='replace')))
            raise RuntimeError(f'公式推論が {timeout} 秒の上限を超えました。ログを確認してください。') from error
        finally:
            capture.unlink(missing_ok=True)
        return time.monotonic() - started

    def generate(self, request, output_dir):
        self.preflight(request)
        raise UnavailableError('実行アダプター未実装。')

    def ensure_requested_cuda(self, output_dir, env):
        if self.config.get('require_cuda',False):
            self.run([self.python,'-c',
                      'import torch; assert torch.cuda.is_available(), "CUDA is unavailable; no CPU fallback"; '
                      'x=torch.ones((32,32),device="cuda"); y=x@x; torch.cuda.synchronize(); '
                      'assert torch.isfinite(y).all()'],output_dir,env=env)

    def export_official(self, original, output_dir):
        normalized = Path(output_dir) / 'motion.json'
        self.run([self.python, settings.ROOT / 'scripts/export_official.py', '--family', self.id,
                  '--input', original, '--output', normalized], output_dir)
        return normalized

    def export_smplx(self, original, output_dir, body_model, *, flat_hand_mean):
        normalized = Path(output_dir) / 'motion.json'
        self.run([self.python, settings.ROOT / 'scripts/export_smplx.py', '--input', original,
                  '--output', normalized, '--body-model', body_model,
                  '--flat-hand-mean', 'true' if flat_hand_mean else 'false'], output_dir)
        return normalized
