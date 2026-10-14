"""Strict VRMA/glTF 2.0 sampling and forward kinematics; preserve the original GLB."""
import json
import struct
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation,Slerp

from app.motion import MotionError,save_motion


def read_glb(path):
    raw=Path(path).read_bytes()
    if len(raw)>32*1024*1024 or len(raw)<20:
        raise MotionError('VRMA size is invalid.')
    magic,version,total=struct.unpack_from('<4sII',raw)
    if magic!=b'glTF' or version!=2 or total!=len(raw):
        raise MotionError('Expected a complete GLB 2.0 VRMA.')
    chunks={};offset=12
    while offset<len(raw):
        if offset+8>len(raw):raise MotionError('Truncated GLB chunk.')
        length,kind=struct.unpack_from('<II',raw,offset);offset+=8
        if offset+length>len(raw) or kind in chunks:raise MotionError('Invalid GLB chunk.')
        chunks[kind]=raw[offset:offset+length];offset+=length
    try:document=json.loads(chunks[0x4e4f534a].decode('utf-8').rstrip(' \0'))
    except (KeyError,ValueError,UnicodeError) as error:raise MotionError('Invalid GLB JSON.') from error
    binary=chunks.get(0x004e4942,b'')
    buffers=document.get('buffers',[])
    if len(buffers)!=1 or buffers[0].get('uri') or buffers[0].get('byteLength',0)>len(binary):
        raise MotionError('VRMA must use one embedded binary buffer.')
    return document,binary


def index(value,size):
    if type(value)!=int or not 0<=value<size:raise MotionError('Invalid glTF index.')
    return value


def accessor(document,binary,identifier,kind):
    items=document.get('accessors',[])
    item=items[index(identifier,len(items))]
    if item.get('componentType')!=5126 or item.get('type')!=kind or 'sparse' in item:
        raise MotionError('Only nonsparse float animation accessors are supported.')
    width={'SCALAR':1,'VEC3':3,'VEC4':4}[kind]
    count=item.get('count')
    if type(count)!=int or not 1<=count<=100000:raise MotionError('Invalid accessor count.')
    views=document.get('bufferViews',[])
    view=views[index(item.get('bufferView'),len(views))]
    if view.get('buffer',0)!=0:raise MotionError('External animation buffer is unsupported.')
    start=view.get('byteOffset',0);length=view.get('byteLength',0);offset=item.get('byteOffset',0)
    stride=view.get('byteStride',width*4)
    if any(type(v)!=int or v<0 for v in (start,length,offset,stride)) or stride<width*4 or stride%4:
        raise MotionError('Invalid animation buffer layout.')
    end=offset+(count-1)*stride+width*4
    if end>length or start+length>len(binary):raise MotionError('Accessor exceeds embedded buffer.')
    values=np.ndarray((count,width),dtype='<f4',buffer=binary,offset=start+offset,strides=(stride,4)).astype(float)
    if not np.isfinite(values).all():raise MotionError('Animation contains NaN or infinity.')
    return values[:,0] if kind=='SCALAR' else values


def sample_track(times,values,sample_times,path,interpolation):
    if np.any(times<0) or np.any(np.diff(times)<=0):raise MotionError('Animation times must increase strictly.')
    if len(values)!=len(times):raise MotionError('Animation input/output counts differ.')
    if interpolation not in ('LINEAR','STEP'):raise MotionError('Unsupported interpolation: '+str(interpolation))
    if path=='rotation':
        norms=np.linalg.norm(values,axis=1)
        if np.any(norms<1e-8):raise MotionError('Zero rotation quaternion.')
        values=values/norms[:,None]
    if len(times)==1:return np.repeat(values,len(sample_times),axis=0)
    clamped=np.clip(sample_times,times[0],times[-1])
    if interpolation=='STEP':return values[np.maximum(0,np.searchsorted(times,clamped,side='right')-1)]
    if path=='rotation':return Slerp(times,Rotation.from_quat(values))(clamped).as_quat()
    return np.column_stack([np.interp(clamped,times,values[:,column]) for column in range(values.shape[1])])


