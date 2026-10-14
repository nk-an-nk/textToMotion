import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from adapters.base import ModelAdapter, redact
from app.gesture import PlanInput, plan_gesture
from app.main import create_app
from app.motion import viewer_fixture, save_motion
from app.realtime import RealtimeConfig, RealtimeService


@pytest.mark.parametrize('text,side', [('右手を挙げて、手を振ってください','right'),('左手を上げて手を振ってください','left'),('右手を振って5秒','right')])
def test_planner_preserves_explicit_sides_and_duration(text,side):
    plan=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text=text,response_text='はい。'))
    assert plan.gesture_type=='explicit_action' and f'your {side} hand' in plan.motion_prompt
    assert plan.expected_duration_ms==(5000 if '5' in text else 3000)
    assert plan.original_text==text and plan.synchronization=='phrase_estimate'


def test_planner_keeps_order_and_does_not_invent_unknown_translation():
    plan=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text='自己紹介して、最後にお辞儀してください',response_text='よろしくお願いします。'))
    assert 'then bow at the end' in plan.motion_prompt and plan.anchor_text=='よろしく'
    for text in ['こんにちは','左へ3歩進んで右を向きながらジャンプして']:
        result=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text=text))
        assert result.gesture_type=='none' and result.motion_prompt==''
    joy=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text='今日は嬉しいことがありました'))
    assert joy.gesture_type=='semantic' and joy.priority<plan.priority
    timed=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text='右手',motion_prompt_override='Wave your right hand for 3 seconds.'))
    assert timed.expected_duration_ms==3000
    spelled=plan_gesture(PlanInput(turn_id='t',response_id='r',user_text='右手',motion_prompt_override='Raise your right hand and wave for three seconds.'))
    assert spelled.expected_duration_ms==3000
    assert plan_gesture(PlanInput(turn_id='t',response_id='r',user_text='右手を振って30秒')).motion_prompt==''


def test_unconfigured_realtime_offers_offline_and_performs_no_network(tmp_path):
    def forbidden(request):raise AssertionError('no API call authorized')
    service=RealtimeService(RealtimeConfig(),httpx.MockTransport(forbidden))
    with TestClient(create_app(data_dir=tmp_path/'data',output_dir=tmp_path/'out',realtime_service=service)) as client:
        cfg=client.get('/api/realtime/config').json()
        assert cfg['enabled'] is False and cfg['offline_available'] is True
        assert client.get('/conversation').status_code==200
        assert client.get('/vendor/three-vrm/three-vrm.module.js').status_code==200
        assert client.post('/api/realtime/calls',content='v=0\r\n').status_code==503
        assert client.post('/api/conversation/prepare',json={'text':'こんにちは'}).status_code==409


