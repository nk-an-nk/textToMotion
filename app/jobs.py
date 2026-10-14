import datetime
import hashlib
import json
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.motion import read_motion, metrics, save_motion
from app.render import render_video
from adapters.base import redact


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, content):
    temporary = Path(path).with_suffix('.tmp')
    temporary.write_text(json.dumps(content, ensure_ascii=False, allow_nan=False, indent=2))
    temporary.replace(path)


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


class JobStore:
    def __init__(self, output_dir, adapters):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.adapters = adapters
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='model-inference')
        self.lock = threading.RLock()
        self.render_lock = threading.Lock()
        for path in self.output_dir.glob('*/experiment.json'):
            data = json.loads(path.read_text())
            if data.get('status') in ('queued','running'):
                data.update(status='failed', error='前のサーバープロセスが終了しました。再実行が必要です。')
                write_json(path, data)

    def create(self, request, details):
        identifier = uuid.uuid4().hex
        directory = self.output_dir / identifier
        directory.mkdir()
        if request.audio_path:
            shutil.copyfile(request.audio_path, directory / 'input.wav')
            request.audio_path = directory / 'input.wav'
        experiment = {'id': identifier, 'status':'queued', 'created_at':now(), 'model_id':request.model_name,
                      'task_type':request.task_type, 'input_text':request.original_text, 'model_text':request.text,
                      'duration_requested':request.duration, 'seed':request.seed, 'input_audio': 'input.wav' if request.audio_path else None,
                      'metadata':details, 'artifacts':{}}
        write_json(directory / 'experiment.json',experiment)
        self.executor.submit(self.generate, identifier, request)
        return experiment

    def get(self, identifier):
        if not isinstance(identifier,str) or len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise FileNotFoundError('Invalid experiment id.')
        path = self.output_dir / identifier / 'experiment.json'
        with self.lock:
            return json.loads(path.read_text())

    def update(self, identifier, **fields):
        with self.lock:
            data = self.get(identifier)
            data.update(fields)
            write_json(self.output_dir / identifier / 'experiment.json',data)
        return data

    def list(self):
        return sorted([self.get(path.parent.name) for path in self.output_dir.glob('*/experiment.json')],key=lambda x:x['created_at'],reverse=True)

    def generate(self, identifier, request):
        directory = self.output_dir / identifier
        started = time.monotonic()
        self.update(identifier,status='running',started_at=now())
        try:
            result = self.adapters[request.model_name].generate(request,directory)
            artifacts = {}
            for key in ('original_motion_path','normalized_motion_path','rendered_video_path','motion_spec_path'):
                path = result.get(key)
                if path:
                    path = Path(path).resolve()
                    if not path.is_relative_to(directory.resolve()) or not path.is_file():
                        raise RuntimeError('Adapter returned an invalid or missing output artifact.')
                    artifacts[key] = str(path.relative_to(directory))
            measurements = {}
            normalized = result.get('normalized_motion_path')
            skeleton_type = None
            if normalized:
                motion = read_motion(normalized)
                measurements = metrics(motion)
                skeleton_type = motion['skeleton_type']
            hashes={k:digest(directory/v) for k,v in artifacts.items()}
            skeleton_seconds=time.monotonic()-started
            self.update(identifier,status='succeeded',finished_at=now(),artifacts=artifacts,
                        inference_time=result.get('inference_time'),time_to_first_result=skeleton_seconds,
                        timings={'skeleton_seconds':skeleton_seconds,'mp4_render_seconds':None,'total_seconds':None},
                        checkpoint=result.get('checkpoint'),device=result.get('device'),gpu_peak_memory_bytes=None,
                        skeleton_type=skeleton_type,
                        model_metadata=result.get('metadata',{}),**measurements,
                        artifact_sha256=hashes)
        except Exception as error:
            # Preserve native outputs even if conversion or inference subsequently fails.
            retained = {p.name:p.name for p in directory.iterdir() if p.suffix.lower() in ('.npz','.bvh','.mp4','.wav','.vrma')}
            self.update(identifier,status='failed',finished_at=now(),error=redact(str(error)),artifacts=retained,
                        time_to_failure=time.monotonic()-started)

    def imported(self, original, motion, *, provenance, audio=None):
        identifier = uuid.uuid4().hex
        directory = self.output_dir / identifier
        directory.mkdir()
        target = directory / ('original' + Path(original).suffix.lower())
        shutil.copyfile(original,target)
        # User uploads are not proof of inference in this instance.
        motion.setdefault('metadata',{})['import_provenance'] = provenance
        save_motion(directory / 'motion.json',motion)
        if audio:
            shutil.copyfile(audio,directory / 'input.wav')
        experiment = {'id':identifier,'created_at':now(),'status':'succeeded','model_id':provenance,
                      'task_type':'import','provenance':provenance,'inference_verified':False,
                      'input_audio':'input.wav' if audio else None,'artifacts':{'original_motion_path':target.name,'normalized_motion_path':'motion.json'},
                      **metrics(motion)}
        write_json(directory / 'experiment.json',experiment)
        return experiment

    def render(self, identifier):
        experiment = self.get(identifier)
        directory = self.output_dir / identifier
        filename = experiment.get('artifacts',{}).get('normalized_motion_path')
        if not filename:
            raise ValueError('変換済みモーションがないため動画を生成できません。')
        with self.render_lock:
            started=time.monotonic()
            try:
                target = render_video(read_motion(directory / filename),directory / 'video.mp4',
                                      directory/'input.wav' if experiment.get('input_audio') else None)
            except Exception as error:
                self.update(identifier,render_status='failed',render_error=redact(str(error)))
                raise
            render_seconds=time.monotonic()-started
            skeleton_seconds=experiment.get('timings',{}).get('skeleton_seconds')
            if skeleton_seconds is None and experiment.get('task_type')!='import':
                skeleton_seconds=experiment.get('time_to_first_result')
            timings={'skeleton_seconds':skeleton_seconds,'mp4_render_seconds':render_seconds,
                     'total_seconds':skeleton_seconds+render_seconds if skeleton_seconds is not None else None}
            self.update(identifier,artifacts={**experiment['artifacts'],'rendered_video_path':target.name},
                        timings=timings,render_status='succeeded',render_error=None,
                        artifact_sha256={**experiment.get('artifact_sha256',{}),'rendered_video_path':digest(target)})
        return target

    def close(self):
        self.executor.shutdown(wait=True)
