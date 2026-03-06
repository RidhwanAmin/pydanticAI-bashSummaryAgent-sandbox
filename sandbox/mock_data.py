"""
Demo mode data loader.

Loads mock webhook payload, transcript, and context files from the
call-summary-agent-with-sandbox/demo-files/ directory — the same demo data
as the TypeScript original, so behaviour is identical in demo mode.
"""

import json
from pathlib import Path
from .models import GongApiResponse, GongWebhookData

# Point at the sibling project's demo files so we don't duplicate them
DEMO_DIR = Path(__file__).parent.parent / "demo-files"


def get_mock_webhook_data() -> GongWebhookData:
    raw = json.loads((DEMO_DIR / "webhook-data.json").read_text())
    return GongWebhookData.model_validate(raw)


def get_mock_transcript() -> GongApiResponse:
    raw = json.loads((DEMO_DIR / "transcript.json").read_text())
    return GongApiResponse.model_validate(raw)


# Paths of context files relative to demo-files/context/ → sandbox paths
_CONTEXT_FILES: list[tuple[str, str]] = [
    ("context/gong-calls/previous/demo-call-000-discovery-call.md",  "gong-calls/previous/demo-call-000-discovery-call.md"),
    ("context/gong-calls/previous/demo-call-intro-initial-call.md",  "gong-calls/previous/demo-call-intro-initial-call.md"),
    ("context/salesforce/account.md",                                 "salesforce/account.md"),
    ("context/salesforce/opportunity.md",                             "salesforce/opportunity.md"),
    ("context/salesforce/contacts.md",                                "salesforce/contacts.md"),
    ("context/research/company-research.md",                          "research/company-research.md"),
    ("context/research/competitive-intel.md",                         "research/competitive-intel.md"),
    ("context/playbooks/sales-playbook.md",                           "playbooks/sales-playbook.md"),
]


def get_demo_context_files() -> dict[str, str]:
    """Return {sandbox_path: content} for all demo context files."""
    result: dict[str, str] = {}
    for demo_rel, sandbox_path in _CONTEXT_FILES:
        content = (DEMO_DIR / demo_rel).read_text()
        result[sandbox_path] = content
    return result
