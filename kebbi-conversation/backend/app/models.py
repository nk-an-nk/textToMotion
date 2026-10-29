from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BASIC_GESTURES = ("greet", "acknowledge", "praise", "surprise", "explain", "think", "question", "none")
GESTURES = (*BASIC_GESTURES[:-1], "joy", "empathy", "encourage", "apologize", "farewell", "confused", "excited", "calm", "sadness", "anger", "fear", "disgust", "affection", "animal", "dance", "exercise", "daily_action", "movement", "none")
GESTURE_DESCRIPTIONS = dict(zip(GESTURES, (
    "greeting", "acknowledging/listening", "specific praise", "surprise", "explaining",
    "thinking", "asking a question", "quiet happiness", "empathy/comfort", "encouragement",
    "apology", "saying goodbye", "gentle confusion", "excitement", "calming/reassuring", "expressing sadness", "expressing anger", "fear or being scared", "disgust", "affection or a hug", "imitating an animal", "dancing or playing music", "sports or exercise", "acting out an everyday action", "looking, pointing or moving directionally", "no motion")))

class MotionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=300)

    @field_validator("id", "description")
    @classmethod
    def clean_candidate(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("invalid candidate")
        return value.strip()
Language = Literal["en", "ja"]

def split_sentences(text):
    """Split Japanese/English end punctuation, preserving decimal numbers and quotes."""
    parts=[];start=0;i=0
    while i < len(text):
        c=text[i]
        boundary=c in "。！？!?" or (c=="." and (i+1==len(text) or text[i+1].isspace()))
        if boundary:
            j=i+1
            while j<len(text) and text[j] in "。！？!?.\"'」』）)":j+=1
            part=text[start:j].strip()
            if part:parts.append(part)
            start=j;i=j
        else:i+=1
    tail=text[start:].strip()
    if tail:parts.append(tail)
    return parts

class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    speech: str = Field(min_length=1, max_length=400)
    gesture: str = Field(min_length=1, max_length=40)
    motion_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("speech")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():raise ValueError("empty sentence")
        return value.strip()

class SentencePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sentences: list[Sentence] = Field(min_length=1, max_length=6)
    language: Language
    timing: Literal["speech_start"]

    @model_validator(mode="after")
    def bounded(self):
        if sum(len(s.speech) for s in self.sentences)>400:raise ValueError("reply too long")
        return self

class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    speech: str = Field(min_length=1, max_length=400)
    gesture: str = Field(min_length=1, max_length=40)
    language: Language
    timing: Literal["speech_start"]
    motion_id: str | None = Field(default=None, min_length=1, max_length=200)

    sentences: list[Sentence] | None = Field(default=None, min_length=1, max_length=6)

    @field_validator("speech")
    @classmethod
    def clean_speech(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("empty speech")
        return value

    @field_validator("gesture")
    @classmethod
    def safe_gesture(cls, value):
        return value if value in GESTURES else "none"

class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    session_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=1000)
    language: Language = "en"
    available_gestures: list[str] = Field(default_factory=lambda: list(GESTURES), max_length=26)
    sentence_plan: bool = False
    selection_mode: Literal["category", "direct"] = "category"
    gesture_profile: Literal["basic", "expanded"] = "basic"
    available_motions: list[MotionCandidate] = Field(default_factory=list, max_length=4096)

    @field_validator("conversation_id")
    @classmethod
    def valid_turn_id(cls, value):
        if value is not None:
            UUID(value)
        return value

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("empty text")
        return value.strip()

    @field_validator("available_gestures")
    @classmethod
    def allowed_categories(cls, value):
        if any(g not in GESTURES for g in value):
            raise ValueError("unknown category")
        return list(dict.fromkeys([*value, "none"]))

    @property
    def allowed_gestures(self):
        supported = BASIC_GESTURES if self.gesture_profile == "basic" else GESTURES
        return [g for g in self.available_gestures if g in supported]

    @property
    def history_key(self):
        if self.selection_mode == "category" and self.gesture_profile == "basic":
            return self.session_id
        return self.session_id + ":" + self.selection_mode + ":" + self.gesture_profile
