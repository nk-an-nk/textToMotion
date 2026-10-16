#!/usr/bin/env python3
"""Faithful utterance translation by a real LLM; no gesture-instruction rewrite."""
from datetime import datetime,timezone
import json
import os
import time
from websockets.sync.client import connect


def translate(text, *, model='gpt-realtime-2.1', api_key=None):
    if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid source utterance.')
    key=api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('MOTION_LAB_OPENAI_API_KEY') or os.environ.get('realtime')
    if not key:raise RuntimeError('OpenAI credential is unavailable; never paste its value in chat.')
    instruction=('Translate the supplied teacher utterance faithfully into natural English. '
                 'Preserve every sentence, greeting, quoted English phrase, meaning, and tone. '
                 'If it is already entirely English, return it verbatim. '
                 'Translate the utterance only: do not turn it into an action or gesture instruction, '
                 'and do not add movements, scene descriptions, explanations, or dialogue turns.')
    instruction+=' Return ONLY the translated English utterance as plain text. Do not use JSON, quotes around the answer, or a code fence.'
    started=time.monotonic();at=datetime.now(timezone.utc).isoformat()
    body=None;content='';sent=False
    with connect('wss://api.openai.com/v1/realtime?model='+model,
                 additional_headers={'Authorization':'Bearer '+key},open_timeout=15,
                 close_timeout=.1,max_size=4*1024*1024) as socket:
        socket.send(json.dumps({'type':'session.update','session':{'type':'realtime','model':model,
                    'instructions':instruction,'output_modalities':['text'],'max_output_tokens':400}}))
        while time.monotonic()-started<45:
            event=json.loads(socket.recv(timeout=max(.1,45-(time.monotonic()-started))))
            kind=event.get('type')
            if kind=='error':raise RuntimeError('LLM translation: '+str(event.get('error',{}).get('code','unknown')))
            if kind=='session.updated' and not sent:
                socket.send(json.dumps({'type':'conversation.item.create','item':{'type':'message',
                            'role':'user','content':[{'type':'input_text','text':text}]}},ensure_ascii=False))
                socket.send(json.dumps({'type':'response.create','response':{'output_modalities':['text'],'max_output_tokens':400}}));sent=True
            elif kind in ('response.output_text.delta','response.text.delta'):content+=event.get('delta','')
            elif kind in ('response.output_text.done','response.text.done'):content=event['text']
            elif kind=='response.done':body=event['response'];break
    elapsed=time.monotonic()-started
    if body is None or body.get('status')!='completed':raise RuntimeError('LLM translation did not complete.')
    final_text=''.join(part.get('text','') for item in body.get('output',[])
                       for part in item.get('content',[]) if part.get('type') in ('text','output_text'))
    if final_text:content=final_text
    if not content:raise RuntimeError('LLM translation completed without text output.')
    translated=content.strip()
    if not translated.strip() or len(translated)>4000 or any('\u3040'<=c<='\u30ff' or '\u4e00'<=c<='\u9fff' for c in translated):
        raise RuntimeError('LLM did not produce an English-only translation.')
    return {'schema':'motion-lab/llm-translation-v1','source_text':text,'english':translated,
            'llm_generated':True,'provider':'OpenAI Realtime API / text output','model':model,
            'response_id':body.get('id'),'translation_seconds':elapsed,'usage':body.get('usage'),'raw_output':content,
            'input_submitted_at_utc':at,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'policy':'faithful English utterance; no action-instruction substitution','actual_charge_usd':None}
