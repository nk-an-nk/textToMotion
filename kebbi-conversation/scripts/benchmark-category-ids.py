#!/usr/bin/env python3
"""Compare category-only selection and category -> LLM ID selection on a fixed robot catalog."""
import argparse
import asyncio
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
from zoneinfo import ZoneInfo

import httpx
from app.llm import Llm, LlmError
from app.models import Request, GESTURES, MotionCandidate
from app.settings import Settings

CASES = [
    ("learning", ["こんにちは、一緒に日本語の練習を始めよう。", "うん、最後までよく聞いているよ。", "助詞を正しく使えていて、よくできたね。", "そんなにたくさんの漢字を書けたなんて、びっくりしたよ。", "「きれいでした」は、形容詞を使って過去のことを説明する表現だよ。"]),
    ("support", ["どう伝えたらよいか、少し考えてみるね。", "今日はどんな言葉を練習したい？", "新しい言葉を覚えられて、うれしいな。", "間違えてしまって、つらかったんだね。", "一つずつ練習すれば大丈夫、もう一度やってみよう。"]),
    ("repair", ["ごめんね、さっきの説明に間違いがあったよ。", "今日はありがとう、また一緒に話そうね。", "あれ、二つの説明が違っていて、少し混乱しちゃった。", "明日の発表が楽しみで、わくわくするね。", "急がなくて大丈夫、ゆっくり深呼吸しよう。"]),
    ("feelings", ["大切にしていた花が枯れてしまって、悲しいよ。", "約束を何度も破られると、怒りを感じるよ。", "突然大きな音がして、怖くなっちゃった。", "腐った食べ物のにおいは、気持ちが悪いね。", "大好きだよ、ぎゅっと抱きしめたいな。"]),
    ("actions", ["鳥になったつもりで、羽をぱたぱた動かしてみよう。", "音楽に合わせて、ギターを弾くまねをしてみるね。", "運動の練習として、ボウリングの球を投げるまねをしよう。", "朝起きたら、歯を磨いて顔を洗うよ。", "右のほうを見てから、左のほうを指してみるね。"]),
]
WARMUP = ["こんにちは。", "会えてうれしいな。", "一緒に練習しよう。", "今日は何を話したい？", "よろしくね。"]


def candidates_from_mapping(body):
    indexed = {}
    for category in GESTURES:
        if category == 'none':
            continue
        for motion in body['mapping'].get(category, []):
            if not motion.get('enabled', True) or motion.get('basicOnly', False):
                continue
            identifier = motion['id']
            description = ('SDK motion: ' + identifier + ('; ' + motion['scene'] if motion.get('scene') else ''))[:300]
            item = indexed.setdefault(identifier, {'id': identifier, 'description': description, 'categories': []})
            item['categories'].append(category)
    return [MotionCandidate(**indexed[k]) for k in sorted(indexed)]


