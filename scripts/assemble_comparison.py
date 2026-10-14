#!/usr/bin/env python3
"""Combine verified trained joints with identical real speech; preserve all source artifacts."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.segmented_dialogue import assemble_audio, digest, write_json, speech_info
from app.motion import read_motion


def assemble(config, motion_root, speech_root, output, model, listener=False):
    if output.exists():
        raise ValueError('Existing render assets are preserved. Choose a new output directory.')
    plan = json.loads(config.read_text())
    for unit in plan['segments']:
        if unit['motion_prompt'] != unit['text']:
            raise ValueError('Comparison input must be the literal utterance for every model.')
    output.mkdir(parents=True)
    manifest = {'schema':'motion-lab/segmented-dialogue-v1','status':'generated','model':model,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'title':plan['title']+' / 同一入力比較',
        'plan_sha256':hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'fps':30,'blend_ms':250,'new_motion_inference':True,'audio_conditioned_model':False,
        'avatar_role':'listener' if listener else 'speaker','speech_reused':True,
        'speech_and_gesture_start_policy':'same_frame_per_segment','segments':[]}
    cursor = 0
    for unit in plan['segments']:
        source = motion_root/unit['id']; voice = speech_root/unit['id']
        receipt = json.loads((source/'motion-generation.json').read_text())
        speech = json.loads((voice/'voice.json').read_text())
        if receipt['original_text'] != unit['text'] or receipt['motion_prompt'] != unit['text'] or speech['requested_text'] != unit['text']:
            raise ValueError('The generated motion and speech have different input text.')
        motion = read_motion(source/'motion.json')
        if motion.get('metadata',{}).get('trained_model_output') is not True or receipt['motion_sha256'] != digest(source/'motion.json'):
            raise ValueError('New trained motion provenance was not verified.')
        folder = output/'segments'/unit['id']; folder.mkdir(parents=True)
        for name in ['motion.json','motion-generation.json']:
            shutil.copyfile(source/name, folder/name)
        for name in ['voice.wav','voice.json']:
            shutil.copyfile(voice/name, folder/name)
        if speech['audio_sha256'] != digest(folder/'voice.wav'):
            raise ValueError('Real speech checksum mismatch.')
        seconds = speech_info(folder/'voice.wav')['duration']; frames = math.ceil(seconds*30)
        native_seconds = len(motion['positions'])/motion['fps']
        prefix = 'segments/'+unit['id']+'/'
        manifest['segments'].append({**unit, 'motion':prefix+'motion.json','motion_receipt':prefix+'motion-generation.json',
            'audio':prefix+'voice.wav','speech_metadata':prefix+'voice.json',
            'motion_sha256':receipt['motion_sha256'],'audio_sha256':speech['audio_sha256'],
            'audio_seconds':seconds,'motion_seconds':native_seconds,'frame_count':frames,
            'start_frame':cursor,'end_frame':cursor+frames,'speech_start_frame':cursor,'gesture_start_frame':cursor,
            'start_seconds':cursor/30,'end_seconds':(cursor+frames)/30,'playback_seconds':frames/30,
            'playback_speed':native_seconds/(frames/30),'speech_generation_seconds':0,
            'speech_original_generation_seconds':speech['generation_wall_seconds'],
            'skeleton_seconds':receipt['skeleton_seconds'],'input_to_skeleton_seconds':receipt['input_to_skeleton_seconds'],
            'input_submitted_at_utc':receipt['input_submitted_at_utc'],
            'skeleton_completed_at_utc':receipt['skeleton_completed_at_utc'],
            'new_gesture_generated':True,'seed':receipt['seed']})
        cursor += frames
    manifest.update(frame_count=cursor,duration_seconds=cursor/30,timeline_audio='timeline.wav')
    audio = assemble_audio(manifest, output)
    manifest['timeline_audio_sha256'] = digest(audio)
    write_json(output/'plan.json', plan); write_json(output/'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('configs/segmented_english_lesson_common.json'))
    parser.add_argument('--motion-root',type=Path,required=True)
    parser.add_argument('--speech-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--listener',action='store_true')
    args = parser.parse_args()
    result = assemble(args.config,args.motion_root,args.speech_root,args.output,args.model,args.listener)
    print(json.dumps({'manifest':str(args.output/'manifest.json'),'frames':result['frame_count']}))
