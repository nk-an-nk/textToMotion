"""Timing/export contracts use explicit doubles, not model inference evidence."""
import csv
import io
import json
from types import SimpleNamespace

import pytest

from app import jobs
from app.jobs import JobStore
from app.motion import save_motion,viewer_fixture
from app.timing import csv_bytes,summary_row
from adapters.base import MotionInput
from scripts import run_ardy_examples


class TimingDouble:
    def generate(self,request,directory):
        original=directory/'original.npz';original.write_bytes(b'test-double-only')
        motion=directory/'motion.json';save_motion(motion,viewer_fixture())
        return {'original_motion_path':original,'normalized_motion_path':motion,
                'device':'test-double','inference_time':.5,'metadata':{}}


def completed_store(tmp_path,monkeypatch,ticks):
    monkeypatch.setattr(jobs,'time',SimpleNamespace(monotonic=lambda:next(ticks)))
    store=JobStore(tmp_path,{'test-double':TimingDouble()})
    record=store.create(MotionInput('instruction','Hello.',None,3,0,'test-double','こんにちは'),{})
    store.close()
    assert store.get(record['id'])['status']=='succeeded'
    return store,record['id']


def test_mp4_total_adds_processing_stages_and_excludes_user_delay(tmp_path,monkeypatch):
    store,identifier=completed_store(tmp_path,monkeypatch,iter([100,101.25,1000,1000.75]))
    def fake_renderer(motion,path,audio):path.write_bytes(b'test-video-double');return path
    monkeypatch.setattr(jobs,'render_video',fake_renderer)
    store.render(identifier)
    record=store.get(identifier)
    assert record['timings']=={'skeleton_seconds':1.25,'mp4_render_seconds':.75,'total_seconds':2.0}
    assert record['render_status']=='succeeded'
    assert record['artifact_sha256']['rendered_video_path']


def test_render_failure_preserves_skeleton_and_does_not_invent_total(tmp_path,monkeypatch):
    store,identifier=completed_store(tmp_path,monkeypatch,iter([100,101.25,1000]))
    def broken_renderer(*args):raise RuntimeError('encoder failed')
    monkeypatch.setattr(jobs,'render_video',broken_renderer)
    with pytest.raises(RuntimeError,match='encoder failed'):store.render(identifier)
    record=store.get(identifier)
    assert record['status']=='succeeded' and record['render_status']=='failed'
    assert record['timings']['skeleton_seconds']==1.25 and record['timings']['total_seconds'] is None
    assert summary_row(record)['error']=='encoder failed'


def test_csv_preserves_numeric_timings_and_escapes_excel_formulas():
    row=summary_row({'model_id':'test-double','input_text':'=1+1','model_text':'Hello.',
                     'status':'succeeded','timings':{'skeleton_seconds':1.25,'mp4_render_seconds':.75,'total_seconds':2.0}})
    data=csv_bytes([row])
    assert data.startswith(b'\xef\xbb\xbf')
    parsed=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))[0]
    assert parsed['input_text']=="'=1+1" and parsed['skeleton_seconds']=='1.25' and parsed['total_seconds']=='2.0'
    assert row['input_text']=='=1+1'


def test_utterance_batch_keeps_failed_case_and_continues_with_real_api_contract(tmp_path,monkeypatch,capsys):
    examples=[{'group':'short','input_text':'こんにちは','model_text':'Hello.','duration':3,'seed':0},
              {'group':'medium','input_text':'説明します','model_text':'Let me explain this again.','duration':6,'seed':0}]
    generated=[]
    record={'id':'0'*32,'model_id':'ardy','input_text':'説明します','model_text':'Let me explain this again.',
            'status':'succeeded','device':'cuda','timings':{'skeleton_seconds':4.,'mp4_render_seconds':2.,'total_seconds':6.},
            'artifacts':{'rendered_video_path':'video.mp4'}}
    def api_double(base,path,data=None):
        if path=='/api/health':return {'status':'ok'}
        if path=='/api/models':return [{'id':'ardy','can_generate':True,'backend':'local'}]
        if path=='/api/generate':
            generated.append(data)
            if len(generated)==1:raise RuntimeError('test-only CUDA failure')
            return record
        if path.endswith('/render'):return {'url':'test-only'}
        return record
    monkeypatch.setattr(run_ardy_examples,'request',api_double)
    rows=run_ardy_examples.run_batch('http://127.0.0.1:8765',examples,tmp_path/'batch')
    assert [row['status'] for row in rows]==['failed','succeeded']
    assert [item['translated_text'] for item in generated]==['Hello.','Let me explain this again.']
    assert rows[1]['example_group']=='medium'
    assert rows[0]['total_seconds'] is None and rows[1]['total_seconds']==6.
    assert '骨格まで: 4.00秒 / MP4まで: 6.00秒' in capsys.readouterr().out
    assert (tmp_path/'batch/summary.csv').is_file() and (tmp_path/'batch/records.json').is_file()
