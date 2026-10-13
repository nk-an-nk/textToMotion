import copy
import json
import numpy as np
import pytest
from app.motion import MotionError, load_bvh, load_npz, metrics, normalize, validate_motion, viewer_fixture


def test_fixture_is_explicitly_not_model_inference():
    data=validate_motion(viewer_fixture())
    assert data['metadata']['trained_model_output'] is False
    assert data['metadata']['provenance']=='synthetic_viewer_fixture'
    assert metrics(data)['duration']==4
    assert metrics(data)['semantic_alignment'] is None


@pytest.mark.parametrize('field,value',[
    ('fps',0),('fps',float('nan')),('fps',500),('positions',[]),('positions',[[[0,0]]]),
    ('joint_names',[]),('joint_names',[{}]),('parents',[]),('schema','guess'),
    ('coordinate_system',{'up':'Z','handedness':'right','unit':'cm'}),
])
def test_malformed_motion_rejected(field,value):
    data=viewer_fixture();data[field]=value
    with pytest.raises(MotionError):validate_motion(data)


def test_cycle_and_nonfinite_coordinates_rejected():
    data=viewer_fixture();data['parents'][1]=2
    with pytest.raises(MotionError,match='cycle'):validate_motion(data)
    data=viewer_fixture();data['positions'][0][0][0]=float('inf')
    with pytest.raises(MotionError,match='finite'):validate_motion(data)


def test_axes_units_and_root_not_guessed_or_zeroed():
    data=normalize([[[100,200,300]]],30,['root'],[-1],skeleton_type='test',source_up='Z',source_unit='cm')
    np.testing.assert_allclose(data['positions'],[[[1,3,-2]]])
    assert data['root_policy']=='original global trajectory preserved'
    with pytest.raises(MotionError):normalize([[[1,2,3]]],30,['root'],[-1],skeleton_type='x',source_up='X',source_unit='m')


BVH='''HIERARCHY
ROOT Hips { OFFSET 0 0 0 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
JOINT Arm { OFFSET 0 100 0 CHANNELS 3 Zrotation Xrotation Yrotation
End Site { OFFSET 0 50 0 } } }
MOTION
Frames: 1
Frame Time: 0.0333333333333333
0 0 0 90 0 0 0 0 0
'''


def test_bvh_forward_kinematics_obeys_declared_intrinsic_order(tmp_path):
    path=tmp_path/'known.bvh';path.write_text(BVH)
    data=load_bvh(path,source_up='Y',source_unit='cm')
    np.testing.assert_allclose(data['positions'][0][1],[-1,0,0],atol=1e-6)
    np.testing.assert_allclose(data['positions'][0][2],[-1.5,0,0],atol=1e-6)
    assert data['parents']==[-1,0,1]


@pytest.mark.parametrize('contents',['HIERARCHY ROOT X {','MOTION Frames: 0 Frame Time: 0','HIERARCHY\nROOT A{}\nMOTION bad',BVH.replace('Frames: 1','Frames: 2')])
def test_bad_bvh_rejected(tmp_path,contents):
    path=tmp_path/'bad.bvh';path.write_text(contents)
    with pytest.raises(MotionError):load_bvh(path,source_up='Y',source_unit='m')


def test_npz_requires_explicit_joint_definition_and_disallows_pickle(tmp_path):
    path=tmp_path/'motion.npz'
    np.savez(path,posed_joints=np.zeros((2,1,3)),fps=30)
    with pytest.raises(MotionError,match='explicit'):load_npz(path)
    np.savez(path,poses=np.zeros((2,165)))
    with pytest.raises(MotionError,match='licensed'):load_npz(path)
    np.savez(path,positions=np.zeros((2,1,3)),fps=30,joint_names=np.array(['root']),parents=np.array([-1]))
    assert load_npz(path)['joint_names']==['root']
    np.savez(path,positions=np.zeros((2,1,3)),fps=30,joint_names=np.array([{'x':1}],dtype=object),parents=np.array([-1]))
    with pytest.raises(ValueError,match='allow_pickle'):load_npz(path)
