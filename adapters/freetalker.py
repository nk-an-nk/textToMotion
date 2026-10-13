from .base import ModelAdapter


class FreeTalkerAdapter(ModelAdapter):
    id = 'freetalker'
    tasks = ('instruction', 'audio')
    # Official documentation tested CUDA; CPU feasibility has not been verified.
