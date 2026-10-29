import os
from dataclasses import dataclass
from urllib.parse import urlparse
from dotenv import load_dotenv

def flag(name, default):
    value = os.getenv(name, str(default)).lower()
    if value not in ("true", "false"):
        raise ValueError(f"{name} must be true or false")
    return value == "true"

@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    api_key: str = ""
    model: str = ""
    base_url: str = "https://api.openai.com/v1"
    json_mode: bool = True
    timeout: float = 20
    session_ttl: float = 900
    max_sessions: int = 128
    history_turns: int = 6
    backend_token: str = ""
    log_enabled: bool = True
    log_content: bool = False
    motion_mapping_file: str = ""

    def __post_init__(self):
        if self.provider not in ("mock", "openai"):
            raise ValueError("LLM_PROVIDER must be mock or openai")
        if self.provider == "openai" and (not self.api_key or not self.model):
            raise ValueError("Live mode requires LLM_API_KEY and LLM_MODEL")
        if urlparse(self.base_url).scheme not in ("http", "https"):
            raise ValueError("LLM_BASE_URL must be HTTP(S)")
        if not (0 < self.timeout <= 60 and 0 < self.session_ttl <= 86400
                and 1 <= self.max_sessions <= 1024 and 0 <= self.history_turns <= 20):
            raise ValueError("Invalid time or capacity limit")

    @classmethod
    def from_env(cls):
        load_dotenv(override=False)
        return cls(provider=os.getenv("LLM_PROVIDER", "mock"), api_key=os.getenv("LLM_API_KEY", ""),
                   model=os.getenv("LLM_MODEL", ""), base_url=os.getenv("LLM_BASE_URL", cls.base_url),
                   json_mode=flag("LLM_JSON_MODE", True), timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
                   session_ttl=float(os.getenv("SESSION_TTL_SECONDS", "900")),
                   max_sessions=int(os.getenv("MAX_SESSIONS", "128")), history_turns=int(os.getenv("HISTORY_TURNS", "6")),
                   backend_token=os.getenv("BACKEND_TOKEN", ""), log_enabled=flag("LOG_ENABLED", True),
                   log_content=flag("LOG_CONTENT", False),
                   motion_mapping_file=os.getenv("MOTION_MAPPING_FILE", ""))
