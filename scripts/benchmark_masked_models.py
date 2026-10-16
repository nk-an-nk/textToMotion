#!/usr/bin/env python3
"""Resident official MoLingo-263, ReMoMask-2 and MoMask generation and timing.

Runs one model per process/GPU. Does not provision GPUs or make audio API calls.
Upstream model source is kept unchanged; model-specific inference follows its
official demo/evaluation. See reports for the pinned revisions and asset hashes.
"""
import argparse
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
from types import SimpleNamespace

NAMES=['hips','leftUpperLeg','rightUpperLeg','spine','leftLowerLeg','rightLowerLeg','chest',
       'leftFoot','rightFoot','upperChest','leftToes','rightToes','neck',
       'leftShoulder','rightShoulder','head','leftUpperArm','rightUpperArm',
       'leftLowerArm','rightLowerArm','leftHand','rightHand']
PARENTS=[-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n')


def frames_for(seconds):
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('Positive finite duration required.')
    return min(196,max(40,math.ceil(seconds*20/4)*4))


def load_momask(weights,torch,np):
    from utils.get_opt import get_opt
    from models.vq.model import RVQVAE
    from models.mask_transformer.transformer import MaskTransformer,ResidualTransformer
    from utils.motion_process import recover_from_ric
    import clip
    mo=get_opt(str(weights/'t2m_nlayer8_nhead6_ld384_ff1024_cdp0.1_rvq6ns/opt.txt'),torch.device('cuda'))
    vo=get_opt(str(weights/mo.vq_name/'opt.txt'),torch.device('cuda'))
    vo.checkpoints_dir=str(weights.parent);vo.dataset_name=weights.name
    vq=RVQVAE(vo,vo.dim_pose,vo.nb_code,vo.code_dim,vo.output_emb_width,vo.down_t,
              vo.stride_t,vo.width,vo.depth,vo.dilation_growth_rate,vo.vq_act,vo.vq_norm)
    st=torch.load(weights/vo.name/'model/net_best_fid.tar',map_location='cpu')
    vq.load_state_dict(st['vq_model'] if 'vq_model' in st else st['net'],strict=True)
    mo.num_tokens=vo.nb_code;mo.num_quantizers=vo.num_quantizers;mo.code_dim=vo.code_dim
    mo.checkpoints_dir=str(weights.parent);mo.dataset_name=weights.name
    ro=get_opt(str(weights/'tres_nlayer8_ld384_ff1024_rvq6ns_cdp0.2_sw/opt.txt'),torch.device('cuda'))
    ro.num_quantizers=vo.num_quantizers;ro.num_tokens=vo.nb_code
    def options(o):
        return dict(code_dim=vo.code_dim,cond_mode='text',latent_dim=o.latent_dim,
                    ff_size=o.ff_size,num_layers=o.n_layers,num_heads=o.n_heads,
                    dropout=o.dropout,clip_dim=512,cond_drop_prob=o.cond_drop_prob,
                    clip_version='ViT-B/32',opt=o)
    masked=MaskTransformer(**options(mo))
    residual=ResidualTransformer(**options(ro),shared_codebook=vo.shared_codebook,share_weight=ro.share_weight)
    ms=torch.load(weights/mo.name/'model/latest.tar',map_location='cpu')
    rs=torch.load(weights/ro.name/'model/net_best_fid.tar',map_location='cpu')
    for module,state in [(masked,ms.get('t2m_transformer',ms.get('trans'))),(residual,rs['res_transformer'])]:
        missing,unexpected=module.load_state_dict(state,strict=False)
        if unexpected or any(not k.startswith('clip_model.') for k in missing):
            raise RuntimeError('MoMask checkpoint mismatch.')
        module.eval().cuda().requires_grad_(False)
    vq.eval().cuda().requires_grad_(False)
    mean=np.load(weights/vo.name/'meta/mean.npy');std=np.load(weights/vo.name/'meta/std.npy')
    def predict(text,frames):
        lens=torch.tensor([frames//4],device='cuda')
        codes=masked.generate([text],lens,timesteps=18,cond_scale=4,
                              temperature=1,topk_filter_thres=.9,gsample=False)
        codes=residual.generate(codes,[text],lens,temperature=1,cond_scale=5)
        values=vq.forward_decoder(codes)[0,:frames].float().cpu().numpy()*std+mean
        return recover_from_ric(torch.from_numpy(values).float(),22).numpy(),values
    def tokens(text):
        clip.tokenize([text],truncate=False)
        return {'tokenizer':'CLIP ViT-B/32','token_limit':77,'input_truncation':False}
    return predict,tokens,{'time_steps':18,'cond_scale':4,'residual_cond_scale':5,'representation':263}


def load_remomask2(weights,torch,np):
    import eval_mask as loaders
    import clip
    from utils.get_opt import get_opt
    from utils.motion_process import recover_from_ric
    from models.rag.ze_retriever import ZeRetriever
    root=weights/'logs/humanml3d'
    mo=get_opt(str(root/'v2_mtrans_vgate/opt.txt'),torch.device('cuda'))
    mo.checkpoints_dir=str(weights/'logs');mo.dataset_name='humanml3d';mo.name='v2_mtrans_vgate'
    vo=get_opt(str(root/mo.vq_name/'opt.txt'),torch.device('cuda'))
    vo.checkpoints_dir=mo.checkpoints_dir;vo.dataset_name=mo.dataset_name;vo.name=mo.vq_name
    loaders.opt=SimpleNamespace(device=torch.device('cuda'));loaders.dim_pose=263;loaders.clip_version='ViT-B/32'
    vq,_=loaders.load_vq_model(vo);loaders.vq_model=vq
    mo.num_tokens1d=vq.num_code1d;mo.num_tokens2d=vq.num_code2d
    aux=loaders.load_trans_aux(mo,'net_best_fid_ep0309.tar').cuda().eval().requires_grad_(False)
    spatial=loaders.load_trans_ts(mo,'net_best_fid_ep0309.tar',retrieval_dim=vq.code_dim2d).cuda().eval().requires_grad_(False)
    vq.cuda().eval().requires_grad_(False)
    for module in spatial.semanticTransEncoder:module.rt_in_value=True;module.vgate=True
    spatial.retr_cfgmix_w=.75
    retriever=ZeRetriever(str(weights/'database_ze'),str(weights/'query_projector.pt'),top_k=1,num_retrieval=10).cuda().eval()
    retriever._clip_model=spatial.clip_model;retriever._clip_device=retriever.motion_features.device
    mean=np.load(root/vo.name/'meta/mean.npy');std=np.load(root/vo.name/'meta/std.npy')
    def predict(text,frames):
        lengths=torch.tensor([frames//4],device='cuda',dtype=torch.long)
        retrieved=retriever([text]);embedding=retriever.encode_text(retriever.tokenize([text]).cuda())
        a=aux.generate(embedding,lengths,10,4,temperature=1,topk_filter_thres=.9,force_mask=False)
        b=spatial.generate(embedding,lengths,10,4,temperature=1,topk_filter_thres=.9,force_mask=False,n_j=6,re_dict=retrieved)
        _,decoded=vq.forward_decoder(a.unsqueeze(-1),b.unsqueeze(-1))
        values=decoded[0,:frames].float().cpu().numpy()*std+mean
        return recover_from_ric(torch.from_numpy(values).float(),22).numpy(),values
    def tokens(text):
        clip.tokenize([text],truncate=False)
        return {'tokenizer':'CLIP ViT-B/32','token_limit':77,'input_truncation':False}
    return predict,tokens,{'time_steps':10,'cond_scale':4,'retrieval_topk':1,'retrieval_pool':10,
                           'retr_cfgmix_w':.75,'rt_in_value':True,'retr_vgate':True,'representation':263}


def load_molingo(weights,torch,np):
    from transformers import T5EncoderModel,T5Tokenizer,T5Config
    from mogen.utils.get_opt import get_opt
    from mogen.models.vae.vae import VAE
    from mogen.utils.motion_representation import recover_from_ric
    import mogen.models.molingo.molingo as models
    mo=get_opt(str(weights/'pretrained_model_263/opt.txt'),'cuda')
    vo=get_opt(str(weights/mo.vae/'opt.txt'),'cuda')
    vae=VAE(input_width=263,output_emb_width=vo.output_emb_width,down_t=vo.down_t,
            stride_t=vo.stride_t,width=vo.width,depth=vo.depth,dilation_growth_rate=vo.dilation_growth_rate,
            activation=vo.activation,norm=vo.norm,pad_mode=vo.pad_mode,ae=vo.ae).cuda()
    st=torch.load(weights/mo.vae/'model/net_best_fid.ckpt',map_location='cpu')['state_dict']
    vae.load_state_dict(OrderedDict((k.removeprefix('module.'),v) for k,v in st.items()),strict=True)
    vae.eval().requires_grad_(False);del st
    checkpoint=torch.load(weights/'pretrained_model_263/net_best_fid.pth',map_location='cpu',mmap=True)
    state=checkpoint['model'];ema=checkpoint['model_ema']
    if not any(k.startswith('t5_model.') for k in state):
        raise RuntimeError('Full official T5 state is required for config-only initialization.')
    # Avoid downloading a duplicate T5 model: the official checkpoint contains it.
    # All tensors, including T5, are subsequently loaded strictly from official EMA.
    original_model=T5EncoderModel.from_pretrained;original_tokenizer=T5Tokenizer.from_pretrained
    tokenizer_dir=str(weights/'t5-tokenizer')
    T5EncoderModel.from_pretrained=classmethod(lambda cls,*a,**kw:cls(T5Config.from_pretrained(tokenizer_dir,local_files_only=True)))
    T5Tokenizer.from_pretrained=classmethod(lambda cls,*a,**kw:original_tokenizer(tokenizer_dir,local_files_only=True))
    try:
        model=getattr(models,'molingo_'+mo.model_size)()(vae_embed_dim=vo.output_emb_width,
                token_size=196//(2**vo.down_t),unit_length=2**vo.down_t,sample_steps=32,
                t5_max_len=mo.t5_max_len,adapter_layers=mo.aligner_layers,ae=vo.ae).cuda()
    finally:
        T5EncoderModel.from_pretrained=original_model;T5Tokenizer.from_pretrained=original_tokenizer
    for name,_ in model.named_parameters():
        if name not in ema:raise RuntimeError('Official EMA is incomplete: '+name)
        state[name]=ema[name]
    model.load_state_dict(state,strict=True);model.eval().requires_grad_(False)
    del state,ema,checkpoint
    mean=np.load(weights/'normalization/Mean.npy');std=np.load(weights/'normalization/Std.npy')
    def predict(text,frames):
        tokens=model.sample_tokens(bsz=1,cfg=5.5,m_lens=torch.tensor([frames],device='cuda'),
                                    cfg_schedule='constant',labels=[text],temperature=1,acc_ratio=3)
        values=vae.decode(tokens/mo.std_factor)[0,:frames].float().cpu().numpy()*std+mean
        return recover_from_ric(torch.from_numpy(values).float(),22).numpy(),values
    def token_info(text):
        ids=model.t5_tok(text,add_special_tokens=True,truncation=False)['input_ids'];count=len(ids)
        if count>mo.t5_max_len:raise ValueError('Canonical input exceeds the official T5 token limit.')
        return {'tokenizer':'T5-large','token_count':count,'unknown_token_count':ids.count(model.t5_tok.unk_token_id),
                'token_limit':mo.t5_max_len,'input_truncation':False}
    return predict,token_info,{'rectified_flow_steps':32,'acc_ratio':3,'cfg':5.5,'cfg_schedule':'constant',
                               'representation':263,'official_ema':True,'strict_full_state_load':True,
                               'duplicate_t5_download_avoided':True,'text_features_cached':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',choices=['molingo','remomask2','momask'],required=True)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--weights',type=Path,required=True)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',choices=['lab_proxy','b300'],required=True)
    p.add_argument('--repeats',type=int,default=3);p.add_argument('--cpu-threads',type=int,default=8)
    p.add_argument('--port',type=int,default=8766);p.add_argument('--serve',action='store_true')
    a=p.parse_args();started=time.monotonic();a.repo=a.repo.resolve();a.weights=a.weights.resolve();a.output=a.output.resolve()
    plan=json.loads(a.config.read_text());a.output.mkdir(parents=True,exist_ok=False)
    for var in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[var]=str(a.cpu_threads)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    if hasattr(os,'sched_getaffinity'):os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[:a.cpu_threads]))
    import numpy as np
    import torch
    if not torch.cuda.is_available():raise RuntimeError('An actual CUDA GPU is required.')
    for alias,scalar in [('float',float),('int',int),('complex',complex),('bool',bool)]:
        if alias not in np.__dict__:setattr(np,alias,scalar)
    torch.set_num_threads(a.cpu_threads);torch.set_float32_matmul_precision('highest')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    limit=12227 if a.profile=='lab_proxy' else None
    if limit:torch.cuda.set_per_process_memory_fraction(min(1,limit*1024**2/torch.cuda.get_device_properties(0).total_memory),0)
    original_load=torch.load
    def official_load(filename,*args,**kw):
        if isinstance(filename,(str,Path)) and a.weights in Path(filename).resolve().parents:kw.setdefault('weights_only',False)
        return original_load(filename,*args,**kw)
    torch.load=official_load;sys.path.insert(0,str(a.repo));os.chdir(a.repo)
    if a.model!='molingo':
        import clip
        original_clip_load=clip.load
        def cached_clip_load(*args,**kw):
            kw.setdefault('download_root',os.environ.get('MOTION_CLIP_CACHE','/workspace/cache/clip'))
            return original_clip_load(*args,**kw)
        clip.load=cached_clip_load
    predict,token_info,settings=globals()['load_'+a.model](a.weights,torch,np)
    torch.cuda.synchronize();load_seconds=time.monotonic()-started
    from scripts.resource_measurement import peak_ram_mib
    hardware={'model':a.model,'profile':a.profile,'gpu':torch.cuda.get_device_name(0),
              'gpu_total_mib':torch.cuda.get_device_properties(0).total_memory/1024**2,
              'torch':torch.__version__,'cuda':torch.version.cuda,'python':sys.version.split()[0],
              'cpu_threads':a.cpu_threads,'cpu_affinity_count':len(os.sched_getaffinity(0)),
              'torch_allocator_limit_mib':limit,'ram_hard_cap_applied':False,
              'model_load_seconds':load_seconds,'settings':settings,
              'source_commit':subprocess.check_output(['git','-C',str(a.repo),'rev-parse','HEAD'],text=True).strip()}
    write(a.output/'hardware.json',hardware)
    def generate(text,frames,seed,original_text=None):
        original_text=original_text or text
        if not isinstance(text,str) or not 0<len(text)<=4096 or not 40<=frames<=196 or frames%4:
            raise ValueError('Invalid canonical text or frame count.')
        info=token_info(text);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize()
        began=time.monotonic();at=datetime.now(timezone.utc).isoformat()
        with torch.inference_mode():joints,features=predict(text,frames)
        torch.cuda.synchronize();prediction_seconds=time.monotonic()-began
        if joints.shape!=(frames,22,3) or not np.isfinite(joints).all():raise ValueError('Invalid official decoder output.')
        motion={'schema':'motion-lab/v1','positions':joints.tolist(),'fps':20,'joint_names':NAMES,'parents':PARENTS,
                'skeleton_type':'humanml3d:22','coordinate_system':{'up':'Y','handedness':'right','unit':'m'},
                'source_coordinates':{'up':'Y','handedness':'right','unit':'m'},
                'metadata':{'source_format':a.model+' official decoded HumanML3D','trained_model_output':True,
                            'input_text':text,'original_text':original_text,'input_translation':True,
                            'seed':seed,'model':a.model,'profile':a.profile,'settings':settings}}
        encoded=json.dumps(motion,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        seconds=time.monotonic()-began
        receipt={'model':a.model,'profile':a.profile,'original_text':original_text,'motion_prompt':text,'seed':seed,
                 'native_frames':frames,'native_fps':20,'skeleton_seconds':seconds,'input_to_skeleton_seconds':seconds,
                 'prediction_and_decode_seconds':prediction_seconds,'bone_ready_seconds':seconds,
                 'input_submitted_at_utc':at,'skeleton_completed_at_utc':datetime.now(timezone.utc).isoformat(),
                 'motion_sha256':hashlib.sha256(encoded).hexdigest(),'gpu_name':hardware['gpu'],
                 'cold_model_load_seconds':load_seconds,'peak_torch_allocated_mib':torch.cuda.max_memory_allocated()/1024**2,
                 'peak_torch_reserved_mib':torch.cuda.max_memory_reserved()/1024**2,
                 'process_peak_ram_mib':peak_ram_mib(),'cpu_threads':a.cpu_threads,'torch_vram_allocator_limit_mib':limit,
                 'new_gesture_generated':True,'input_translation':True,'text_features_cached':False,**info}
        return motion,receipt,features,encoded
    for unit in plan['segments']:
        translation=unit.get('translation',{})
        if not translation.get('llm_generated') or translation.get('source_text')!=unit['text'] or translation.get('english')!=unit['motion_prompt']:
            raise ValueError('Verified shared LLM translation is required.')
        generate(unit['motion_prompt'],frames_for(unit['audio_seconds']),999,unit['text'])
    measurements=[]
    for unit in plan['segments']:
        for repeat in range(a.repeats):
            motion,receipt,features,encoded=generate(unit['motion_prompt'],frames_for(unit['audio_seconds']),repeat,unit['text'])
            receipt.update(id=unit['id'],repeat=repeat)
            receipt.update(translation_reused=True,shared_translation_seconds=unit['translation']['translation_seconds'],
                           translation_timing_scope='separately measured upstream translation; excluded from resident generation timer')
            target=a.output/unit['id'] if repeat==0 else a.output/'repeats'/unit['id']/str(repeat)
            target.mkdir(parents=True);(target/'motion.json').write_bytes(encoded)
            np.save(target/'features.npy',features,allow_pickle=False);write(target/'motion-generation.json',receipt)
            measurements.append(receipt);print(json.dumps({k:receipt[k] for k in ['id','repeat','skeleton_seconds','peak_torch_allocated_mib']}),flush=True)
    write(a.output/'measurements.json',measurements)
    if not a.serve:return
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            body=json.dumps({'status':'resident','model':a.model,'profile':a.profile}).encode()
            self.send_response(200);self.end_headers();self.wfile.write(body)
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=32768:raise ValueError('Invalid request size.')
                r=json.loads(self.rfile.read(size));motion,receipt,features,encoded=generate(r['text'],int(r['frames']),int(r.get('seed',0)),r.get('original_text'))
                request_id=str(r['id'])
                if not request_id.isalnum():raise ValueError('Invalid request id.')
                dest=a.output/'live'/request_id;dest.mkdir(parents=True)
                (dest/'motion.json').write_bytes(encoded);np.save(dest/'features.npy',features,allow_pickle=False);write(dest/'motion-generation.json',receipt)
                body=json.dumps({'motion':motion,'receipt':receipt},ensure_ascii=False,allow_nan=False).encode();status=200
            except Exception as error:body=json.dumps({'error':type(error).__name__+': '+str(error)}).encode();status=500
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',a.port),Handler)
    (a.output/'READY').write_text('resident\n');print('RESIDENT_READY',flush=True);server.serve_forever()


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]));main()
