import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {RecordedMotionSink,KebbiMotionSink} from '../../app/ui/motion-sink.js';
test('recorded output can replay complete tracks; unimplemented Kebbi refuses commands',()=>{
  const original=new THREE.AnimationClip('wave',1,[new THREE.QuaternionKeyframeTrack('rightArm.quaternion',[0,1],[0,0,0,1,0,0,.6,.8])]);
  const sink=new RecordedMotionSink();sink.play(original);sink.returnToIdle();original.tracks[0].values[0]=100;
  const decoded=JSON.parse(JSON.stringify(sink.serialize()));assert.equal(decoded.replay_only,true);
  const replayed=[];sink.replayTo({playSequence:clips=>replayed.push(...clips)});assert.equal(replayed[0].tracks[0].values[0],0);assert.equal(replayed[0].duration,1);
  assert.throws(()=>new KebbiMotionSink().play(original),/未実装/);
});
