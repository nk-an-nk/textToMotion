from .base import ModelAdapter


class VibesAdapter(ModelAdapter):
    id = 'vibes'
    tasks = ('conversation_text', 'instruction')
    needs_cuda = True

    def blockers(self):
        return super().blockers() + ['公開 body checkpoint の公式リンク・取得を未確認。face checkpoint を身体モデルとして代用しません。']
