"""
Standalone test for the Vercel Sandbox filesystem setup.

Imports directly from the sandbox/ package — the same modules the real
agent uses — so this tests the exact same code path in isolation.

Usage:
    uv run python test_sandbox.py
"""

import asyncio
from dotenv import load_dotenv
load_dotenv(".env.local")

from sandbox.mock_data import get_mock_webhook_data
from sandbox import setup


async def main():
    webhook_data = get_mock_webhook_data()
    print("Setting up sandbox (same path as the real agent)...\n")

    log_queue: asyncio.Queue = asyncio.Queue()
    sandbox, file_tree = await setup(webhook_data, log_queue)

    # Drain and print all log entries from setup
    while not log_queue.empty():
        entry = log_queue.get_nowait()
        if entry:
            print(f"[{entry.context}] {entry.message}")

    print(f"\nFile tree:\n{file_tree}")

    # Verify files are accessible inside the sandbox
    print("\n--- find . (inside sandbox) ---")
    result = await sandbox.run_command("find", ["."])
    print(await result.stdout())

    # Keep sandbox alive for inspection
    print("Sandbox is live. Keeping alive for 5 minutes...")
    print("Press Ctrl+C to stop early.\n")
    try:
        for remaining in range(300, 0, -1):
            print(f"  Stopping in {remaining:3d}s  (sandbox_id={sandbox.sandbox_id})", end="\r")
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass

    print("\n")
    await sandbox.stop()
    print("Sandbox stopped.")


asyncio.run(main())
