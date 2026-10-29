import asyncio
import json
import logging
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.models import Reply
from app.sessions import Sessions, CapacityError

def request(**extra):
    return {"session_id":"test-session", "conversation_id":str(uuid4()), "text":"I got 100 points!", "language":"en", **extra}

def test_mock_flow_and_history_and_forget(caplog):
    app=create_app()
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="kebbi.events"):
        assert client.get("/health").json()=={"status":"ok","provider":"mock"}
        response=client.post("/api/respond",json=request())
        assert response.status_code==200
        assert response.json()=={"speech":"Great job! What did you enjoy learning?","gesture":"praise","language":"en","timing":"speech_start"}
        assert response.headers['cache-control']=='no-store'
        assert len(app.state.sessions.entries['test-session'].history)==2
        assert client.delete('/api/sessions/test-session').status_code==200
        assert not app.state.sessions.entries
    assert "I got 100" not in caplog.text
    assert "Great job" not in caplog.text
    events=[json.loads(r.message) for r in caplog.records if r.name=='kebbi.events']
    assert [e['event'] for e in events]==['llm_request_start','llm_response_received']
    assert events[0]['conversation_id']==events[1]['conversation_id']

@pytest.mark.parametrize('data',[request(text=' '),request(text='a'*1001),request(language='fr'),request(available_gestures=['invented']),request(session_id='../bad'),request(conversation_id='bad')])
def test_invalid_input_is_sanitized(data):
    with TestClient(create_app()) as client:
        r=client.post('/api/respond',json=data)
        assert r.status_code==422 and r.json()=={'detail':'invalid_request'}

@pytest.mark.parametrize('text,language,gesture',[('Hello Kebbi','en','greet'),('こんにちは','ja','greet'),('What animal?','en','question')])
def test_mock_language_and_gestures(text,language,gesture):
    with TestClient(create_app()) as client:
        r=client.post('/api/respond',json=request(text=text,language=language))
        assert r.json()['language']==language and r.json()['gesture']==gesture

def test_unavailable_motion_fallback():
    with TestClient(create_app()) as client:
        assert client.post('/api/respond',json=request(available_gestures=['none'])).json()['gesture']=='none'

def live_client(handler, **extra):
    return TestClient(create_app(Settings(provider='openai',api_key='private-secret',model='test-model', **extra),httpx.MockTransport(handler)))

def envelope(content,finish='stop'):
    return httpx.Response(200,json={'choices':[{'finish_reason':finish,'message':{'content':content}}]})

def test_live_contract_history_and_unknown_label(caplog):
    captured=[]
    def handler(req):
        captured.append(json.loads(req.content))
        return envelope(json.dumps({'speech':'Hello!','gesture':'invented','language':'en','timing':'speech_start'}))
    with live_client(handler) as client:
        for _ in range(2):
            r=client.post('/api/respond',json=request())
            assert r.status_code==200 and r.json()['gesture']=='none'
    assert captured[0]['model']=='test-model'
    assert captured[0]['store'] is False and captured[0]['response_format']['json_schema']['strict'] is True
    assert len(captured[1]['messages'])==4
    assert 'private-secret' not in caplog.text

@pytest.mark.parametrize('content', ['not json', '{}', json.dumps({'speech':'a'*401,'gesture':'none','language':'en','timing':'speech_start'}),json.dumps({'speech':'ok','gesture':3,'language':'en','timing':'speech_start'})])
def test_bad_llm_json(content):
    with live_client(lambda req:envelope(content)) as client:
        r=client.post('/api/respond',json=request())
        assert r.status_code==502 and r.json()=={'detail':'invalid_llm_response'}

def test_incomplete_response_is_rejected():
    with live_client(lambda req:envelope('{}','length')) as client:
        assert client.post('/api/respond',json=request()).status_code==502

def test_timeout():
    def fail(req):raise httpx.ReadTimeout('sensitive upstream details')
    with live_client(fail) as client:
        r=client.post('/api/respond',json=request())
        assert r.status_code==504 and 'sensitive' not in r.text

def test_upstream_error_does_not_leak_body():
    with live_client(lambda req:httpx.Response(401,text='private-secret')) as client:
        r=client.post('/api/respond',json=request())
        assert r.status_code==502 and 'private-secret' not in r.text

