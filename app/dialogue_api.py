"""Independent batch motion API and optional local research record persistence."""
import hmac
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field

from adapters.base import MotionInput, redact
from app.gesture import PlanInput, plan_gesture
from app.jobs import write_json
from app.realtime import RealtimeService
from app.timing import csv_bytes


class MotionRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=100)
    response_id: str = Field(min_length=1, max_length=100)
    gesture_id: str = Field(min_length=1, max_length=100)
    model_name: str = Field(default='ardy', max_length=100)
    original_text: str = Field(default='', max_length=4000)
    motion_prompt: str = Field(min_length=1, max_length=4000)
    duration: float = Field(default=3, ge=.5, le=20, allow_inf_nan=False)
    seed: int = Field(default=0, ge=0, le=4294967295)
    deadline_ms: int = Field(default=3000, ge=0, le=30000)
    allow_external_demo: bool = False


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ResearchEvent(BaseModel):
    experiment_mode: Literal['A', 'B', 'C', 'D'] = 'D'
    provenance: Literal['live', 'offline_validation'] = 'live'
    name: str = Field(pattern=r'^[a-z_]{1,60}$')
    clock_domain: Literal['client_performance', 'client_audio', 'server_monotonic']
    time_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estimated: bool = False
    turn_id: str = Field(default='', max_length=100)
    response_id: str = Field(default='', max_length=100)
    gesture_id: str = Field(default='', max_length=100)
    detail: str = Field(default='', max_length=2000)


class ResearchSession(BaseModel):
    save_locally: Literal[True]
    experiment_mode: Literal['A', 'B', 'C', 'D'] = 'D'
    provenance: Literal['live', 'offline_validation']
    events: list[ResearchEvent] = Field(max_length=2000)


