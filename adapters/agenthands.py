from .base import ModelAdapter


class AgentHandsAdapter(ModelAdapter):
    id = 'xrblocks'
    tasks = ('conversation_text',)

    def blockers(self):
        return ['AgentHands は既存の手動作の選択・制御 addon です。学習済み full-body motion generator として登録していません。']
