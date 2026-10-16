#!/usr/bin/env python3
"""Actual PCM -> Realtime -> an already resident masked model -> received bones."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
from websockets.sync.client import connect

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.realtime import RealtimeConfig
from scripts.measure_audio_dialogue import measure
from scripts.runpod_jupyter import TrialJupyter
from scripts.benchmark_masked_models import frames_for
from scripts.llm_translate_motion import translate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,required=True);p.add_argument('--auth',type=Path,required=True)
    p.add_argument('--student-wav',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',choices=['molingo','remomask2','momask'],required=True)
    p.add_argument('--profile',choices=['lab_proxy','b300'],required=True)
    a=p.parse_args();client=TrialJupyter(a.state,a.auth)
    kernel=client.request('POST','/api/kernels',{'name':'python3'})['id'];session=uuid.uuid4().hex
    url=client.base.replace('https:','wss:')+'/api/kernels/'+kernel+'/channels?session_id='+session
    try:
        with connect(url,additional_headers={'Authorization':'token '+client.token},origin=client.base,
                     max_size=16*1024*1024,open_timeout=20) as socket:
            def execute(code):
                mid=uuid.uuid4().hex
                socket.send(json.dumps({'header':{'msg_id':mid,'username':'motion-lab','session':session,
                    'date':datetime.now(timezone.utc).isoformat(),'msg_type':'execute_request','version':'5.3'},
                    'parent_header':{},'metadata':{},'channel':'shell','content':{'code':code,'silent':False,
                    'store_history':False,'user_expressions':{},'allow_stdin':False,'stop_on_error':True}}))
                output=[]
                while True:
                    msg=json.loads(socket.recv(timeout=120))
                    if msg.get('parent_header',{}).get('msg_id')!=mid:continue
                    kind=msg.get('msg_type',msg.get('header',{}).get('msg_type'))
                    if kind=='stream':output.append(msg['content']['text'])
                    if kind=='execute_reply':
                        if msg['content']['status']!='ok':raise RuntimeError('Resident RPC failed: '+msg['content'].get('ename','unknown'))
                        return ''.join(output)
            ready=json.loads(execute('import json,urllib.request\nprint(urllib.request.urlopen("http://127.0.0.1:8766/health").read().decode())'))
            if ready.get('model')!=a.model or ready.get('profile')!=a.profile:raise RuntimeError('Incorrect resident model/profile.')
            base=RealtimeConfig.environment()
            config=RealtimeConfig(api_key=base.api_key,enabled=True,model=base.model,voice=base.voice,
                                  budget_usd=1,max_calls=1,session_seconds=60)
            receipt=measure(a.student_wav,a.output,config,close_timeout=.1)
            anchor=receipt.pop('_student_end_monotonic')
            translation=translate(receipt['teacher_transcript'])
            (a.output/'translation.json').write_text(json.dumps(translation,ensure_ascii=False,indent=2)+'\n')
            sent=time.monotonic()
            request={'id':uuid.uuid4().hex,'text':translation['english'],'original_text':receipt['teacher_transcript'],
                     'frames':frames_for(receipt['teacher_audio_seconds']),'seed':0}
            code=('request='+repr(request)+'\n'
                  'r=urllib.request.Request("http://127.0.0.1:8766/generate",data=json.dumps(request,ensure_ascii=False).encode(),headers={"Content-Type":"application/json"},method="POST")\n'
                  'with urllib.request.urlopen(r,timeout=110) as result: payload=result.read().decode()\nprint(payload)')
            result=json.loads(execute(code));received=time.monotonic()
            native=result['receipt'];motion=result['motion']
            if native['model']!=a.model or native['profile']!=a.profile or motion['metadata']['input_text']!=translation['english'] or native['original_text']!=receipt['teacher_transcript']:
                raise RuntimeError('Received bones do not match the actual teacher transcript.')
            encoded=json.dumps(motion,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
            if hashlib.sha256(encoded).hexdigest()!=native['motion_sha256']:raise RuntimeError('Received skeleton checksum mismatch.')
            dest=a.output/'generated/01';dest.mkdir(parents=True)
            (dest/'motion.json').write_bytes(encoded)
            (dest/'motion-generation.json').write_text(json.dumps(native,ensure_ascii=False,indent=2)+'\n')
            receipt.update(model=a.model,profile=a.profile,avatar_role='speaker',gpu_name=native['gpu_name'],
                resident_mode='FP32 / '+a.profile,realtime_close_timeout_seconds=.1,
                generation_dispatch_seconds_after_student_end=sent-anchor,
                bone_ready_observed_seconds_after_student_end=received-anchor,
                generation_command_observed_seconds=received-sent,completion_poll_interval_seconds=0,
                motion_generation_seconds=native['bone_ready_seconds'],
                bone_minus_first_realtime_audio_seconds=received-anchor-receipt['first_teacher_audio_seconds_after_student_end'],
                teacher_playback_seconds_after_student_end=max(received-anchor,receipt['response_done_seconds_after_student_end']),
                playback_policy='buffer_teacher_voice_until_trained_motion_received',
                actual_inference_after_received_teacher_transcript=True,remote_upload_and_startup_included=False,
                input_translation=True,translated_motion_prompt=translation['english'],translation_model=translation['model'],
                translation_seconds=translation['translation_seconds'],translation_included_in_end_to_end=True,
                model_was_resident_before_student_input=True,input_text_embedding_recomputed=True,
                inference_backend='runpod_resident',measured_end_to_end=True,
                timing_scope='one client monotonic clock; audio input to received decoded skeleton')
            (a.output/'measurement.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({k:receipt[k] for k in ['model','profile','motion_generation_seconds',
                'bone_ready_observed_seconds_after_student_end','bone_minus_first_realtime_audio_seconds']},ensure_ascii=False))
    finally:client.request('DELETE','/api/kernels/'+kernel)


if __name__=='__main__':main()
