import asyncio
import importlib.util
import io
import json
from pathlib import Path
import pytest


def test_paused_official_space_does_not_connect_or_wake_gpu(monkeypatch,tmp_path):
    source=Path(__file__).resolve().parents[1]/'scripts/kimodo_online.py'
    spec=importlib.util.spec_from_file_location('kimodo_online_policy_test',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(json.dumps({'runtime':{'stage':'PAUSED'}}).encode()))
    def forbidden_connection(*args,**kwargs):
        raise AssertionError('A paused Space must not receive a connection that can wake it.')
    monkeypatch.setattr(module.websockets,'connect',forbidden_connection)
    with pytest.raises(RuntimeError,match='GPU起動・再開処理は行いません'):
        asyncio.run(module.generate('wave',3,0,tmp_path/'motion.npz'))
    assert not (tmp_path/'motion.npz').exists()
