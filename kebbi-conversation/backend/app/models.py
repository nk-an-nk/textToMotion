from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

GESTURES = ("greet", "acknowledge", "praise", "surprise", "explain", "think", "question", "none")
Language = Literal["en", "ja"]

class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    speech: str = Field(min_length=1, max_length=400)
    gesture: str = Field(min_length=1, max_length=40)
    language: Language
    timing: Literal["speech_start"]

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
    available_gestures: list[str] = Field(default_factory=lambda: list(GESTURES), max_length=8)

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
