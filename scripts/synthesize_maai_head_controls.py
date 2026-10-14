#!/usr/bin/env python3
"""Apply MaAI's published nod interpolator to saved trained predictions; retain the source."""
import argparse
import hashlib
import json
from pathlib import Path


def scalar(value):
    while isinstance(value,list):value=value[0]
    return float(value)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);a=p.parse_args()
    from maai.util import generate_natural_nod
    plan=json.loads(a.plan.read_text());source=a.plan.parent/plan['motion_file']
    controls=json.loads(source.read_text());events=[];available=0
    for pred in controls['predictions']:
        start=pred['input_audio_seconds']
        if start<available or scalar(pred['p_nod'])<.5:continue
        values,axis=generate_natural_nod(range_rad=scalar(pred['nod_range']),
            count=int(scalar(pred['nod_repetitions_pred']))+1,
            use_pre_rise=bool(scalar(pred['nod_swing_up_pred'])),velocity=max(.001,scalar(pred['nod_speed'])),fps=30)
        events.append({'start_seconds':start,'pitch_frames_radians':values.tolist(),'fps':30})
        available=start+len(values)/30
    controls.update(nod_events=events,source_prediction_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    render_synthesis='maai.util.generate_natural_nod; head pitch sign adapted to VRM forward +Z')
    target=source.with_name('head-controls-synthesized.json')
    if target.exists():raise ValueError('Existing synthesized head control is preserved.')
    target.write_text(json.dumps(controls,ensure_ascii=False,indent=2)+'\n')
    plan.update(original_prediction_file=plan['motion_file'],original_prediction_sha256=plan['motion_sha256'],
                motion_file=target.name,motion_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    a.plan.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'synthesized_nods':len(events),'source_preserved':str(source)}))


if __name__=='__main__':main()
