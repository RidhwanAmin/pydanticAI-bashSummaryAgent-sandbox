"""
Workflow orchestrator — owns the full sandbox lifecycle and step sequencing.

Steps:
  1. step_get_transcript   — fetch (or mock) Gong transcript, log early status
  2. step_setup_sandbox    — create Vercel Sandbox, generate files, upload them
  3. step_run_agent        — hand pre-ready sandbox to agent.run_gong_agent()
  4. step_emit_result      — log final structured summary

Separation of concerns:
  - workflow.py  creates/stops the sandbox and uploads files
  - agent.py     only runs the agent against a ready sandbox
  - test_sandbox.py  independently tests step 2 in isolation
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from vercel.sandbox.aio import Sandbox

from config import is_demo_mode
from sandbox.gong_client import fetch_gong_transcript
from sandbox.models import CallSummaryOutput, GongWebhook, GongWebhookData, LogEntry
from sandbox import setup as setup_sandbox
from agent import run_gong_agent


# ---------------------------------------------------------------------------
# Shared log helper
# ---------------------------------------------------------------------------

def _log(
    queue: asyncio.Queue[LogEntry | None],
    level: str,
    context: str,
    message: str,
) -> None:
    queue.put_nowait(LogEntry(
        time=datetime.now(timezone.utc).isoformat(),
        level=level,  # type: ignore[arg-type]
        context=context,
        message=message,
    ))


# ---------------------------------------------------------------------------
# Step 1 — transcript
# ---------------------------------------------------------------------------

async def step_get_transcript(
    webhook: GongWebhook,
    log_queue: asyncio.Queue[LogEntry | None],
) -> None:
    """Fetch (or mock) the transcript and log early status to the SSE stream."""
    call_id = webhook.callData.metaData.id
    _log(log_queue, "info", "workflow", "Workflow started")

    if is_demo_mode():
        _log(log_queue, "info", "transcript", "Demo mode — using mock transcript")
    else:
        _log(log_queue, "info", "transcript", f"Fetching transcript (callId={call_id})")
        try:
            await fetch_gong_transcript(call_id)
            _log(log_queue, "info", "transcript", "Transcript fetched")
        except Exception as exc:
            _log(log_queue, "error", "transcript", f"Failed to fetch transcript: {exc}")
            raise


# ---------------------------------------------------------------------------
# Step 2 — sandbox setup
# ---------------------------------------------------------------------------

async def step_setup_sandbox(
    webhook_data: GongWebhookData,
    log_queue: asyncio.Queue[LogEntry | None],
) -> tuple[Sandbox, str]:
    """
    Create the Vercel Sandbox, generate all context files, upload them.

    Returns (sandbox, file_tree) — caller must call sandbox.stop() when done.
    Delegates entirely to sandbox.setup() so test_sandbox.py can call that directly.
    """
    return await setup_sandbox(webhook_data, log_queue)


# ---------------------------------------------------------------------------
# Step 3 — agent
# ---------------------------------------------------------------------------

async def step_run_agent(
    webhook_data: GongWebhookData,
    log_queue: asyncio.Queue[LogEntry | None],
    sandbox: Sandbox,
    file_tree: str,
) -> CallSummaryOutput:
    """Run the PydanticAI agent against the prepared sandbox."""
    _log(log_queue, "info", "agent", "Starting AI agent")
    return await run_gong_agent(webhook_data, log_queue, sandbox, file_tree)


# ---------------------------------------------------------------------------
# Step 4 — emit result
# ---------------------------------------------------------------------------

async def step_emit_result(
    summary: CallSummaryOutput,
    log_queue: asyncio.Queue[LogEntry | None],
) -> None:
    """Log the final structured summary to the SSE stream."""
    _log(log_queue, "info", "result", "--- Generated Summary ---")
    _log(log_queue, "info", "result", summary.summary)
    _log(log_queue, "info", "workflow", "Workflow complete")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_workflow(
    webhook: GongWebhook,
    log_queue: asyncio.Queue[LogEntry | None],
) -> CallSummaryOutput:
    """Run all four steps. Sandbox is created here and always stopped in finally."""
    sandbox: Sandbox | None = None
    try:
        # Step 1 — early transcript logging
        await step_get_transcript(webhook, log_queue)

        # Step 2 — sandbox + file upload
        sandbox, file_tree = await step_setup_sandbox(webhook, log_queue)

        # Step 3 — agent logs directly to main stream
        summary = await step_run_agent(webhook, log_queue, sandbox, file_tree)

        # Step 4 — emit result
        await step_emit_result(summary, log_queue)
        return summary

    finally:
        if sandbox:
            try:
                await sandbox.stop()
            except Exception:
                pass
        await log_queue.put(None)  # signal end of SSE stream
