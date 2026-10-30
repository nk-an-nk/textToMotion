import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings


def run_request(id_result, **changes):
    captured = []
    def handler(req):
        body=json.loads(req.content); captured.append(body)
        content = ({"sentences":["こんにちは。","説明するね。"],"language":"ja"} if len(captured)==1 else
                   {"selections":[{"gesture":"greet","motion_id":None},{"gesture":"explain","motion_id":None}]} if len(captured)==2 else id_result)
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(content)}}]})
    request={"session_id":"category-id-test","text":"日本語を教えて","language":"ja",
             "reply_model":"gpt-4.1-2025-04-14","sentence_plan":True,
             "selection_mode":"category","category_motion_selection":"llm","gesture_profile":"expanded",
             "available_gestures":["greet","explain"],"available_motions":[
                 {"id":"wave","description":"wave hello","categories":["greet"]},
                 {"id":"explain","description":"explain with hands","categories":["explain"]},
                 {"id":"sad","description":"sad pose","categories":["sadness"]}]}
    request.update(changes)
    with TestClient(create_app(Settings(provider="openai",api_key="test-key",model="motion-model"),httpx.MockTransport(handler))) as client:
        response=client.post('/api/respond',json=request)
    return response,captured


def test_three_stages_keep_category_fixed_and_filter_each_sentence_candidates():
    response,calls=run_request({"sentence_0":0,"sentence_1":0})
    assert response.status_code==200,response.text
    result=response.json()
    assert [p['motion_id'] for p in result['sentences']]==['wave','explain']
    assert [p['gesture'] for p in result['sentences']]==['greet','explain']
    assert [c['model'] for c in calls]==['gpt-4.1-2025-04-14','motion-model','motion-model']
    assert result['motion_id_selection']=='llm'
    assert result['motion_selection_ms'] >= result['category_selection_ms']
    assert result['motion_selection_ms'] >= result['id_selection_ms']
    rows=json.loads(calls[2]['messages'][-1]['content'])['sentences']
    assert [[c['id'] for c in row['available_motions']] for row in rows]==[['wave'],['explain']]
    assert 'sad pose' not in json.dumps(calls[2])
    assert 'wave hello' not in json.dumps(calls[1])


@pytest.mark.parametrize('bad',[{'sentence_0':1,'sentence_1':0},{'sentence_0':-1,'sentence_1':0},
    {'sentence_0':'wave','sentence_1':0},{'sentence_0':0},{'sentence_0':True,'sentence_1':0},
    {'sentence_0':0,'sentence_1':0,'gesture':'sadness'}])
def test_bad_or_cross_category_ids_rejected_without_rule_fallback(bad):
    response,calls=run_request(bad)
    assert len(calls)==3
    assert response.status_code==502
    assert response.json()['detail']=='invalid_llm_response'


def test_null_id_is_preserved_instead_of_picking_local_candidate():
    response,_=run_request({'sentence_0':None,'sentence_1':0})
    assert response.status_code==200
    assert response.json()['sentences'][0].get('motion_id') is None


def test_no_candidates_skip_id_call_and_never_invent_ids():
    response,calls=run_request({},available_motions=[])
    assert response.status_code==200 and len(calls)==2
    assert all(p.get('motion_id') is None for p in response.json()['sentences'])


def test_old_rule_protocol_keeps_two_api_calls():
    response,calls=run_request({},category_motion_selection='rule')
    assert response.status_code==200 and len(calls)==2
    assert response.json()['motion_id_selection']=='rule'
    assert all(p.get('motion_id') is None for p in response.json()['sentences'])


def test_unknown_category_in_catalog_rejected_before_any_api_request():
    response,calls=run_request({},available_motions=[{'id':'x','description':'x','categories':['bogus']}])
    assert response.status_code==422 and calls==[]
