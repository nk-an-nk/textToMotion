"""Conservative Japanese planner. Unsupported instructions stay untranslated, never guessed."""
import re
import uuid
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class GesturePlan(BaseModel):
    turn_id: str = Field(min_length=1, max_length=100)
    response_id: str = Field(min_length=1, max_length=100)
    gesture_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    gesture_type: Literal['idle', 'beat', 'semantic', 'deictic', 'explicit_action', 'none']
    original_text: str = Field(max_length=4000)
    motion_prompt: str = Field(default='', max_length=4000)
    anchor_text: str = Field(default='', max_length=500)
    priority: int = Field(default=0, ge=0, le=100)
    expected_duration_ms: int = Field(default=2000, ge=500, le=20000)
    earliest_start_ms: int = Field(default=0, ge=0, le=20000)
    deadline_ms: int = Field(default=3000, ge=0, le=30000)
    status: str = 'planned'
    translation_method: str = 'conservative_rules'
    synchronization: str = 'phrase_estimate'
    reason: str = ''

    @model_validator(mode='after')
    def valid_window(self):
        if self.deadline_ms < self.earliest_start_ms:
            raise ValueError('deadline precedes earliest start')
        return self


class PlanInput(BaseModel):
    turn_id: str = Field(min_length=1, max_length=100)
    response_id: str = Field(min_length=1, max_length=100)
    user_text: str = Field(default='', max_length=4000)
    response_text: str = Field(default='', max_length=4000)
    motion_prompt_override: str = Field(default='', max_length=4000)
    deadline_ms: int = Field(default=3000, ge=0, le=30000)


def plan_gesture(value: PlanInput) -> GesturePlan:
    text = value.user_text.strip()
    common = dict(turn_id=value.turn_id, response_id=value.response_id, original_text=text,
                  deadline_ms=value.deadline_ms)
    if value.motion_prompt_override.strip():
        durations=re.findall(r'\b(?:for|over)\s+([0-9]+(?:\.[0-9]+)?)\s+seconds?\b',value.motion_prompt_override,re.I)
        duration_ms=round(sum(map(float,durations))*1000) if durations else 2000
        if not 500<=duration_ms<=20000:
            return GesturePlan(**common,gesture_type='none',status='default_only',reason='指定された動作時間は対応範囲0.5〜20秒を超えています。')
        return GesturePlan(**common, gesture_type='explicit_action', priority=100,
                           motion_prompt=value.motion_prompt_override.strip(), translation_method='user_provided',
                           expected_duration_ms=duration_ms,
                           anchor_text=value.response_text[:80])
    # Exact known constructions keep side, order and requested durations. More
    # complex instructions must use the English override or optional LLM planner.
    clean = re.sub(r'[\s、,。.!！?？]', '', text)
    match = re.fullmatch(r'(右|左)手を(?:挙げて|上げて)?(?:手を)?振って(?:ください)?(?:([0-9]+)秒(?:間)?)?', clean)
    if match:
        side = 'right' if match[1] == '右' else 'left'
        duration = int(match[2]) if match[2] else 3
        if not 1<=duration<=20:
            return GesturePlan(**common,gesture_type='none',status='default_only',reason='指定された動作時間は対応範囲1〜20秒を超えています。')
        return GesturePlan(**common, gesture_type='explicit_action', priority=100,
                           motion_prompt=f'Raise your {side} hand and wave for {duration} seconds.',
                           expected_duration_ms=duration*1000, anchor_text=value.response_text[:80])
    if re.fullmatch(r'(?:自己紹介して|自己紹介をして)最後にお辞儀して(?:ください)?', clean):
        anchor = 'よろしく' if 'よろしく' in value.response_text else value.response_text[-15:]
        return GesturePlan(**common, gesture_type='explicit_action', priority=90,
                           motion_prompt='Introduce yourself with small speaking gestures, then bow at the end.',
                           expected_duration_ms=4000, anchor_text=anchor,
                           reason='順序は保持。フレーズの位置と時刻は推定であり、単語時刻ではありません。')
    if re.fullmatch(r'お辞儀して(?:ください)?', clean):
        return GesturePlan(**common, gesture_type='explicit_action', priority=90, motion_prompt='Bow.',
                           anchor_text=value.response_text[:80])
    if any(word in text for word in ('嬉しい', 'うれしい', '嬉しかった')):
        return GesturePlan(**common, gesture_type='semantic', priority=30,
                           motion_prompt='Use small, cheerful upper-body speaking gestures.',
                           anchor_text=value.response_text[:40],
                           reason='会話の感情から提案。生成結果の意味的一致・自然さは別途評価が必要です。')
    return GesturePlan(**common, gesture_type='none', status='default_only',
                       reason='安全に翻訳できる指示がありません。英語の動作指示を指定するかデフォルト動作を使用します。')
