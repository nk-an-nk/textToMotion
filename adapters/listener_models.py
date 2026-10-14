"""Listener comparison entries. Preparation never counts as pretrained inference."""
from .base import ModelAdapter
from .humanml import HumanMLAdapter


class ReactMotionAdapter(HumanMLAdapter):
    id = 'reactmotion'
    tasks = ('instruction', 'conversation_text')


class MaaiAdapter(ModelAdapter):
    id = 'maai'
    tasks = ('audio',)
    implemented = False

    def blockers(self):
        return super().blockers() + [
            'MaAI nod_para / normal-ver2 のCUDA推論は専用比較CLIで検証済み。全身骨格APIへの変換は未実装。',
            'scripts/generate_listener_comparison.py --model maai で実音声から頭部の予測を保存できます。',
        ]
