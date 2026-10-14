"""GA WebRTC SDP bridge. Standard API credentials never leave this process."""
import asyncio
import json
import math
import os
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from app.gesture import PlanInput, plan_gesture


@dataclass
class RealtimeConfig:
    api_key: str = ''
    enabled: bool = False
    model: str = 'gpt-realtime-2.1'
    voice: str = 'marin'
    text_first: bool = False
    planner_model: str = 'gpt-4.1-mini'
    budget_usd: float = 0
    session_allowance_usd: float = 1
    session_seconds: int = 60
    max_calls: int = 3

    @classmethod
    def environment(cls):
        # Cloud network secrets may use their own variable name. OPENAI_API_KEY
        # remains the conventional name for a direct local Windows/Linux key.
        return cls(api_key=(os.environ.get('OPENAI_API_KEY') or
                            os.environ.get('MOTION_LAB_OPENAI_API_KEY') or
                            os.environ.get('realtime') or ''),
                   enabled=os.environ.get('OPENAI_REALTIME_ENABLED') == '1',
                   model=os.environ.get('OPENAI_REALTIME_MODEL', 'gpt-realtime-2.1'),
                   voice=os.environ.get('OPENAI_REALTIME_VOICE', 'marin'),
                   text_first=os.environ.get('OPENAI_TEXT_FIRST_ENABLED') == '1',
                   planner_model=os.environ.get('OPENAI_PLANNER_MODEL', 'gpt-4.1-mini'),
                   budget_usd=float(os.environ.get('OPENAI_API_BUDGET_USD', '0')),
                   session_allowance_usd=float(os.environ.get('OPENAI_SESSION_ALLOWANCE_USD', '1')),
                   session_seconds=min(180, max(10, int(os.environ.get('OPENAI_SESSION_SECONDS', '60')))),
                   max_calls=min(100, max(1, int(os.environ.get('OPENAI_MAX_CALLS', '3')))))


