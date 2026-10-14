"""Synthetic GLB math/validation cases; no text generation is claimed."""
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

from app.motion import MotionError,read_motion
from app.vrma import normalize_vrma
from adapters.text_to_vrma import TextToVrmaAdapter
from scripts import generate_text_to_vrma,setup_lab


def fixture_glb(path,*,times=None,interpolation='LINEAR',mutate=None):
    times=times if times is not None else [0.,1.]
    arrays=[np.asarray(times,dtype='<f4'),np.asarray([[0,1,0],[1,1,0]],dtype='<f4'),
            np.asarray([[0,0,0,1],[0,0,np.sqrt(.5),np.sqrt(.5)]],dtype='<f4')]
    binary=b'';views=[];accessors=[]
    for values,kind in zip(arrays,['SCALAR','VEC3','VEC4']):
        views.append({'buffer':0,'byteOffset':len(binary),'byteLength':values.nbytes})
        accessors.append({'bufferView':len(views)-1,'componentType':5126,'type':kind,'count':len(values)})
        binary+=values.tobytes()
    document={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
              'bufferViews':views,'accessors':accessors,
              'nodes':[{'translation':[0,1,0],'children':[1]},
                       {'translation':[1,0,0],'children':[2]},{'translation':[1,0,0]}],
              'extensions':{'VRMC_vrm_animation':{'humanoid':{'humanBones':{'hips':{'node':0},'leftUpperArm':{'node':1},'leftHand':{'node':2}}}}},
              'animations':[{'samplers':[{'input':0,'output':1,'interpolation':interpolation},
                                        {'input':0,'output':2,'interpolation':interpolation}],
                             'channels':[{'sampler':0,'target':{'node':0,'path':'translation'}},
                                         {'sampler':1,'target':{'node':1,'path':'rotation'}}]}]}
    if mutate:mutate(document)
    encoded=json.dumps(document).encode();encoded+=b' '*((-len(encoded))%4)
    binary+=b'\0'*((-len(binary))%4)
    body=struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary
    path.write_bytes(struct.pack('<4sII',b'glTF',2,len(body)+12)+body)
    return path


def test_vrma_samples_slerp_global_fk_and_preserves_original_root(tmp_path):
    source=fixture_glb(tmp_path/'original.vrma');original=source.read_bytes()
    target=normalize_vrma(source,tmp_path/'motion.json',fps=2,metadata={'trained_model_output':False})
    motion=read_motion(target);positions=np.asarray(motion['positions'])
    assert positions.shape==(2,3,3) and motion['parents']==[-1,0,1]
    np.testing.assert_allclose(positions[0,2],[2,1,0],atol=1e-6)
    np.testing.assert_allclose(positions[1,2],[1.5+np.sqrt(.5),1+np.sqrt(.5),0],atol=1e-6)
    np.testing.assert_allclose(positions[1,0],[.5,1,0],atol=1e-6)
    assert source.read_bytes()==original and motion['metadata']['trained_model_output'] is False


@pytest.mark.parametrize('mutation',[
    lambda doc:doc['buffers'][0].update(uri='https://example.com/external.bin'),
    lambda doc:doc['accessors'][1].update(count=999),
    lambda doc:doc['nodes'][2].update(children=[0]),
    lambda doc:doc['nodes'][0].update(children=[1,2]),
    lambda doc:doc['animations'][0]['samplers'][0].update(interpolation='CUBICSPLINE'),
    lambda doc:doc['nodes'][0].update(matrix=[1]*16),
])
def test_invalid_or_unsupported_vrma_is_rejected(tmp_path,mutation):
    source=fixture_glb(tmp_path/'invalid.vrma',mutate=mutation)
    with pytest.raises(MotionError):normalize_vrma(source,tmp_path/'motion.json')
    assert not (tmp_path/'motion.json').exists()


def test_step_interpolation_and_duplicate_times(tmp_path):
    source=fixture_glb(tmp_path/'step.vrma',interpolation='STEP')
    motion=read_motion(normalize_vrma(source,tmp_path/'step.json',fps=2))
    np.testing.assert_allclose(motion['positions'][1][2],[2,1,0],atol=1e-6)
    source=fixture_glb(tmp_path/'duplicate.vrma',times=[0.,0.])
    with pytest.raises(MotionError):normalize_vrma(source,tmp_path/'bad.json')


def test_cpu_engine_is_stopped_before_any_vrma_generation(tmp_path,monkeypatch):
    data=tmp_path/'data';output=tmp_path/'output'
    python=setup_lab.interpreter(data/'envs/ardy')
    python.parent.mkdir(parents=True);python.touch()
    stopped=[]
    class ProcessDouble:
        def poll(self):return None
        def terminate(self):stopped.append(True)
        def wait(self,**kwargs):return 0
    monkeypatch.setattr(generate_text_to_vrma.subprocess,'Popen',lambda *args,**kwargs:ProcessDouble())
    monkeypatch.setattr(generate_text_to_vrma.subprocess,'run',lambda *args,**kwargs:pytest.fail('CPU must not generate VRMA'))
    monkeypatch.setattr(generate_text_to_vrma.shutil,'which',lambda name:'/node')
    monkeypatch.setattr(generate_text_to_vrma.urllib.request,'urlopen',
                        lambda *args,**kwargs:io.StringIO(json.dumps({'status':'ok','model':'core8','device':'cpu','fps':20})))
    monkeypatch.setattr(sys,'argv',['worker','--data-dir',str(data),'--output-dir',str(output),
                                  '--prompt','Hello.','--duration','3','--seed','0'])
    with pytest.raises(RuntimeError,match='no CPU fallback'):generate_text_to_vrma.main()
    assert stopped and not (output/'original.vrma').exists()


def test_text_to_vrma_requires_shared_ardy_and_has_no_llm_fallback(tmp_path):
    adapter=TextToVrmaAdapter(tmp_path)
    adapter.config={'enabled':True,'engine':'openai'}
    reasons=adapter.blockers()
    assert any('ARDYエンジン' in reason for reason in reasons)
    assert any('LLM2Vec' in reason for reason in reasons)
    with pytest.raises(ValueError,match='ardy before'):
        setup_lab.validate_profile({'models':['text_to_vrma'],'cuda_build':'cu128',
                                    'text_encoder_device':'cpu','min_free_gib':40,'port':8765})
