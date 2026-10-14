import test from 'node:test';
import assert from 'node:assert/strict';
import {faceFrontMotion} from '../../app/ui/presentation-motion.js';

test('front presentation removes a quarter turn without changing source joints or limb distances',()=>{
 const source={joint_names:['hips','spine','leftUpperLeg','rightUpperLeg','head'],
  positions:[[[2,1,3],[2,1.5,3],[2.2,1,3],[1.8,1,3],[2,1.8,3]],
             [[4,1,5],[4,1.5,5],[4,1,4.8],[4,1,5.2],[4,1.8,5]]],metadata:{trained_model_output:false,source:'authored_geometry_fixture'}};
 const original=JSON.stringify(source),result=faceFrontMotion(source);
 assert.equal(JSON.stringify(source),original);
 for(const frame of result.positions){
  assert.deepEqual(frame[0],source.positions[0][0]);
  assert.ok(Math.abs(frame[2][0]-2.2)<1e-10&&Math.abs(frame[2][2]-3)<1e-10);
  assert.ok(Math.abs(frame[3][0]-1.8)<1e-10&&Math.abs(frame[3][2]-3)<1e-10);
  assert.ok(Math.abs(Math.hypot(...frame[4].map((v,i)=>v-frame[0][i]))-.8)<1e-10);
 }
 assert.equal(result.metadata.trained_model_output,false);
});
