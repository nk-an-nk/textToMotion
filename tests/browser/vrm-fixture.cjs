// Authored test-only humanoids. No third-party model or pretrained output is embedded.
function vrmFixture(heightScale=1) {
  const nodes=[{name:'test-root',children:[1]}],bones={};
  function bone(name,parent,translation){const index=nodes.length;nodes.push({name,translation:translation.map(n=>n*heightScale),children:[]});nodes[parent].children.push(index);bones[name]={node:index};return index;}
  const hips=bone('hips',0,[0,.95,0]),spine=bone('spine',hips,[0,.12,0]),chest=bone('chest',spine,[0,.18,0]);
  const neck=bone('neck',chest,[0,.18,0]);bone('head',neck,[0,.13,0]);
  for(const side of ['left','right']) {const sign=side==='left'?1:-1;
    const shoulder=bone(side+'Shoulder',chest,[sign*.08,.1,0]),arm=bone(side+'UpperArm',shoulder,[sign*.12,0,0]);
    const forearm=bone(side+'LowerArm',arm,[sign*.3,0,0]);bone(side+'Hand',forearm,[sign*.25,0,0]);
    const upper=bone(side+'UpperLeg',hips,[sign*.1,-.02,0]),lower=bone(side+'LowerLeg',upper,[0,-.43,0]),foot=bone(side+'Foot',lower,[0,-.43,0]);bone(side+'Toes',foot,[0,-.05,.15]);
  }
  const json={asset:{version:'2.0',generator:'Motion Lab authored test fixture'},scene:0,scenes:[{nodes:[0]}],nodes,
    extensionsUsed:['VRMC_vrm'],extensions:{VRMC_vrm:{specVersion:'1.0',meta:{name:'Authored format fixture',authors:['Motion Lab tests'],licenseUrl:'https://vrm.dev/licenses/1.0/',avatarPermission:'everyone'},humanoid:{humanBones:bones}}}};
  const content=Buffer.from(JSON.stringify(json)),length=Math.ceil(content.length/4)*4,buffer=Buffer.alloc(20+length,0x20);
  buffer.writeUInt32LE(0x46546c67,0);buffer.writeUInt32LE(2,4);buffer.writeUInt32LE(buffer.length,8);buffer.writeUInt32LE(length,12);buffer.writeUInt32LE(0x4e4f534a,16);content.copy(buffer,20);return buffer;
}
function vrmaFixture() {
  const floats=new Float32Array([0,1, 0,0,0,1, 0,0,Math.sin(.3),Math.cos(.3), 0,1,0,.1,1,0]);
  const json={asset:{version:'2.0',generator:'Motion Lab authored VRMA test'},scene:0,scenes:[{nodes:[0]}],
    nodes:[{name:'hips',translation:[0,1,0],children:[1]},{name:'rightUpperArm',translation:[-.2,.3,0]}],
    buffers:[{byteLength:floats.byteLength}],bufferViews:[{buffer:0,byteOffset:0,byteLength:8},{buffer:0,byteOffset:8,byteLength:32},{buffer:0,byteOffset:40,byteLength:24}],
    accessors:[{bufferView:0,componentType:5126,count:2,type:'SCALAR',min:[0],max:[1]},{bufferView:1,componentType:5126,count:2,type:'VEC4'},{bufferView:2,componentType:5126,count:2,type:'VEC3'}],
    animations:[{samplers:[{input:0,output:1,interpolation:'LINEAR'},{input:0,output:2,interpolation:'LINEAR'}],channels:[{sampler:0,target:{node:1,path:'rotation'}},{sampler:1,target:{node:0,path:'translation'}}]}],
    extensionsUsed:['VRMC_vrm_animation'],extensions:{VRMC_vrm_animation:{specVersion:'1.0',humanoid:{humanBones:{hips:{node:0},rightUpperArm:{node:1}}}}}};
  const encoded=Buffer.from(JSON.stringify(json)),n=Math.ceil(encoded.length/4)*4,buffer=Buffer.alloc(28+n+floats.byteLength);
  buffer.writeUInt32LE(0x46546c67,0);buffer.writeUInt32LE(2,4);buffer.writeUInt32LE(buffer.length,8);buffer.writeUInt32LE(n,12);buffer.writeUInt32LE(0x4e4f534a,16);
  buffer.fill(0x20,20,20+n);encoded.copy(buffer,20);buffer.writeUInt32LE(floats.byteLength,20+n);buffer.writeUInt32LE(0x004e4942,24+n);Buffer.from(floats.buffer).copy(buffer,28+n);return buffer;
}
module.exports={vrmFixture,vrmaFixture};
