import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {VRMAvatarMotionSink} from './motion-sink.js';

const COLORS = [0x138b7a,0xe68554,0x5578b5,0xa26ca9,0xa8a033,0x916e56,0x447e9d,0xb3586b,0x527e42];

export class MotionViewer {
  constructor(container) {
    this.container=container; this.actors=[]; this.avatar=false;
    this.scene=new THREE.Scene(); this.scene.background=new THREE.Color(0xedf1ed);
    this.vrmSink=new VRMAvatarMotionSink(this.scene);this.lastDraw=performance.now();
    this.camera=new THREE.PerspectiveCamera(38,1,.01,200);
    this.camera.position.set(3.5,2.3,5.2);
    this.renderer=new THREE.WebGLRenderer({antialias:true});
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=.9;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
    container.appendChild(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.target.set(0,1,0);this.controls.enableDamping=true;
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x819387,2.5));
    const light=new THREE.DirectionalLight(0xffffff,2.5);light.position.set(3,5,3);this.scene.add(light);
    this.scene.add(new THREE.GridHelper(24,48,0xa6bcb0,0xd2ddd4));
    const floor=new THREE.Mesh(new THREE.PlaneGeometry(80,80),new THREE.MeshStandardMaterial({color:0xedf1ed,roughness:1}));
    floor.rotation.x=-Math.PI/2;floor.position.y=-.01;this.scene.add(floor);
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(container);this.resize();
  }
  resize(){const w=this.container.clientWidth,h=this.container.clientHeight;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();}
  clear(){for(const actor of this.actors){this.scene.remove(actor.group);actor.group.traverse(obj=>{obj.geometry?.dispose();if(obj.material) obj.material.dispose();});}this.actors=[];}
  load(motions){
    this.clear();
    motions.forEach(({data,record},index)=>{
      const group=new THREE.Group();group.position.x=(index-(motions.length-1)/2)*2.4;
      const color=COLORS[index%COLORS.length], skeleton=new THREE.Group(),avatar=new THREE.Group();
      const edges=data.parents.map((p,i)=>[i,p]).filter(([,p])=>p>=0);
      const lines=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color}));
      lines.geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(edges.length*6),3));skeleton.add(lines);
      const joints=data.joint_names.map(()=>{const mesh=new THREE.Mesh(new THREE.SphereGeometry(.035,10,8),new THREE.MeshStandardMaterial({color}));skeleton.add(mesh);return mesh;});
      const bones=edges.map(()=>{const mesh=new THREE.Mesh(new THREE.CylinderGeometry(.055,.06,1,10),new THREE.MeshStandardMaterial({color,roughness:.65}));avatar.add(mesh);return mesh;});
      group.add(skeleton,avatar);this.scene.add(group);
      this.actors.push({group,skeleton,avatar,edges,lines,joints,bones,data,record,color});
    });
    this.setAvatar(this.avatar);this.draw(0);this.resetCamera();
    if(this.vrmVisible)for(const actor of this.actors)actor.group.visible=false;
    if(this.vrmSink.vrm&&motions[0])this.vrmSink.play(this.vrmSink.prepareMotion(motions[0].data),{offline:true});
  }
  setAvatar(value){this.avatar=value;for(const actor of this.actors){actor.skeleton.visible=!value;actor.avatar.visible=value;}}
  setVRMVisible(value){this.vrmVisible=value;if(this.vrmSink.vrm)this.vrmSink.vrm.scene.visible=value;for(const actor of this.actors)actor.group.visible=!value;}
  resetCamera(){
    if(this.actors.length){const bounds=new THREE.Box3();for(const actor of this.actors){for(const pos of actor.data.positions[0])bounds.expandByPoint(new THREE.Vector3(...pos).add(actor.group.position));}
      const target=bounds.getCenter(new THREE.Vector3());const size=bounds.getSize(new THREE.Vector3());const distance=Math.max(size.x,size.y,size.z,1.7)*2.15;
      this.controls.target.copy(target);this.camera.position.copy(target).add(new THREE.Vector3(distance*.7,distance*.3,distance));
    }else if(this.vrmSink.vrm){const bounds=new THREE.Box3().setFromObject(this.vrmSink.vrm.scene);const target=bounds.getCenter(new THREE.Vector3());const height=bounds.getSize(new THREE.Vector3()).y;
      this.controls.target.copy(target);this.camera.position.copy(target).add(new THREE.Vector3(.4,.1,1).multiplyScalar(Math.max(height,1)*1.65));
    }else{this.camera.position.set(3.5,2.3,5.2);this.controls.target.set(0,1,0);}this.controls.update();
  }
  draw(time){
    const now=performance.now(),delta=Math.min(.1,(now-this.lastDraw)/1000);this.lastDraw=now;
    if(!this.vrmSink.manual)this.vrmSink.tick(delta,{offlineTime:time});
    for(const actor of this.actors){
      const frame=actor.data.positions[Math.min(actor.data.positions.length-1,Math.floor(time*actor.data.fps))];
      actor.joints.forEach((joint,index)=>joint.position.fromArray(frame[index]));
      const values=actor.lines.geometry.attributes.position.array;
      actor.edges.forEach(([i,p],index)=>{
        values.set(frame[i],index*6);values.set(frame[p],index*6+3);
        const a=new THREE.Vector3(...frame[i]),b=new THREE.Vector3(...frame[p]);
        const delta=b.clone().sub(a),bone=actor.bones[index];
        bone.position.copy(a).add(b).multiplyScalar(.5);bone.scale.y=delta.length();
        if(delta.length()>0)bone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());
      });
      actor.lines.geometry.attributes.position.needsUpdate=true;actor.lines.geometry.computeBoundingSphere();
    }
    this.controls.update();this.renderer.render(this.scene,this.camera);
  }
}
