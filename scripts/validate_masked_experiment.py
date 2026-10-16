#!/usr/bin/env python3
"""Validate the delivered comparison's learned outputs, input provenance and videos."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import wave


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def require(value,message):
    if not value:raise ValueError(message)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('reports/masked-models-20261016'));a=p.parse_args();root=a.root
    plan=read(Path('configs/masked_comparison_20261016.json'));expected={u['id']:u for u in plan['segments']}
    count=0;voices={};students=set();responses=set();clips=0;videos=0
    for profile in ['lab_proxy','b300']:
        for model in ['molingo','remomask2','momask']:
            case=root/profile/'native'/model;trials=read(case/'measurements.json');hardware=read(case/'hardware.json')
            require({(x['id'],x['repeat']) for x in trials}=={(i,n) for i in expected for n in range(3)},'Missing or duplicate measured trials')
            require(hardware['cpu_threads']==8 and hardware['cpu_affinity_count']==8,'CPU inference limits differ')
            require(hardware['torch_allocator_limit_mib']==(12227 if profile=='lab_proxy' else None),'VRAM profile differs')
            for row in trials:
                u=expected[row['id']];folder=case/u['id'] if row['repeat']==0 else case/'repeats'/u['id']/str(row['repeat'])
                motion=read(folder/'motion.json')
                require(digest(folder/'motion.json')==row['motion_sha256'],'Native skeleton checksum mismatch')
                require(row['motion_prompt']==u['motion_prompt'] and row['original_text']==u['text'],'Common model input differs')
                require(motion['metadata']['trained_model_output'] is True,'Learned output flag missing')
                require(len(motion['joint_names'])==22 and len(motion['positions'])==row['native_frames'] and motion['fps']==20,'Native skeleton shape differs')
                require(all(len(frame)==22 and all(len(point)==3 and all(math.isfinite(v) for v in point) for point in frame) for frame in motion['positions']),'Invalid native coordinates')
                require(row['skeleton_seconds']>0 and not row['input_truncation'],'Missing timing or truncated input')
                if model=='molingo':require(row['unknown_token_count']==0,'Unknown T5 token remains')
                count+=1
            dialogue=root/profile/'dialogue'/model;m=read(dialogue/'measurement.json');t=read(dialogue/'translation.json');native=read(dialogue/'generated/01/motion-generation.json')
            require(m['typed_student_input'] is False and m['measured_end_to_end'] and m['model_was_resident_before_student_input'],'Conversation is not measured audio input')
            require(m['teacher_transcript']=='こんにちは！今日も元気そうだね！英会話の練習を始めましょう','Actual teacher reply differs')
            require(t['llm_generated'] and t['source_text']==m['teacher_transcript'] and t['english']==native['motion_prompt'],'Live translation differs from actual inference input')
            require(native['original_text']==m['teacher_transcript'] and native['model']==model and native['profile']==profile,'Wrong live model/input')
            require(digest(dialogue/'generated/01/motion.json')==native['motion_sha256'],'Live skeleton checksum mismatch')
            require(m['generation_command_observed_seconds']>=m['motion_generation_seconds'],'Native generation exceeds observed command duration')
            require(abs(m['bone_minus_first_realtime_audio_seconds']-(m['bone_ready_observed_seconds_after_student_end']-m['first_teacher_audio_seconds_after_student_end']))<1e-6,'Realtime gap differs')
            require(m['translation_included_in_end_to_end'] and m['translation_seconds']>0,'Translation timing missing')
            students.add(digest(dialogue/'student.wav'));responses.add(m['response_id'])
            for kind in ['common','dialogue']:
                folder=root/profile/(kind+'-video')/model;video=folder/('combined.mp4' if kind=='common' else 'dialogue.mp4');v=read(video.with_suffix('.json'))
                require(digest(video)==v['video_sha256'] and not v['browser_errors'],'Video checksum/browser errors')
                if kind=='common':
                    manifest=read(folder/'manifest.json');require(len(manifest['segments'])==5,'Missing segment')
                    require(v['capture']['upper_body_only'] and v['capture']['lower_body']['maxRawRotationError']<1e-5,'Rendered lower body not fixed')
                    require(v['capture']['camera']['front_alignment']>.99,'Camera is not frontal')
                    require(len(v['segment_videos'])==5 and v['skipped_render_frames']==0,'Missing segment video/frame')
                    for unit in manifest['segments']:
                        i=unit['id'];base=folder/'segments'/i;sha=digest(base/'voice.wav');voices.setdefault(i,set()).add(sha)
                        require(unit['speech_start_frame']==unit['gesture_start_frame']==unit['start_frame'],'Segment speech/gesture offset')
                        require(digest(base/'motion.json')==unit['motion_sha256'],'Retarget source hash differs')
                        require((base/'video.mp4').exists(),'Missing single-segment MP4');clips+=1
                else:
                    require(v['upper_body_only'] and v['stats']['maxRawLowerBodyRotationError']<1e-5 and v['setup']['front_alignment']>.99,'Wrong conversation presentation')
                    require(v['audio_gesture_start_offset_seconds']==0 and v['waiting_duration_compressed'] is False and v['live_recording'] is False,'Conversation replay timing differs')
                videos+=1
    require(len(students)==1 and len(responses)==6,'Student input was not shared or Realtime reply was reused')
    require(all(len(values)==1 for values in voices.values()) and len(voices)==5,'Common speech differs across conditions')
    result={'schema':'motion-lab/masked-experiment-validation-v1','status':'passed','measured_native_trials':count,'fresh_audio_dialogues':len(responses),'main_videos':videos,'single_segment_videos':clips,'llm_english_input_verified':True,'moLingo_unknown_tokens':0,'actual_rtx5070_measured':False,'quality_score_measured':False}
    (root/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
