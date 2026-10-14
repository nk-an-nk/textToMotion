import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {VRMLoaderPlugin,VRMUtils} from '@pixiv/three-vrm';
import {VRMAnimationLoaderPlugin,createVRMAnimationClip} from '@pixiv/three-vrm-animation';
import {retargetMotion} from './retarget.js';

export function inspectGLB(buffer,extension) {
  if(buffer.byteLength>64*1024*1024||buffer.byteLength<20)throw new Error('GLBの上限は64MiBです。');
  const view=new DataView(buffer);
  if(view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2||view.getUint32(8,true)!==buffer.byteLength||view.getUint32(16,true)!==0x4e4f534a)throw new Error('GLB 2.0形式が必要です。');
  const size=view.getUint32(12,true);if(20+size>buffer.byteLength)throw new Error('GLB JSONが切れています。');
  const json=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,size)));
  if(!json.extensions?.[extension])throw new Error(extension+'の定義がありません。');
  for(const item of [...(json.buffers||[]),...(json.images||[])])if(item.uri&&!item.uri.startsWith('data:'))throw new Error('外部ファイルを参照するモデルは読み込めません。');
  return json;
}

export class VRMAvatarMotionSink {
  constructor(scene) {this.scene=scene;this.vrm=null;this.mode='default';this.defaultEnabled=true;this.speaking=false;this.lip=0;this.elapsed=0;this.blendSeconds=.3;this.manual=false;this.jointWeights={};this.idleRootOffset=new THREE.Vector3();}
  async loadAvatar(buffer) {
    inspectGLB(buffer,'VRMC_vrm');
    const loader=new GLTFLoader();loader.register(parser=>new VRMLoaderPlugin(parser));
    const gltf=await loader.parseAsync(buffer,'');const vrm=gltf.userData.vrm;
    if(!vrm||vrm.meta?.metaVersion!=='1') {VRMUtils.deepDispose(gltf.scene);throw new Error('VRM 1.0アバターを選択してください。');}
    this.dispose();this.vrm=vrm;this.scene.add(vrm.scene);this.mixer=new THREE.AnimationMixer(vrm.scene);
    this.skeleton=new THREE.SkeletonHelper(vrm.scene);this.skeleton.visible=false;this.scene.add(this.skeleton);
    this.rest=new Map();vrm.humanoid.normalizedHumanBones&&Object.entries(vrm.humanoid.normalizedHumanBones).forEach(([name,bone])=>{
      if(bone.node)this.rest.set(name,{node:bone.node,q:bone.node.quaternion.clone(),p:bone.node.position.clone()});
    });
    this.mode='default';this.elapsed=0;this.idleRootOffset.set(0,0,0);this.tick(0);return vrm.meta;
  }
  prepareMotion(data) {
    if(!this.vrm)throw new Error('先にVRMを読み込んでください。');const current=this.capture();
    try {for(const b of this.rest.values()){b.node.quaternion.copy(b.q);b.node.position.copy(b.p);}return retargetMotion(this.vrm,data);}
    finally {for(const [name,b] of this.rest){b.node.quaternion.copy(current.get(name).q);b.node.position.copy(current.get(name).p);}this.vrm.scene.updateMatrixWorld(true);}
  }
  async prepareVRMA(buffer) {
    if(!this.vrm)throw new Error('先にVRMを読み込んでください。');inspectGLB(buffer,'VRMC_vrm_animation');
    const loader=new GLTFLoader();loader.register(parser=>new VRMAnimationLoaderPlugin(parser));
    const gltf=await loader.parseAsync(buffer,'');const animation=gltf.userData.vrmAnimations?.[0];
    if(!animation)throw new Error('VRMAにアニメーションがありません。');return createVRMAnimationClip(animation,this.vrm);
  }
  capture() {return new Map([...this.rest].map(([name,b])=>[name,{q:b.node.quaternion.clone(),p:b.node.position.clone()}]));}
  play(clip,{offline=false,preserveSequence=false}={}) {
    if(!this.vrm)throw new Error('VRMが未設定です。');
    if(!preserveSequence)this.sequence=null;
    this.from=this.capture();this.mixer.stopAllAction();this.action=this.mixer.clipAction(clip);this.action.setLoop(THREE.LoopOnce,1);
    this.action.clampWhenFinished=true;this.action.reset().play();this.clip=clip;this.played=0;this.blended=0;
    const hips=this.rest.get('hips');this.rootAnchor=hips?.node.position.clone();this.rootStart=null;
    this.mode=offline?'offline':'generated';this.offline=offline;this.mixer.update(0);
    this.rootStart=hips?.node.position.clone();
  }
  playSequence(clips) {
    if(!clips.length)throw new Error('再生するモーションがありません。');
    const hips=this.rest.get('hips'),base=hips?.node.position.clone(),offset=new THREE.Vector3(),items=[];
    let start=0;
    for(const clip of clips) {
      items.push({clip,start,anchor:base?.clone().add(offset)});start+=clip.duration;
      const track=clip.tracks.find(track=>track.name.endsWith('.position'));
      if(track)offset.add(new THREE.Vector3().fromArray(track.values,track.values.length-3).sub(new THREE.Vector3().fromArray(track.values,0)));
    }
    this.sequence={items,duration:start,index:-1};return start;
  }
  returnToIdle({immediate=false}={}) {
    if(!this.vrm)return;this.sequence=null;this.from=this.capture();this.mixer.stopAllAction();this.action=null;this.blended=0;
    const hips=this.rest.get('hips');if(hips){this.idleRootOffset.copy(hips.node.position).sub(hips.p);this.idleRootOffset.y=0;}
    this.mode=immediate?'default':'returning';if(immediate)this.tick(0);
  }
  defaultPose() {
    for(const b of this.rest.values()){b.node.quaternion.copy(b.q);b.node.position.copy(b.p);}
    this.rest.get('hips')?.node.position.add(this.idleRootOffset);
    // Lower T-pose arms; no random nodding or head shaking.
    for(const [name,angle] of [['leftUpperArm',-.95],['rightUpperArm',.95]]) {
      const b=this.rest.get(name);if(b)b.node.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),angle));
    }
    if(this.defaultEnabled) {
      const b=this.rest.get('spine');if(b)b.node.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),Math.sin(this.elapsed*1.6)*.012));
      for(const side of ['left','right']) {
        const arm=this.rest.get(side+'LowerArm');if(arm&&this.speaking)arm.node.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),(side==='left'?-.06:.06)*(1+Math.sin(this.elapsed*2.2))));
      }
    }
  }
  blendFrom(alpha) {
    for(const [name,b] of this.rest) {
      const from=this.from?.get(name);if(!from)continue;
      const weight=Math.min(1,Math.max(0,this.jointWeights[name]??1))*alpha;
      b.node.quaternion.copy(from.q.clone().slerp(b.node.quaternion,weight));b.node.position.lerpVectors(from.p,b.node.position.clone(),weight);
    }
  }
  tick(delta,{speaking=this.speaking,lip=this.lip,offlineTime=null}={}) {
    if(!this.vrm)return;this.elapsed+=delta;this.speaking=speaking;this.lip=lip;
    if(this.sequence&&offlineTime!==null) {
      const index=Math.max(0,this.sequence.items.findLastIndex(item=>offlineTime>=item.start)),item=this.sequence.items[index];
      if(index!==this.sequence.index){this.sequence.index=index;this.play(item.clip,{offline:true,preserveSequence:true});if(item.anchor)this.rootAnchor.copy(item.anchor);}
      offlineTime=Math.max(0,offlineTime-item.start);
    }
    if(this.mode==='offline') {if(offlineTime!==null){this.action.time=Math.min(offlineTime,this.clip.duration);this.mixer.update(0);
      const hips=this.rest.get('hips');if(hips&&this.rootStart&&this.rootAnchor)hips.node.position.add(this.rootAnchor.clone().sub(this.rootStart));}}
    else if(this.mode==='generated') {
      this.mixer.update(delta);this.played+=delta;this.blended+=delta;
      const hips=this.rest.get('hips');if(hips&&this.rootStart&&this.rootAnchor)hips.node.position.add(this.rootAnchor.clone().sub(this.rootStart));
      this.blendFrom(Math.min(1,this.blended/this.blendSeconds));
      if(this.played>=this.clip.duration)this.returnToIdle();
    } else {
      this.defaultPose();if(this.mode==='returning') {this.blended+=delta;this.blendFrom(Math.min(1,this.blended/this.blendSeconds));if(this.blended>=this.blendSeconds)this.mode='default';}
    }
    const phase=this.elapsed%4.7,blink=this.defaultEnabled&&phase<.16?Math.sin(phase/.16*Math.PI):0;
    this.vrm.expressionManager?.setValue('blink',blink);this.vrm.expressionManager?.setValue('aa',speaking?Math.min(1,Math.max(0,lip*8)):0);
    this.vrm.update(delta);
  }
  dispose() {if(this.vrm){this.scene.remove(this.vrm.scene);this.mixer?.stopAllAction();VRMUtils.deepDispose(this.vrm.scene);}if(this.skeleton){this.scene.remove(this.skeleton);this.skeleton.geometry.dispose();this.skeleton.material.dispose();}this.vrm=null;this.rest=new Map();}
}

export class RecordedMotionSink {
  constructor(){this.events=[];this.clips=[];}
  play(clip){this.clips.push(THREE.AnimationClip.toJSON(clip));this.events.push({kind:'clip_received',time_ms:performance.now(),clock_domain:'client_performance',clip_index:this.clips.length-1});}
  returnToIdle(){this.events.push({kind:'return_requested',time_ms:performance.now(),clock_domain:'client_performance'});}
  getClips(){return this.clips.map(data=>THREE.AnimationClip.parse(data));}
  serialize(){return {format:'motion-lab/recorded-clips-v1',replay_only:true,events:this.events,clips:this.clips};}
  replayTo(sink){return sink.playSequence(this.getClips());}
}
export class KebbiMotionSink {play(){throw new Error('Kebbi出力は未実装です。関節角・速度・安全制約の検証が必要です。');}returnToIdle(){}}
