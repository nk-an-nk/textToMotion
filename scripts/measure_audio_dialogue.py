#!/usr/bin/env python3
"""Receive a real PCM greeting over Realtime, then measure the teacher response."""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import wave
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.realtime import RealtimeConfig, RealtimeService
from app.segmented_dialogue import comparable_text

STUDENT = '先生、こんにちは！'
TEACHER = 'こんにちは！今日も元気そうだね！英会話の練習を始めましょう'


def pcm_input(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise ValueError('Input must be mono signed 16-bit PCM at 24000 Hz.')
        pcm = wav.readframes(wav.getnframes())
    if not pcm or len(pcm) > 24000 * 2 * 10:
        raise ValueError('Input must contain between zero and ten seconds of audio.')
    return pcm


def measure(student_path, output, config, *, close_timeout=3):
    if output.exists():
        raise ValueError('Existing conversation results are preserved.')
    pcm = pcm_input(student_path)
    asyncio.run(RealtimeService(config).reserve())
    session = RealtimeService(config).session()
    session['audio']['input'].update(format={'type': 'audio/pcm', 'rate': 24000}, turn_detection=None)
    session['audio']['output']['format'] = {'type': 'audio/pcm', 'rate': 24000}
    session['instructions'] = ('あなたは英会話の先生です。生徒から音声で挨拶を受けたら、次の文章だけをそのまま明るく発話してください。'
                               '説明や別の文章を加えないでください：' + TEACHER)
    events = []; teacher_pcm = bytearray(); transcript = ''; student_transcript = ''
    first_input = input_end = first_audio = transcript_done = response_done = None
    asr_done = None; response_id = None; usage = None
    began = time.monotonic()
    with connect('wss://api.openai.com/v1/realtime?model=' + config.model,
                 additional_headers={'Authorization': 'Bearer ' + config.api_key},
                 open_timeout=15, close_timeout=close_timeout, max_size=4 * 1024 * 1024) as socket:
        socket.send(json.dumps({'type': 'session.update', 'session': session}, ensure_ascii=False))
        while time.monotonic() - began < 60:
            event = json.loads(socket.recv(timeout=max(.1, 60 - (time.monotonic() - began))))
            kind = event.get('type'); now = time.monotonic()
            if kind == 'error':
                raise RuntimeError('Realtime error: ' + str(event.get('error', {}).get('code', 'unknown')))
            if kind == 'session.updated' and first_input is None:
                first_input = time.monotonic(); input_at = datetime.now(timezone.utc).isoformat()
                # Send only audio, paced at its recorded rate. No input_text is supplied.
                for offset in range(0, len(pcm), 960):
                    due = first_input + offset / 48000
                    if due > time.monotonic():
                        time.sleep(due - time.monotonic())
                    socket.send(json.dumps({'type': 'input_audio_buffer.append',
                        'audio': base64.b64encode(pcm[offset:offset+960]).decode()}))
                due = first_input + len(pcm) / 48000
                if due > time.monotonic(): time.sleep(due - time.monotonic())
                input_end = time.monotonic(); input_end_at = datetime.now(timezone.utc).isoformat()
                socket.send(json.dumps({'type': 'input_audio_buffer.commit'}))
                socket.send(json.dumps({'type': 'response.create', 'response': {
                    'output_modalities': ['audio'], 'max_output_tokens': 512}}))
            elif kind == 'conversation.item.input_audio_transcription.completed':
                asr_done = now; student_transcript = event['transcript']
                events.append({'event': 'student_transcription_complete', 'seconds_after_student_end': now-input_end})
            elif kind == 'conversation.item.input_audio_transcription.failed':
                raise RuntimeError('Student audio transcription failed.')
            elif kind == 'response.created': response_id = event['response']['id']
            elif kind == 'response.output_audio.delta' and event.get('response_id') == response_id:
                if first_audio is None:
                    first_audio = now
                    events.append({'event': 'teacher_first_audio', 'seconds_after_student_end': now-input_end})
                teacher_pcm.extend(base64.b64decode(event['delta'], validate=True))
                if len(teacher_pcm) > 48000 * 15: raise RuntimeError('Teacher speech exceeded 15 seconds.')
            elif kind == 'response.output_audio_transcript.done' and event.get('response_id') == response_id:
                transcript_done = now; transcript = event['transcript']
                events.append({'event': 'teacher_transcript_complete', 'seconds_after_student_end': now-input_end})
            elif kind == 'response.done' and event['response']['id'] == response_id:
                if event['response']['status'] != 'completed': raise RuntimeError('Teacher response did not complete.')
                response_done = now; usage = event['response'].get('usage')
            if response_done is not None and asr_done is not None: break
    if not teacher_pcm or first_audio is None or response_done is None or asr_done is None:
        raise RuntimeError('Audio input, transcription and completed teacher audio were not verified.')
    if comparable_text(student_transcript) != comparable_text(STUDENT) or comparable_text(transcript) != comparable_text(TEACHER):
        raise RuntimeError('Recognized conversation differs from the controlled comparison text.')
    output.mkdir(parents=True)
    (output/'student.wav').write_bytes(student_path.read_bytes())
    with wave.open(str(output/'teacher.wav'), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(teacher_pcm)
    receipt = {'schema':'motion-lab/audio-input-dialogue-v1','model':config.model,
        'input_transport':'input_audio_buffer.append + commit', 'typed_student_input':False,
        'input_source':'prerecorded_synthetic_voice_replayed_at_recorded_rate',
        'clock_domain':'single_client_monotonic', 'student_audio_seconds':len(pcm)/48000,
        'student_audio_started_at_utc':input_at,'student_audio_ended_at_utc':input_end_at,
        'student_transcript':student_transcript,'teacher_transcript':transcript,
        'teacher_audio_seconds':len(teacher_pcm)/48000,
        'asr_seconds_after_student_end':asr_done-input_end,
        'first_teacher_audio_seconds_after_student_end':first_audio-input_end,
        'teacher_transcript_seconds_after_student_end':transcript_done-input_end,
        'response_done_seconds_after_student_end':response_done-input_end,
        'first_teacher_audio_seconds_after_input_start':first_audio-first_input,
        'events':events,'response_id':response_id,'usage':usage,'actual_charge_usd':None,
        'max_output_tokens':512,'max_teacher_audio_seconds':15,
        'student_sha256':hashlib.sha256((output/'student.wav').read_bytes()).hexdigest(),
        'teacher_sha256':hashlib.sha256((output/'teacher.wav').read_bytes()).hexdigest()}
    (output/'measurement.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    # The same actual response is reused across models, avoiding different teacher audio.
    voice=output/'teacher-speech'/'01'; voice.mkdir(parents=True)
    (voice/'voice.wav').write_bytes((output/'teacher.wav').read_bytes())
    (voice/'voice.json').write_text(json.dumps({'schema':'motion-lab/realtime-speech-v1',
        'requested_text':transcript,'transcript':transcript,'duration_seconds':len(teacher_pcm)/48000,
        'audio_sha256':receipt['teacher_sha256'],'generation_wall_seconds':response_done-input_end,
        'first_audio_seconds':first_audio-input_end,'response_done_seconds':response_done-input_end,
        'model':config.model,'synthetic_voice':True,'input_transport':receipt['input_transport']},ensure_ascii=False,indent=2)+'\n')
    (output/'teacher-plan.json').write_text(json.dumps({'schema':'motion-lab/segmented-dialogue-plan-v1',
        'fps':30,'blend_ms':250,'title':'音声入力から教師の返答',
        'segments':[{'id':'01','text':transcript,'motion_prompt':transcript}]},ensure_ascii=False,indent=2)+'\n')
    (output/'teacher-speech'/'manifest.json').write_text(json.dumps({
        'schema':'motion-lab/segmented-dialogue-v1','status':'generated','new_motion_inference':False,
        'segments':[{'id':'01','text':transcript,'audio':'01/voice.wav','speech_metadata':'01/voice.json',
                     'audio_sha256':receipt['teacher_sha256']}]},ensure_ascii=False,indent=2)+'\n')
    receipt['_student_end_monotonic']=input_end
    return receipt


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--student-wav',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); base=RealtimeConfig.environment()
    if not base.api_key: parser.error('Realtime credential is unavailable.')
    config=RealtimeConfig(api_key=base.api_key,enabled=True,model=base.model,voice=base.voice,
                          budget_usd=1,max_calls=1,session_seconds=60)
    try:
        receipt=measure(args.student_wav,args.output,config)
        print(json.dumps({key:receipt[key] for key in ['student_transcript','teacher_transcript',
            'asr_seconds_after_student_end','first_teacher_audio_seconds_after_student_end',
            'teacher_transcript_seconds_after_student_end','response_done_seconds_after_student_end']},ensure_ascii=False))
    except Exception as error:
        message=str(error) if isinstance(error,(ValueError,RuntimeError)) else type(error).__name__
        print(message.replace(base.api_key,'[REDACTED]'),file=sys.stderr);sys.exit(1)
