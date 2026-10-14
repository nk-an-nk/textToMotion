import * as THREE from 'three';

const key = value => value.toLowerCase().replace(/[^a-z0-9]/g, '').replace(/^mixamorig/, '');
export function jointMap(motion) {
  const names=new Map(motion.joint_names.map((name,i)=>[key(name),i]));
  const find=(...aliases)=>aliases.map(key).map(name=>names.get(name)).find(i=>i!==undefined);
  const map={hips:find('hips','pelvis','root'),spine:find('spine','spine1'),chest:find('chest','spine2'),
    upperChest:find('upperChest','spine3'),neck:find('neck','neck1'),head:find('head')};
  for(const side of ['left','right']) {
    map[side+'Shoulder']=find(side+'Shoulder');
    map[side+'UpperArm']=find(side+'UpperArm',side+'Arm',side+'Shoulder');
    map[side+'LowerArm']=find(side+'LowerArm',side+'ForeArm',side+'Elbow');
    map[side+'Hand']=find(side+'Hand',side+'Wrist');
    const hasUp=names.has(key(side+'UpLeg'));
    map[side+'UpperLeg']=find(side+'UpperLeg',side+'UpLeg',side+'Hip',...(!hasUp?[side+'Leg']:[]));
    map[side+'LowerLeg']=find(side+'LowerLeg',side+'Shin',side+'Knee',...(hasUp?[side+'Leg']:[]));
    map[side+'Foot']=find(side+'Foot',side+'Ankle');map[side+'Toes']=find(side+'Toes',side+'ToeBase');
  }
  return Object.fromEntries(Object.entries(map).filter(([,i])=>i!==undefined));
}

const CHILDREN={hips:'spine',spine:'chest',chest:'neck',upperChest:'neck',neck:'head',
  leftShoulder:'leftUpperArm',leftUpperArm:'leftLowerArm',leftLowerArm:'leftHand',leftFoot:'leftToes',
  rightShoulder:'rightUpperArm',rightUpperArm:'rightLowerArm',rightLowerArm:'rightHand',rightFoot:'rightToes',
  leftUpperLeg:'leftLowerLeg',leftLowerLeg:'leftFoot',rightUpperLeg:'rightLowerLeg',rightLowerLeg:'rightFoot'};

function bodyFrame(points,map) {
  const hips=points[map.hips],top=points[map.chest??map.spine];
  const l=points[map.leftUpperLeg],r=points[map.rightUpperLeg];
  if(!hips||!top||!l||!r)throw new Error('胴体と左右の脚の定義が必要です。');
  const y=top.clone().sub(hips).normalize(),x=l.clone().sub(r).normalize(),z=x.clone().cross(y).normalize();
  if(z.lengthSq()<.5)throw new Error('胴体の向きを推定できません。');
  x.copy(y).cross(z).normalize();
  return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x,y,z));
}

