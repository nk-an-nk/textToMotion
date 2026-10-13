#!/usr/bin/env python3
"""Read-only machine inspection. Does not disclose environment or credential values."""
import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def command(argv, timeout=15):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": result.returncode, "output": (result.stdout + result.stderr).strip()[:2500]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"exit_code": None, "output": str(error)}


def inspect(torch_python=None):
    disk = shutil.disk_usage(Path(__file__).resolve().parents[1])
    memory = {}
    if Path('/proc/meminfo').exists():
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            if key in ('MemTotal', 'MemAvailable'):
                memory[key] = int(value.strip().split()[0]) * 1024
    torch_code = """
import importlib.util, json
if importlib.util.find_spec('torch') is None:
    print(json.dumps({'installed': False}))
else:
    import torch
    result = {'installed': True, 'version': torch.__version__, 'compiled_cuda': torch.version.cuda,
              'cuda_available': torch.cuda.is_available(), 'mps_available': torch.backends.mps.is_available()}
    result['cpu_operation'] = float((torch.ones(2,2) @ torch.ones(2,2)).sum()) == 16
    if torch.cuda.is_available():
        try:
            tensor = torch.ones(2,2,device='cuda') @ torch.ones(2,2,device='cuda')
            torch.cuda.synchronize()
            result['cuda_operation'] = float(tensor.sum()) == 16
            result['gpu'] = torch.cuda.get_device_name(0)
            result['vram_bytes'] = torch.cuda.get_device_properties(0).total_memory
        except Exception as error:
            result['cuda_operation_error'] = str(error)
    print(json.dumps(result))
"""
    probe = command([torch_python or sys.executable, '-c', torch_code], 30)
    try:
        torch_info = json.loads(probe['output'])
    except (ValueError, TypeError):
        torch_info = probe
    versions = {name: command([name, '--version']) for name in ('python', 'node', 'npm', 'git', 'gh', 'blender', 'ffmpeg', 'docker')}
    return {
        'inspected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'os': platform.platform(), 'architecture': platform.machine(), 'cpu_count': os.cpu_count(),
        'cpu': command(['lscpu']), 'memory': memory,
        'disk': {'total_bytes': disk.total, 'free_bytes': disk.free},
        'python_executable': sys.executable, 'torch_probe_interpreter': torch_python or sys.executable,
        'torch': torch_info, 'nvidia_smi': command(['nvidia-smi']), 'versions': versions,
        'docker_daemon': command(['docker', 'info', '--format', '{{json .ServerVersion}}']),
        'existing_virtualenvs': [str(p) for p in (Path('/workspace/textToMotion/.venv'), Path('/workspace/shared/motion-lab/envs/ardy')) if (p/'pyvenv.cfg').exists()],
        'bindings_presence': {name: bool(os.environ.get(name)) for name in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'SMPLX_MODEL_PATH')},
    }


def markdown(info):
    inspected = datetime.datetime.fromisoformat(info['inspected_at']).astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    lines = ['# 実行環境調査', '', f"調査時刻（日本時間）: {inspected.isoformat()}", '',
             f"- OS: {info['os']}", f"- アーキテクチャ: {info['architecture']}",
             f"- CPU: {info['cpu_count']} 論理コア", f"- RAM: {info['memory'].get('MemTotal',0)/2**30:.2f} GiB",
             f"- 空きディスク: {info['disk']['free_bytes']/2**30:.2f} GiB", '',
             '## GPU の実測', '', '```json', json.dumps(info['torch'], ensure_ascii=False, indent=2), '```', '',
             'nvidia-smi: ' + str(info['nvidia_smi']), '',
             '## ツール', '', '| ツール | 検査結果 |', '|---|---|']
    for name, status in info['versions'].items():
        lines.append(f"| {name} | {status['output'].splitlines()[0] if status['output'] else '出力なし'} (exit={status['exit_code']}) |")
    lines += ['', f"Docker daemon: {info['docker_daemon']}", '', '## 仮想環境', '']
    lines += ['- ' + path for path in info['existing_virtualenvs']]
    lines += ['', '## 制約', '',
              '- このインスタンスは Linux x86_64。Apple Silicon / MPS の実行検証はしていません。',
              '- NVIDIA GPU のデバイス・VRAM はありません。CUDA 専用の公式デモはこの環境では実行できません。',
              '- 当初の .venv に PyTorch は未導入。別途導入した CPU 版は、追加調査の interpreter として明記します。',
              '- 資格情報は変数名と存在だけを調査。値は保存していません。',
              '- 有料 GPU の起動・課金処理は行っていません。GPU 再現手順は docs/gpu_setup.md を参照。', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--torch-python')
    parser.add_argument('--output', default='docs/environment.md')
    parser.add_argument('--json', default='reports/environment.json')
    args = parser.parse_args()
    info = inspect(args.torch_python)
    for path, content in ((args.output, markdown(info)), (args.json, json.dumps(info, ensure_ascii=False, indent=2))):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + '\n')
    print(json.dumps({'report': args.output, 'torch': info['torch']}, ensure_ascii=False))
