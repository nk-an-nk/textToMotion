#!/usr/bin/env python3
"""Real local model smoke and MP4, executed in the application venv; no fixtures."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=['kimodo','ardy','text_to_vrma'],required=True)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    args=parser.parse_args()
    from adapters.registry import adapters
    from adapters.base import MotionInput
    from app.jobs import JobStore,write_json
    adapter=adapters(args.data_dir)[args.model]
    # Assets are already downloaded and hashed. Enable preflight only in this test
    # process; persistent readiness is written by setup only after a real result.
    adapter.config.update(checkpoint_cached=True,text_encoder_cached=True,require_cuda=True,
                          backend='local',text_encoder_device='cpu',engine='ardy',enabled=True)
    store=JobStore(args.data_dir/'outputs',{args.model:adapter})
    try:
        prompt='Raise your right hand and wave for three seconds.' if args.model=='kimodo' else 'Hello.'
        original=prompt if args.model=='kimodo' else 'こんにちは'
        record=store.create(MotionInput('instruction',prompt,None,3,0,args.model,original),
                            {'verification':'local CUDA setup smoke; actual pretrained inference'})
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            record=store.get(record['id'])
            if record['status'] not in ('queued','running'):
                break
            time.sleep(.25)
        if record['status']!='succeeded' or record.get('device')!='cuda':
            raise RuntimeError('Local CUDA generation failed: '+json.dumps(record,ensure_ascii=False))
        video=store.render(record['id'])
        record=store.get(record['id'])
        from app.motion import read_motion
        motion=read_motion(store.output_dir/record['id']/'motion.json')
        if not motion.get('metadata',{}).get('trained_model_output'):
            raise RuntimeError('Result was not marked as official trained model output.')
        result={'model':args.model,'status':'succeeded','experiment_id':record['id'],
                'device':'cuda','text_encoder_device':'cpu','input_text':original,'model_text':prompt,
                'video':str(video),'inference_time':record['inference_time'],
                'time_to_first_result':record['time_to_first_result'],
                'frames':len(motion['positions']),'fps':motion['fps'],'timings':record['timings']}
        args.result.parent.mkdir(parents=True,exist_ok=True)
        write_json(args.result,result)
        print(json.dumps(result,ensure_ascii=False))
        print(f"{args.model}: 骨格まで {record['timings']['skeleton_seconds']:.2f}秒 / "
              f"MP4まで {record['timings']['total_seconds']:.2f}秒")
    finally:
        store.close()


if __name__=='__main__':
    main()
