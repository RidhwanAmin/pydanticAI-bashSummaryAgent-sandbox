"""
Vercel Sandbox lifecycle — create, upload files, return ready sandbox.

This is the only place that calls Sandbox.create() and write_files().
workflow.py calls setup() to get a ready sandbox; test_sandbox.py calls
it directly for isolated testing.
"""

from __future__ import annotations

import asyncio

from vercel.sandbox.aio import Sandbox
from vercel.sandbox.models import WriteFile

from config import config
from .models import GongWebhookData, LogEntry
from .context import generate_files, generate_file_tree


async def setup(
    webhook_data: GongWebhookData,
    log_queue: asyncio.Queue[LogEntry | None],
) -> tuple[Sandbox, str]:
    """
    Create the sandbox, generate and upload all context files.

    Returns (sandbox, file_tree).
    Caller is responsible for calling sandbox.stop() when done.
    """
    def log(message: str) -> None:
        log_queue.put_nowait(LogEntry(
            time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            level="info",
            context="sandbox",
            message=message,
        ))

    log("Creating sandbox...")
    sandbox = await Sandbox.create(timeout=config.sandbox_timeout)
    log(f"Sandbox created (id={sandbox.sandbox_id})")

    log("Generating context files...")
    files = await generate_files(webhook_data)
    file_names = sorted(files.keys())
    log(f"Files ready ({len(file_names)}):\n" + "\n".join(f"  → {f}" for f in file_names))

    log(f"Uploading {len(file_names)} files...")
    await sandbox.write_files([
        WriteFile(path=path, content=content.encode())
        for path, content in files.items()
    ])
    log("Files uploaded — sandbox filesystem ready")

    return sandbox, generate_file_tree(files)