def test_auth_history_bound_and_eviction():
    with TestClient(create_app(Settings(backend_token='test-access',history_turns=1,max_sessions=2))) as client:
        assert client.post('/api/respond',json=request()).status_code==401
        headers={'Authorization':'Bearer test-access'}
        for session in ['one','one','two','three']:
            assert client.post('/api/respond',headers=headers,json=request(session_id=session)).status_code==200
        entries=client.app.state.sessions.entries
        assert list(entries)==['two','three']
        assert all(len(e.history)==2 for e in entries.values())

@pytest.mark.asyncio
async def test_session_ttl_capacity_and_serialization():
    now=[0.0];sessions=Sessions(5,1,lambda:now[0])
    async with sessions.conversation('a') as history:
        history.append('one')
        with pytest.raises(CapacityError):
            async with sessions.conversation('b'):pass
    now[0]=10
    async with sessions.conversation('a') as history:
        assert history==[]
    order=[]
    async def turn(n):
        async with sessions.conversation('a'):
            order.append(n);await asyncio.sleep(0);order.append(n)
    await asyncio.gather(turn(1),turn(2))
    assert order==[1,1,2,2]

def test_disabled_history():
    app=create_app(Settings(history_turns=0))
    with TestClient(app) as client:
        client.post('/api/respond',json=request())
        assert app.state.sessions.entries['test-session'].history==[]


def test_direct_schema_and_candidate_description():
    captured=[]
    def handler(req):
        captured.append(json.loads(req.content))
        return envelope(json.dumps({'speech':'Yes, I agree.','gesture':'none','language':'en','timing':'speech_start','motion_id':'666_BA_Nodhead'}))
    with live_client(handler) as client:
        r=client.post('/api/respond',json=request(selection_mode='direct',available_motions=[{'id':'666_BA_Nodhead','description':'acknowledge: nod head for agreement'}]))
        assert r.status_code==200 and r.json()['motion_id']=='666_BA_Nodhead'
    schema=captured[0]['response_format']['json_schema']['schema']
    assert schema['properties']['motion_id']['enum']==[None,'666_BA_Nodhead']
    assert schema['properties']['gesture']['enum']==['none']
    assert 'nod head for agreement' in captured[0]['messages'][0]['content']

@pytest.mark.parametrize('mode,profile,gesture,motion,expected_gesture,expected_motion',[
    ('direct','basic','praise','invented','none',None),
    ('direct','basic','greet',None,'none',None),
    ('category','basic','empathy','666_BA_Nodhead','none',None),
    ('category','expanded','empathy','666_BA_Nodhead','empathy',None),
])
def test_modes_enforce_their_contract(mode,profile,gesture,motion,expected_gesture,expected_motion):
    def handler(req):
        return envelope(json.dumps({'speech':'I hear you.','gesture':gesture,'language':'en','timing':'speech_start','motion_id':motion}))
    with live_client(handler) as client:
        r=client.post('/api/respond',json=request(selection_mode=mode,gesture_profile=profile))
        assert r.status_code==200
        assert r.json()['gesture']==expected_gesture and r.json().get('motion_id')==expected_motion

@pytest.mark.parametrize('data',[
    request(selection_mode='execute'),request(gesture_profile='unknown'),
    request(available_motions=[{'id':'x','description':''}]),
    request(available_motions=[{'id':'x','description':'a'*301}]),
    request(available_motions=[{'id':'x','description':'ok'}]*4097),
])
def test_invalid_experiment_settings(data):
    with TestClient(create_app()) as client:
        assert client.post('/api/respond',json=data).status_code==422


def test_experiment_histories_are_isolated_and_all_forgotten():
    with TestClient(create_app()) as client:
        for mode,profile in [('category','basic'),('category','expanded'),('direct','basic')]:
            assert client.post('/api/respond',json=request(selection_mode=mode,gesture_profile=profile)).status_code==200
        assert len(client.app.state.sessions.entries)==3
        assert all(len(e.history)==2 for e in client.app.state.sessions.entries.values())
        assert client.delete('/api/sessions/test-session').status_code==200
        assert not client.app.state.sessions.entries


def test_requested_language_cannot_change_in_reply():
    with live_client(lambda req:envelope(json.dumps({'speech':'Hi','gesture':'none','language':'ja','timing':'speech_start'}))) as client:
        assert client.post('/api/respond',json=request(language='en')).status_code==502