export function retargetMotion(vrm,motion) {
  if(!motion?.positions?.length||motion.positions.length>3600||motion.joint_names.length>200||!(motion.fps>0&&motion.fps<=240))
    throw new Error('モーション形式・サイズ・FPSが無効です。');
  const map=jointMap(motion);
  for(const name of ['hips','spine','leftUpperArm','leftLowerArm','rightUpperArm','rightLowerArm','leftUpperLeg','leftLowerLeg','rightUpperLeg','rightLowerLeg','leftFoot','rightFoot'])
    if(map[name]===undefined)throw new Error('対応できない骨格: '+name);
  const nodes=Object.fromEntries(Object.keys(CHILDREN).concat('head','leftHand','rightHand','leftToes','rightToes')
    .map(name=>[name,vrm.humanoid.getNormalizedBoneNode(name)]).filter(([,node])=>node));
  const rest=new Map(Object.entries(nodes).map(([name,node])=>[name,{node,q:node.quaternion.clone(),p:node.position.clone()}]));
  vrm.scene.updateMatrixWorld(true);
  const targetPoints={},targetMap={};
  for(const [name,node] of Object.entries(nodes)) {targetMap[name]=Object.keys(targetPoints).length;targetPoints[targetMap[name]]=node.getWorldPosition(new THREE.Vector3());}
  const targetFrame=bodyFrame(targetPoints,targetMap);
  const restWorld=new Map(Object.entries(nodes).map(([name,node])=>[name,node.getWorldQuaternion(new THREE.Quaternion())]));
  const lengths=(points,m)=>['left','right'].map(side=>points[m[side+'UpperLeg']].distanceTo(points[m[side+'LowerLeg']])+points[m[side+'LowerLeg']].distanceTo(points[m[side+'Foot']])).reduce((a,b)=>a+b)/2;
  const pointsOf=frame=>frame.map(p=>{
    if(!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite))throw new Error('非有限な関節位置です。');
    return new THREE.Vector3(...p);
  });
  const first=pointsOf(motion.positions[0]),sourceLength=lengths(first,map);
  if(sourceLength<.05)throw new Error('脚の寸法を推定できません。');
  const scale=lengths(targetPoints,targetMap)/sourceLength;
  const order=[];vrm.scene.traverse(node=>{const item=Object.entries(nodes).find(([,n])=>n===node);if(item)order.push(item[0]);});
  const values=new Map(order.map(name=>[name,[]])),rootValues=[],times=[];
  const hips=nodes.hips;
  try {
    for(let f=0;f<motion.positions.length;f++) {
      const frame=motion.positions[f];if(frame.length!==motion.joint_names.length)throw new Error('フレームの関節数が一致しません。');
      const points=pointsOf(frame),frameQ=bodyFrame(points,map);
      for(const saved of rest.values()){saved.node.quaternion.copy(saved.q);saved.node.position.copy(saved.p);}
      for(const name of order) {
        const node=nodes[name],child=CHILDREN[name];let world;
        if(name==='hips')world=frameQ.clone().multiply(targetFrame.clone().invert()).multiply(restWorld.get(name));
        else if(child&&map[name]!==undefined&&map[child]!==undefined&&map[name]!==map[child]&&nodes[child]) {
          const from=targetPoints[targetMap[child]].clone().sub(targetPoints[targetMap[name]]);
          const to=points[map[child]].clone().sub(points[map[name]]);
          if(from.lengthSq()<1e-10||to.lengthSq()<1e-10)continue;
          world=new THREE.Quaternion().setFromUnitVectors(from.normalize(),to.normalize()).multiply(restWorld.get(name));
        } else continue; // Positions cannot identify wrist/head twist; retain rest rotation.
        const parent=node.parent.getWorldQuaternion(new THREE.Quaternion());
        node.quaternion.copy(parent.invert().multiply(world)).normalize();
      }
      hips.position.copy(rest.get('hips').p).add(points[map.hips].clone().sub(first[map.hips]).multiplyScalar(scale));
      const ground=Math.min(nodes.leftFoot.getWorldPosition(new THREE.Vector3()).y,nodes.rightFoot.getWorldPosition(new THREE.Vector3()).y);
      if(ground<0)hips.position.y-=ground; // Approximate floor clamp, not contact-aware IK.
      times.push(f/motion.fps);rootValues.push(...hips.position.toArray());
      for(const name of order) {
        const q=nodes[name].quaternion.clone(),track=values.get(name);
        if(track.length&&new THREE.Quaternion().fromArray(track,track.length-4).dot(q)<0)q.set(-q.x,-q.y,-q.z,-q.w);
        track.push(...q.toArray());
      }
    }
  } finally {for(const saved of rest.values()){saved.node.quaternion.copy(saved.q);saved.node.position.copy(saved.p);}vrm.scene.updateMatrixWorld(true);}
  const tracks=order.map(name=>new THREE.QuaternionKeyframeTrack(nodes[name].uuid+'.quaternion',times,values.get(name)));
  tracks.push(new THREE.VectorKeyframeTrack(hips.uuid+'.position',times,rootValues));
  const clip=new THREE.AnimationClip('motion-lab-retarget',motion.positions.length/motion.fps,tracks);
  clip.userData={method:'body-frame plus minimum-swing; no inferred axial twist',sourceJointMap:map,
    scale,floorCorrection:'approximate clamp; foot sliding remains possible',trainedModelOutput:motion.metadata?.trained_model_output??null};
  return clip;
}
