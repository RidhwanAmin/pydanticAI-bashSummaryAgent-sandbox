"""
Pydantic models for:
  - Gong webhook payload (input)
  - Gong transcript API response (internal)
  - CallSummaryOutput (structured agent result)

Using Pydantic v2 with Optional fields to match the TypeScript source types.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Gong webhook / API types
# ---------------------------------------------------------------------------

class MetaData(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    scheduled: Optional[str] = None
    started: Optional[str] = None
    duration: Optional[int] = None
    system: Optional[str] = None
    primaryUserId: Optional[str] = None
    direction: Optional[str] = None
    scope: Optional[str] = None
    media: Optional[str] = None
    language: Optional[str] = None
    workspaceId: Optional[str] = None
    meetingUrl: Optional[str] = None
    isPrivate: Optional[bool] = None
    calendarEventId: Optional[str] = None
    customData: Optional[Any] = None
    purpose: Optional[str] = None


class Party(BaseModel):
    id: str
    emailAddress: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    userId: Optional[str] = None
    speakerId: Optional[str] = None
    affiliation: Optional[str] = None  # "Internal" | "External"
    phoneNumber: Optional[str] = None
    methods: Optional[list[str]] = None


class CallContextField(BaseModel):
    name: str
    value: Any


class CallContextObject(BaseModel):
    objectType: str
    objectId: Optional[str] = None
    fields: Optional[list[CallContextField]] = None
    timing: Optional[str] = None


class CallContextEntry(BaseModel):
    system: str
    objects: Optional[list[CallContextObject]] = None


class CallData(BaseModel):
    metaData: MetaData
    parties: Optional[list[Party]] = None
    context: Optional[list[CallContextEntry]] = None


class GongWebhookData(BaseModel):
    callData: CallData


class GongWebhook(GongWebhookData):
    isTest: bool = False
    isPrivate: bool = False


# Gong transcript API response
class TranscriptSentence(BaseModel):
    start: int
    end: int
    text: str


class TranscriptSegment(BaseModel):
    speakerId: str
    topic: str
    sentences: list[TranscriptSentence]


class CallTranscript(BaseModel):
    callId: str
    transcript: list[TranscriptSegment]


class GongApiResponse(BaseModel):
    callTranscripts: list[CallTranscript]


# ---------------------------------------------------------------------------
# Structured agent output
# ---------------------------------------------------------------------------

class Task(BaseModel):
    taskDescription: str
    taskOwner: str
    ownerCompany: Literal["internal", "customer", "partner"]


class Objection(BaseModel):
    description: str
    quote: str
    speaker: str
    speakerCompany: str
    handled: bool
    handledAnswer: str
    handledScore: int  # 0–100
    handledBy: str


class CallSummaryOutput(BaseModel):
    summary: str
    tasks: list[Task]
    objections: list[Objection]


# ---------------------------------------------------------------------------
# SSE log entry (matches TypeScript StreamLogEntry)
# ---------------------------------------------------------------------------

class LogEntry(BaseModel):
    time: str
    context: str
    level: Literal["info", "warn", "error"]
    message: str
    data: Optional[dict[str, Any]] = None
