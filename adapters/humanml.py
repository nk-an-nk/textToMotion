"""Official generators wrapped by the measured comparison runner."""
import json
from pathlib import Path
import shutil
from app import settings
from .base import ModelAdapter


class HumanMLAdapter(ModelAdapter):
    tasks=('instruction',)
    implemented=True
    needs_cuda=True
    weight_subdir=''

    def weights(self):
        return Path(self.config.get('weights_dir',self.data/'checkpoints'/self.id/self.weight_subdir))

    def blockers(self):
        reasons=super().blockers()
        if not self.weights().is_dir():reasons.append('公開チェックポイント未取得。scripts/setup_comparison_models.py を実行してください。')
        return reasons

    def generate(self,request,output_dir):
        self.preflight(request);output_dir=Path(output_dir)
        plan=output_dir/'comparison-plan.json';plan.write_text(json.dumps({'title':'Official model inference',
            'segments':[{'id':'01','text':request.text,'motion_prompt':request.text}]},ensure_ascii=False),encoding='utf-8')
        speech=output_dir/'duration/01';speech.mkdir(parents=True)
        # These text-to-motion models use the duration only. This is not fabricated speech.
        (speech/'voice.json').write_text(json.dumps({'requested_text':request.text,'duration_seconds':request.duration}),encoding='utf-8')
        worker='generate_listener_comparison.py' if self.id=='reactmotion' else 'generate_humanml_comparison.py'
        env=self.environment();env['HF_HUB_ENABLE_HF_TRANSFER']='0'
        elapsed=self.run([self.python,settings.ROOT/'scripts'/worker,'--model',self.id,'--repo',self.repo,
            '--weights',self.weights(),'--config',plan,'--speech',speech.parent,'--output',output_dir/'native',
            '--seed',str(request.seed)],output_dir,env=env)
        folder=output_dir/'native/01';normalized=output_dir/'motion.json';original=output_dir/'joints.npy'
        shutil.copy(folder/'motion.json',normalized);shutil.copy(folder/'joints.npy',original)
        receipt=json.loads((folder/'motion-generation.json').read_text())
        return {'original_motion_path':original,'normalized_motion_path':normalized,'rendered_video_path':None,
            'inference_time':elapsed,'checkpoint':str(self.weights()),'device':'cuda',
            'metadata':{'trained_model_output':True,'duration_native_seconds':receipt['native_frames']/20,
                'actual_generator_seconds':receipt['skeleton_seconds'],'cold_model_load_seconds':receipt['cold_model_load_seconds'],
                'avatar_role':'listener' if self.id=='reactmotion' else 'speaker','input_translation':False}}


class MotionLCMAdapter(HumanMLAdapter):id='motionlcm'
class MoMaskAdapter(HumanMLAdapter):
    id='momask'
    weight_subdir='t2m'
class MMMAdapter(HumanMLAdapter):
    id='mmm'
    weight_subdir='text-to-motion_2localLayer_rerun'
