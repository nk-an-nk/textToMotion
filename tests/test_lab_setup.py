"""Setup safety/continuation tests. Doubles are not pretrained inference evidence."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import setup_lab,prepare_lab_text,setup_models
from adapters.ardy import ArdyAdapter
from adapters.kimodo import KimodoAdapter
from adapters.base import MotionInput


def profile(models=None):
    return {'models':models or ['kimodo'],'cuda_build':'cu128','text_encoder_device':'cpu',
            'min_free_gib':40,'port':8765}


@pytest.mark.parametrize('change',[
    {'models':['miburi']},{'models':['kimodo','kimodo']},{'models':[]},
    {'cuda_build':'cu121'},{'text_encoder_device':'cuda'},{'port':80},{'min_free_gib':0},
])
def test_lab_profile_rejects_unsupported_or_oversized_configuration(change):
    with pytest.raises(ValueError):setup_lab.validate_profile({**profile(),**change})


def test_license_gate_precedes_downloads_or_environment_creation(tmp_path):
    args=SimpleNamespace(accept_model_license=False,data_dir=tmp_path/'new')
    with pytest.raises(RuntimeError,match='AcceptModelLicense'):setup_lab.setup(args,profile())
    assert not args.data_dir.exists()


def test_changed_weights_are_preserved_and_rejected(tmp_path):
    folder=tmp_path/'checkpoints/ardy'/setup_lab.CATALOG['ardy']['checkpoint'].split('/')[-1]
    folder.mkdir(parents=True)
    file=folder/'weights.safetensors'
    file.write_bytes(b'changed-weight')
    setup_lab.write_json(folder/'motion-lab-download.json',
                         {'repo':setup_lab.CATALOG['ardy']['checkpoint'],
                          'sha256':{file.name:hashlib.sha256(b'original-weight').hexdigest()}})
    with pytest.raises(RuntimeError,match='changed'):setup_lab.checkpoint_valid(tmp_path,'ardy')
    assert file.read_bytes()==b'changed-weight'


def test_manifest_cannot_read_outside_checkpoint_directory(tmp_path):
    folder=tmp_path/'checkpoints/ardy'/setup_lab.CATALOG['ardy']['checkpoint'].split('/')[-1]
    folder.mkdir(parents=True)
    setup_lab.write_json(folder/'motion-lab-download.json',
                         {'repo':setup_lab.CATALOG['ardy']['checkpoint'],'sha256':{'../../secret':'none'}})
    assert setup_lab.checkpoint_valid(tmp_path,'ardy') is False


def test_encoder_checksum_change_is_detected_without_download(tmp_path):
    file=tmp_path/'adapter.safetensors'
    file.write_bytes(b'original')
    record={'path':str(tmp_path),'sha256':{file.name:prepare_lab_text.digest(file)}}
    assert prepare_lab_text.valid_record(record)
    file.write_bytes(b'changed')
    assert not prepare_lab_text.valid_record(record)


def test_public_encoder_check_does_not_mark_missing_llama_complete(tmp_path,monkeypatch):
    file=tmp_path/'adapter.safetensors'
    file.write_bytes(b'public-adapter')
    record={'path':str(tmp_path),'sha256':{file.name:prepare_lab_text.digest(file)}}
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({repo:record for repo in prepare_lab_text.REPOSITORIES[1:]}),encoding='utf-8')
    monkeypatch.setattr(sys,'argv',['prepare_lab_text','--manifest',str(manifest),'--check','--public-only'])
    prepare_lab_text.main()
    monkeypatch.setattr(sys,'argv',['prepare_lab_text','--manifest',str(manifest),'--check'])
    with pytest.raises(RuntimeError,match='missing'):
        prepare_lab_text.main()


def test_runner_redacts_tokens_and_signed_urls(tmp_path):
    runner=setup_lab.Runner(tmp_path/'log.txt',{})
    token='hf_'+'A'*30
    output=runner.run([sys.executable,'-c',
                       f'print("{token} https://example.com/file?signature=private")'],capture=True)
    assert token not in output and 'signature=private' not in output
    assert token not in runner.log.read_text()


def test_blackwell_build_is_installed_and_constrained(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    python=setup_lab.interpreter(tmp_path/'envs/kimodo')
    python.parent.mkdir(parents=True);python.touch()
    calls=[]
    monkeypatch.setattr(setup_models,'clone',lambda *args:source)
    monkeypatch.setattr(setup_models,'run',lambda command,**kwargs:calls.append((list(map(str,command)),kwargs)))
    monkeypatch.setattr(setup_models.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout='pinned-test-dependency\n'))
    setup_models.install('kimodo',tmp_path,'cuda',False,'cu128')
    assert any('torch==2.9.0+cu128' in command for command,_ in calls)
    assert any('https://download.pytorch.org/whl/cu128' in command for command,_ in calls)
    source_call=next(kwargs for command,kwargs in calls if str(source) in command)
    assert Path(source_call['env']['PIP_CONSTRAINT']).read_text()=='torch==2.9.0+cu128\n'


@pytest.mark.parametrize('adapter_type',[ArdyAdapter,KimodoAdapter])
def test_requested_cuda_failure_never_launches_cpu_or_online_fallback(tmp_path,adapter_type):
    adapter=adapter_type(tmp_path)
    adapter.config={'backend':'local','require_cuda':True,'text_encoder_device':'cpu'}
    adapter.preflight=lambda request:None
    calls=[]
    def failing_gpu_probe(command,*args,**kwargs):
        calls.append(command)
        raise RuntimeError('CUDA unavailable')
    adapter.run=failing_gpu_probe
    with pytest.raises(RuntimeError,match='CUDA unavailable'):
        adapter.generate(MotionInput('instruction','Wave',None,3,0,adapter.id),tmp_path)
    assert len(calls)==1 and '-c' in calls[0]
    assert 'no CPU fallback' in calls[0][-1]


def test_low_vram_ardy_passes_cpu_encoder_to_local_api_worker(tmp_path):
    adapter=ArdyAdapter(tmp_path)
    adapter.config={'text_encoder_device':'cpu','model':'core8'}
    adapter.preflight=lambda request:None
    calls=[]
    adapter.run=lambda command,*args,**kwargs:calls.append(command) or .1
    adapter.cuda_available=lambda:True
    adapter.export_official=lambda *args:tmp_path/'motion.json'
    result=adapter.generate(MotionInput('instruction','Wave',None,3,0,'ardy'),tmp_path)
    assert str(calls[0][1]).endswith('generate_ardy_local.py')
    assert calls[0][calls[0].index('--text-device')+1]=='cpu'
    assert result['metadata']['text_encoder_device']=='cpu'


def test_kimodo_local_encoder_and_checkpoint_do_not_use_external_api(tmp_path):
    adapter=KimodoAdapter(tmp_path)
    adapter.config={'backend':'local','text_encoder_device':'cpu'}
    adapter.preflight=lambda request:None
    environments=[]
    adapter.run=lambda command,*args,**kwargs:environments.append(kwargs['env']) or .1
    adapter.cuda_available=lambda:True
    exports=[]
    adapter.export_official=lambda *args,**kwargs:exports.append(kwargs) or tmp_path/'motion.json'
    adapter.generate(MotionInput('instruction','Wave',None,3,0,'kimodo'),tmp_path)
    assert exports==[{'model':'kimodo-soma-rp-v1.1','checkpoint_dir':str(tmp_path/'checkpoints/kimodo')}]
    assert environments[0]['TEXT_ENCODER_MODE']=='local'
    assert environments[0]['TEXT_ENCODER_DEVICE']=='cpu'
    assert environments[0]['CHECKPOINT_DIR']==str(tmp_path/'checkpoints/kimodo')


def test_failed_inference_is_not_marked_ready_and_completed_steps_resume(tmp_path,monkeypatch):
    calls=[]
    data=tmp_path/'data'
    monkeypatch.setattr(setup_lab,'preflight',lambda:{'commands':{key:True for key in ['git','node','npm','ffmpeg','nvidia-smi']},'gpu_query_exit_code':0})
    monkeypatch.setattr(setup_lab,'prepare_app',lambda *args:Path(sys.executable))
    monkeypatch.setattr(setup_lab,'checkpoint_valid',lambda *args:True)
    monkeypatch.setattr(setup_lab.shutil,'disk_usage',lambda *args:SimpleNamespace(free=100*2**30))
    monkeypatch.setattr(setup_lab.getpass,'getpass',lambda *args:'test-token-only')
    class FakeRunner:
        def __init__(self,log,env):self.env=env
        def run(self,command,**kwargs):
            arguments=list(map(str,command));calls.append(arguments)
            if setup_lab.TORCH_PROBE in arguments:
                return json.dumps({'torch':'2.9.0+cu128','cuda':'12.8','gpu':'test-double','capability':[12,0]})
            if '--install' in arguments:
                python=setup_lab.interpreter(data/'envs/kimodo')
                python.parent.mkdir(parents=True,exist_ok=True);python.touch()
            if any(arg.endswith('verify_lab_model.py') for arg in arguments):
                raise RuntimeError('test-only real-inference failure')
            return ''
    monkeypatch.setattr(setup_lab,'Runner',FakeRunner)
    args=SimpleNamespace(accept_model_license=True,data_dir=data)
    for _ in range(2):
        with pytest.raises(RuntimeError,match='real-inference failure'):setup_lab.setup(args,profile())
    assert sum('--install' in command for command in calls)==1
    assert sum(any(arg.endswith('verify_lab_model.py') for arg in command) for command in calls)==2
    assert not setup_lab.load_json(data/'runtime.json')['kimodo']['text_encoder_cached']
    assert not setup_lab.load_json(data/'lab-setup.json').get('verified')


def test_start_rejects_missing_verified_artifacts_before_launch(tmp_path,monkeypatch):
    data=tmp_path/'data'
    setup_lab.write_json(data/'lab-setup.json',{'verified':{'kimodo':'test-only'},'cuda_build':'cu128'})
    setup_lab.write_json(data/'runtime.json',{'kimodo':{'text_encoder_cached':True}})
    monkeypatch.setattr(setup_lab.subprocess,'run',lambda *args,**kwargs:pytest.fail('Must not start the app'))
    with pytest.raises(RuntimeError,match='outputs are missing'):
        setup_lab.start(SimpleNamespace(data_dir=data),profile())
