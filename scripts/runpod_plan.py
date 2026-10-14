#!/usr/bin/env python3
"""Read-only RunPod pricing/balance inspection. No GPU creation or deposits."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.base import redact


def graphql(query, authenticated=False):
    headers={'Content-Type':'application/json','User-Agent':'motion-lab-readonly/1.0'}
    if authenticated:
        token=os.environ.get('RUNPOD_API_KEY')
        if not token: raise RuntimeError('RUNPOD_API_KEY is missing. Save it in cloud settings and Publish; never paste it into chat.')
        headers['Authorization']='Bearer '+token
    request=urllib.request.Request('https://api.runpod.io/graphql', data=json.dumps({'query':query}).encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request,timeout=20) as response: result=json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'RunPod read-only query returned HTTP {error.code}.') from None
    if result.get('errors'):
        raise RuntimeError('RunPod query failed: '+redact(' / '.join(x.get('message','unknown') for x in result['errors'])))
    return result['data']


def estimate(plan, hourly_usd):
    numbers=[hourly_usd,plan['max_hours'],plan['usd_to_jpy_budget_rate'],plan['budget_yen'],plan['storage_gb'],plan['storage_usd_per_gb_month'],plan['cost_reserve_fraction']]
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>=0 for x in numbers) or plan['max_hours']<=0 or plan['usd_to_jpy_budget_rate']<=0:
        raise ValueError('Budget inputs must be finite and valid.')
    storage=plan['storage_gb']*plan['storage_usd_per_gb_month']/720*plan['max_hours']
    usd=(hourly_usd*plan['max_hours']+storage)*(1+plan['cost_reserve_fraction'])
    yen=usd*plan['usd_to_jpy_budget_rate']
    if hourly_usd>plan['max_gpu_hourly_usd'] or yen>plan['budget_yen']:
        raise ValueError('The planned rental exceeds the authorized budget or hourly limit.')
    return {'gpu_hourly_usd':hourly_usd,'max_hours':plan['max_hours'],'storage_upper_estimate_usd':storage,'usd_with_reserve':usd,'yen_with_reserve':yen}


def inspect(plan, account=False):
    if plan.get('schema')!='motion-lab/runpod-trial-v1':raise ValueError('Unsupported trial plan.')
    info=graphql('query { gpuTypes { id displayName memoryInGb securePrice communityPrice } }')
    rows=[]
    for gpu in info['gpuTypes']:
        if gpu['id'] not in plan['gpu_type_ids']:continue
        price=gpu.get('securePrice' if plan['cloud_type']=='SECURE' else 'communityPrice')
        if price is None:continue
        try: cost=estimate(plan,price)
        except ValueError:continue
        rows.append({'id':gpu['id'],'name':gpu['displayName'],'vram_gb':gpu['memoryInGb'],**cost})
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'budget_yen':plan['budget_yen'],'fx_budget_rate':plan['usd_to_jpy_budget_rate'],
            'fx_note':'Conservative budgeting assumption, not a live exchange-rate quote.','cloud_type':plan['cloud_type'],
            'gpu_candidates':rows,'stock_confirmed':False,'gpu_created':False,'automatic_deposit':False,'account_inspected':False}
    if account:
        # Never log or save the full account response, Pod env, identity or credentials.
        data=graphql('query { myself { clientBalance currentSpendPerHr } }',authenticated=True)['myself']
        report.update(account_inspected=True,balance_usd=data.get('clientBalance'),existing_spend_per_hour_usd=data.get('currentSpendPerHr'))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/runpod_trial.json'))
    parser.add_argument('--account',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output and args.output.exists():parser.error('Existing pricing report is preserved; choose a new filename.')
    try:
        result=inspect(json.loads(args.config.read_text(encoding='utf-8')),args.account)
        if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    except Exception as error:
        print(redact(str(error)),file=sys.stderr);sys.exit(1)
