"""Lifecycle behavior for paid experiment Pods; all provider calls are mocked."""
import json
from unittest.mock import patch

import pytest

from scripts import runpod_retained_experiment as retained
from scripts.benchmark_masked_models import frames_for


def state(tmp_path,**extra):
    folder=tmp_path/'lab_proxy';folder.mkdir()
    p=folder/'state.json'
    p.write_text(json.dumps(dict(pod_id='owned',pod_name='experiment-owned',retention_hours=24,
                                deadline_epoch=2000,stop_confirmed=False,**extra)))
    (tmp_path/'credit-budget-private.json').write_text(json.dumps({'retained_storage_reserve_usd':1.0}))
    return p


def test_completion_stops_and_preserves_volume_for_24h(tmp_path):
    p=state(tmp_path)
    with patch.object(retained,'owned_pod',side_effect=[{'desiredStatus':'RUNNING'},{'desiredStatus':'EXITED'}]),patch.object(retained,'api') as api,patch.object(retained.time,'time',return_value=1000):
        result=retained.stop(p,'completed')
    api.assert_called_once_with('POST','/pods/owned/stop')
    assert result['stop_confirmed'] and result['retention_until_epoch']==1000+24*3600
    assert not result.get('deletion_confirmed')


def test_stopped_pod_is_not_deleted_during_retention(tmp_path):
    p=state(tmp_path,retention_until_epoch=100000)
    d=json.loads(p.read_text());d['stop_confirmed']=True;p.write_text(json.dumps(d))
    with patch.object(retained.time,'time',return_value=2000),patch.object(retained,'api') as api:
        retained.tick(tmp_path)
    api.assert_not_called()


def test_retention_cleanup_is_scoped_to_the_owned_pod(tmp_path):
    p=state(tmp_path,retention_until_epoch=1500)
    d=json.loads(p.read_text());d['stop_confirmed']=True;p.write_text(json.dumps(d))
    with patch.object(retained.time,'time',return_value=2000),patch.object(retained,'owned_pod',side_effect=[{'id':'owned'},None]),patch.object(retained,'api') as api:
        retained.tick(tmp_path)
    api.assert_called_once_with('DELETE','/pods/owned')
    assert json.loads(p.read_text())['deletion_confirmed']


def test_low_remaining_credit_stops_without_deleting(tmp_path):
    p=state(tmp_path)
    with patch.object(retained.time,'time',return_value=1500),patch.object(retained,'account',return_value={'clientBalance':1.1}),patch.object(retained,'stop') as stop:
        retained.tick(tmp_path)
    stop.assert_called_once()
    assert stop.call_args.args[0]==p


def test_new_rental_is_refused_when_it_would_consume_retention_credit(tmp_path):
    (tmp_path/'credit-budget-private.json').write_text(json.dumps({'retained_storage_reserve_usd':1.0}))
    with patch.object(retained,'account',return_value={'clientBalance':1.5}),patch.object(retained,'api') as api:
        with pytest.raises(RuntimeError,match='remaining credit'):retained.create(tmp_path,'b300',10)
    api.assert_not_called()


@pytest.mark.parametrize('minutes',[0,-1,float('nan'),float('inf')])
def test_invalid_runtime_cannot_create_a_billable_resource(tmp_path,minutes):
    with patch.object(retained,'api') as api:
        with pytest.raises(ValueError):retained.create(tmp_path,'b300',minutes)
    api.assert_not_called()


def test_common_motion_lengths_cover_speech_and_keep_official_limits():
    assert [frames_for(s) for s in [.95,3.6,2.6,2.4,3.6]]==[40,72,52,48,72]
    assert frames_for(20)==196
    with pytest.raises(ValueError):frames_for(float('nan'))
