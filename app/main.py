import json
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app import settings
from app.audio import inspect_wav
from app.jobs import JobStore, write_json
from app.motion import MotionError, read_motion, viewer_fixture, save_motion
from adapters.base import MotionInput, UnavailableError
from adapters.registry import adapters, catalog
from app.timing import csv_bytes,summary_row

MAX_UPLOAD = 32 * 1024 * 1024


class InputRequest(BaseModel):
    task_type: Literal['conversation_text', 'audio', 'instruction']
    text: str = Field(default='', max_length=4000)
    translated_text: str = Field(default='', max_length=4000)
    audio_id: str | None = None
    duration: float = Field(default=3, ge=.5, le=20, allow_inf_nan=False)
    seed: int = Field(default=0, ge=0, le=4294967295)

    @model_validator(mode='after')
    def check_input(self):
        if self.task_type == 'audio':
            if not self.audio_id or not re.fullmatch('[0-9a-f]{32}', self.audio_id):
                raise ValueError('音声入力にはアップロード済みの audio_id が必要です。')
        elif not self.text.strip():
            raise ValueError('テキストを入力してください。')
        if self.task_type != 'audio' and re.search('[\u3040-\u30ff\u3400-\u9fff]', self.text) and not self.translated_text.strip():
            raise ValueError('日本語入力にはモデルへ渡す英訳を指定してください。自動翻訳は未導入です。元文と英訳は両方保存します。')
        return self


class GenerateRequest(InputRequest):
    model_name: str


class CompareRequest(InputRequest):
    model_names: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def unique_models(self):
        if len(set(self.model_names)) != len(self.model_names):
            raise ValueError('モデル名の重複を除いてください。')
        return self


class DiagnosticRequest(BaseModel):
    duration:float=Field(default=3,ge=.5,le=10,allow_inf_nan=False)
    seed:int=Field(default=0,ge=0,le=4294967295)