def test_large_catalog_is_not_truncated_by_schema_limits():
    from app.models import Request
    from app.llm import selection_contract, constrain_reply
    motions=[{'id':f'motion_{i:04d}','description':'SDK motion name'} for i in range(1200)]
    req=Request(**request(selection_mode='direct',available_motions=motions))
    system,schema=selection_contract(req)
    assert 'motion_1199' in system
    assert 'enum' not in schema['properties']['motion_id']
    reply=Reply(speech='Hello',gesture='none',language='en',timing='speech_start',motion_id='motion_1199')
    assert constrain_reply(reply,req).motion_id=='motion_1199'
    assert constrain_reply(reply.model_copy(update={'motion_id':'invented'}),req).motion_id is None


def test_preclassified_mapping_endpoint(tmp_path):
    path=tmp_path/'mapping.json'
    with TestClient(create_app(Settings(motion_mapping_file=str(path)))) as client:
        assert client.get('/api/motion-mapping').status_code==404
        body={'mapping':{'greet':[{'id':'sample','scene':'greet'}]}}
        path.write_text(json.dumps(body))
        assert client.get('/api/motion-mapping').json()==body
        path.write_text('invalid')
        assert client.get('/api/motion-mapping').status_code==404


def test_sentence_plan_mock_splits_punctuation_and_retains_history():
    app=create_app()
    with TestClient(app) as client:
        r=client.post('/api/respond',json=request(text='Hello',sentence_plan=True))
        assert r.status_code==200
        assert [s['speech'] for s in r.json()['sentences']]==['Hello!','Nice to meet you!']
        assert app.state.sessions.entries['test-session'].history[-1]['content']=='Hello! Nice to meet you!'


def test_sentence_plan_schema_and_per_sentence_candidate_validation():
    captured=[]
    def handler(req):
        captured.append(json.loads(req.content))
        return envelope(json.dumps({'sentences':[
            {'speech':'こんにちは！元気？','gesture':'none','motion_id':'known'},
            {'speech':'一緒に遊ぼう。','gesture':'none','motion_id':'invented'}], 'language':'ja','timing':'speech_start'}))
    with live_client(handler) as client:
        r=client.post('/api/respond',json=request(text='こんにちは',language='ja',sentence_plan=True,selection_mode='direct',available_motions=[{'id':'known','description':'a greeting'}]))
        assert r.status_code==200
        assert [s['speech'] for s in r.json()['sentences']]==['こんにちは！','元気？','一緒に遊ぼう。']
        assert r.json()['sentences'][-1].get('motion_id') is None
        schema=captured[0]['response_format']['json_schema']['schema']
        assert set(schema['properties'])=={'sentences','language','timing'}
        assert schema['properties']['sentences']['items']['properties']['motion_id']['enum']==['known']

@pytest.mark.parametrize('parts',[[],[{'speech':'x','gesture':'greet','motion_id':None}]*7,[{'speech':'x'*401,'gesture':'greet','motion_id':None}],[{'speech':' ','gesture':'greet','motion_id':None}]])
def test_invalid_sentence_plans_are_rejected(parts):
    with live_client(lambda req:envelope(json.dumps({'sentences':parts,'language':'en','timing':'speech_start'}))) as client:
        assert client.post('/api/respond',json=request(sentence_plan=True)).status_code==502


def test_english_decimal_and_japanese_sentence_boundaries():
    from app.models import split_sentences
    assert split_sentences('It is 3.14. Do you like it?')==['It is 3.14.','Do you like it?']
    assert split_sentences('「そうだね！」次は何をする？')==['「そうだね！」','次は何をする？']


def test_same_session_keeps_multiturn_context_in_sentence_mode():
    payloads=[]
    def handler(req):
        payloads.append(json.loads(req.content))
        return envelope(json.dumps({'sentences':[{'speech':'What color is your panda?','gesture':'question','motion_id':None}], 'language':'en','timing':'speech_start'}))
    with live_client(handler) as client:
        assert client.post('/api/respond',json=request(sentence_plan=True,text='I like pandas')).status_code==200
        assert client.post('/api/respond',json=request(sentence_plan=True,text='Black and white')).status_code==200
    assert payloads[1]['messages'][1:]==[
        {'role':'user','content':'I like pandas'}, {'role':'assistant','content':'What color is your panda?'},
        {'role':'user','content':'Black and white'}]

