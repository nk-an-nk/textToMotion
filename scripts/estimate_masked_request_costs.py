#!/usr/bin/env python3
"""Apply the report's verified 2026-10-15 reference rates to actual usage, no API calls."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
r=ROOT/'reports/masked-models-20261016';pricing=json.loads((ROOT/'reports/presentation-20261016/measurements.json').read_text());rates=pricing['pricing_usd_per_million'];rows=[]
def cost(usage):
    i,o=usage['input_token_details'],usage['output_token_details']
    if i.get('cached_tokens',0):raise ValueError('Cached usage requires a separate cached-token price.')
    # reasoning_tokens is an included detail of text_tokens, not an extra billable count.
    return (i.get('text_tokens',0)*rates['text_input']+i.get('audio_tokens',0)*rates['audio_input']+o.get('text_tokens',0)*rates['text_output']+o.get('audio_tokens',0)*rates['audio_output'])/1e6
for profile in ['lab_proxy','b300']:
    for model in ['molingo','remomask2','momask']:
        d=json.loads((r/profile/'dialogue'/model/'measurement.json').read_text());t=json.loads((r/profile/'dialogue'/model/'translation.json').read_text());rate=.89 if profile=='lab_proxy' else 8.99
        gpu=(d['student_audio_seconds']+d['bone_ready_observed_seconds_after_student_end'])*rate/3600;api=cost(d['usage']);translation=cost(t['usage'])
        rows.append({'profile':profile,'model':model,'gpu_request_window_usd':gpu,'realtime_voice_estimate_usd':api,'translation_estimate_usd':translation,'api_subtotal_usd':api+translation,'request_subtotal_usd':gpu+api+translation,'request_subtotal_jpy_at_200':200*(gpu+api+translation),'native_generation_only_gpu_usd':rate*d['motion_generation_seconds']/3600,'actual_invoice_usd':None})
(r/'request-cost-estimates.json').write_text(json.dumps({'pricing_source':pricing['pricing_source'],'pricing_verified_date':pricing['pricing_verified_date'],'usd_per_million_tokens':rates,'jpy_per_usd_assumption':200,'scope':'Student audio start to bones received GPU time plus actual Realtime and fresh LLM-translation usage; reasoning tokens are already included in text_tokens','excluded':['ASR separate billing','recorded student voice creation','setup','idle','storage','MP4 rendering'],'rows':rows},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'request_estimates':len(rows),'jpy_range_at_200':[min(x['request_subtotal_jpy_at_200'] for x in rows),max(x['request_subtotal_jpy_at_200'] for x in rows)]}))
