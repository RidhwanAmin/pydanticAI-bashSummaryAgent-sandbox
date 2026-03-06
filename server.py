"""
FastAPI server — Python equivalent of the Next.js /api/gong-webhook route.

Endpoints:
  POST /webhook/gong  — accepts Gong webhook payload (or {} for demo mode)
                         returns JSON or SSE stream depending on Accept header

SSE streaming:
  Send  Accept: text/event-stream  to get real-time agent logs as Server-Sent Events.
  Each event is a JSON-encoded LogEntry.  The stream ends with data: "[DONE]".

Demo mode:
  Automatically active when GONG_ACCESS_KEY / GONG_SECRET_KEY are not set.
  Uses mock data from call-summary-agent-with-sandbox/demo-files/.

Run:
  uv run uvicorn server:app --reload --port 3000
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(".env.local")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config import is_demo_mode
from sandbox.models import GongWebhook, LogEntry
from sandbox.mock_data import get_mock_webhook_data
from workflow import run_workflow

app = FastAPI(title="Call Summary Agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_webhook_data(body: dict) -> GongWebhook:
    if is_demo_mode():
        mock = get_mock_webhook_data()
        return GongWebhook(**mock.model_dump(), isTest=True, isPrivate=False)
    return GongWebhook.model_validate(body)


async def _sse_generator(webhook: GongWebhook, is_curl: bool):
    """Async generator that yields SSE-formatted log entries."""
    log_queue: asyncio.Queue[LogEntry | None] = asyncio.Queue()

    # Run workflow in background task
    asyncio.create_task(run_workflow(webhook, log_queue))

    while True:
        entry = await log_queue.get()
        if entry is None:
            yield 'data: "[DONE]"\n\n'
            break

        if is_curl:
            time_str = datetime.fromisoformat(entry.time).strftime("%H:%M:%S")
            data_str = f" {json.dumps(entry.data)}" if entry.data else ""
            output = f"[{time_str}] [{entry.context}] {entry.message}{data_str}"
        else:
            output = entry.model_dump_json()

        yield f"data: {output}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/webhook/gong")
async def gong_webhook(request: Request):
    accept = request.headers.get("accept", "")
    wants_stream = "text/event-stream" in accept
    is_curl = "curl" in request.headers.get("user-agent", "").lower()

    try:
        body = await request.json()
    except Exception:
        body = {}

    if is_demo_mode():
        print("Demo mode: using mock webhook data")

    webhook = _get_webhook_data(body)

    if wants_stream:
        return StreamingResponse(
            _sse_generator(webhook, is_curl),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: run workflow synchronously and return JSON summary
    log_queue: asyncio.Queue[LogEntry | None] = asyncio.Queue()
    summary = await run_workflow(webhook, log_queue)

    return JSONResponse(
        content={
            "message": "Workflow complete",
            "callId": webhook.callData.metaData.id,
            "summary": summary.model_dump(),
        }
    )


@app.get("/")
async def root():
    return {"status": "ok", "demo_mode": is_demo_mode()}
