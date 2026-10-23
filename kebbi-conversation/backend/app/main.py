import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from uuid import uuid4
import httpx
from fastapi import FastAPI, Header, HTTPException, Response, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .settings import Settings
from .models import Request, Reply
from .llm import Llm, LlmError
from .sessions import Sessions, CapacityError

log = logging.getLogger("kebbi.events")
log.setLevel(logging.INFO)
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)

def create_app(settings=None, transport=None):
    settings = settings or Settings.from_env()
    sessions = Sessions(settings.session_ttl, settings.max_sessions)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=settings.timeout, transport=transport) as client:
            app.state.llm = Llm(settings, client)
            yield
        sessions.entries.clear()

    app = FastAPI(title="Kebbi conversation", lifespan=lifespan)
    app.state.sessions = sessions

    async def authorized(authorization: str = Header(default="")):
        if settings.backend_token and not secrets.compare_digest(authorization, "Bearer " + settings.backend_token):
            raise HTTPException(401, detail="unauthorized")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_, __):
        # Pydantic errors can contain original user input. Never echo or log them.
        return JSONResponse(status_code=422, content={"detail": "invalid_request"})

    @app.get("/health", dependencies=[Depends(authorized)])
    async def health():
        return {"status": "ok", "provider": settings.provider}

    @app.post("/api/respond", response_model=Reply, dependencies=[Depends(authorized)])
    async def respond(request: Request, response: Response):
        turn = request.conversation_id or str(uuid4())
        started = time.monotonic()
        def event(name, **fields):
            if settings.log_enabled:
                log.info(json.dumps({"conversation_id": turn, "event": name,
                                     "elapsed_ms": round((time.monotonic()-started)*1000, 3), **fields}, ensure_ascii=False))
        event("llm_request_start")
        try:
            async with sessions.conversation(request.session_id) as history:
                reply = await app.state.llm.respond(request, list(history))
                if settings.history_turns:
                    history.extend([{"role": "user", "content": request.text}, {"role": "assistant", "content": reply.speech}])
                    del history[:-2*settings.history_turns]
            event("llm_response_received", gesture=reply.gesture,
                  **({"user_text": request.text, "speech": reply.speech} if settings.log_content else {}))
            response.headers["X-Conversation-Id"] = turn
            response.headers["Cache-Control"] = "no-store"
            return reply
        except CapacityError:
            event("request_rejected", code="session_capacity")
            raise HTTPException(503, detail="session_capacity") from None
        except LlmError as error:
            event("llm_error", code=error.code)
            raise HTTPException(504 if error.code == "llm_timeout" else 502, detail=error.code) from None

    @app.delete("/api/sessions/{session_id}", dependencies=[Depends(authorized)])
    async def forget(session_id: str):
        if not sessions.clear(session_id):
            raise HTTPException(409, detail="session_busy")
        return {"status": "cleared"}
    return app

app = create_app()
