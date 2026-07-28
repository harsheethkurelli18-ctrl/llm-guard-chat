import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.llm.client import LLMClient
from app.models import ChatRequest
from app.security.output_filter import scrub_output
from app.security.prompt_guard import guard_input
from app.security.rate_limiter import RateLimiter

router = APIRouter()
logger = logging.getLogger("llm_guard_chat.chat")

llm_client = LLMClient()
rate_limiter = RateLimiter(max_requests=settings.rate_limit_per_minute, window_seconds=60)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"

    if not rate_limiter.allow(client_ip):
        retry = rate_limiter.retry_after(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry:.0f}s.",
        )

    user_text = payload.last_user_message()

    if len(user_text) > settings.max_message_length:
        raise HTTPException(status_code=413, detail="Message too long.")

    guard_result = guard_input(user_text, settings.injection_block_threshold)

    if guard_result.blocked:
        logger.warning(
            "Blocked message from %s (score=%.2f): %s",
            client_ip, guard_result.risk_score, guard_result.reasons,
        )

        async def blocked_stream():
            yield _sse("guard", {
                "blocked": True,
                "risk_score": guard_result.risk_score,
                "reasons": guard_result.reasons,
            })
            yield _sse("done", {})

        return StreamingResponse(blocked_stream(), media_type="text/event-stream")

    messages = [{"role": m.role, "content": m.content} for m in payload.messages]

    async def event_stream():
        yield _sse("guard", {
            "blocked": False,
            "risk_score": guard_result.risk_score,
            "reasons": guard_result.reasons,
        })

        buffer = []
        provider_used = None
        try:
            async for chunk, provider_name in llm_client.stream_reply(
                messages, settings.system_prompt
            ):
                provider_used = provider_name
                buffer.append(chunk)
                # Stream raw chunks for responsiveness; final scrub happens
                # on the assembled text below in case a leak spans chunks.
                yield _sse("token", {"text": chunk})
        except RuntimeError as exc:
            yield _sse("error", {"message": str(exc)})
            yield _sse("done", {})
            return

        full_text = "".join(buffer)
        scrubbed, was_redacted = scrub_output(full_text, settings.system_prompt)
        if was_redacted:
            logger.warning("Redacted a suspected system-prompt leak in model output.")
            yield _sse("redaction_notice", {"redacted": True})

        yield _sse("done", {"provider": provider_used})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "primary_provider": llm_client.primary.name if llm_client.primary else None,
        "fallback_enabled": llm_client.fallback is not None,
    }
