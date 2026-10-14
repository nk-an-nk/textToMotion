import * as THREE from 'three';
import {jointMap} from './retarget.js';

// A presentation transform only. The original learned positions are never mutated.
export function faceFrontMotion(motion) {
  const map=jointMap(motion),top=map.chest??map.spine;
  if([map.hips,map.leftUpperLeg,map.rightUpperLeg,top].some(i=>i===undefined))throw new Error('A torso and hip pair are required to face the avatar forward.');
  const anchor=new THREE.Vector3(...motion.positions[0][map.hips]);
  const positions=motion.positions.map(frame=>{
    const hip=new THREE.Vector3(...frame[map.hips]);
    const across=new THREE.Vector3(...frame[map.leftUpperLeg]).sub(new THREE.Vector3(...frame[map.rightUpperLeg]));
    const up=new THREE.Vector3(...frame[top]).sub(hip),forward=across.cross(up);
    if(forward.x**2+forward.z**2<1e-12)throw new Error('Torso heading is degenerate.');
    const rotation=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),-Math.atan2(forward.x,forward.z));
    return frame.map(point=>new THREE.Vector3(...point).sub(hip).applyQuaternion(rotation).add(anchor).toArray());
  });
  return {...motion,positions,metadata:{...motion.metadata,presentation_transform:'per-frame torso yaw removed; root anchored; original source file preserved'}};
}
