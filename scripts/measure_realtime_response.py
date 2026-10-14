#!/usr/bin/env python3
"""Fresh response latency measurements; legacy speech generation stays unchanged."""
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


def measure(text, config):
    asyncio.run(RealtimeService(config).reserve())
    session = RealtimeService(config).session()
    session['audio']['input']['turn_detection'] = None
    session['audio']['output']['format'] = {'type': 'audio/pcm', 'rate': 24000}
    session['max_output_tokens'] = 512
    session['instructions'] = '指定された文章だけを明るく自然に読み上げてください。日本語の部分は日本語、英語の部分は英語の自然な発音にしてください。翻訳、前置き、説明、文章の省略をしないでください。'
    began = time.monotonic()
    submitted = first_audio = audio_done = done = None
    response_id = None
    pcm = bytearray()
    transcript = ''
    usage = None
    with connect('wss://api.openai.com/v1/realtime?model=' + config.model,
                 additional_headers={'Authorization': 'Bearer ' + config.api_key},
                 open_timeout=15, close_timeout=3, max_size=4 * 1024 * 1024) as socket:
        socket.send(json.dumps({'type': 'session.update', 'session': session}, ensure_ascii=False))
        while time.monotonic() - began < 60:
            event = json.loads(socket.recv(timeout=max(.1, 60 - (time.monotonic() - began))))
            kind = event.get('type')
            if kind == 'error':
                raise RuntimeError('Realtime error: ' + str(event.get('error', {}).get('code', 'unknown')))
            if kind == 'session.updated' and submitted is None:
                submitted = time.monotonic()
                submitted_at = datetime.now(timezone.utc).isoformat()
                socket.send(json.dumps({'type': 'conversation.item.create', 'item': {'type': 'message',
                    'role': 'user', 'content': [{'type': 'input_text', 'text': '次の文章だけを読み上げてください：' + text}]}}, ensure_ascii=False))
                socket.send(json.dumps({'type': 'response.create', 'response': {
                    'output_modalities': ['audio'], 'max_output_tokens': 512}}))
            elif kind == 'response.created':
                response_id = event['response']['id']
            elif kind == 'response.output_audio.delta' and event.get('response_id') == response_id:
                if first_audio is None:
                    first_audio = time.monotonic()
                pcm.extend(base64.b64decode(event['delta'], validate=True))
                if len(pcm) > 24000 * 2 * 10:
                    raise RuntimeError('Speech exceeded the 10-second trial limit.')
            elif kind == 'response.output_audio.done' and event.get('response_id') == response_id:
                audio_done = time.monotonic()
            elif kind == 'response.output_audio_transcript.done' and event.get('response_id') == response_id:
                transcript = event['transcript']
            elif kind == 'response.done' and event['response']['id'] == response_id:
                if event['response'].get('status') != 'completed':
                    raise RuntimeError('Speech was not completed.')
                usage = event['response'].get('usage')
                done = time.monotonic()
                break
    if not pcm or first_audio is None or done is None or comparable_text(text) != comparable_text(transcript):
        raise RuntimeError('Audio, completion, or exact requested transcript was not verified.')
    return bytes(pcm), {'input_submitted_at_utc': submitted_at,
        'session_setup_seconds': submitted - began,
        'first_audio_seconds': first_audio - submitted,
        'complete_audio_seconds': audio_done - submitted if audio_done is not None else None,
        'response_done_seconds': done - submitted,
        'generation_wall_seconds': time.monotonic() - began,
        'clock_domain': 'single_client_monotonic', 'response_id': response_id,
        'transcript': transcript, 'usage': usage}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/segmented_english_lesson.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    base = RealtimeConfig.environment()
    if not base.api_key:
        parser.error('Realtime key is unavailable; never paste its value into chat.')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        for unit in json.loads(args.config.read_text())['segments']:
            output = args.output_dir / unit['id'] / 'voice.wav'
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists() or output.with_suffix('.json').exists():
                raise RuntimeError('Existing speech is preserved; choose a new output directory.')
            config = RealtimeConfig(api_key=base.api_key, enabled=True, model=base.model, voice=base.voice,
                                    budget_usd=1, max_calls=1, session_seconds=60)
            pcm, timing = measure(unit['text'], config)
            with wave.open(str(output), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(pcm)
            receipt = {'schema': 'motion-lab/realtime-speech-v1', 'provider': 'OpenAI',
                'api': 'Realtime GA WebSocket', 'model': base.model, 'voice': base.voice,
                'synthetic_voice': True, 'requested_text': unit['text'], 'sample_rate': 24000,
                'duration_seconds': len(pcm) / 48000, 'audio_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'actual_charge_usd': None,
                'max_output_tokens': 512, 'max_audio_seconds': 10, **timing}
            output.with_suffix('.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'id': unit['id'], 'first_audio_seconds': timing['first_audio_seconds'],
                              'response_done_seconds': timing['response_done_seconds'], 'wav': str(output)}), flush=True)
    except Exception as error:
        # Network exceptions can contain headers; retain only safe error classes and controlled messages.
        message = str(error) if isinstance(error, (RuntimeError, TimeoutError)) else type(error).__name__
        print(message.replace(base.api_key, '[REDACTED]'), file=sys.stderr)
        sys.exit(1)