def mount_dialogue(app, store, instances, data_dir, realtime_service=None):
    service = realtime_service or RealtimeService()
    app.state.realtime = service
    router = APIRouter()
    remote = os.environ.get('MOTION_SERVICE_URL', '').rstrip('/')
    if remote and (not re.fullmatch(r'https?://[^/?#@]+(?::[0-9]+)?', remote)):
        raise ValueError('MOTION_SERVICE_URL must be an HTTP(S) origin without credentials or a path.')
    access_token = os.environ.get('MOTION_SERVICE_ACCESS_TOKEN', '')

    def authorize(request: Request):
        if access_token and not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer '+access_token):
            raise HTTPException(401, 'Motion service authentication required.')

    async def proxy(method, path, body=None):
        headers = {}
        if os.environ.get('MOTION_SERVICE_TOKEN'):
            headers['Authorization'] = 'Bearer '+os.environ['MOTION_SERVICE_TOKEN']
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.request(method, remote+path, json=body, headers=headers)
            except httpx.HTTPError as error:
                raise HTTPException(502, '研究室モーションサービスに接続できません。会話は継続できます。') from error
        if response.status_code >= 400:
            raise HTTPException(response.status_code, 'モーションサービスからエラーが返りました。')
        return Response(response.content, media_type=response.headers.get('content-type', 'application/json'),
                        status_code=response.status_code)

    @router.get('/api/realtime/config')
    def config():
        return {**service.public_config(), 'motion_service': 'remote' if remote else 'local',
                'motion_streaming': False, 'research_audio_saved': False}

    @router.post('/api/realtime/calls')
    async def realtime_call(request: Request):
        # Same-origin browser route. Do not expose a credentialed proxy to foreign pages.
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Same-origin request required.')
        raw = await request.body()
        if len(raw) > 65536:
            raise HTTPException(413, 'SDP too large.')
        try: sdp = raw.decode('utf-8')
        except UnicodeError: raise HTTPException(422, 'Invalid SDP encoding.')
        return Response(await service.call(sdp), media_type='application/sdp')

    @router.post('/api/conversation/plan')
    def plan(value: PlanInput):
        return plan_gesture(value)

    @router.post('/api/conversation/prepare')
    async def prepare(value: TextRequest):
        return await service.prepare_text(value.text)

    def motion_record(identifier):
        try: record = store.get(identifier)
        except (FileNotFoundError, ValueError): raise HTTPException(404, 'Motion request not found.')
        if not record.get('metadata', {}).get('dialogue'):
            raise HTTPException(404, 'Not a dialogue motion request.')
        return record

    def public(record):
        meta = record['metadata']['dialogue']
        return {'request_id': record['id'], **meta, 'status': record['status'], 'transport': 'batch',
                'error': record.get('error'), 'timings': record.get('timings', {}),
                'server_started_monotonic_ms': record.get('server_started_monotonic_ms'),
                'server_finished_monotonic_ms': record.get('server_finished_monotonic_ms'),
                'has_vrma': str(record.get('artifacts', {}).get('original_motion_path', '')).endswith('.vrma'),
                'trained_model_output': record.get('trained_model_output'),
                'cancellation': record.get('cancellation')}

    @router.post('/api/motion/requests', status_code=202, dependencies=[Depends(authorize)])
    async def create_motion(value: MotionRequest):
        if remote: return await proxy('POST', '/api/motion/requests', value.model_dump())
        if value.model_name not in instances:
            raise HTTPException(404, 'Unknown motion model.')
        if (instances[value.model_name].config.get('backend') == 'official_demo'
                and not value.allow_external_demo):
            raise HTTPException(409, 'オンラインデモへの外部送信は許可されていません。ローカルモデルを選択してください。')
        if re.search(r'[\u3040-\u30ff\u3400-\u9fff]', value.motion_prompt):
            raise HTTPException(422, 'Motion prompt must be translated to English.')
        model_input = MotionInput(task_type='instruction', text=value.motion_prompt, original_text=value.original_text,
                                  audio_path=None, duration=value.duration, seed=value.seed, model_name=value.model_name)
        details = {'dialogue': {'turn_id': value.turn_id, 'response_id': value.response_id, 'gesture_id': value.gesture_id,
                    'deadline_ms': value.deadline_ms, 'server_requested_monotonic_ms': time.monotonic()*1000},
                   'translation': 'gesture_planner', 'audio_conditioned': False}
        # Availability checks and inference execute on the existing worker, not in the speech request.
        return public(store.create(model_input, details))

    @router.get('/api/motion/requests/{identifier}', dependencies=[Depends(authorize)])
    async def get_motion(identifier: str):
        if not re.fullmatch('[0-9a-f]{32}', identifier): raise HTTPException(404, 'Invalid ID.')
        if remote: return await proxy('GET', '/api/motion/requests/'+identifier)
        return public(motion_record(identifier))

    @router.delete('/api/motion/requests/{identifier}', dependencies=[Depends(authorize)])
    async def cancel_motion(identifier: str):
        if not re.fullmatch('[0-9a-f]{32}', identifier): raise HTTPException(404, 'Invalid ID.')
        if remote: return await proxy('DELETE', '/api/motion/requests/'+identifier)
        motion_record(identifier)
        return public(store.cancel(identifier))

    @router.get('/api/motion/requests/{identifier}/{format}', dependencies=[Depends(authorize)])
    async def result(identifier: str, format: Literal['motion', 'vrma']):
        if not re.fullmatch('[0-9a-f]{32}', identifier): raise HTTPException(404, 'Invalid ID.')
        if remote: return await proxy('GET', '/api/motion/requests/'+identifier+'/'+format)
        record = motion_record(identifier)
        if record['status'] != 'succeeded': raise HTTPException(409, 'Motion is not available or was invalidated.')
        key = 'normalized_motion_path' if format == 'motion' else 'original_motion_path'
        filename = record.get('artifacts', {}).get(key)
        directory = (store.output_dir/identifier).resolve()
        target = (directory/(filename or '')).resolve()
        if (not filename or not target.is_relative_to(directory) or not target.is_file()
                or format == 'vrma' and target.suffix != '.vrma'):
            raise HTTPException(404, 'Requested artifact missing.')
        return FileResponse(target, media_type='application/json' if format == 'motion' else 'model/gltf-binary')

    @router.post('/api/research/sessions', status_code=201)
    def save_research(value: ResearchSession):
        identifier = uuid.uuid4().hex
        folder = Path(data_dir)/'conversations'
        folder.mkdir(exist_ok=True)
        record = value.model_dump()
        for event in record['events']: event['detail'] = redact(event['detail'])
        write_json(folder/(identifier+'.json'), record)
        return {'id': identifier, 'json_url': '/api/research/sessions/'+identifier,
                'csv_url': '/api/research/sessions/'+identifier+'.csv', 'audio_saved': False}

    @router.get('/api/research/sessions/{identifier}')
    def research(identifier: str):
        csv = identifier.endswith('.csv')
        identifier = identifier.removesuffix('.csv')
        if not re.fullmatch('[0-9a-f]{32}', identifier): raise HTTPException(404, 'Invalid ID.')
        path = Path(data_dir)/'conversations'/(identifier+'.json')
        if not path.is_file(): raise HTTPException(404, 'Record not found.')
        record = json.loads(path.read_text())
        if csv:
            return Response(csv_bytes(record['events'], fields=list(ResearchEvent.model_fields)),
                            media_type='text/csv; charset=utf-8',
                            headers={'Content-Disposition': 'attachment; filename="dialogue-events.csv"'})
        return record

    app.include_router(router)