class RealtimeService:
    def __init__(self, config=None, transport=None):
        self.config = config or RealtimeConfig.environment()
        self.transport = transport
        self.calls = 0
        self.reserved_usd = 0.0
        self.lock = asyncio.Lock()
        self.last_accept = 0.0

    def public_config(self):
        c = self.config
        ready = bool(c.api_key and c.enabled and c.budget_usd > 0)
        return {'enabled': ready, 'model': c.model, 'voice': c.voice,
                'text_first_enabled': ready and c.text_first, 'session_seconds': c.session_seconds,
                'offline_available': True, 'transport': 'ga_webrtc_server_mediated',
                'budget_policy': 'preauthorized allowances; actual provider charges are not measured',
                'reason': '' if ready else 'APIキー、実行許可、予算の設定が必要です。オフライン検証は利用できます。'}

    async def reserve(self):
        c = self.config
        if not self.public_config()['enabled']:
            raise HTTPException(503, 'Realtime APIは未設定または実行許可・予算がありません。')
        if not (math.isfinite(c.budget_usd) and math.isfinite(c.session_allowance_usd)
                and c.session_allowance_usd > 0):
            raise HTTPException(503, 'API予算設定が無効です。')
        async with self.lock:
            if self.calls >= c.max_calls or self.reserved_usd + c.session_allowance_usd > c.budget_usd:
                raise HTTPException(429, '設定された接続回数または事前許可額に達しました。')
            self.calls += 1
            self.reserved_usd += c.session_allowance_usd
        # Do not refund failures: a connection timeout can occur after provider work.

    def session(self):
        return {'type': 'realtime', 'model': self.config.model,
                'instructions': '自然な日本語で、短く会話してください。音声の書き起こしを含む通常の音声応答を返してください。動作を実行できたと推測して断言しないでください。',
                'output_modalities': ['audio'], 'max_output_tokens': 512,
                'audio': {'input': {'transcription': {'model': 'gpt-4o-mini-transcribe', 'language': 'ja'},
                                    'turn_detection': {'type': 'server_vad', 'create_response': False,
                                                       'interrupt_response': True, 'silence_duration_ms': 600}},
                          'output': {'voice': self.config.voice}}}

    async def call(self, sdp):
        if len(sdp.encode()) > 65536 or not sdp.startswith('v=0'):
            raise HTTPException(422, 'SDP offerが無効です。')
        await self.reserve()
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            try:
                response = await client.post('https://api.openai.com/v1/realtime/calls',
                    headers={'Authorization': 'Bearer ' + self.config.api_key, 'Accept': 'application/sdp'},
                    files={'sdp': (None, sdp, 'application/sdp'),
                           'session': (None, json.dumps(self.session(), ensure_ascii=False), 'application/json')})
            except httpx.HTTPError as error:
                raise HTTPException(502, 'Realtime接続で通信エラーが発生しました。') from error
        if response.status_code not in (200, 201):
            raise HTTPException(502, f'Realtime APIがHTTP {response.status_code}を返しました。モデル設定・権限・課金設定を確認してください。')
        if not response.text.startswith('v=0'):
            raise HTTPException(502, 'Realtime APIが有効なSDP answerを返しませんでした。')
        return response.text

    async def prepare_text(self, text):
        if not self.config.text_first:
            raise HTTPException(409, 'Text-firstは機能フラグで無効です。')
        await self.reserve()
        schema = {'type': 'object', 'properties': {'reply': {'type': 'string'}, 'motion_prompt': {'type': 'string'},
                   'anchor_text': {'type': 'string'}, 'gesture_type': {'type': 'string',
                   'enum': ['none', 'beat', 'semantic', 'deictic', 'explicit_action']}},
                   'required': ['reply', 'motion_prompt', 'anchor_text', 'gesture_type'], 'additionalProperties': False}
        started = time.monotonic()*1000
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            try:
                response = await client.post('https://api.openai.com/v1/responses',
                    headers={'Authorization': 'Bearer ' + self.config.api_key},
                    json={'model': self.config.planner_model, 'max_output_tokens': 700,
                          'instructions': '日本語の短い返答と英語の動作指示を作成。動作不要ならmotion_promptは空。明示的な指示の左右・順序・方向・部位・継続時間を保持し、新しい動作条件を追加しない。anchor_textはreply中のフレーズ。',
                          'input': text, 'text': {'format': {'type': 'json_schema', 'name': 'reply_gesture',
                                                            'schema': schema, 'strict': True}}})
            except httpx.HTTPError as error:
                raise HTTPException(502, 'Text-firstの通信に失敗しました。') from error
        if response.status_code != 200:
            raise HTTPException(502, f'Text-first APIがHTTP {response.status_code}を返しました。')
        try:
            body = response.json()
            content = ''.join(part.get('text', '') for item in body.get('output', [])
                              for part in item.get('content', []) if part.get('type') == 'output_text')
            result = json.loads(content)
            if set(result) != set(schema['required']) or any(not isinstance(v, str) for v in result.values()):
                raise ValueError()
            if len(result['reply']) > 4000 or len(result['motion_prompt']) > 4000:
                raise ValueError()
            if result['gesture_type'] not in schema['properties']['gesture_type']['enum']:
                raise ValueError()
            if result['anchor_text'] and result['anchor_text'] not in result['reply']:
                raise ValueError()
            if '右' in text and 'left' in result['motion_prompt'].lower() and '左' not in text:
                raise ValueError('side mismatch')
            if '左' in text and 'right' in result['motion_prompt'].lower() and '右' not in text:
                raise ValueError('side mismatch')
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(502, '応答・動作計画の構造または左右の検査に失敗しました。') from error
        known=plan_gesture(PlanInput(turn_id='prepared',response_id='pending',user_text=text,response_text=result['reply']))
        if known.gesture_type=='explicit_action':
            result.update(motion_prompt=known.motion_prompt,anchor_text=known.anchor_text,gesture_type=known.gesture_type)
        elif result['gesture_type']=='explicit_action':
            result.update(motion_prompt='',gesture_type='none',anchor_text='')
        return {**result, 'server_started_monotonic_ms': started,
                'server_finished_monotonic_ms': time.monotonic()*1000,
                'verbatim_speech_guaranteed': False}
