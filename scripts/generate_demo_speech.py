#!/usr/bin/env python3
"""Generate one short, explicitly authorized Japanese Realtime response as WAV."""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import wave

from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.realtime import RealtimeConfig, RealtimeService


def generate(text, config, timeout=30):
    """Use GA events, retaining actual provider audio/transcript and usage only."""
    asyncio.run(RealtimeService(config).reserve())
    session = RealtimeService(config).session()
    session['audio']['input']['turn_detection'] = None
    session['audio']['output']['format'] = {'type': 'audio/pcm', 'rate': 24000}
    session['max_output_tokens'] = 256
    session['instructions'] = '自然な日本語で、指定された短い文章だけを読み上げてください。前置きや説明を追加しないでください。'
    started = time.monotonic()
    pcm, transcript, response_id, usage = bytearray(), '', None, None
    with connect('wss://api.openai.com/v1/realtime?model=' + config.model,
                 additional_headers={'Authorization': 'Bearer ' + config.api_key},
                 open_timeout=15, close_timeout=3, max_size=4*1024*1024) as websocket:
        websocket.send(json.dumps({'type': 'session.update', 'session': session}, ensure_ascii=False))
        requested = False
        while time.monotonic() - started < timeout:
            event = json.loads(websocket.recv(timeout=max(.1, timeout-(time.monotonic()-started))))
            kind = event.get('type')
            if kind == 'error':
                error = event.get('error', {})
                # Authentication errors can contain credential fragments; never log messages.
                raise RuntimeError('Realtime API error: ' + str(error.get('code') or error.get('type') or 'unknown'))
            if kind == 'session.updated' and not requested:
                requested = True
                websocket.send(json.dumps({'type': 'conversation.item.create', 'item': {
                    'type': 'message', 'role': 'user', 'content': [{'type': 'input_text',
                    'text': '次の文章だけを読み上げてください：' + text}]}}, ensure_ascii=False))
                websocket.send(json.dumps({'type': 'response.create', 'response': {
                    'output_modalities': ['audio'], 'max_output_tokens': 256}}))
            elif kind == 'response.created':
                response_id = event['response']['id']
            elif kind == 'response.output_audio.delta' and event.get('response_id') == response_id:
                pcm.extend(base64.b64decode(event['delta'], validate=True))
                if len(pcm) > 24000*2*20:
                    raise RuntimeError('Demo speech exceeded 20 seconds; stopped without saving a success result.')
            elif kind == 'response.output_audio_transcript.done' and event.get('response_id') == response_id:
                transcript = event['transcript']
            elif kind == 'response.done' and event['response']['id'] == response_id:
                response = event['response']
                if response.get('status') != 'completed':
                    raise RuntimeError('Realtime response did not complete: ' + str(response.get('status')))
                usage = response.get('usage')
                break
        else:
            raise TimeoutError('Realtime speech generation timed out.')
    if not pcm or len(pcm) % 2 or not transcript:
        raise RuntimeError('Realtime did not return complete PCM16 audio and a transcript.')
    return bytes(pcm), {'response_id': response_id, 'transcript': transcript, 'usage': usage,
                        'generation_wall_seconds': time.monotonic()-started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--text', default='こんにちは。よろしくお願いします。')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-usd', type=float, required=True,
                        help='Explicit one-session allowance, at least 1 USD; not a provider billing cap.')
    parser.add_argument('--model', default=os.environ.get('OPENAI_REALTIME_MODEL', 'gpt-realtime-2.1'))
    parser.add_argument('--voice', default=os.environ.get('OPENAI_REALTIME_VOICE', 'marin'))
    args = parser.parse_args()
    if not math.isfinite(args.budget_usd) or args.budget_usd < 1:
        parser.error('--budget-usd must be at least 1 (one authorized short API response).')
    if not args.text.strip() or len(args.text) > 200:
        parser.error('--text must contain 1–200 characters.')
    if args.output.suffix.lower() != '.wav':
        parser.error('--output must end in .wav.')
    if args.output.exists() or args.output.with_suffix('.json').exists():
        parser.error('Output exists; use a new filename to preserve previous results.')
    api_key = RealtimeConfig.environment().api_key
    if not api_key:
        parser.error('No API key is available (OPENAI_API_KEY, MOTION_LAB_OPENAI_API_KEY, or realtime). Apply the environment secret securely; do not paste it in chat.')
    config = RealtimeConfig(api_key=api_key, enabled=True, model=args.model, voice=args.voice,
                            budget_usd=args.budget_usd, max_calls=1, session_seconds=30)
    try:
        pcm, details = generate(args.text, config)
    except Exception as error:
        # Keep network library exception messages (which may include headers) out of logs.
        message = str(error) if isinstance(error, (RuntimeError, TimeoutError)) else type(error).__name__
        print('Speech generation failed: ' + message.replace(api_key, '[redacted]'), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(pcm)
    metadata = {'schema': 'motion-lab/realtime-speech-v1', 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                'provider': 'OpenAI', 'api': 'Realtime GA WebSocket', 'model': args.model, 'voice': args.voice,
                'synthetic_voice': True, 'requested_text': args.text, 'sample_rate': 24000,
                'duration_seconds': len(pcm)/(24000*2), 'audio_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                'authorized_allowance_usd': 1, 'actual_charge_usd': None, **details}
    args.output.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'wav': str(args.output), 'transcript': details['transcript'],
                      'duration_seconds': metadata['duration_seconds'],
                      'generation_wall_seconds': details['generation_wall_seconds']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
