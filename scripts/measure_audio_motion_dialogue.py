#!/usr/bin/env python3
"""Actual audio input → actual teacher transcript → generator → measured completion."""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.measure_audio_dialogue import measure
from scripts.runpod_jupyter import TrialJupyter
from app.realtime import RealtimeConfig


def local_generation(model,root,data_dir):
    """The lab PC path uses its own GPU and needs no RunPod account or SSH."""
    import shutil
    from adapters.base import MotionInput
    from adapters.registry import adapters
    from app.segmented_dialogue import generate_segments
    m=json.loads((root/'measurement.json').read_text())
    if model in ['kimodo','ardy']:
        generate_segments(root/'teacher-plan.json',root/'generated',model=model,budget_usd=0,
                          data_dir=data_dir,ardy_backend='local',speech_source=root/'teacher-speech/manifest.json')
        return root/'generated/segments'
    listener=model in ['reactmotion','maai']
    text=m['student_transcript'] if listener else m['teacher_transcript']
    if model=='maai':
        speech=root/'student-speech/01';speech.mkdir(parents=True)
        shutil.copyfile(root/'student.wav',speech/'voice.wav')
        (speech/'voice.json').write_text(json.dumps({'requested_text':text,'transcript':text,
            'duration_seconds':m['student_audio_seconds'],'audio_sha256':m['student_sha256'],'generation_wall_seconds':0},ensure_ascii=False)+'\n')
        plan=root/'student-plan.json';plan.write_text(json.dumps({'segments':[{'id':'01','text':text,'motion_prompt':text}]},ensure_ascii=False)+'\n')
        adapter=adapters(data_dir)['maai']
        if not adapter.python.is_file() or not adapter.repo.is_dir():raise RuntimeError('Install the dedicated MaAI environment first.')
        env=adapter.environment();env['HF_HUB_ENABLE_HF_TRANSFER']='0'
        adapter.run([adapter.python,Path(__file__).with_name('generate_listener_comparison.py'),'--model','maai',
            '--repo',adapter.repo,'--config',plan,'--speech',speech.parent,'--output',root/'generated'],root,env=env)
    else:
        adapter=adapters(data_dir)[model];job=root/'generator-job';job.mkdir()
        request=MotionInput('conversation_text' if listener else 'instruction',text,None,
            m['student_audio_seconds'] if listener else m['teacher_audio_seconds'],0,model,text)
        adapter.generate(request,job)
        shutil.copytree(job/'native',root/'generated')
    return root/'generated'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--student-wav',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',choices=['motionlcm','momask','mmm','reactmotion','maai','kimodo','ardy'],required=True)
    p.add_argument('--backend',choices=['runpod','local'],default='runpod')
    p.add_argument('--data-dir',type=Path)
    a=p.parse_args();base=RealtimeConfig.environment()
    if not base.api_key:raise RuntimeError('Realtime credential is unavailable. Set it in the local process using hidden input; never paste its value into chat.')
    config=RealtimeConfig(api_key=base.api_key,enabled=True,model=base.model,voice=base.voice,budget_usd=1,max_calls=1,session_seconds=60)
    receipt=measure(a.student_wav,a.output,config)
    # The observer's monotonic timestamp is returned privately, not serialized to an artifact.
    anchor=receipt.pop('_student_end_monotonic')
    submitted=time.monotonic()
    if a.backend=='local':
        from app import settings
        motion_root=local_generation(a.model,a.output,a.data_dir or settings.DATA)
        completed=time.monotonic()
    elif a.model=='kimodo':
        from app.segmented_dialogue import generate_segments
        result=generate_segments(a.output/'teacher-plan.json',a.output/'generated',model='kimodo',budget_usd=0,
            speech_source=a.output/'teacher-speech/manifest.json')
        motion_root=a.output/'generated/segments'
    else:
        client=TrialJupyter(Path('.motion-lab/runpod-trial.json'),Path('.motion-lab/runpod/jupyter_auth.json'))
        name='live-'+a.model+'-'+a.output.name
        archive=a.output/'input.tar.gz'
        if a.model=='ardy':
            encoder_python=Path('/workspace/shared/motion-lab/envs/ardy/bin/python')
            subprocess.run([str(encoder_python),'scripts/encode_ardy_comparison.py','--config',str(a.output/'teacher-plan.json'),
                            '--output',str(a.output/'embeddings')],check=True)
        with tarfile.open(archive,'w:gz') as z:
            for n in ['teacher-plan.json','teacher-speech','student.wav','measurement.json']:z.add(a.output/n,arcname=n)
            if a.model=='ardy':z.add(a.output/'embeddings',arcname='embeddings')
        client.upload(archive,name+'.tar.gz')
        repo='/workspace/model-comparison/'+a.model
        venv={ 'motionlcm':'.venv-lcm','momask':'.venv-masked','mmm':'.venv-masked','reactmotion':'.venv-react','maai':'.venv-maai','ardy':'.venv-ardy'}[a.model]
        root='/workspace/textToMotion/runpod-results/live-dialogue/'+name
        command=['/workspace/model-comparison/'+venv+'/bin/python']
        listener=a.model in ['reactmotion','maai']
        command+=['/workspace/textToMotion/scripts/generate_'+('listener' if listener else 'humanml')+'_comparison.py',
                  '--model',a.model,'--repo',repo,'--config',root+'/input/'+('student-plan.json' if listener else 'teacher-plan.json'),
                  '--speech',root+'/input/'+('student-speech' if listener else 'teacher-speech'),'--output',root+'/generated']
        weights={'motionlcm':'weights/motionlcm','momask':'weights/momask/t2m','mmm':'weights/mmm/text-to-motion_2localLayer_rerun','reactmotion':'weights/reactmotion'}
        if a.model in weights:command+=['--weights','/workspace/model-comparison/'+weights[a.model]]
        if a.model=='ardy':
            command=['/workspace/model-comparison/.venv-ardy/bin/python','/workspace/textToMotion/scripts/generate_ardy_embedding.py',
                '--embeddings',root+'/input/embeddings','--config',root+'/input/teacher-plan.json',
                '--speech',root+'/input/teacher-speech','--weights','/workspace/model-comparison/weights/ardy','--output',root+'/generated']
        code='''import pathlib,tarfile,subprocess,time,os,json,shutil
r=pathlib.Path(ROOT);(r/'input').mkdir(parents=True)
with tarfile.open('/'+ARCHIVE) as z:z.extractall(r/'input',filter='data')
m=json.loads((r/'input/measurement.json').read_text())
sp=r/'input/student-speech/01';sp.mkdir(parents=True)
shutil.copy(r/'input/student.wav',sp/'voice.wav')
(sp/'voice.json').write_text(json.dumps({'requested_text':m['student_transcript'],'transcript':m['student_transcript'],'duration_seconds':m['student_audio_seconds'],'audio_sha256':m['student_sha256'],'generation_wall_seconds':0},ensure_ascii=False))
(r/'input/student-plan.json').write_text(json.dumps({'title':'Student audio response','segments':[{'id':'01','text':m['student_transcript'],'motion_prompt':m['student_transcript']}]},ensure_ascii=False))
env=os.environ.copy()
for k in list(env):
 if k.endswith('_KEY') or k.endswith('_TOKEN') or k in ['JUPYTER_PASSWORD','PUBLIC_KEY','realtime']:env.pop(k)
env.update(HF_HUB_ENABLE_HF_TRANSFER='0',HF_HUB_DISABLE_XET='1')
with (r/'generator.log').open('w') as log:
 p=subprocess.Popen(COMMAND,env=env,stdout=log,stderr=subprocess.STDOUT)
 while p.poll() is None:print('generator_running',flush=True);time.sleep(5)
 if p.returncode:print((r/'generator.log').read_text()[-1600:]);raise RuntimeError('Official model inference failed')
print('generator_complete',flush=True)
'''.replace('ROOT',repr(root)).replace('ARCHIVE',repr(name+'.tar.gz')).replace('COMMAND',repr(command))
        asyncio.run(client.execute(code))
        # Record completion before retrieving files; the five-second polling bound is explicit.
        completed=time.monotonic();motion_root=a.output/'generated';motion_root.mkdir()
        client.download(root.lstrip('/')+'/generated/timings.json',motion_root/'timings.json')
        folder=motion_root/'01';folder.mkdir()
        client.download(root.lstrip('/')+'/generated/01/motion-generation.json',folder/'motion-generation.json')
        motion=json.loads((folder/'motion-generation.json').read_text())
        filename=motion.get('output_file','motion.json')
        client.download(root.lstrip('/')+'/generated/01/'+filename,folder/filename)
    if a.model=='kimodo' and a.backend!='local':completed=time.monotonic()
    motion=json.loads((motion_root/'01/motion-generation.json').read_text())
    receipt.update(model=a.model,avatar_role='listener' if a.model in ['reactmotion','maai'] else 'speaker',
        generation_dispatch_seconds_after_student_end=submitted-anchor,
        bone_ready_observed_seconds_after_student_end=completed-anchor,
        generation_command_observed_seconds=completed-submitted,
        completion_poll_interval_seconds=5 if a.backend=='runpod' and a.model!='kimodo' else 0,
        motion_generation_seconds=motion['skeleton_seconds'],
        cold_model_load_seconds=motion.get('cold_model_load_seconds'),
        bone_minus_first_realtime_audio_seconds=(completed-anchor)-receipt['first_teacher_audio_seconds_after_student_end'],
        teacher_playback_seconds_after_student_end=max(completed-anchor,receipt['response_done_seconds_after_student_end']),
        playback_policy='buffer_teacher_voice_until_trained_motion_available',
        actual_inference_after_received_teacher_transcript=True,
        measurement_scope='audio_input_and_generator_completion_single_client_monotonic',
        remote_upload_and_startup_included=a.backend=='runpod' and a.model!='kimodo',
        inference_backend=a.backend,
        measured_end_to_end=True)
    (a.output/'measurement.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['model','first_teacher_audio_seconds_after_student_end',
        'bone_ready_observed_seconds_after_student_end','motion_generation_seconds','bone_minus_first_realtime_audio_seconds']},ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as e:
        message=str(e) if isinstance(e,(RuntimeError,ValueError)) else type(e).__name__
        for k in ['realtime','OPENAI_API_KEY','HF_TOKEN','RUNPOD_API_KEY']:
            if os.environ.get(k):message=message.replace(os.environ[k],'[REDACTED]')
        print(message,file=sys.stderr);sys.exit(1)