def normalize_vrma(path,output,*,fps=30,metadata=None):
    if not np.isfinite(fps) or not 1<=fps<=240:raise MotionError('Invalid sample FPS.')
    document,binary=read_glb(path)
    nodes=document.get('nodes',[])
    bones=document.get('extensions',{}).get('VRMC_vrm_animation',{}).get('humanoid',{}).get('humanBones',{})
    if not bones or 'hips' not in bones or len(bones)>200 or len(nodes)>1000:
        raise MotionError('VRMA humanoid bones are missing or excessive.')
    mapping={name:index(value.get('node'),len(nodes)) for name,value in bones.items()}
    if len(set(mapping.values()))!=len(mapping):raise MotionError('Humanoid bone nodes must be unique.')
    parents=[-1]*len(nodes)
    for parent,node in enumerate(nodes):
        for child in node.get('children',[]):
            child=index(child,len(nodes))
            if parents[child]!=-1:raise MotionError('Node has multiple parents.')
            parents[child]=parent
    needed=set(mapping.values())
    for bone in list(needed):
        visited=set();current=bone
        while current!=-1:
            if current in visited:raise MotionError('Cyclic node hierarchy.')
            visited.add(current);needed.add(current);current=parents[current]
    animations=document.get('animations',[])
    if len(animations)!=1:raise MotionError('Choose a VRMA with exactly one animation.')
    animation=animations[0];samplers=animation.get('samplers',[])
    tracks={};duration=0.
    for channel in animation.get('channels',[]):
        target=channel.get('target',{});node=index(target.get('node'),len(nodes))
        if node not in needed:continue  # Expression/look-at animation stays in the original VRMA.
        prop=target.get('path')
        if prop not in ('translation','rotation','scale'):raise MotionError('Unsupported body animation target.')
        key=(node,prop)
        if key in tracks:raise MotionError('Duplicate body animation channel.')
        sampler=samplers[index(channel.get('sampler'),len(samplers))]
        times=accessor(document,binary,sampler.get('input'),'SCALAR')
        values=accessor(document,binary,sampler.get('output'),'VEC4' if prop=='rotation' else 'VEC3')
        duration=max(duration,float(times[-1]))
        tracks[key]=(times,values,sampler.get('interpolation','LINEAR'))
    frames=int(np.ceil(duration*fps-1e-6))
    if not 1<=frames<=3600:raise MotionError('VRMA duration is outside the supported limit.')
    sample_times=np.arange(frames)/fps
    local={}
    for node in needed:
        item=nodes[node]
        if 'matrix' in item:raise MotionError('Matrix nodes are unsupported; use TRS VRMA.')
        values={}
        for prop,default,width in [('translation',[0,0,0],3),('rotation',[0,0,0,1],4),('scale',[1,1,1],3)]:
            value=np.asarray(item.get(prop,default),dtype=float)
            if value.shape!=(width,) or not np.isfinite(value).all():raise MotionError('Invalid node transform.')
            values[prop]=sample_track(*tracks[node,prop][:2],sample_times,prop,tracks[node,prop][2]) if (node,prop) in tracks else np.repeat(value[None],frames,axis=0)
        if np.any(np.linalg.norm(values['rotation'],axis=1)<1e-8):raise MotionError('Invalid node quaternion.')
        matrix=np.repeat(np.eye(4)[None],frames,axis=0)
        matrix[:,:3,:3]=Rotation.from_quat(values['rotation']).as_matrix()*values['scale'][:,None,:]
        matrix[:,:3,3]=values['translation'];local[node]=matrix
    world={}
    def transform(node):
        if node not in world:
            parent=parents[node]
            world[node]=local[node] if parent==-1 else transform(parent)@local[node]
        return world[node]
    for node in needed:transform(node)
    names=list(mapping)
    reverse={node:name for name,node in mapping.items()}
    output_parents=[]
    for name in names:
        ancestor=parents[mapping[name]]
        while ancestor!=-1 and ancestor not in reverse:ancestor=parents[ancestor]
        output_parents.append(-1 if ancestor==-1 else names.index(reverse[ancestor]))
    positions=np.stack([world[mapping[name]][:,:3,3] for name in names],axis=1)
    result={'schema':'motion-lab/v1','positions':positions.tolist(),'fps':float(fps),
            'joint_names':names,'parents':output_parents,'skeleton_type':f'VRMA:humanoid{len(names)}',
            'coordinate_system':{'up':'Y','handedness':'right','unit':'m'},
            'root_policy':'original global VRMA hips trajectory preserved',
            'metadata':{**(metadata or {}),'source_format':'VRMA/GLB','source_duration':duration,
                        'expressions_and_look_at':'retained in original VRMA; absent from skeleton video'}}
    save_motion(output,result)
    return Path(output)
