import asyncio
import json
import httpx
import pytest
from app.combined_generation import respond_combined
from app.llm import Llm,LlmError
from app.models import Request
from app.settings import Settings


def execute(first):
    async def run():
        captured=[]
        def handler(request):
            payload=json.loads(request.content);captured.append(payload)
            content=first if len(captured)==1 else {'sentence_0':0,'sentence_1':0}
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]})
        req=Request(session_id='combined',text='パンダが好き',language='ja',reply_model='gpt-4.1-2025-04-14',
            sentence_plan=True,selection_mode='category',category_motion_selection='llm',gesture_profile='expanded',
            available_gestures=['acknowledge','question'],available_motions=[
                {'id':'nod','description':'nod gently','categories':['acknowledge']},
                {'id':'ask','description':'asking a question','categories':['question']}])
        history=[{'role':'user','content':'好きな動物はパンダです。'},{'role':'assistant','content':'パンダが好きなんだね。'}]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm=Llm(Settings(provider='openai',api_key='fake',model='motion-model'),client)
            try: result=await respond_combined(llm,req,history)
            except LlmError: return None,captured
        return result,captured
    return asyncio.run(run())


def test_combined_uses_two_calls_preserves_sentences_categories_and_history():
    result,calls=execute({'sentences':[{'speech':'パンダが好きなんだね。','gesture':'acknowledge'},
        {'speech':'どこが好き？','gesture':'question'}],'language':'ja'})
    reply,metrics=result
    assert len(calls)==2 and [c['model'] for c in calls]==['gpt-4.1-2025-04-14','motion-model']
    assert calls[0]['messages'][1]['content']=='好きな動物はパンダです。'
    assert 'nod gently' not in json.dumps(calls[0])
    assert [p.motion_id for p in reply.sentences]==['nod','ask']
    assert [p.gesture for p in reply.sentences]==['acknowledge','question']
    assert reply.speech=='パンダが好きなんだね。どこが好き？'
    assert all(v>=0 for v in metrics.values())


@pytest.mark.parametrize('first',[
    {'sentences':[{'speech':'こんにちは','gesture':'bogus'}],'language':'ja'},
    {'sentences':[],'language':'ja'},
    {'sentences':[{'speech':'こんにちは','gesture':'question','motion_id':'nod'}],'language':'ja'},
    {'sentences':[{'speech':'Hello','gesture':'question'}],'language':'en'},
    {'sentences':[{'speech':'a'*401,'gesture':'question'}],'language':'ja'},
])
def test_invalid_combined_plan_never_requests_ids(first):
    result,calls=execute(first)
    assert result is None and len(calls)==1