@pytest.mark.parametrize('model',['gpt-4.1-mini-2025-04-14','gpt-4.1-2025-04-14'])
@pytest.mark.parametrize('mode',['category','direct'])
def test_reply_model_only_generates_text_and_fixed_model_selects_motion(model,mode,caplog):
    captured=[]
    def handler(req):
        payload=json.loads(req.content);captured.append(payload)
        if len(captured)==1:
            return envelope(json.dumps({'sentences':['パンダが好きなんだね。','どんなところが好き？'],'language':'ja'}))
        return envelope(json.dumps({'selections':[
            {'gesture':'none' if mode=='direct' else 'acknowledge','motion_id':'known' if mode=='direct' else None},
            {'gesture':'none' if mode=='direct' else 'question','motion_id':'known' if mode=='direct' else None}]}))
    with live_client(handler) as client, caplog.at_level(logging.INFO,logger='kebbi.events'):
        r=client.post('/api/respond',json=request(text='パンダが好き',language='ja',sentence_plan=True,
            reply_model=model,selection_mode=mode,gesture_profile='expanded',
            available_motions=[{'id':'known','description':'SECRET_CANDIDATE_DESCRIPTION'}]))
        assert r.status_code==200,r.text
        body=r.json()
        assert body['speech']=='パンダが好きなんだね。どんなところが好き？'
        assert len(body['sentences'])==2
        assert body['reply_model']==model and body['motion_model']=='test-model'
        assert body['text_generation_ms']>=0 and body['motion_selection_ms']>=0
    assert len(captured)==2
    text,motion=captured
    assert text['model']==model and motion['model']=='test-model'
    assert set(text['response_format']['json_schema']['schema']['properties'])=={'sentences','language'}
    assert 'SECRET_CANDIDATE_DESCRIPTION' not in json.dumps(text)
    assert json.loads(motion['messages'][-1]['content'])=={'sentences':['パンダが好きなんだね。','どんなところが好き？']}
    assert set(motion['response_format']['json_schema']['schema']['properties'])=={'selections'}
    assert 'パンダ' not in caplog.text and 'private-secret' not in caplog.text


def test_reply_model_rejects_unapproved_model_before_upstream():
    def fail(req):raise AssertionError('Must not call upstream')
    with live_client(fail) as client:
        r=client.post('/api/respond',json=request(reply_model='arbitrary-expensive-model'))
        assert r.status_code==422 and r.json()=={'detail':'invalid_request'}

@pytest.mark.parametrize('bad',['{bad',json.dumps({'selections':[]}),json.dumps({'selections':[{'gesture':'greet','motion_id':None,'speech':'rewritten'}]})])
def test_motion_stage_failure_does_not_save_history_or_return_rewritten_speech(bad):
    count=0
    def handler(req):
        nonlocal count
        count+=1
        return envelope(json.dumps({'sentences':['Hello.'],'language':'en'}) if count==1 else bad)
    with live_client(handler) as client:
        r=client.post('/api/respond',json=request(reply_model='gpt-4.1-2025-04-14',sentence_plan=True))
        assert r.status_code==502
        assert all(not entry.history for entry in client.app.state.sessions.entries.values())


def test_comparison_history_is_isolated_by_model_language_and_deleted_together():
    models=['gpt-4.1-mini-2025-04-14','gpt-4.1-2025-04-14']
    with TestClient(create_app()) as client:
        for model,language in [(models[0],'en'),(models[1],'en'),(models[1],'ja')]:
            for _ in range(2):
                r=client.post('/api/respond',json=request(reply_model=model,language=language,sentence_plan=True))
                assert r.status_code==200
        assert len(client.app.state.sessions.entries)==3
        assert all(len(e.history)==4 for e in client.app.state.sessions.entries.values())
        assert client.post('/api/respond',json=request(session_id='test-session-other')).status_code==200
        assert client.delete('/api/sessions/test-session').status_code==200
        assert list(client.app.state.sessions.entries)==['test-session-other']

@pytest.mark.parametrize('textplan',[
    {'sentences':['x']*7,'language':'en'},
    {'sentences':['x'*401],'language':'en'},
    {'sentences':[' '],'language':'en'},
    {'sentences':['Hello.'],'language':'ja'},
    {'sentences':['One. Two. Three. Four. Five. Six. Seven.'],'language':'en'},
])
def test_separate_text_stage_validates_before_requesting_motion(textplan):
    captured=[]
    def handler(req):
        captured.append(req)
        assert len(captured)==1
        return envelope(json.dumps(textplan))
    with live_client(handler) as client:
        assert client.post('/api/respond',json=request(reply_model='gpt-4.1-2025-04-14',sentence_plan=True)).status_code==502
        assert len(captured)==1
