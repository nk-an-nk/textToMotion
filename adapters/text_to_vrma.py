import json
import shutil
import sys
from pathlib import Path

from adapters.base import ModelAdapter
from adapters.ardy import ArdyAdapter
from app import settings
from app.vrma import normalize_vrma


class TextToVrmaAdapter(ModelAdapter):
    id='text_to_vrma'
    tasks=('instruction',)
    implemented=True

    def blockers(self):
        reasons=[]
        if self.config.get('engine','ardy')!='ardy':reasons.append('比較設定はARDYエンジンを指定してください。')
        if not self.config.get('enabled',False):reasons.append('text-to-vrmaの公式ソース・依存・実生成を未検証。Windowsセットアップで準備してください。')
        if not self.repo.is_dir():reasons.append('text-to-vrma公式ソースが未取得。')
        if not shutil.which('node'):reasons.append('Node.js 20.6以上が必要です。')
        if not (self.repo/'node_modules/three/package.json').is_file():reasons.append('text-to-vrmaのNode依存が未導入。')
        reasons.extend(ArdyAdapter(self.data).blockers())
        return reasons

    def generate(self,request,output_dir):
        self.preflight(request)
        output=Path(output_dir)
        env=self.environment()
        env['HF_HUB_OFFLINE']='1'
        elapsed=self.run([sys.executable,settings.ROOT/'scripts/generate_text_to_vrma.py',
                          '--data-dir',self.data,'--output-dir',output,'--prompt',request.text,
                          '--duration',str(request.duration),'--seed',str(request.seed)],
                         output,env=env,timeout=1600)
        metadata=json.loads((output/'original.metadata.json').read_text(encoding='utf-8'))
        metadata['source_commit']='53c50504d1dc5137d4414b27ae8afaff89a62943'
        normalized=normalize_vrma(output/'original.vrma',output/'motion.json',metadata=metadata)
        return {'original_motion_path':output/'original.vrma','motion_spec_path':output/'original.spec.json',
                'normalized_motion_path':normalized,'rendered_video_path':None,'inference_time':elapsed,
                'checkpoint':metadata['checkpoint'],'device':'cuda','metadata':metadata}
