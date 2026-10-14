import io
import json
import time
import wave
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.motion import save_motion, viewer_fixture
from adapters.base import ModelAdapter, UnavailableError, redact


def wav_bytes(seconds=.2):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(b'\0\0'*int(seconds*16000))
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path/'data',output_dir=tmp_path/'outputs')) as value:yield value


def test_application_and_local_viewer_assets(client):
    assert client.get('/').status_code==200
    assert client.get('/api/health').json()['viewer_assets_present'] is True
    assert client.get('/vendor/three/build/three.module.js').status_code==200
    models=client.get('/api/models').json()
    assert len(models)==15 and {'text_to_vrma','reactmotion','maai','motionlcm','momask','mmm'} <= {model['id'] for model in models}
    assert all(m['execution_status']!='実際に推論成功' for m in models)


@pytest.mark.parametrize('payload',[
    {'task_type':'instruction','model_name':'ardy','text':''},
    {'task_type':'unknown','model_name':'ardy','text':'wave'},
    {'task_type':'audio','model_name':'streamtalk','text':'wave'},
    {'task_type':'instruction','model_name':'ardy','text':'右手を振って'},
    {'task_type':'instruction','model_name':'ardy','text':'wave','duration':-1},
    {'task_type':'instruction','model_name':'ardy','text':'wave','seed':-1},
])
def test_invalid_generation_rejected(client,payload):
    assert client.post('/api/generate',json=payload).status_code==422


def test_missing_dependencies_dont_fallback_to_fixture(client):
    response=client.post('/api/generate',json={'task_type':'instruction','model_name':'ardy','text':'wave'})
    assert response.status_code==409
    assert client.get('/api/experiments').json()==[]


def test_comparison_reports_each_unavailable_model(client):
    response=client.post('/api/compare',json={'task_type':'instruction','model_names':['ardy','kimodo'],'text':'wave'})
    assert response.status_code==202
    assert [x['status'] for x in response.json()['results']]==['rejected','rejected']


def test_wav_upload_inspection_and_invalid_inputs(client):
    response=client.post('/api/audio',files={'file':('voice.wav',wav_bytes(),'audio/wav')})
    assert response.status_code==201
    assert response.json()['duration']==.2
    assert client.get(response.json()['url']).content==wav_bytes()
    assert client.post('/api/audio',files={'file':('voice.wav',b'not audio')}).status_code==422
    assert client.post('/api/audio',files={'file':('voice.mp3',b'not audio')}).status_code==415
    assert client.post('/api/audio',files={'file':('voice.wav',wav_bytes()[:-5])}).status_code==422


def test_fixture_audio_motion_metadata_and_download(client):
    upload=client.post('/api/audio',files={'file':('voice.wav',wav_bytes())}).json()
    response=client.post('/api/viewer-fixture',params={'audio_id':upload['audio_id']})
    assert response.status_code==201
    record=response.json();prefix='/api/experiments/'+record['id']
    assert record['inference_verified'] is False
    assert client.get(prefix+'/files/input.wav').content==wav_bytes()
    motion=client.get(prefix+'/files/motion.json').json()
    assert motion['metadata']['trained_model_output'] is False
    assert client.get(prefix+'/files/experiment.json').json()['model_id']=='synthetic_viewer_fixture'
    assert client.get(prefix+'/files/../../requirements-app.lock').status_code==404
    assert client.get('/api/experiments/not-an-id').status_code==404


def test_import_preserves_original_and_is_not_inference(client):
    content=json.dumps(viewer_fixture()).encode()
    response=client.post('/api/import',files={'file':('../../test.json',content)},data={'source_up':'Y','source_unit':'m'})
    assert response.status_code==201
    record=response.json();prefix='/api/experiments/'+record['id']
    assert record['model_id']=='user_import' and record['inference_verified'] is False
    assert client.get(prefix+'/files/original.json').content==content
    assert client.post('/api/import',files={'file':('bad.npz',b'not zip')}).status_code==422
    assert client.post('/api/import',files={'file':('bad.json',b'{')}).status_code==422


class SuccessAdapter(ModelAdapter):
    id='ardy';tasks=('instruction',);implemented=True
    def blockers(self):return []
    def generate(self,request,output_dir):
        # Test double exercises the adapter contract; it is not a pretrained model.
        original=output_dir/'original.npz'
        np.savez(original,positions=viewer_fixture()['positions'])
        normalized=output_dir/'motion.json';save_motion(normalized,viewer_fixture())
        return {'original_motion_path':original,'normalized_motion_path':normalized,'inference_time':.01,
                'device':'test-double','checkpoint':'unit-test-only'}


class FailureAdapter(SuccessAdapter):
    id='kimodo'
    def generate(self,request,output_dir):raise RuntimeError('deliberate model failure')


def test_comparison_continues_after_one_model_failure_and_records_translation(tmp_path):
    success=SuccessAdapter(tmp_path);failure=FailureAdapter(tmp_path)
    app=create_app(data_dir=tmp_path/'data',output_dir=tmp_path/'outputs',model_adapters={'ardy':success,'kimodo':failure})
    with TestClient(app) as client:
        response=client.post('/api/compare',json={'task_type':'instruction','model_names':['kimodo','ardy'],
                                              'text':'右手を振って','translated_text':'Wave your right hand','seed':7})
        ids=[x['id'] for x in response.json()['results']]
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            records=[client.get('/api/experiments/'+id).json() for id in ids]
            if all(r['status'] in ('succeeded','failed') for r in records):break
            time.sleep(.01)
        assert [r['status'] for r in records]==['failed','succeeded']
        record=records[1]
        assert record['input_text']=='右手を振って' and record['model_text']=='Wave your right hand'
        assert record['seed']==7 and record['device']=='test-double'
        assert record['artifact_sha256'] and record['skeleton_type']=='synthetic-16'
        assert record['gpu_peak_memory_bytes'] is None and record['semantic_alignment'] is None


def test_credentials_and_signed_queries_redacted():
    output=redact('Authorization: Bearer SECRET hf_1234567890123456 https://host/file?Signature=SECRET')
    assert 'SECRET' not in output and 'hf_1234567890123456' not in output


def test_timing_csv_imports_have_no_invented_generation_times(client):
    import csv
    import io
    client.post('/api/viewer-fixture')
    response=client.get('/api/experiments.csv')
    assert response.status_code==200 and response.content.startswith(b'\xef\xbb\xbf')
    rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows and all(row['skeleton_seconds']=='' and row['total_seconds']=='' for row in rows)


def test_short_and_medium_utterances_are_shared_by_ui_and_batch(client):
    samples=client.get('/api/examples/ardy-utterances').json()
    assert len(samples)==10 and len({sample['id'] for sample in samples})==10
    assert sum(sample['group']=='short' for sample in samples)==5
    assert sum(sample['group']=='medium' for sample in samples)==5
    assert all(sample['duration']==(3 if sample['group']=='short' else 6) for sample in samples)
    assert samples[0]['model_text']=='Hello.'
