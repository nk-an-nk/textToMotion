#!/usr/bin/env python3
"""Balanced synthetic backend benchmark. Does not command TTS or robot motion."""
import argparse,csv,json,statistics,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
CASES=[('greeting','Hello Kebbi!'),('sadness','I feel sad because my friend did not play with me.'),('achievement','I worked hard and got full marks on my English quiz!'),('animal','Can you pretend to be a bird?')]
MODES=[('direct','basic'),('category','expanded'),('category','basic')]
BASIC=['greet','acknowledge','praise','surprise','explain','think','question','none']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mapping',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--url',default='http://127.0.0.1:8000');p.add_argument('--repeats',type=int,default=2);a=p.parse_args()
    data=json.loads(a.mapping.read_text());mapping=data['mapping'];motions=[{'id':x['id'],'description':x['description']} for x in data['motions']]
    a.output.mkdir(parents=True,exist_ok=True);rows=[]
    def request(mode,profile,case,text,repeat,warmup=False):
        gestures=[g for g,values in mapping.items() if values and (profile=='expanded' or g in BASIC)]+['none']
        body={'session_id':'benchmark-'+uuid.uuid4().hex,'conversation_id':str(uuid.uuid4()),'text':text,'language':'en','selection_mode':mode,'gesture_profile':profile,'available_gestures':gestures,'available_motions':motions if mode=='direct' else []}
        payload=json.dumps(body,ensure_ascii=False).encode();start=time.perf_counter();reply={}
        try:
            req=Request(a.url.rstrip('/')+'/api/respond',data=payload,headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=30) as r:reply=json.load(r);status=r.status
        except HTTPError as e:status=e.code;reply=json.load(e)
        except (TimeoutError,URLError):status=0;reply={'detail':'client_timeout_or_unavailable'}
        row={'repeat':repeat,'case':case,'selection_mode':mode,'gesture_profile':profile,'warmup':warmup,'http_status':status,'elapsed_ms':round((time.perf_counter()-start)*1000,3),'request_bytes':len(payload),'candidate_count':len(motions) if mode=='direct' else len(gestures)-1,'gesture':reply.get('gesture',''),'motion_id':reply.get('motion_id',''),'speech_chars':len(reply.get('speech','')),'error':reply.get('detail','')}
        rows.append(row);(a.output/'selection-benchmark.json').write_text(json.dumps({'metadata':{'model':data['model'],'mapping_sha256':data['catalog_sha256'],'sdk_count':len(motions),'repeats':a.repeats,'includes_robot_output':False,'classification_time_excluded':True,'warmup_excluded_from_statistics':True},'rows':rows},ensure_ascii=False,indent=2))
        print(json.dumps(row,ensure_ascii=False),flush=True)
    for mode,profile in MODES:request(mode,profile,'warmup','Hello Kebbi!',0,True)
    for repeat in range(a.repeats):
        for index,(case,text) in enumerate(CASES):
            offset=(repeat+index)%len(MODES);order=MODES[offset:]+MODES[:offset]
            if repeat%2:order=list(reversed(order))
            for mode,profile in order:request(mode,profile,case,text,repeat+1)
    with (a.output/'selection-benchmark.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=[]
    for mode,profile in MODES:
        all_rows=[r for r in rows if not r['warmup'] and r['selection_mode']==mode and r['gesture_profile']==profile];successful=[r for r in all_rows if r['http_status']==200];values=[r['elapsed_ms'] for r in successful]
        summary.append({'selection_mode':mode,'gesture_profile':profile,'attempts':len(all_rows),'successes':len(successful),'failures':len(all_rows)-len(successful),'mean_ms':round(statistics.mean(values),3) if values else None,'median_ms':round(statistics.median(values),3) if values else None,'min_ms':min(values) if values else None,'max_ms':max(values) if values else None,'mean_speech_chars':round(statistics.mean([r['speech_chars'] for r in successful]),1) if successful else None,'mean_request_bytes':round(statistics.mean([r['request_bytes'] for r in all_rows]),1)})
    (a.output/'selection-benchmark-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
