"""Protocol guards only; synthetic NPZ fixtures are never model-inference evidence."""
import io
import json

import numpy as np
import pytest

from scripts import ardy_online


def test_client_auth_uses_the_installed_versions_parameter_without_logging_token():
    class Modern:
        def __init__(self, src, token=None): pass
    class Legacy:
        def __init__(self, src, hf_token=None): pass
    assert ardy_online.client_auth_kwargs(Modern, 'test-only') == {'token':'test-only'}
    assert ardy_online.client_auth_kwargs(Legacy, 'test-only') == {'hf_token':'test-only'}


def test_native_ardy_frames_cover_utterance_and_obey_service_minimum():
    assert ardy_online.native_duration(.9666666667) == 1
    assert ardy_online.native_duration(3.6666666667) == 3.7
    assert ardy_online.native_duration(3.7000001) == 3.7
    assert ardy_online.native_duration(10) == 10


def test_paused_service_does_not_receive_a_request(monkeypatch):
    requests=[]
    def response(url, **kwargs):
        requests.append(url)
        return io.BytesIO(json.dumps({'runtime':{'stage':'PAUSED'}}).encode())
    monkeypatch.setattr(ardy_online.urllib.request, 'urlopen', response)
    with pytest.raises(RuntimeError, match='no GPU start/resume'):
        ardy_online.check_service()
    assert requests == ['https://huggingface.co/api/spaces/'+ardy_online.SPACE]


def test_changed_service_source_requires_new_review(monkeypatch):
    monkeypatch.setattr(ardy_online.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(json.dumps({'runtime':{'stage':'RUNNING'},'sha':'unreviewed'}).encode()))
    with pytest.raises(RuntimeError, match='source changed'):
        ardy_online.check_service()


def test_protocol_rejects_a_sample_from_another_prompt_or_malformed_joints(tmp_path):
    original=tmp_path/'fixture.npz'
    np.savez(original, posed_joints=np.zeros((20,27,3), dtype=np.float32), text='fixture request', fps=20)
    payload={'prompt':'fixture request','seed':0,'fps':20,'num_frames':20,'num_joints':27,'root':np.zeros((20,3)).tolist()}
    ardy_online.validate_result(payload, original, prompt='fixture request', seed=0, frames=20)
    with pytest.raises(ValueError, match='requested prompt'):
        ardy_online.validate_result(payload, original, prompt='different real request', seed=0, frames=20)
    np.savez(original, posed_joints=np.zeros((19,27,3), dtype=np.float32), text='fixture request', fps=20)
    with pytest.raises(ValueError, match='joint positions'):
        ardy_online.validate_result(payload, original, prompt='fixture request', seed=0, frames=20)
