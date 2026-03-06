"""
Sandbox context generation.

Builds the {sandbox_path: text_content} dict that gets uploaded to the
Vercel Sandbox, and generates the file tree string shown in the agent prompt.
"""

from __future__ import annotations

import json

from config import is_demo_mode
from .gong_client import convert_transcript_to_markdown, fetch_gong_transcript
from .mock_data import get_demo_context_files, get_mock_transcript, get_mock_webhook_data
from .models import GongWebhookData


async def generate_files(webhook_data: GongWebhookData) -> dict[str, str]:
    """Return {sandbox_path: content} for all files the agent should see."""
    files: dict[str, str] = {}

    if is_demo_mode():
        transcript = get_mock_transcript()
        effective_webhook = get_mock_webhook_data()
    else:
        transcript = await fetch_gong_transcript(webhook_data.callData.metaData.id)
        effective_webhook = webhook_data

    markdown = convert_transcript_to_markdown(transcript, effective_webhook)

    meta = effective_webhook.callData.metaData
    safe_title = "".join(c if c.isalnum() else "-" for c in (meta.title or "call").lower())
    files[f"gong-calls/{meta.id}-{safe_title}.md"] = markdown
    files["gong-calls/metadata.json"] = json.dumps({
        "callId": meta.id,
        "title": meta.title,
        "scheduled": meta.scheduled,
        "duration": meta.duration,
        "system": meta.system,
        "participants": [
            {"name": p.name, "email": p.emailAddress, "affiliation": p.affiliation, "title": p.title}
            for p in (effective_webhook.callData.parties or [])
        ],
    }, indent=2)

    if is_demo_mode():
        context_files = get_demo_context_files()
        files.update(context_files)

    return files


def generate_file_tree(files: dict[str, str]) -> str:
    """Generate a tree-style listing of sandbox files for the agent prompt."""
    tree: dict = {}
    for path in sorted(files.keys()):
        node = tree
        for part in path.split("/"):
            node = node.setdefault(part, {})

    lines: list[str] = ["."]

    def _walk(node: dict, prefix: str) -> None:
        entries = sorted(node.keys())
        for i, name in enumerate(entries):
            is_last = i == len(entries) - 1
            lines.append(prefix + ("└── " if is_last else "├── ") + name)
            child = node[name]
            if child:
                _walk(child, prefix + ("    " if is_last else "│   "))

    _walk(tree, "")
    return "\n".join(lines)
