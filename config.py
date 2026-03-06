"""
Centralized configuration loaded from environment variables.

Demo mode is automatically enabled when Gong credentials are absent,
allowing the app to run end-to-end with mock data and no external API keys.
"""

import os


def is_demo_mode() -> bool:
    """True when Gong credentials are missing — uses mock data instead of live API."""
    return not os.getenv("GONG_ACCESS_KEY") or not os.getenv("GONG_SECRET_KEY")


class Config:
    company_name: str = os.getenv("COMPANY_NAME", "Your Company")
    # OpenAI model — swap to e.g. "openai:gpt-4o-mini" for cost savings
    model: str = os.getenv("AI_MODEL", "openai:gpt-4o")

    gong_base_url: str = os.getenv("GONG_BASE_URL", "https://api.gong.io")
    gong_access_key: str = os.getenv("GONG_ACCESS_KEY", "")
    gong_secret_key: str = os.getenv("GONG_SECRET_KEY", "")

    # Sandbox timeout in milliseconds (10 minutes)
    sandbox_timeout: int = 600_000


config = Config()
