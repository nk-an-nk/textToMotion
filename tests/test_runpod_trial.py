"""A trial must preserve other Pods and reject a rental without sufficient funds."""
import json
from pathlib import Path
import pytest
from scripts import runpod_trial


def test_foreign_pod_cannot_be_terminated(tmp_path, monkeypatch):
    state = tmp_path / 'trial.json'
    state.write_text(json.dumps({'pod_id': 'ours', 'pod_name': 'motion-lab-trial-ours'}))
    calls = []
    def api(method, path, body=None):
        calls.append((method, path))
        return {'id': 'ours', 'name': 'another-users-pod'}
    monkeypatch.setattr(runpod_trial, 'api', api)
    with pytest.raises(RuntimeError, match='ownership'):
        runpod_trial.terminate(state, 'finished')
    assert calls == [('GET', '/pods/ours')]


def test_cleanup_deletes_only_owned_trial_and_verifies_removal(tmp_path, monkeypatch):
    state = tmp_path / 'trial.json'
    state.write_text(json.dumps({'pod_id': 'ours', 'pod_name': 'motion-lab-trial-ours'}))
    calls = []
    def api(method, path, body=None):
        calls.append((method, path))
        if path == '/pods': return [{'id': 'existing-user-pod'}]
        if method == 'GET': return {'id': 'ours', 'name': 'motion-lab-trial-ours'}
    monkeypatch.setattr(runpod_trial, 'api', api)
    result = runpod_trial.terminate(state, 'finished')
    assert result['deletion_confirmed']
    assert calls == [('GET', '/pods/ours'), ('DELETE', '/pods/ours'), ('GET', '/pods')]


def test_insufficient_balance_performs_no_mutations(tmp_path, monkeypatch):
    plan = json.loads((Path(__file__).parents[1] / 'configs/runpod_trial.json').read_text())
    monkeypatch.setattr(runpod_trial, 'inspect', lambda *a, **kw: {
        'gpu_candidates': [{'id': plan['gpu_type_ids'][0], 'usd_with_reserve': 2.3}],
        'balance_usd': 0})
    monkeypatch.setattr(runpod_trial, 'api', lambda *a, **kw: pytest.fail('No mutation is permitted'))
    with pytest.raises(RuntimeError, match='balance'):
        runpod_trial.create(tmp_path / 'trial.json', plan, tmp_path / 'absent-key.pub', 45)
    assert not (tmp_path / 'trial.json').exists()
