"""Separate batch workflow: real speech and a newly generated gesture for every explicit unit."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import wave

from adapters.base import MotionInput, redact
from adapters.registry import adapters
from app import settings
from app.motion import read_motion
from app.timing import csv_bytes


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def split_units(text):
    """Slash is the explicit delimiter; embedded English !/? never creates extra units."""
    return [part.strip() for part in text.split('/') if part.strip()]


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    if plan.get('schema') != 'motion-lab/segmented-dialogue-plan-v1':
        raise ValueError('Unsupported segmented dialogue plan.')
    if plan.get('fps') != 30 or not 0 <= plan.get('blend_ms', 250) <= 1000:
        raise ValueError('Use 30fps and a blend duration between 0 and 1000ms.')
    segments = plan.get('segments', [])
    if not 1 <= len(segments) <= 20:
        raise ValueError('Provide 1–20 explicit speech/gesture units.')
    identifiers = set()
    for segment in segments:
        identifier = segment.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', identifier) or identifier in identifiers:
            raise ValueError('Segment IDs must be unique safe filenames.')
        identifiers.add(identifier)
        if not isinstance(segment.get('text'), str) or not 1 <= len(segment['text'].strip()) <= 200:
            raise ValueError('Each utterance needs 1–200 characters.')
        if not isinstance(segment.get('motion_prompt'), str) or not 1 <= len(segment['motion_prompt'].strip()) <= 4000:
            raise ValueError('Each unit needs an explicit model motion instruction.')
    return plan


def comparable_text(text):
    normalized = unicodedata.normalize('NFKC', text).replace('’', "'").casefold()
    return ''.join(char for char in normalized if char.isalnum())


def speech_info(path):
    with wave.open(str(path)) as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 24000):
            raise ValueError('Segment speech must be PCM16, mono, 24kHz.')
        frames = source.getnframes()
        return {'duration': frames/24000, 'samples': frames, 'sample_rate': 24000}


def assemble_audio(manifest, root):
    """Pad only to frame boundaries. All voices start exactly with their corresponding gesture."""
    root = Path(root)
    destination = root/'timeline.wav'
    with wave.open(str(destination), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
        for unit in manifest['segments']:
            with wave.open(str(root/unit['audio']), 'rb') as source:
                pcm = source.readframes(source.getnframes())
            required_samples = unit['frame_count']*24000//manifest['fps']
            if len(pcm)//2 > required_samples:
                raise ValueError('A segment would truncate speech; refuse to concatenate.')
            output.writeframes(pcm + b'\0\0'*(required_samples-len(pcm)//2))
    return destination


def verify_completed(plan, manifest, root, *, model, fingerprint, seed):
    """An idempotent completed retry preserves the manifest used by existing videos."""
    if manifest['plan_sha256'] != fingerprint or len(manifest['segments']) != len(plan['segments']):
        raise ValueError('Completed output belongs to a different plan.')
    cursor = 0
    for index, (expected, unit) in enumerate(zip(plan['segments'], manifest['segments'])):
        if any(expected[key] != unit[key] for key in ('id', 'text', 'motion_prompt')) or unit['seed'] != seed+index:
            raise ValueError('Completed output has a different segment request.')
        audio = root/unit['audio']; motion = root/unit['motion']
        speech = json.loads((root/unit['speech_metadata']).read_text(encoding='utf-8'))
        receipt = json.loads((root/unit['motion_receipt']).read_text(encoding='utf-8'))
        if (digest(audio) != unit['audio_sha256'] or digest(motion) != unit['motion_sha256']
                or speech['audio_sha256'] != unit['audio_sha256'] or speech['requested_text'] != expected['text']
                or comparable_text(speech['transcript']) != comparable_text(expected['text'])
                or receipt['model'] != model or receipt['seed'] != seed+index
                or receipt['motion_sha256'] != unit['motion_sha256'] or receipt['motion_prompt'] != expected['motion_prompt']
                or read_motion(motion).get('metadata', {}).get('trained_model_output') is not True):
            raise ValueError('Completed speech or gesture provenance does not match.')
        if any(unit[key] != cursor for key in ('start_frame', 'speech_start_frame', 'gesture_start_frame')):
            raise ValueError('Completed output is not synchronized.')
        cursor += unit['frame_count']
        if unit['end_frame'] != cursor:
            raise ValueError('Completed output frame ranges differ.')
    if cursor != manifest['frame_count'] or digest(root/manifest['timeline_audio']) != manifest['timeline_audio_sha256']:
        raise ValueError('Completed timeline hash or duration does not match.')
    return manifest


def load_speech_source(filename, plan):
    """Share the same real utterances for model comparison; verify before copying."""
    filename = Path(filename).resolve(); manifest = json.loads(filename.read_text(encoding='utf-8'))
    if manifest.get('status') != 'generated' or manifest.get('schema') != 'motion-lab/segmented-dialogue-v1':
        raise ValueError('Speech source must be a completed segmented manifest.')
    if len(manifest['segments']) != len(plan['segments']):
        raise ValueError('Speech source has different speech units.')
    result = {}
    for expected, unit in zip(plan['segments'], manifest['segments']):
        if any(unit[key] != expected[key] for key in ('id', 'text')):
            raise ValueError('Speech source text or unit order differs from the plan.')
        paths = {}
        for key in ('audio', 'speech_metadata'):
            path = (filename.parent/unit[key]).resolve()
            if not path.is_relative_to(filename.parent):
                raise ValueError('Speech source artifact escapes its manifest directory.')
            paths[key] = path
        speech = json.loads(paths['speech_metadata'].read_text(encoding='utf-8'))
        if (digest(paths['audio']) != unit['audio_sha256'] or speech['audio_sha256'] != unit['audio_sha256']
                or speech['requested_text'] != expected['text']
                or comparable_text(speech['transcript']) != comparable_text(expected['text'])):
            raise ValueError('Speech source hash or actual transcript differs from the plan.')
        speech_info(paths['audio'])
        result[unit['id']] = paths
    return result, digest(filename)


def generate_segments(config_path, output_dir, *, model='kimodo', budget_usd=0, data_dir=None, seed=0,
                      ardy_backend='local', speech_source=None):
    plan = load_plan(config_path)
    if not math.isfinite(budget_usd) or budget_usd < 0:
        raise ValueError('API allowance must be finite and nonnegative.')
    root = Path(output_dir).resolve(); root.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    source_units, source_fingerprint = load_speech_source(speech_source, plan) if speech_source else ({}, None)
    saved_plan = root/'plan.json'
    if saved_plan.exists() and json.loads(saved_plan.read_text(encoding='utf-8')) != plan:
        raise ValueError('Output contains a different plan. Choose a new output directory.')
    previous_manifest = root/'manifest.json'
    if previous_manifest.exists():
        previous = json.loads(previous_manifest.read_text(encoding='utf-8'))
        if previous['model'] != model:
            raise ValueError('Output belongs to a different motion model.')
        if previous.get('speech_source_manifest_sha256') != source_fingerprint or previous.get('ardy_backend', 'local') != ardy_backend:
            raise ValueError('Existing output used a different speech source or ARDY backend.')
        if previous.get('status') == 'generated':
            return verify_completed(plan, previous, root, model=model, fingerprint=fingerprint, seed=seed)
    write_json(saved_plan, plan)
    adapter = adapters(data_dir).get(model)
    if ardy_backend not in ('local', 'community_demo') or (ardy_backend != 'local' and model != 'ardy'):
        raise ValueError('The optional community backend is only available for ARDY.')
    if model == 'ardy' and ardy_backend == 'community_demo':
        from adapters.ardy_online import ArdyOnlineAdapter
        adapter = ArdyOnlineAdapter(data_dir)
    if adapter is None:
        raise ValueError('Unknown motion model.')
    blockers = adapter.blockers()
    if blockers:
        raise RuntimeError(' / '.join(blockers))
    if hasattr(adapter, 'check_service'):
        adapter.check_service()
    pending_speech = 0 if source_units else sum(not (root/'segments'/unit['id']/'voice.json').exists() for unit in plan['segments'])
    if budget_usd < pending_speech:
        raise ValueError(f'Authorize at least {pending_speech} USD of session allowances for {pending_speech} new speech responses.')
    if model == 'kimodo' and adapter.config.get('backend') == 'official_demo':
        # Readiness check before any paid voice request; never start/resume the provider GPU.
        import urllib.request
        with urllib.request.urlopen('https://huggingface.co/api/spaces/nvidia/Kimodo', timeout=20) as response:
            if json.load(response).get('runtime', {}).get('stage') != 'RUNNING':
                raise RuntimeError('The official Kimodo service is not running.')
    manifest = {'schema': 'motion-lab/segmented-dialogue-v1', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'plan_sha256': fingerprint, 'model': model, 'title': plan['title'], 'fps': plan['fps'],
                'blend_ms': plan.get('blend_ms', 250), 'new_motion_inference': True, 'audio_conditioned_model': False,
                'speech_and_gesture_start_policy': 'same_frame_per_segment', 'segments': []}
    if model == 'ardy':
        manifest['ardy_backend'] = ardy_backend
    if source_units:
        manifest['speech_source_manifest_sha256'] = source_fingerprint
        manifest['speech_reused'] = True
    cursor = 0; began = time.monotonic()
    for index, unit in enumerate(plan['segments']):
        directory = root/'segments'/unit['id']; directory.mkdir(parents=True, exist_ok=True)
        request = {**unit, 'model': model, 'seed': seed+index, 'plan_sha256': fingerprint}
        if source_units:
            request['speech_source_manifest_sha256'] = source_fingerprint
        request_path = directory/'request.json'
        if request_path.exists() and json.loads(request_path.read_text(encoding='utf-8')) != request:
            raise ValueError('Existing segment request differs; use a new output directory.')
        write_json(request_path, request)
        text_path = directory/'speech.txt'
        if text_path.exists() and text_path.read_text(encoding='utf-8') != unit['text']:
            raise ValueError('Existing speech text differs.')
        text_path.write_text(unit['text'], encoding='utf-8')
        voice = directory/'voice.wav'; voice_metadata = directory/'voice.json'
        print(json.dumps({'segment': unit['id'], 'stage': 'speech', 'text': unit['text']}, ensure_ascii=False), flush=True)
        if not voice_metadata.exists():
            if voice.exists():
                raise ValueError('Partial voice output exists without metadata; preserve it and select a new directory.')
            if source_units:
                shutil.copyfile(source_units[unit['id']]['audio'], voice)
                shutil.copyfile(source_units[unit['id']]['speech_metadata'], voice_metadata)
            else:
                subprocess.run([sys.executable, str(settings.ROOT/'scripts/generate_demo_speech.py'), '--text-file', str(text_path),
                                '--output', str(voice), '--budget-usd', '1', '--max-audio-seconds', '10'], check=True)
        speech = json.loads(voice_metadata.read_text(encoding='utf-8'))
        if speech['audio_sha256'] != digest(voice) or speech['requested_text'] != unit['text']:
            raise ValueError('Saved speech provenance does not match the segment.')
        if comparable_text(speech['transcript']) != comparable_text(unit['text']):
            raise ValueError('Actual speech transcript differs from the requested words; do not substitute it silently.')
        audio = speech_info(voice)
        frame_count = max(1, math.ceil(audio['duration']*plan['fps']))
        duration = frame_count/plan['fps']
        if duration > 10:
            raise ValueError('This workflow requires units no longer than 10 seconds; divide this unit explicitly.')
        # The official demo enforces a two-second minimum. Preserve its native result
        # and explicitly retime only playback to the utterance length; never reuse a clip.
        native_duration = max(2, duration) if model == 'kimodo' and adapter.config.get('backend') == 'official_demo' else max(.5, duration)
        if hasattr(adapter, 'native_duration'):
            native_duration = adapter.native_duration(duration)
        motion = directory/'motion.json'; receipt_path = directory/'motion-generation.json'
        print(json.dumps({'segment': unit['id'], 'stage': 'new_gesture', 'duration_seconds': duration,
                          'motion_prompt': unit['motion_prompt']}, ensure_ascii=False), flush=True)
        if not receipt_path.exists():
            if motion.exists():
                raise ValueError('Partial motion output exists without a generation receipt; preserve it before retrying.')
            started = time.monotonic()
            submitted_at = datetime.now(timezone.utc).isoformat()
            value = MotionInput(task_type='instruction', text=unit['motion_prompt'], original_text=unit['text'],
                                audio_path=None, duration=min(10, native_duration+1e-7), seed=seed+index, model_name=model)
            try:
                result = adapter.generate(value, directory)
            except Exception as error:
                write_json(directory/'failure.json', {'stage': 'new_gesture', 'error': redact(str(error)),
                           'input_submitted_at_utc': submitted_at, 'failed_at_utc': datetime.now(timezone.utc).isoformat(),
                           'failed_attempt_seconds': time.monotonic()-started})
                raise
            normalized = Path(result['normalized_motion_path'])
            if normalized.resolve() != motion.resolve():
                raise ValueError('Adapter returned an unexpected normalized motion location.')
            generated = read_motion(motion)
            if generated.get('metadata', {}).get('trained_model_output') is not True:
                raise ValueError('The adapter did not return a trained-model result.')
            elapsed = time.monotonic()-started
            write_json(receipt_path, {'model': model, 'original_text': unit['text'], 'motion_prompt': unit['motion_prompt'],
                                      'seed': seed+index, 'duration_requested': native_duration, 'motion_sha256': digest(motion),
                                      'skeleton_seconds': elapsed, 'input_to_skeleton_seconds': elapsed,
                                      'input_submitted_at_utc': submitted_at, 'skeleton_completed_at_utc': datetime.now(timezone.utc).isoformat(),
                                      'inference_seconds': result.get('inference_time'),
                                      'device': result.get('device'), 'metadata': result.get('metadata', {})})
        generated = read_motion(motion); receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if (receipt['motion_sha256'] != digest(motion) or receipt['motion_prompt'] != unit['motion_prompt']
                or receipt['original_text'] != unit['text'] or receipt['seed'] != seed+index or receipt['model'] != model):
            raise ValueError('Motion receipt does not match this segment.')
        motion_duration = len(generated['positions'])/generated['fps']
        if abs(motion_duration-native_duration) > 1/generated['fps'] + .001:
            raise ValueError('The native model result differs from its requested duration.')
        entry = {'id': unit['id'], 'text': unit['text'], 'motion_prompt': unit['motion_prompt'],
                 'audio': str(voice.relative_to(root)).replace('\\', '/'), 'speech_metadata': str(voice_metadata.relative_to(root)).replace('\\', '/'),
                 'motion': str(motion.relative_to(root)).replace('\\', '/'), 'motion_receipt': str(receipt_path.relative_to(root)).replace('\\', '/'),
                 'audio_sha256': digest(voice), 'motion_sha256': digest(motion), 'audio_seconds': audio['duration'],
                 'motion_seconds': motion_duration, 'frame_count': frame_count, 'start_frame': cursor,
                 'playback_speed': motion_duration/duration, 'playback_seconds': duration,
                 'speech_start_frame': cursor, 'gesture_start_frame': cursor, 'end_frame': cursor+frame_count,
                 'start_seconds': cursor/plan['fps'], 'end_seconds': (cursor+frame_count)/plan['fps'],
                 'speech_generation_seconds': 0 if source_units else speech['generation_wall_seconds'], 'skeleton_seconds': receipt['skeleton_seconds'],
                 'new_gesture_generated': True, 'seed': seed+index}
        entry.update(input_to_skeleton_seconds=receipt['skeleton_seconds'],
                     input_submitted_at_utc=receipt.get('input_submitted_at_utc'),
                     skeleton_completed_at_utc=receipt.get('skeleton_completed_at_utc'))
        if source_units:
            entry.update(speech_reused=True, speech_original_generation_seconds=speech['generation_wall_seconds'])
        manifest['segments'].append(entry); cursor += frame_count
        manifest.update(frame_count=cursor, duration_seconds=cursor/plan['fps'], generation_wall_seconds=time.monotonic()-began)
        write_json(previous_manifest, manifest)
        print(json.dumps({'segment': unit['id'], 'stage': 'ready', 'speech_start_frame': entry['speech_start_frame'],
                          'gesture_start_frame': entry['gesture_start_frame'], 'frame_count': frame_count,
                          'speech_generation_seconds': entry['speech_generation_seconds'],
                          'text_to_skeleton_seconds': entry['skeleton_seconds']}, ensure_ascii=False), flush=True)
    audio = assemble_audio(manifest, root)
    manifest.update(status='generated', timeline_audio=audio.name, timeline_audio_sha256=digest(audio))
    write_json(previous_manifest, manifest)
    fields = ['id', 'text', 'motion_prompt', 'audio_seconds', 'motion_seconds', 'start_seconds', 'end_seconds',
              'speech_start_frame', 'gesture_start_frame', 'speech_generation_seconds', 'skeleton_seconds',
              'input_to_skeleton_seconds', 'input_submitted_at_utc', 'skeleton_completed_at_utc']
    (root/'timings.csv').write_bytes(csv_bytes([{key: unit[key] for key in fields} for unit in manifest['segments']], fields))
    return manifest
