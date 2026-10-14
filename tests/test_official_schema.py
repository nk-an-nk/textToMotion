import json
import numpy as np
import pytest
from app.official_schema import normalize_kimodo_online
from app.motion import MotionError
from scripts.export_official import official_fps


def test_exporter_requires_official_fps_and_rejects_invalid_values():
    assert official_fps({'fps':np.asarray(20)},'ardy')==20
    with pytest.raises(ValueError,match='no fps'):
        official_fps({},'kimodo')
    for value in (0,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError,match='finite and positive'):
            official_fps({'fps':np.asarray(value)},'ardy')


def test_official_output_matches_frames_and_hierarchy_without_executing_source(tmp_path):
    source=tmp_path/'repo/kimodo/skeleton';source.mkdir(parents=True)
    bones=[('root',None)]+[(f'j{i}','root') for i in range(1,30)]
    definition='class SOMASkeleton30:\n    bone_order_names_with_parents = '+repr(bones)
    (source/'definitions.py').write_text(definition)
    original=tmp_path/'original.npz';np.savez(original,posed_joints=np.zeros((3,30,3)))
    metadata={'fps':30,'frames_requested':3,'trained_model_output':False,'prompt':'unit-test only'}
    result=normalize_kimodo_online(original,tmp_path/'motion.json',tmp_path/'repo',metadata)
    data=json.loads(result.read_text());assert len(data['joint_names'])==30 and data['parents'][1]==0
    with pytest.raises(MotionError,match='frame count'):
        normalize_kimodo_online(original,result,tmp_path/'repo',{**metadata,'frames_requested':4})
    (source/'definitions.py').write_text('raise RuntimeError("must not execute")\n'+definition)
    normalize_kimodo_online(original,result,tmp_path/'repo',metadata)
