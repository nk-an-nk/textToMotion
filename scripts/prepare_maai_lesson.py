#!/usr/bin/env python3
"""Combine real MaAI head predictions and common speech, with no fabricated full-body joints."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import wave


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['motion-root','speech-root','config','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Existing head predictions are preserved.')
    plan=json.loads(a.config.read_text());predictions=[];pcm=bytearray();cursor=0;units=[];receipts=[]
    for u in plan['segments']:
        controls=json.loads((a.motion_root/u['id']/'head-controls.json').read_text());r=json.loads((a.motion_root/u['id']/'motion-generation.json').read_text())
        if controls['input_text']!=u['text'] or not controls['trained_model_output']:raise ValueError('MaAI text or model provenance mismatch.')
        wavpath=a.speech_root/u['id']/'voice.wav'
        if hashlib.sha256(wavpath.read_bytes()).hexdigest()!=controls['input_audio_sha256']:raise ValueError('MaAI did not receive the shared real audio.')
        with wave.open(str(wavpath),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,24000):raise ValueError('Wrong speech format.')
            samples=wav.getnframes();audio=wav.readframes(samples)
        frames=math.ceil(samples/800);pcm.extend(audio+b'\0\0'*(frames*800-samples))
        units.append({**u,'start_seconds':cursor/30,'end_seconds':(cursor+frames)/30})
        for pred in controls['predictions']:
            predictions.append({k:v for k,v in pred.items() if k.startswith('nod_') or k=='p_nod'}|{'input_audio_seconds':cursor/30+pred['input_audio_seconds']})
        cursor+=frames;receipts.append(r)
    a.output.mkdir(parents=True)
    controls={'schema':'motion-lab/maai-head-controls-v1','trained_model_output':True,'model':'maai',
              'predictions':predictions,'source_segments':receipts,'body_pose':'avatar_default_not_learned'}
    file=a.output/'head-controls.json';file.write_text(json.dumps(controls,ensure_ascii=False,indent=2)+'\n')
    for name in ['teacher.wav','timeline.wav']:
        with wave.open(str(a.output/name),'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(pcm)
    result={'schema':'motion-lab/listener-lesson-video-plan-v1','model':'maai','fps':30,'frame_count':cursor,
            'duration_seconds':cursor/30,'student_audio_seconds':0,'teacher_start_seconds':0,'teacher_audio_seconds':cursor/30,
            'student_text':'','teacher_text':'','lesson_segments':units,'motion_scope':'head_only','avatar_role':'listener',
            'motion_file':'head-controls.json','motion_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
            'measurement':{},'caption':'同一5文の実音声→MaAI頭部予測 / 全身はアバターの基本姿勢'}
    (a.output/'plan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
