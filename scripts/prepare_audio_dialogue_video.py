#!/usr/bin/env python3
"""Build an honest replay of measured audio-input response latency."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import wave


def prepare(root,output):
    if output.exists():raise ValueError('Existing videos and assets are preserved.')
    m=json.loads((root/'measurement.json').read_text())
    if not m.get('measured_end_to_end') or m.get('typed_student_input') is not False:
        raise ValueError('Video requires a verified audio-input end-to-end measurement.')
    generation=root/'generated'/'01'
    if not generation.exists():generation=root/'generated/segments/01'
    receipt=json.loads((generation/'motion-generation.json').read_text())
    scope='head_only' if m['model']=='maai' else 'full_body'
    filename='head-controls.json' if scope=='head_only' else 'motion.json'
    motion=json.loads((generation/filename).read_text())
    if hashlib.sha256((generation/filename).read_bytes()).hexdigest()!=receipt['motion_sha256']:
        raise ValueError('Motion provenance hash differs.')
    if (motion.get('trained_model_output') if scope=='head_only' else motion.get('metadata',{}).get('trained_model_output')) is not True:
        raise ValueError('Pretrained output is required.')
    output.mkdir(parents=True)
    for name in ['student.wav','teacher.wav','measurement.json']:shutil.copy(root/name,output/name)
    for name in [filename,'motion-generation.json']:shutil.copy(generation/name,output/name)
    fps=30;teacher_start=math.ceil((m['student_audio_seconds']+m['teacher_playback_seconds_after_student_end'])*fps)/fps
    frames=math.ceil((teacher_start+m['teacher_audio_seconds']+.5)*fps)
    plan={'schema':'motion-lab/audio-dialogue-video-plan-v1','model':m['model'],'fps':fps,'frame_count':frames,
        'duration_seconds':frames/fps,'student_audio_seconds':m['student_audio_seconds'],'teacher_start_seconds':teacher_start,
        'teacher_audio_seconds':m['teacher_audio_seconds'],'student_text':m['student_transcript'],'teacher_text':m['teacher_transcript'],
        'measurement':m,'motion_file':filename,'motion_scope':scope,'avatar_role':m['avatar_role'],
        'motion_sha256':receipt['motion_sha256'],'speech_and_gesture_start_policy':'same_frame_when_buffered_teacher_starts',
        'caption':'音声入力からの実測を再生 / ライブ録画ではありません',
        'body_pose':'avatar_default_pose' if scope=='head_only' else 'pretrained_full_body_joints'}
    with wave.open(str(output/'timeline.wav'),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000)
        with wave.open(str(root/'student.wav'),'rb') as src:pcm=src.readframes(src.getnframes())
        with wave.open(str(root/'teacher.wav'),'rb') as src:teacher=src.readframes(src.getnframes())
        start=round(teacher_start*24000);count=frames*800
        wav.writeframes(pcm+b'\0\0'*(start-len(pcm)//2)+teacher+b'\0\0'*(count-start-len(teacher)//2))
    (output/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();d=prepare(a.root,a.output);print(json.dumps({'model':d['model'],'frames':d['frame_count'],'plan':str(a.output/'plan.json')}))
