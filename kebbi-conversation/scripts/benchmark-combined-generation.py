#!/usr/bin/env python3
"""Paired PC test: three calls versus combined reply/category plus LLM motion ID choice."""
import argparse
import asyncio
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time
from zoneinfo import ZoneInfo

import httpx
import app.llm as llm_module
import app.combined_generation as combined_module
from app.llm import Llm,LlmError
from app.models import Request,GESTURES
from app.settings import Settings
from app.combined_generation import respond_combined

CASES = [
    {'id':'grammar','text':'「きれいかったです」は自然な日本語ですか。正しい言い方と理由を教えてください。',
     'history':[], 'rubric':'「きれいでした」等の正しい形を示し、ナ形容詞の過去形を適切に説明。誤用を肯定しない。'},
    {'id':'particle','text':'「図書館に本を読みます」は自然ですか。「に」と「で」の違いも教えてください。',
     'history':[], 'rubric':'「図書館で本を読みます」と訂正し、動作の場所には「で」を使うと説明。'},
    {'id':'shopping','text':'買い物の日本語を練習したいです。店員さんになってください。赤いノートを二冊ください。',
     'history':[], 'rubric':'店員役として赤いノート2冊の注文に対応し、会話練習を継続。'},
    {'id':'support','text':'漢字を十個練習しましたが、三個しか覚えられず、がっかりしています。どうすればいいですか。',
     'history':[], 'rubric':'気持ちに配慮し、具体的で実行可能な学習助言を示す。責めたり過剰に褒めたりしない。'},
    {'id':'memory','text':'さっき好きだと言った動物は何だった？',
     'history':[{'role':'user','content':'好きな動物はパンダだよ。'},
                {'role':'assistant','content':'パンダが好きなんだね。どんなところが好き？'}],
     'rubric':'会話履歴からパンダと答える。別の動物を創作せず、会話を最初から始め直さない。'},
]


