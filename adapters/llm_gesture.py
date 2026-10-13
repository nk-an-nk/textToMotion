from .base import ModelAdapter


class LLMGestureAdapter(ModelAdapter):
    id = 'llm_gesture'
    tasks = ('conversation_text', 'audio')
    needs_cuda = True
