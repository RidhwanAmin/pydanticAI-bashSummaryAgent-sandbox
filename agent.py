"""
PydanticAI agent — pure agent logic only.

Responsibilities:
  - Define the Agent with its system prompt and output type
  - Register the bash tool that executes commands in an already-running sandbox
  - run_gong_agent() receives a ready sandbox (created + files uploaded by workflow.py)

What this file does NOT do:
  - Create or stop the Vercel Sandbox
  - Generate or upload files
  - Fetch transcripts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic_ai import Agent, RunContext
from vercel.sandbox.aio import Sandbox

from config import config
from sandbox.models import CallSummaryOutput, GongWebhookData, LogEntry


# ---------------------------------------------------------------------------
# Dependency container injected into every tool call via RunContext
# ---------------------------------------------------------------------------

@dataclass
class SandboxDeps:
    sandbox: Sandbox
    log_queue: asyncio.Queue[LogEntry | None]


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert sales call analyst that reviews call transcripts and provides \
actionable insights.

You have access to a bash tool. Use it to explore the call files before writing \
your summary. The filesystem contains:
  - gong-calls/   call transcript(s) as markdown + metadata.json
  - salesforce/   account, opportunity, contacts (demo mode)
  - research/     company research, competitive intel (demo mode)
  - playbooks/    sales playbook (demo mode)

## Exploration strategy
1. ls each directory to orient yourself
2. grep for key topics: pricing, concern, objection, action, next steps
3. cat specific sections you need more detail on

## Summary format
Headline statement (1-2 sentences establishing context).

*{POINT_NAME}*
- Goal: one sentence
- Key Insight: one sentence
- Concerns/Risks: one sentence

Finish with Next Steps listing action items and owners.

## Objection scoring (0-100)
- 0-50  : not handled sufficiently
- 51-70 : partially handled
- 71-90 : well handled
- 91-100: perfectly handled\
"""

TASK_PROMPT = (
    "Analyse this call transcript and provide a comprehensive summary.\n\n"
    "Focus on: key discussion points and decisions, objections or concerns raised, "
    "action items and next steps, overall call assessment.\n\n"
    "Start by exploring the sandbox filesystem with the bash tool."
)

agent: Agent[SandboxDeps, CallSummaryOutput] = Agent(
    model=config.model,
    output_type=CallSummaryOutput,
    deps_type=SandboxDeps,
    system_prompt=SYSTEM_PROMPT,
    defer_model_check=True,
)


# ---------------------------------------------------------------------------
# Bash tool — executes commands in the sandbox filesystem
# ---------------------------------------------------------------------------

@agent.tool
async def bash(ctx: RunContext[SandboxDeps], command: str) -> str:
    """Execute a bash command (grep, cat, ls, find) in the sandbox to explore call files."""
    _log(ctx.deps, "info", "bash", f"$ {command}")

    result = await ctx.deps.sandbox.run_command("bash", ["-c", command])
    stdout = await result.stdout()
    stderr = await result.stderr()
    output = (stdout or stderr or "").strip()

    if output:
        lines = output.splitlines()
        preview = "\n".join(lines[:8])
        if len(lines) > 8:
            preview += f"\n... ({len(lines) - 8} more lines)"
        _log(ctx.deps, "info", "bash-output", preview)

    if result.exit_code != 0:
        _log(ctx.deps, "warn", "bash", f"exit code {result.exit_code}")

    _log(ctx.deps, "info", "agent", "Analyzing results...")
    return output


# ---------------------------------------------------------------------------
# Public entry point — expects a sandbox already created and files uploaded
# ---------------------------------------------------------------------------

async def run_gong_agent(
    webhook_data: GongWebhookData,
    log_queue: asyncio.Queue[LogEntry | None],
    sandbox: Sandbox,
    file_tree: str,
) -> CallSummaryOutput:
    """
    Run the agent against an already-prepared sandbox.

    The caller (workflow.py) is responsible for:
      - creating the sandbox
      - uploading files
      - stopping the sandbox after this returns
    """
    def log(level: str, context: str, message: str) -> None:
        _log_raw(log_queue, level, context, message)

    meta = webhook_data.callData.metaData
    parties = webhook_data.callData.parties or []
    log("info", "agent", f"Call: {meta.title or 'Untitled'}")
    log("info", "agent", f"Participants: {len(parties)}")
    log("info", "agent", f"Calling model: {config.model}")

    instructions = _build_instructions(meta, parties, file_tree)
    deps = SandboxDeps(sandbox=sandbox, log_queue=log_queue)

    result = await agent.run(
        f"{instructions}\n\n{TASK_PROMPT}",
        deps=deps,
    )

    usage = result.usage()
    log("info", "agent", f"Analysis complete — tokens: {usage.total_tokens} total ({usage.input_tokens} input, {usage.output_tokens} output)")
    return result.output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_instructions(meta, parties, file_tree: str) -> str:
    duration_str = f"{meta.duration // 60} minutes" if meta.duration else "Unknown"
    participants = "\n".join(
        f"- {p.name or 'Unknown'} ({p.affiliation or 'Unknown'})"
        + (f" — {p.title}" if p.title else "")
        for p in parties
    )
    return (
        f"## Call Context\n\n"
        f"**Call:** {meta.title or 'Untitled Call'}\n"
        f"**Date:** {meta.scheduled or meta.started or 'Unknown'}\n"
        f"**Duration:** {duration_str}\n"
        f"**System:** {meta.system or 'Unknown'}\n\n"
        f"**Participants:**\n{participants}\n\n"
        f"**Company:** {config.company_name}\n"
        f"**Date:** {datetime.now(timezone.utc).isoformat()}\n\n"
        f"## Sandbox Filesystem\n```\n{file_tree}\n```"
    )


def _log(deps: SandboxDeps, level: str, context: str, message: str) -> None:
    _log_raw(deps.log_queue, level, context, message)


def _log_raw(
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