def test_cloud_realtime_secret_alias_enables_backend_without_exposing_it(monkeypatch):
    for name in ('OPENAI_API_KEY', 'MOTION_LAB_OPENAI_API_KEY', 'realtime'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('realtime', 'private-cloud-test-credential')
    monkeypatch.setenv('OPENAI_REALTIME_ENABLED', '1')
    monkeypatch.setenv('OPENAI_API_BUDGET_USD', '1')
    service = RealtimeService()
    assert service.config.api_key == 'private-cloud-test-credential'
    assert service.public_config()['enabled'] is True
    assert 'private-cloud-test-credential' not in json.dumps(service.public_config())
    monkeypatch.setenv('OPENAI_API_KEY', 'private-local-test-credential')
    assert RealtimeConfig.environment().api_key == 'private-local-test-credential'


def configured_service(handler,budget=2,max_calls=2,text_first=False):
    return RealtimeService(RealtimeConfig(api_key='sk-private-test-only-secret',enabled=True,
        budget_usd=budget,session_allowance_usd=1,max_calls=max_calls,text_first=text_first),httpx.MockTransport(handler))


def test_ga_sdp_bridge_schema_and_no_standard_key_in_browser(tmp_path):
    captured=[]
    def upstream(request):
        captured.append(request)
        assert request.url.path=='/v1/realtime/calls'
        assert request.headers['Authorization']=='Bearer sk-private-test-only-secret'
        body=request.read().decode()
        assert 'gpt-realtime-2.1' in body and '"type": "realtime"' in body
        assert '"output_modalities": ["audio"]' in body and '"create_response": false' in body
        assert 'OpenAI-Beta' not in request.headers
        return httpx.Response(201,text='v=0\r\ns=mock-answer\r\n',headers={'Location':'https://api.openai.com/v1/realtime/calls/rtc_test'})
    app=create_app(data_dir=tmp_path/'data',output_dir=tmp_path/'out',realtime_service=configured_service(upstream))
    with TestClient(app) as client:
        response=client.post('/api/realtime/calls',content='v=0\r\ns=offer\r\n',headers={'Origin':'http://testserver'})
        assert response.status_code==200 and response.text.startswith('v=0')
        assert 'sk-private' not in response.text and 'sk-private' not in json.dumps(client.get('/api/realtime/config').json())
        assert client.post('/api/realtime/calls',content='v=0',headers={'Origin':'https://foreign.invalid'}).status_code==403
        assert client.post('/api/realtime/calls',content='not-sdp').status_code==422
        assert len(captured)==1


@pytest.mark.parametrize('failure', ['network','permission'])
def test_realtime_failure_preserves_error_and_budget_reservation(failure,tmp_path):
    def upstream(request):
        if failure=='network':raise httpx.ConnectError('private error must not leak',request=request)
        return httpx.Response(403,text='private upstream body')
    service=configured_service(upstream,budget=1)
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o',realtime_service=service)) as client:
        response=client.post('/api/realtime/calls',content='v=0')
        assert response.status_code==502 and 'private' not in response.text
        assert client.post('/api/realtime/calls',content='v=0').status_code==429


def test_text_first_structured_api_and_mismatch_side_rejection(tmp_path):
    def upstream(request):
        body=json.loads(request.read());assert request.url.path=='/v1/responses'
        assert body['text']['format']['type']=='json_schema'
        prompt='Raise your left hand.' if body['input']=='右手を振って' else 'Raise your right hand.'
        output={'reply':'こんにちは。','motion_prompt':prompt,'anchor_text':'こんにちは','gesture_type':'explicit_action'}
        return httpx.Response(200,json={'output':[{'content':[{'type':'output_text','text':json.dumps(output)}]}]})
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o',realtime_service=configured_service(upstream,text_first=True))) as client:
        result=client.post('/api/conversation/prepare',json={'text':'こんにちは'})
        assert result.status_code==200 and result.json()['verbatim_speech_guaranteed'] is False
        assert result.json()['server_finished_monotonic_ms']>=result.json()['server_started_monotonic_ms']
        assert client.post('/api/conversation/prepare',json={'text':'右手を振って'}).status_code==502


class BlockingAdapter(ModelAdapter):
    id='ardy';implemented=True;tasks=('instruction',)
    def __init__(self,path):super().__init__(path);self.enter=threading.Event();self.release=threading.Event();self.calls=0
    def blockers(self):return []
    def generate(self,request,directory):
        self.calls+=1;self.enter.set();assert self.release.wait(3)
        save_motion(directory/'motion.json',viewer_fixture());(directory/'original.npz').write_bytes(b'test-double')
        return {'normalized_motion_path':directory/'motion.json','original_motion_path':directory/'original.npz','device':'test-double'}


def payload():return {'turn_id':'t1','response_id':'r1','gesture_id':'g1','model_name':'ardy','original_text':'右手を振って','motion_prompt':'Wave your right hand.'}


def test_motion_accepts_immediately_and_cancels_running_and_queued_work(tmp_path):
    adapter=BlockingAdapter(tmp_path/'d')
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o',model_adapters={'ardy':adapter})) as client:
        first=client.post('/api/motion/requests',json=payload());assert first.status_code==202
        a=first.json()['request_id'];assert adapter.enter.wait(1)
        second=client.post('/api/motion/requests',json={**payload(),'turn_id':'t2'});b=second.json()['request_id']
        assert client.delete('/api/motion/requests/'+b).json()['cancellation']['queued_work_prevented'] is True
        assert client.delete('/api/motion/requests/'+a).json()['status']=='cancelled'
        adapter.release.set()
        for future in client.app.state.store.futures.values():
            if not future.cancelled():future.result(timeout=2)
        assert adapter.calls==1
        assert client.get('/api/motion/requests/'+a).json()['status']=='cancelled'
        assert client.get('/api/motion/requests/'+a+'/motion').status_code==409
        assert client.get('/api/experiments/'+a+'/files/motion.json').status_code==200  # Research original retained.


def test_unavailable_gpu_isolated_from_speech_and_external_demo_requires_consent(tmp_path):
    adapter=BlockingAdapter(tmp_path/'d');adapter.config['backend']='official_demo'
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o',model_adapters={'ardy':adapter})) as client:
        assert client.post('/api/motion/requests',json=payload()).status_code==409
        assert adapter.calls==0
        assert client.post('/api/motion/requests',json={**payload(),'motion_prompt':'右手を振って'}).status_code==409
    with TestClient(create_app(data_dir=tmp_path/'other',output_dir=tmp_path/'otherout')) as client:
        response=client.post('/api/motion/requests',json=payload());assert response.status_code==202
        id=response.json()['request_id']
        for _ in range(100):
            result=client.get('/api/motion/requests/'+id).json()
            if result['status']=='failed':break
            time.sleep(.005)
        assert result['status']=='failed' and result['error']
        assert client.get('/api/health').status_code==200 and client.get('/api/realtime/config').status_code==200


def test_motion_service_auth_and_research_opt_in_csv_clock_domains(tmp_path,monkeypatch):
    monkeypatch.setenv('MOTION_SERVICE_ACCESS_TOKEN','private-service-test-token')
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o')) as client:
        assert client.post('/api/motion/requests',json=payload()).status_code==401
        assert client.get('/api/experiments').status_code==401
        client.headers.update({'Authorization':'Bearer private-service-test-token'})
        event={'name':'first_audio_playback','clock_domain':'client_audio','time_ms':None,'estimated':False,'detail':'=FORMULA sk-private-test-secret'}
        assert client.post('/api/research/sessions',json={'save_locally':False,'provenance':'offline_validation','events':[event]}).status_code==422
        result=client.post('/api/research/sessions',json={'save_locally':True,'provenance':'offline_validation','events':[event]}).json()
        row=client.get(result['json_url']).json()['events'][0]
        assert row['time_ms'] is None and 'sk-private' not in row['detail']
        csv=client.get(result['csv_url']);assert csv.content.startswith(b'\xef\xbb\xbf') and "'=FORMULA" in csv.text
        assert 'client_audio' in csv.text and result['audio_saved'] is False


def test_secret_redaction_includes_openai_keys():assert 'sk-' not in redact('sk-proj-123456789abc')


def test_remote_motion_api_preserves_context_and_authentication(tmp_path,monkeypatch):
    import app.dialogue_api as routes
    monkeypatch.setenv('MOTION_SERVICE_URL','https://gpu.example:8765')
    monkeypatch.setenv('MOTION_SERVICE_TOKEN','server-only-worker-token')
    id='f'*32;calls=[]
    def downstream(request):
        calls.append(request)
        assert request.headers['Authorization']=='Bearer server-only-worker-token'
        if request.method=='POST':
            body=json.loads(request.read());assert body['turn_id']=='t1' and body['original_text']=='右手を振って'
            return httpx.Response(202,json={'request_id':id,'status':'queued'})
        if request.method=='DELETE':return httpx.Response(200,json={'request_id':id,'status':'cancelled'})
        if request.url.path.endswith('/motion'):return httpx.Response(200,json=viewer_fixture())
        return httpx.Response(200,json={'request_id':id,'status':'succeeded','trained_model_output':False})
    original=httpx.AsyncClient
    monkeypatch.setattr(routes.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(downstream),**kw))
    with TestClient(create_app(data_dir=tmp_path/'d',output_dir=tmp_path/'o')) as client:
        response=client.post('/api/motion/requests',json=payload());assert response.status_code==202
        assert client.get('/api/motion/requests/'+id).json()['status']=='succeeded'
        assert client.get('/api/motion/requests/'+id+'/motion').json()['metadata']['trained_model_output'] is False
        assert client.delete('/api/motion/requests/'+id).json()['status']=='cancelled'
        assert client.app.state.store.list()==[] and len(calls)==4