def aggregate(rows):
    result = {}
    for mode in ['rule', 'llm']:
        attempted = [r for r in rows if not r['warmup'] and r['mode'] == mode]
        valid = [r for r in attempted if r['status'] == 'ok']
        stats = {'attempted': len(attempted), 'success': len(valid), 'failures': len(attempted)-len(valid)}
        for field in ['total_ms', 'category_selection_ms', 'id_selection_ms']:
            values = [r[field] for r in valid]
            stats[field] = None if not values else {'mean': statistics.mean(values),
                'median': statistics.median(values), 'min': min(values), 'max': max(values)}
        stats['amortized_ms_per_sentence'] = sum(r['total_ms'] for r in valid)/sum(len(r['sentences']) for r in valid) if valid else None
        stats['non_null_motion_ids'] = sum(p.get('motion_id') is not None for r in valid for p in r['selections'])
        result[mode] = stats
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api-key-file', type=Path)
    parser.add_argument('--model', default='gpt-4.1-mini-2025-04-14')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error('repeats must be 1..10')
    key = args.api_key_file.read_text().strip() if args.api_key_file else os.environ['LLM_API_KEY']
    args.output.mkdir(parents=True, exist_ok=True)
    body = json.loads(args.catalog.read_text())
    candidates = candidates_from_mapping(body)
    candidate_bytes = json.dumps([m.model_dump() for m in candidates], ensure_ascii=False, indent=2).encode()
    protocol = {'selector_contract': 'per-sentence-category-choice-index-v1',
        'selector_source_sha256': hashlib.sha256(Path(__import__('app.llm',fromlist=['x']).__file__).read_bytes()).hexdigest(),
        'model': args.model, 'language': 'ja', 'profile': 'expanded25', 'sentence_count': 5,
        'repeats': args.repeats, 'concurrency': 1, 'timeout_per_api_call_s': 20, 'retries': 0,
        'candidate_count': len(candidates), 'catalog_sha256': hashlib.sha256(args.catalog.read_bytes()).hexdigest(),
        'candidates_sha256': hashlib.sha256(candidate_bytes).hexdigest(),
        'category_counts': dict(Counter(g for m in candidates for g in m.categories)), 'cases': CASES,
        'warmup': WARMUP, 'clock': 'time.perf_counter',
        'scope': 'Fixed replies -> category selection -> optional LLM ID selection; excludes text generation, ASR, TTS, USB and real robot output. Old-mode local robot selection time excluded.',
        'order': 'Alternate rule/llm order per case and repetition; one warmup per mode excluded.'}
    protocol_path = args.output/'protocol.json'
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise SystemExit('Existing protocol differs; use a new output directory')
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2))
    (args.output/'candidates.json').write_bytes(candidate_bytes)
    path = args.output/'trials.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []
    done = {r['trial_id'] for r in rows}
    plan = [(f'warmup:{mode}', 'warmup', 0, mode, WARMUP, True) for mode in ['rule','llm']]
    for rep in range(1, args.repeats+1):
        for index, (case, sentences) in enumerate(CASES):
            modes = ['rule','llm'] if (rep+index)%2 else ['llm','rule']
            plan.extend((f'{rep}:{case}:{mode}',case,rep,mode,sentences,False) for mode in modes)
    captures = []
    async def request_hook(request):
        payload=json.loads(request.content)
        request.extensions['benchmark_started']=time.perf_counter()
        request.extensions['benchmark_meta']={'model':payload['model'], 'request_bytes':len(request.content),
            'payload_sha256':hashlib.sha256(request.content).hexdigest()}
    async def response_hook(response):
        await response.aread()
        meta=dict(response.request.extensions['benchmark_meta'])
        meta.update({'http_status':response.status_code,
            'elapsed_ms':(time.perf_counter()-response.request.extensions['benchmark_started'])*1000})
        try:
            envelope=response.json()
            meta.update({'resolved_model':envelope.get('model'), 'usage':envelope.get('usage'), 'service_tier':envelope.get('service_tier')})
        except ValueError:
            pass
        captures.append(meta)
    settings=Settings(provider='openai',api_key=key,model=args.model)
    async with httpx.AsyncClient(timeout=20,event_hooks={'request':[request_hook],'response':[response_hook]}) as client:
        llm=Llm(settings,client)
        for trial_id,case,rep,mode,sentences,warmup in plan:
            if trial_id in done:
                continue
            request=Request(session_id='category-ids-benchmark',text='固定返答文の動作選択',language='ja',
                sentence_plan=True,selection_mode='category',gesture_profile='expanded',available_gestures=list(GESTURES),
                category_motion_selection=mode,available_motions=candidates)
            captures.clear()
            row={'trial_id':trial_id,'case':case,'repeat':rep,'mode':mode,'warmup':warmup,
                 'sentences':sentences,'started_at':datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()}
            start=time.perf_counter()
            try:
                parts,metrics=await llm.select_actions(request,sentences)
                row.update({'status':'ok',**metrics,'selections':[p.model_dump() for p in parts]})
            except LlmError as error:
                row.update({'status':error.code})
            row['total_ms']=(time.perf_counter()-start)*1000
            row['api_calls']=list(captures)
            with path.open('a',encoding='utf-8') as file:
                file.write(json.dumps(row,ensure_ascii=False)+'\n')
            rows.append(row)
            print(f'{trial_id} {row["status"]} {row["total_ms"]/1000:.3f}s',flush=True)
    result=aggregate(rows)
    (args.output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    fields=['trial_id','case','repeat','mode','warmup','status','total_ms','category_selection_ms','id_selection_ms']
    with (args.output/'trials.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    asyncio.run(main())
