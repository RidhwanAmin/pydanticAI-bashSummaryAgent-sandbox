"""
Gong API client.

Fetches call transcripts using Basic Auth (access-key:secret-key).
Converts the raw API response to a readable Markdown document that the
agent can grep/cat inside the sandbox.
"""

import base64
import httpx
from .models import GongApiResponse, GongWebhookData, Party
from config import config


def _auth_header() -> str:
    if not config.gong_access_key or not config.gong_secret_key:
        raise ValueError("Gong API credentials not configured")
    creds = f"{config.gong_access_key}:{config.gong_secret_key}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


async def fetch_gong_transcript(call_id: str) -> GongApiResponse:
    """Fetch transcript for a call from the Gong API."""
    url = f"{config.gong_base_url}/v2/calls/transcript"
    headers = {
        "Authorization": _auth_header(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=headers,
            json={"filter": {"callIds": [call_id]}},
            timeout=30,
        )
    response.raise_for_status()
    return GongApiResponse.model_validate(response.json())


def convert_transcript_to_markdown(
    api_response: GongApiResponse,
    webhook_data: GongWebhookData,
) -> str:
    """Convert Gong API transcript response to Markdown."""
    if not api_response.callTranscripts:
        return "# No transcript available\n"

    call_transcript = api_response.callTranscripts[0]

    # Build speaker ID → Party map
    speaker_map: dict[str, Party] = {}
    if webhook_data.callData.parties:
        for party in webhook_data.callData.parties:
            if party.speakerId:
                speaker_map[party.speakerId] = party

    meta = webhook_data.callData.metaData
    lines: list[str] = ["# Call Transcript\n", "## Call Information\n"]
    lines.append(f"- **Call ID:** {meta.id}")
    if meta.title:
        lines.append(f"- **Title:** {meta.title}")
    if meta.scheduled:
        lines.append(f"- **Scheduled:** {meta.scheduled}")
    if meta.started:
        lines.append(f"- **Started:** {meta.started}")
    if meta.duration is not None:
        lines.append(f"- **Duration:** {_format_duration(meta.duration)}")
    if meta.system:
        lines.append(f"- **System:** {meta.system}")
    lines.append("")

    lines.append("## Participants\n")
    for party in (webhook_data.callData.parties or []):
        aff = party.affiliation or "Unknown"
        entry = f"- **{party.name or 'Unknown'}** ({aff})"
        if party.emailAddress:
            entry += f" - {party.emailAddress}"
        if party.title:
            entry += f" - {party.title}"
        lines.append(entry)
    lines.append("")

    lines.append("## Transcript\n")
    current_topic = ""
    for segment in call_transcript.transcript:
        if segment.topic != current_topic:
            current_topic = segment.topic
            lines.append(f"### {current_topic or 'Conversation'}\n")

        speaker = speaker_map.get(segment.speakerId)
        speaker_name = speaker.name if speaker else f"Speaker {segment.speakerId}"
        speaker_info = _format_speaker_info(speaker) if speaker else f"(ID: {segment.speakerId})"
        lines.append(f"**{speaker_name}** {speaker_info}\n")

        for sentence in segment.sentences:
            ts = _format_timestamp(sentence.start)
            lines.append(f"> [{ts}] {sentence.text}\n")

    return "\n".join(lines)


def _format_speaker_info(speaker: Party) -> str:
    parts = []
    if speaker.affiliation:
        parts.append(speaker.affiliation)
    if speaker.emailAddress:
        parts.append(speaker.emailAddress)
    if speaker.title:
        parts.append(speaker.title)
    return f"_({', '.join(parts)})_" if parts else ""


def _format_timestamp(ms: int) -> str:
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
