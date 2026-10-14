import json
from app.settings import ROOT
from .ardy import ArdyAdapter
from .kimodo import KimodoAdapter
from .language_of_motion import LanguageOfMotionAdapter
from .streamtalk import StreamTalkAdapter
from .miburi import MiburiAdapter
from .llm_gesture import LLMGestureAdapter
from .vibes import VibesAdapter
from .freetalker import FreeTalkerAdapter
from .agenthands import AgentHandsAdapter
from .text_to_vrma import TextToVrmaAdapter
from .listener_models import ReactMotionAdapter, MaaiAdapter
from .humanml import MotionLCMAdapter, MoMaskAdapter, MMMAdapter

CLASSES = [LanguageOfMotionAdapter, ArdyAdapter, KimodoAdapter, MiburiAdapter, StreamTalkAdapter,
           LLMGestureAdapter, VibesAdapter, FreeTalkerAdapter, AgentHandsAdapter,TextToVrmaAdapter,
           ReactMotionAdapter, MaaiAdapter, MotionLCMAdapter, MoMaskAdapter, MMMAdapter]
CATALOG = json.loads((ROOT / 'configs/models.json').read_text())


def adapters(data_dir=None):
    return {cls.id: cls(data_dir) for cls in CLASSES}


def catalog(data_dir=None):
    instances = adapters(data_dir)
    results = []
    for model in CATALOG:
        adapter = instances[model['id']]
        blockers = adapter.blockers()
        state = '未実行'
        if adapter.python.exists() and adapter.implemented:
            state = '環境構築のみ完了'
        if model['id']=='text_to_vrma' and (adapter.repo/'node_modules/three/package.json').is_file():
            state='環境構築のみ完了'
        if adapter.needs_cuda and not adapter.cuda_available() or model['id'] in ('vibes', 'xrblocks'):
            state = '利用不可'
        results.append({**model, 'execution_status': state, 'can_generate': not blockers,
                        'can_diagnose': model['id']=='ardy' and not adapter.diagnostic_blockers(),
                        'backend': adapter.config.get('backend','local'),
                        'blockers': blockers, 'official_url': 'https://github.com/' + model['repo']})
    return results
