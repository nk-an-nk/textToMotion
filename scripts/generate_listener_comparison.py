#!/usr/bin/env python3
"""Official ReactMotion joints or MaAI nod predictions; never substitute fallback poses."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
try:
    from scripts.resource_measurement import peak_ram_mib
except ModuleNotFoundError:
    from resource_measurement import peak_ram_mib


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',choices=['reactmotion','maai'],required=True)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--weights',type=Path)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--speech',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--vram-mib',type=int,default=12227)
    p.add_argument('--cpu-threads',type=int,default=8)
    p.add_argument('--seed',type=int,default=0)
    a=p.parse_args();began=time.monotonic()
    if a.output.exists(): raise ValueError('Existing listener outputs are preserved.')
    plan=json.loads(a.config.read_text());a.output=a.output.resolve();a.repo=a.repo.resolve();a.speech=a.speech.resolve()
    if a.weights: a.weights=a.weights.resolve()
    for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]=str(a.cpu_threads)
    os.environ['HF_HUB_ENABLE_HF_TRANSFER']='0'
    if hasattr(os,'sched_getaffinity'):os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[:a.cpu_threads]))
    import numpy as np
    import torch
    for alias,scalar in [('float',float),('int',int),('bool',bool)]:
        if alias not in np.__dict__:setattr(np,alias,scalar)
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required for this measurement.')
    torch.set_num_threads(a.cpu_threads)
    torch.cuda.set_per_process_memory_fraction(min(1,a.vram_mib*1024**2/torch.cuda.get_device_properties(0).total_memory))
    sys.path.insert(0,str(a.repo));os.chdir(a.repo)
    if a.model=='reactmotion':
        from transformers import T5Tokenizer,T5ForConditionalGeneration
        from demo_inference import build_prompt,build_vqvae,parse_motion_tokens,decode_motion_codes
        tokenizer=T5Tokenizer.from_pretrained(a.weights/'generator')
        model=T5ForConditionalGeneration.from_pretrained(a.weights/'generator').eval().cuda()
        vae=build_vqvae(str(next(a.weights.rglob('t2m.pth'))))
        mean=np.load(next(a.weights.rglob('mean.npy'))).astype(np.float32)
        std=np.load(next(a.weights.rglob('std.npy'))).astype(np.float32)
    else:
        from maai import Maai,MaaiInput
        from scipy.signal import resample_poly
        import wave
        model=Maai(mode='nod_para',lang='jp',audio_ch1=MaaiInput.Zero(),audio_ch2=MaaiInput.Zero(),
                   model_type='normal-ver2',frame_rate=12.5,context_len_sec=20,device='cuda',use_mimi_onnx=False)
    torch.cuda.synchronize();loading=time.monotonic()-began;a.output.mkdir(parents=True)
    names=['hips','leftUpperLeg','rightUpperLeg','spine','leftLowerLeg','rightLowerLeg','chest',
           'leftFoot','rightFoot','upperChest','leftToes','rightToes','neck','leftShoulder','rightShoulder',
           'head','leftUpperArm','rightUpperArm','leftLowerArm','rightLowerArm','leftHand','rightHand']
    parents=[-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19]
    def serial(value):
        if isinstance(value,torch.Tensor):return value.detach().cpu().tolist()
        if isinstance(value,np.ndarray):return value.tolist()
        if isinstance(value,dict):return {k:serial(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [serial(v) for v in value]
        if isinstance(value,np.generic):return value.item()
        return value
    results=[]
    for i,unit in enumerate(plan['segments']):
        text=unit['text'];folder=a.output/unit['id'];folder.mkdir();started=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
        torch.manual_seed(a.seed+i);torch.cuda.manual_seed_all(a.seed+i);torch.cuda.reset_peak_memory_stats()
        extra={}
        if a.model=='reactmotion':
            prompt=build_prompt(text,'','',use_transcription=True,use_audio=False,use_emotion=False)
            encoded=tokenizer(prompt,truncation=False,return_tensors='pt')
            if encoded['input_ids'].shape[-1]>512:raise ValueError('Canonical listener input exceeds 512 tokens.')
            with torch.inference_mode():
                out=model.generate(**{k:v.cuda() for k,v in encoded.items()},max_length=256,do_sample=True,
                                   temperature=.85,top_p=.95,top_k=200,num_return_sequences=1)
                decoded=tokenizer.decode(out[0],skip_special_tokens=False)
                codes=parse_motion_tokens(decoded)
                if not codes:raise RuntimeError('ReactMotion returned no motion tokens; upstream fallback is refused.')
                joints=decode_motion_codes(codes,vae,mean,std)
            if joints.ndim!=3 or joints.shape[1:]!=(22,3) or not np.isfinite(joints).all():raise ValueError('Invalid learned joint positions.')
            np.save(folder/'joints.npy',joints,allow_pickle=False)
            motion={'schema':'motion-lab/v1','positions':joints.tolist(),'fps':20,'joint_names':names,
                'parents':parents,'skeleton_type':'humanml3d:22','coordinate_system':{'up':'Y','handedness':'right','unit':'m'},
                'metadata':{'trained_model_output':True,'model':'reactmotion','input_text':text,'avatar_role':'listener'}}
            save(folder/'motion.json',motion);filename='motion.json'
            extra={'native_frames':len(joints),'native_fps':20,'raw_generated_tokens':decoded,'motion_codes':codes,
                   'input_unknown_token_count':int((encoded['input_ids']==tokenizer.unk_token_id).sum())}
        else:
            wavpath=a.speech/unit['id']/'voice.wav'
            with wave.open(str(wavpath),'rb') as wav:
                if wav.getnchannels()!=1 or wav.getsampwidth()!=2:raise ValueError('MaAI input must be mono PCM16.')
                sr=wav.getframerate();samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
            import math
            gcd=math.gcd(sr,16000);samples=resample_poly(samples,16000//gcd,sr//gcd).astype(np.float32)
            predictions=[];first=None;times=[]
            # Preserve chronological audio context across consecutive lesson segments.
            for offset in range(0,len(samples),1280):
                chunk=np.pad(samples[offset:offset+1280],(0,max(0,1280-len(samples[offset:offset+1280]))))
                tick=time.monotonic();model.process(chunk,np.zeros_like(chunk));torch.cuda.synchronize()
                times.append(time.monotonic()-tick)
                while not model.result_dict_queue.empty():
                    result=model.result_dict_queue.get_nowait()
                    pred=serial({k:result[k] for k in ['p_nod','nod_repetitions','nod_repetitions_pred',
                        'nod_range','nod_speed','nod_swing_up','nod_swing_up_pred']})
                    pred['input_audio_seconds']=(offset+len(chunk))/16000
                    pred['processing_seconds_since_input_start']=time.monotonic()-started
                    predictions.append(pred)
                    if first is None:first=time.monotonic()-started
            if not predictions:raise RuntimeError('MaAI produced no trained nod predictions.')
            save(folder/'head-controls.json',{'schema':'motion-lab/maai-head-controls-v1','trained_model_output':True,
                'model':'maai','input_text':text,'input_audio_sha256':hashlib.sha256(wavpath.read_bytes()).hexdigest(),
                'predictions':predictions,'body_pose':'avatar_rest_pose_not_model_generated',
                'motion_scope':'head_nod_parameters_only','audio_seconds':len(samples)/16000})
            filename='head-controls.json';extra={'first_prediction_processing_seconds':first,
                'first_prediction_audio_available_seconds':predictions[0]['input_audio_seconds'],
                'chunk_processing_seconds':times,'prediction_count':len(predictions),'audio_conditioned_model':True,
                'audio_processed_at_maximum_speed':True,'motion_scope':'head_only'}
        torch.cuda.synchronize();seconds=time.monotonic()-started
        receipt={'id':unit['id'],'model':a.model,'original_text':text,'motion_prompt':text,'seed':a.seed+i,
            'input_submitted_at_utc':utc,'skeleton_completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'input_to_skeleton_seconds':seconds,'skeleton_seconds':seconds,'cold_model_load_seconds':loading,
            'motion_sha256':hashlib.sha256((folder/filename).read_bytes()).hexdigest(),
            'output_file':filename,'new_gesture_generated':True,'gpu_name':torch.cuda.get_device_name(0),
            'cpu_threads':a.cpu_threads,'torch_vram_allocator_limit_mib':a.vram_mib,
            'peak_torch_allocated_mib':torch.cuda.max_memory_allocated()/1024**2,
            'peak_torch_reserved_mib':torch.cuda.max_memory_reserved()/1024**2,
            'process_peak_ram_mib':peak_ram_mib(),
            'input_translation':False,'input_truncation':False,'avatar_role':'listener',**extra}
        save(folder/'motion-generation.json',receipt);results.append(receipt)
        print(json.dumps({k:receipt[k] for k in ['model','id','skeleton_seconds','peak_torch_allocated_mib']},ensure_ascii=False),flush=True)
    save(a.output/'timings.json',{'model':a.model,'model_load_seconds':loading,'segments':results})


if __name__=='__main__':main()