def create_app(*, data_dir=None, output_dir=None, model_adapters=None):
    data_dir = Path(data_dir or settings.DATA)
    output_dir = Path(output_dir or settings.OUTPUTS)
    uploads = data_dir / 'uploads'
    uploads.mkdir(parents=True, exist_ok=True)
    instances = model_adapters if model_adapters is not None else adapters(data_dir)
    store = JobStore(output_dir, instances)

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.close()

    app = FastAPI(title='Motion Lab',version='0.1.0',lifespan=lifespan)
    app.state.store = store
    app.mount('/static',StaticFiles(directory=settings.UI),name='ui')
    # Vendor Three.js locally. A network/CDN outage does not break playback.
    vendor = settings.ROOT / 'node_modules/three'
    if vendor.is_dir():
        app.mount('/vendor/three',StaticFiles(directory=vendor),name='three')

    @app.get('/')
    def index():
        return FileResponse(settings.UI / 'index.html')

    @app.get('/api/health')
    def health():
        return {'status':'ok','version':'0.1.0','viewer_assets_present':vendor.is_dir(),
                'ready_models':sum(not instance.blockers() for instance in instances.values()),
                'note':'Application readiness is separate from pretrained model readiness.'}

    @app.get('/api/models')
    def models():
        result = catalog(data_dir)
        successful = {e['model_id'] for e in store.list() if e['status']=='succeeded' and e.get('task_type')!='import'}
        for model in result:
            if model['id'] in successful:
                model['execution_status'] = '実際に推論成功'
        return result

    async def receive(upload, suffixes):
        suffix = Path(upload.filename or '').suffix.lower()
        if suffix not in suffixes:
            raise HTTPException(415,'対応形式: ' + ', '.join(sorted(suffixes)))
        target = uploads / (uuid.uuid4().hex + suffix)
        total = 0
        try:
            with target.open('wb') as handle:
                while chunk := await upload.read(1024*1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413,'アップロードの上限は32MiBです。')
                    handle.write(chunk)
            if not total:
                raise HTTPException(422,'ファイルが空です。')
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

    def audio_path(identifier):
        if not identifier or not re.fullmatch('[0-9a-f]{32}',identifier):
            raise HTTPException(404,'音声IDが無効です。')
        target = uploads / (identifier + '.wav')
        if not target.is_file():
            raise HTTPException(404,'音声が見つかりません。')
        return target

    @app.post('/api/audio',status_code=201)
    async def upload_audio(file: UploadFile = File(...)):
        target = await receive(file,{'.wav'})
        try:
            info = inspect_wav(target)
        except ValueError as error:
            target.unlink(missing_ok=True)
            raise HTTPException(422,str(error)) from error
        return {'audio_id':target.stem,'url':f'/api/audio/{target.stem}',**info}

    @app.get('/api/audio/{identifier}')
    def download_audio(identifier:str):
        return FileResponse(audio_path(identifier),media_type='audio/wav')

    def prepare(request, name):
        if name not in instances:
            raise HTTPException(404,'未知のモデルです。')
        source = audio_path(request.audio_id) if request.task_type=='audio' else None
        duration = inspect_wav(source)['duration'] if source else request.duration
        if duration > 20:
            raise HTTPException(422,'推論に使用する音声は20秒以内にしてください。取り込み・同期再生は120秒まで対応します。')
        model_input = MotionInput(task_type=request.task_type,text=request.translated_text.strip() or request.text.strip(),
                                  original_text=request.text,audio_path=source,duration=duration,seed=request.seed,model_name=name)
        try:
            instances[name].preflight(model_input)
        except UnavailableError as error:
            raise HTTPException(409,str(error)) from error
        model = next((m for m in catalog(data_dir) if m['id']==name),{})
        return model_input, {'translation':'user_provided' if request.translated_text.strip() else None,
                             'git_commit':model.get('commit'),'model_version':model.get('name'),
                             'checkpoint_repository':model.get('checkpoint'), 'audio_conditioned':source is not None,
                             'gpu_memory_note':'Peak model memory is not measured by external CLI; never substitute an estimate.'}

    @app.post('/api/generate',status_code=202)
    def generate(request:GenerateRequest):
        model_input, details = prepare(request,request.model_name)
        return store.create(model_input,details)

    @app.post('/api/diagnose/ardy',status_code=202)
    def diagnose_ardy(request:DiagnosticRequest):
        instance=instances.get('ardy')
        if instance is None or not hasattr(instance,'diagnostic_blockers'):
            raise HTTPException(409,'ARDY CPU 診断が未設定です。')
        reasons=instance.diagnostic_blockers()
        if reasons:raise HTTPException(409,' / '.join(reasons))
        value=MotionInput(task_type='unconditional_diagnostic',text='',original_text='',audio_path=None,
                          duration=request.duration,seed=request.seed,model_name='ardy')
        return store.create(value,{'text_conditioned':False,'audio_conditioned':False,'trained_model_output':True,
                                   'git_commit':next(m['commit'] for m in catalog(data_dir) if m['id']=='ardy'),
                                   'notice':'学習済み重みの無条件CPU診断。動作指示や会話に対応した生成の成功ではありません。'})

    @app.post('/api/compare',status_code=202)
    def compare(request:CompareRequest):
        batch_id = uuid.uuid4().hex
        results = []
        for name in request.model_names:
            try:
                model_input, details = prepare(request,name)
                results.append(store.create(model_input,{**details,'comparison_id':batch_id}))
            except HTTPException as error:
                results.append({'model_id':name,'status':'rejected','error':error.detail,'http_status':error.status_code})
        return {'comparison_id':batch_id,'results':results}

    @app.get('/api/experiments')
    def experiments():
        return store.list()

    @app.get('/api/experiments.csv')
    def experiment_timings():
        rows=[]
        for record in store.list():
            filename=record.get('artifacts',{}).get('rendered_video_path')
            video=f"/api/experiments/{record['id']}/files/{filename}" if filename else ''
            rows.append(summary_row(record,video))
        return Response(csv_bytes(rows),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="motion-timings.csv"'})

    @app.get('/api/examples/ardy-utterances')
    def ardy_utterances():
        return json.loads((settings.ROOT/'configs/ardy-utterances.json').read_text(encoding='utf-8'))

    @app.get('/api/experiments/{identifier}')
    def experiment(identifier:str):
        try:
            return store.get(identifier)
        except (FileNotFoundError,ValueError):
            raise HTTPException(404,'実験が見つかりません。')

    @app.get('/api/experiments/{identifier}/files/{filename:path}')
    def artifact(identifier:str,filename:str):
        record = experiment(identifier)
        allowed = set(record.get('artifacts',{}).values()) | {'experiment.json','inference.log'}
        if record.get('input_audio'):
            allowed.add('input.wav')
        directory = (output_dir / identifier).resolve()
        target = (directory / filename).resolve()
        if filename not in allowed or not target.is_relative_to(directory) or not target.is_file():
            raise HTTPException(404,'この成果物は見つからないか公開対象外です。')
        return FileResponse(target,filename=target.name)

    @app.post('/api/import',status_code=201)
    async def import_motion(file:UploadFile=File(...), source_up:Literal['Y','Z']=Form('Y'),
                            source_unit:Literal['m','cm','mm']=Form('m'), audio_id:str|None=Form(None)):
        target = await receive(file,{'.json','.npz','.bvh'})
        try:
            motion = read_motion(target,source_up=source_up,source_unit=source_unit)
            return store.imported(target,motion,provenance='user_import',audio=audio_path(audio_id) if audio_id else None)
        except (MotionError,ValueError,KeyError,TypeError,UnicodeError) as error:
            raise HTTPException(422,str(error)) from error
        finally:
            target.unlink(missing_ok=True)

    @app.post('/api/viewer-fixture',status_code=201)
    def fixture(audio_id:str|None=None):
        motion = viewer_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            save_motion(path,motion)
            return store.imported(path,motion,provenance='synthetic_viewer_fixture',audio=audio_path(audio_id) if audio_id else None)

    @app.post('/api/experiments/{identifier}/render')
    def render(identifier:str):
        experiment(identifier)
        try:
            target = store.render(identifier)
            return {'url':f'/api/experiments/{identifier}/files/{target.name}'}
        except (ValueError,RuntimeError) as error:
            raise HTTPException(422,str(error)) from error

    return app


app = create_app()
