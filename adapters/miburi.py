from .base import ModelAdapter


class MiburiAdapter(ModelAdapter):
    id = 'miburi'
    tasks = ('audio',)
    needs_cuda = True
    # The official offline CLI exists, but integration is not validated or advertised as implemented.
