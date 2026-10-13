# 実行環境調査

調査時刻（日本時間）: 2026-10-13T21:44:20.547512+09:00

- OS: Linux-6.18.44-x86_64-with-glibc2.41
- アーキテクチャ: x86_64
- CPU: 5 論理コア
- RAM: 33.29 GiB
- 空きディスク: 26.16 GiB

## GPU の実測

```json
{
  "installed": true,
  "version": "2.9.0+cpu",
  "compiled_cuda": null,
  "cuda_available": false,
  "mps_available": false,
  "cpu_operation": false
}
```

nvidia-smi: {'exit_code': None, 'output': "[Errno 2] No such file or directory: 'nvidia-smi'"}

## ツール

| ツール | 検査結果 |
|---|---|
| python | Python 3.12.14 (exit=0) |
| node | v24.19.0 (exit=0) |
| npm | 11.9.0 (exit=0) |
| git | git version 2.52.0 (exit=0) |
| gh | gh version 2.46.0 (2025-01-13 Debian 2.46.0-3) (exit=0) |
| blender | Blender 4.3.2 (exit=0) |
| ffmpeg | ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers (exit=8) |
| docker | Docker version 28.4.0, build d8eb465 (exit=0) |

Docker daemon: {'exit_code': 0, 'output': '"28.4.0"'}

## 仮想環境

- /workspace/textToMotion/.venv
- /workspace/shared/motion-lab/envs/ardy

## 制約

- このインスタンスは Linux x86_64。Apple Silicon / MPS の実行検証はしていません。
- NVIDIA GPU のデバイス・VRAM はありません。CUDA 専用の公式デモはこの環境では実行できません。
- 当初の .venv に PyTorch は未導入。別途導入した CPU 版は、追加調査の interpreter として明記します。
- 資格情報は変数名と存在だけを調査。値は保存していません。
- 有料 GPU の起動・課金処理は行っていません。GPU 再現手順は docs/gpu_setup.md を参照。