def stats(rows):
    result={}
    for mode in ['separate','combined']:
        attempted=[r for r in rows if r['mode']==mode and not r['warmup']]
        valid=[r for r in attempted if r['status']=='ok']
        item={'attempted':len(attempted),'success':len(valid),'failures':len(attempted)-len(valid)}
        for field in ['total_ms','generation_category_ms','id_selection_ms','characters','sentence_count']:
            v=[r[field] for r in valid]
            item[field]=None if not v else {'mean':statistics.mean(v),'median':statistics.median(v),'min':min(v),'max':max(v)}
        item['ms_per_100_chars']=100*sum(r['total_ms'] for r in valid)/sum(r['characters'] for r in valid) if valid else None
        item['ms_per_sentence']=sum(r['total_ms'] for r in valid)/sum(r['sentence_count'] for r in valid) if valid else None
        result[mode]=item
    return result


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--api-key-file',type=Path)
    parser.add_argument('--model',default='gpt-4.1-mini-2025-04-14')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=10:parser.error('repeats must be 1..10')
    key=args.api_key_file.read_text().strip() if args.api_key_file else os.environ['LLM_API_KEY']
    helper_path=Path(__file__).with_name('benchmark-category-ids.py')
    spec=importlib.util.spec_from_file_location('catalog_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    candidates=helper.candidates_from_mapping(json.loads(args.catalog.read_text()))
    args.output.mkdir(parents=True,exist_ok=True)
    candidate_bytes=json.dumps([m.model_dump() for m in candidates],ensure_ascii=False,indent=2).encode()
    protocol={'model':args.model,'id_model':args.model,'profile':'expanded25','language':'ja','repeats':args.repeats,
        'conditions':{'separate':'reply -> categories -> IDs (3 calls)','combined':'reply+categories -> IDs (2 calls)'},
        'cases':CASES,'warmup_per_condition':1,'candidate_count':len(candidates),
        'candidate_sha256':hashlib.sha256(candidate_bytes).hexdigest(),
        'source_sha256':{name:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                         for name,module in [('llm.py',llm_module),('combined_generation.py',combined_module)]},
        'order':'Alternate condition order per case and repetition','concurrency':1,'timeout_per_call_s':20,'retries':0,
        'generation_constraints':'1-6 sentences; <=400 characters; same conversational system instruction; no 1-2 sentence preference',
        'scope':'PC request -> completed reply/category/ID plan validation. Includes network and API waits; excludes ASR,TTS,robot and USB.',
        'quality_review':'Preliminary rubric review of generated text, categories and ID descriptions; no human subject or real robot rating.'}
    protocol_path=args.output/'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text())!=protocol:
        raise SystemExit('Protocol differs; use a new output directory')
    protocol_path.write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    (args.output/'candidates.json').write_bytes(candidate_bytes)
    path=args.output/'trials.jsonl'
    rows=[json.loads(x) for x in path.read_text().splitlines() if x] if path.exists() else []
    done={r['trial_id'] for r in rows}
    warm={'id':'warmup','text':'こんにちは。日本語の会話練習をしたいです。','history':[]}
    plan=[(f'warmup:{mode}',mode,warm,0,True) for mode in ['separate','combined']]
    for rep in range(1,args.repeats+1):
        for index,case in enumerate(CASES):
            modes=['separate','combined'] if (rep+index)%2 else ['combined','separate']
            plan.extend((f'{rep}:{case["id"]}:{mode}',mode,case,rep,False) for mode in modes)
    captures=[]
    async def request_hook(request):
        body=json.loads(request.content)
        request.extensions['started']=time.perf_counter()
        request.extensions['meta']={'model':body['model'],'request_bytes':len(request.content),
            'payload_sha256':hashlib.sha256(request.content).hexdigest()}
    async def response_hook(response):
        await response.aread()
        meta=dict(response.request.extensions['meta'])
        meta.update({'http_status':response.status_code,'elapsed_ms':(time.perf_counter()-response.request.extensions['started'])*1000})
        try:
            body=response.json();choice=body.get('choices',[{}])[0]
            meta.update({'resolved_model':body.get('model'),'usage':body.get('usage'),'service_tier':body.get('service_tier'),
                         'finish_reason':choice.get('finish_reason'),'raw_content':choice.get('message',{}).get('content')})
        except ValueError:pass
        captures.append(meta)
    async with httpx.AsyncClient(timeout=20,event_hooks={'request':[request_hook],'response':[response_hook]}) as client:
        llm=Llm(Settings(provider='openai',api_key=key,model=args.model),client)
        for trial_id,mode,case,rep,warmup in plan:
            if trial_id in done:continue
            request=Request(session_id='combined-benchmark',text=case['text'],language='ja',reply_model=args.model,
                sentence_plan=True,selection_mode='category',category_motion_selection='llm',gesture_profile='expanded',
                available_gestures=list(GESTURES),available_motions=candidates)
            row={'trial_id':trial_id,'mode':mode,'case':case['id'],'repeat':rep,'warmup':warmup,
                'input':case['text'],'history':case['history'],'started_at':datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()}
            captures.clear();started=time.perf_counter()
            try:
                if mode=='separate':
                    reply=await llm.respond_separate(request,list(case['history']))
                    timing={'generation_category_ms':reply.text_generation_ms+reply.category_selection_ms,
                            'text_generation_ms':reply.text_generation_ms,'category_selection_ms':reply.category_selection_ms,
                            'id_selection_ms':reply.id_selection_ms}
                else:reply,timing=await respond_combined(llm,request,list(case['history']))
                row.update({'status':'ok',**timing,'reply':reply.model_dump(),'characters':len(reply.speech),
                            'sentence_count':len(reply.sentences)})
            except LlmError as error:row['status']=error.code
            row['total_ms']=(time.perf_counter()-started)*1000;row['api_calls']=list(captures)
            with path.open('a',encoding='utf-8') as file:file.write(json.dumps(row,ensure_ascii=False)+'\n')
            rows.append(row)
            print(f'{trial_id} {row["status"]} {row["total_ms"]/1000:.3f}s {row.get("characters",0)}chars {row.get("sentence_count",0)}sentences',flush=True)
    summary=stats(rows)
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    fields=['trial_id','mode','case','repeat','warmup','status','total_ms','generation_category_ms','text_generation_ms','category_selection_ms','id_selection_ms','characters','sentence_count']
    with (args.output/'trials.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':asyncio.run(main())
