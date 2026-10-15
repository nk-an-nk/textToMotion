#!/usr/bin/env python3
"""Real student PCM -> Realtime reply -> already resident remote Kimodo -> received bones."""
import argparse
import base64
import json
import math
from pathlib import Path
import sys
import time
import uuid
from datetime import datetime, timezone
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.measure_audio_dialogue import measure
from scripts.runpod_jupyter import TrialJupyter
from app.realtime import RealtimeConfig
from app.official_schema import normalize_kimodo_online


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--auth', type=Path, required=True)
    p.add_argument('--student-wav', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=['fp32-100','tf32-100','tf32-20'], required=True)
    p.add_argument('--repo', type=Path, required=True)
    a = p.parse_args()
    client = TrialJupyter(a.state, a.auth)
    kernel = client.request('POST', '/api/kernels', {'name':'python3'})['id']
    session = uuid.uuid4().hex
    url = client.base.replace('https:', 'wss:')+'/api/kernels/'+kernel+'/channels?session_id='+session
    try:
        with connect(url, additional_headers={'Authorization':'token '+client.token},
                     origin=client.base, max_size=16*1024*1024, open_timeout=20) as socket:
            def execute(code):
                message_id = uuid.uuid4().hex
                socket.send(json.dumps({'header':{'msg_id':message_id,'username':'motion-lab',
                    'session':session,'date':datetime.now(timezone.utc).isoformat(),
                    'msg_type':'execute_request','version':'5.3'},'parent_header':{},'metadata':{},
                    'channel':'shell','content':{'code':code,'silent':False,'store_history':False,
                    'user_expressions':{},'allow_stdin':False,'stop_on_error':True}}))
                streams = []
                while True:
                    message = json.loads(socket.recv(timeout=90))
                    if message.get('parent_header',{}).get('msg_id') != message_id:
                        continue
                    kind = message.get('msg_type',message.get('header',{}).get('msg_type'))
                    if kind == 'stream': streams.append(message['content']['text'])
                    if kind == 'execute_reply':
                        if message['content']['status'] != 'ok':
                            raise RuntimeError('Resident inference RPC failed: '+message['content'].get('ename','unknown'))
                        return ''.join(streams)
            # Start the bridge kernel before the timed student input; Kimodo is
            # already loaded and warmed in a separate loopback-only service.
            execute('import json,urllib.request\nprint("bridge_ready")')
            base = RealtimeConfig.environment()
            config = RealtimeConfig(api_key=base.api_key, enabled=True, model=base.model,
                                    voice=base.voice, budget_usd=1, max_calls=1, session_seconds=60)
            # response.done has already delivered the complete response. Bound
            # the close handshake so it cannot add the legacy three-second
            # teardown wait before motion dispatch. Legacy callers retain 3 s.
            receipt = measure(a.student_wav,a.output,config,close_timeout=.1)
            anchor = receipt.pop('_student_end_monotonic')
            submitted = time.monotonic()
            request = {'id':'live-'+uuid.uuid4().hex[:12], 'text':receipt['teacher_transcript'],
                       'frames':math.ceil(receipt['teacher_audio_seconds']*30),'mode':a.mode}
            code = ('request='+repr(request)+'\n'
                    'r=urllib.request.Request("http://127.0.0.1:8766/generate",'
                    'data=json.dumps(request,ensure_ascii=False).encode(),'
                    'headers={"Content-Type":"application/json"},method="POST")\n'
                    'with urllib.request.urlopen(r,timeout=80) as response: payload=response.read().decode()\n'
                    'print(payload)\n')
            response = json.loads(execute(code))
            if response['upper_motion']['metadata']['input_text'] != receipt['teacher_transcript']:
                raise ValueError('Generated motion does not match the received teacher transcript.')
            original = base64.b64decode(response['original_base64'],validate=True)
            completed = time.monotonic()
            generation = a.output/'generated/01'
            generation.mkdir(parents=True)
            (generation/'original.npz').write_bytes(original)
            (generation/'upper-motion.json').write_text(json.dumps(response['upper_motion'],ensure_ascii=False)+'\n')
            native = response['receipt']
            metadata = {'fps':30,'frames_requested':request['frames'],'trained_model_output':True,
                        'text_conditioned':True,'input_text':request['text'],'model_id':'kimodo',
                        'checkpoint':'Kimodo-SOMA-RP-v1','backend':'owned_resident_gpu','mode':a.mode}
            normalize_kimodo_online(generation/'original.npz',generation/'motion.json',a.repo,metadata)
            import hashlib
            generation_receipt = {**native,'model':'kimodo','original_text':request['text'],
                'motion_prompt':request['text'],'skeleton_seconds':native['bone_ready_seconds'],
                'motion_sha256':hashlib.sha256((generation/'motion.json').read_bytes()).hexdigest()}
            (generation/'motion-generation.json').write_text(json.dumps(generation_receipt,ensure_ascii=False,indent=2)+'\n')
            receipt.update(model='kimodo',avatar_role='speaker',resident_mode=a.mode,
                gpu_name='B300',realtime_close_timeout_seconds=.1,
                generation_dispatch_seconds_after_student_end=submitted-anchor,
                bone_ready_observed_seconds_after_student_end=completed-anchor,
                generation_command_observed_seconds=completed-submitted,
                completion_poll_interval_seconds=0,motion_generation_seconds=native['bone_ready_seconds'],
                bone_minus_first_realtime_audio_seconds=(completed-anchor)-receipt['first_teacher_audio_seconds_after_student_end'],
                teacher_playback_seconds_after_student_end=max(completed-anchor,receipt['response_done_seconds_after_student_end']),
                playback_policy='buffer_teacher_voice_until_trained_motion_received',
                actual_inference_after_received_teacher_transcript=True,
                measurement_scope='audio_input_to_received_upper_body_skeleton_single_client_monotonic',
                remote_upload_and_startup_included=False,model_was_resident_before_student_input=True,
                input_text_embedding_recomputed=True,inference_backend='runpod_resident',measured_end_to_end=True)
            (a.output/'measurement.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({k:receipt[k] for k in ['resident_mode','first_teacher_audio_seconds_after_student_end',
                'bone_ready_observed_seconds_after_student_end','motion_generation_seconds',
                'bone_minus_first_realtime_audio_seconds']},ensure_ascii=False))
    finally:
        client.request('DELETE','/api/kernels/'+kernel)


if __name__ == '__main__':
    main()
