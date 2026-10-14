import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {validateTimeline}=createRequire(import.meta.url)('../../scripts/segmented_video_plan.cjs');
const plan=()=>({schema:'motion-lab/segmented-dialogue-v1',status:'generated',fps:30,new_motion_inference:true,blend_ms:250,frame_count:90,duration_seconds:3,
 segments:[{id:'01',frame_count:30,start_frame:0,end_frame:30,speech_start_frame:0,gesture_start_frame:0,audio_seconds:.99,motion_seconds:2,new_gesture_generated:true},
 {id:'02',frame_count:60,start_frame:30,end_frame:90,speech_start_frame:30,gesture_start_frame:30,audio_seconds:1.98,motion_seconds:2,new_gesture_generated:true}]});
test('native model minimum may be retimed while speech starts on its exact frame',()=>{assert.equal(validateTimeline(plan()),90);});
test('a one-frame speech/gesture offset is rejected',()=>{const p=plan();p.segments[1].speech_start_frame++;assert.throws(()=>validateTimeline(p),/same contiguous frame/);});
test('a gap, overlap, truncated speech or incomplete generation cannot export',()=>{
 for(const edit of [p=>p.segments[1].start_frame++,p=>p.segments[0].audio_seconds=1.01,p=>p.status='partial',p=>p.segments[1].new_gesture_generated=false,p=>p.frame_count--]){
  const p=plan();edit(p);assert.throws(()=>validateTimeline(p));
 }
});
