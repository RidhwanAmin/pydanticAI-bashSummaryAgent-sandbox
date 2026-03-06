## Project Overview

Python re-implementation of `call-summary-agent-with-sandbox` — an AI-powered
sales call summary agent that:

1. Receives a Gong webhook (or uses mock data in **demo mode**)
2. Fetches the call transcript from the Gong API
3. Uploads the transcript + context files into a **Vercel Sandbox**
4. Runs a **PydanticAI agent** (OpenAI GPT-4o) that iteratively calls a `bash` tool
   (`grep`, `cat`, `ls`, `find`) to explore the sandbox filesystem
5. Returns a **structured summary** — key discussion points, action items with
   ownership, and objections with handling scores
6. Streams real-time agent logs to the caller via **Server-Sent Events (SSE)**

The TypeScript original used Next.js + Vercel Workflow DevKit + AI SDK.
This Python version uses FastAPI + asyncio + PydanticAI — same behaviour,
same demo data, same sandbox approach.

---

## Tech Stack

| Layer | TypeScript original | Python equivalent |
|---|---|---|
| Web framework | Next.js App Router | FastAPI + Uvicorn |
| AI agent | AI SDK `ToolLoopAgent` | PydanticAI `Agent` |
| LLM model | Anthropic Claude Haiku | **OpenAI GPT-4o** |
| Structured output | Zod schema | Pydantic `BaseModel` |
| Code sandbox | `@vercel/sandbox` + `bash-tool` npm | `vercel.sandbox.aio.Sandbox` + `@agent.tool bash()` |
| Durable workflow | Vercel Workflow DevKit | Plain `asyncio` (no Python SDK equivalent) |
| SSE streaming | `ReadableStream` + `WritableStream` | `asyncio.Queue` + FastAPI `StreamingResponse` |
| HTTP client | `fetch` | `httpx` |

---

## File Structure

```
pydanticai-bash/
├── server.py          # FastAPI app — POST /webhook/gong, GET /
├── workflow.py        # 4-step orchestrator; owns sandbox lifecycle
├── agent.py           # PydanticAI Agent + bash tool; receives ready sandbox
├── config.py          # Env-var config; is_demo_mode()
├── main.py            # Scratch file — basic Vercel Sandbox smoke test
├── test_sandbox.py    # Standalone test for sandbox setup; keeps alive 5 min
├── pyproject.toml     # uv project — Python 3.13
├── sandbox/
│   ├── __init__.py    # Public API: setup, generate_files, generate_file_tree
│   ├── setup.py       # Sandbox.create() + write_files(); returns (sandbox, file_tree)
│   ├── context.py     # generate_files(), generate_file_tree() with recursive _walk()
│   ├── models.py      # Pydantic models: GongWebhook, CallSummaryOutput, LogEntry, …
│   ├── gong_client.py # Gong API Basic-Auth client; transcript → Markdown converter
│   └── mock_data.py   # Load demo-files/ from sibling TS project (no duplication)
└── call-summary-agent-with-sandbox/   # Original TypeScript project (reference + demo data)
    └── demo-files/    # Shared mock data — used directly by sandbox/mock_data.py
```

### Import conventions

- Files **inside** `sandbox/` use **relative imports**: `from .models import ...`
- Files **outside** `sandbox/` import the package: `from sandbox import setup` or `from sandbox.models import ...`
- `config.py` is at root and imported directly by all files: `from config import config`

---

## Workflow Steps

`run_workflow()` in `workflow.py` owns the full lifecycle and runs 4 steps sequentially:

```
step 1 — step_get_transcript()
    ├── demo mode: no-op (mock transcript used later in step 2)
    └── live mode: fetch_gong_transcript(call_id) via Gong API

step 2 — step_setup_sandbox()  →  delegates to sandbox/setup.py
    ├── Sandbox.create(timeout=600_000)   # 10 min, milliseconds
    ├── generate_files(webhook_data)       # builds {path: content} dict
    │     ├── convert transcript → Markdown
    │     ├── write metadata.json
    │     └── load demo context files (demo mode only)
    ├── sandbox.write_files([WriteFile(path, content.encode())])
    └── generate_file_tree(files)         # returns tree string for agent prompt

step 3 — step_run_agent()  →  delegates to agent.py
    ├── agent.run(prompt, deps=SandboxDeps(sandbox, log_queue))
    │     └── bash tool loop:
    │           └── sandbox.run_command("bash", ["-c", command])
    └── returns CallSummaryOutput (validated Pydantic model)

step 4 — step_emit_result()
    └── logs summary + "Workflow complete" to SSE stream

finally:
    ├── sandbox.stop()
    └── log_queue.put(None)   # signals SSE stream end
```

---

## Key Design Decisions

### Why OpenAI instead of Anthropic?
User preference. Change `AI_MODEL` env var or edit `config.py` to switch models.
PydanticAI supports `openai:gpt-4o`, `openai:gpt-4o-mini`, `anthropic:claude-haiku-4-5`, etc.

### Why PydanticAI?
- **Structured output without boilerplate** — `output_type=CallSummaryOutput` returns a
  validated Pydantic model directly; no manual JSON parsing.
- **Tool support** — `@agent.tool` registers the bash function; `RunContext[Deps]` gives
  the tool access to the sandbox and log queue.
- **`defer_model_check=True`** — module-level `Agent(...)` definition does not initialize
  the OpenAI client at import time, so `OPENAI_API_KEY` isn't required until `agent.run()`.
- **Model-agnostic** — swap OpenAI for Anthropic/Gemini by changing the model string.

### Why Vercel Sandbox + custom bash tool?
Files are uploaded to a real isolated filesystem. The agent calls `grep`, `cat`, `ls`,
`find` exactly like the TypeScript `bash-tool` npm package. This is token-efficient —
the model only reads what it needs per tool call instead of loading all files into context.

`@agent.tool async def bash(ctx, command)` wraps `sandbox.run_command("bash", ["-c", command])`
and logs every command + output preview to the SSE stream.

### Separation of concerns: agent vs sandbox
- `agent.py` — **never** creates or stops the sandbox; it only receives a ready one
- `sandbox/setup.py` — **only** place that calls `Sandbox.create()` and `write_files()`
- `workflow.py` — owns the sandbox lifetime; creates in step 2, stops in `finally`
- `test_sandbox.py` — tests steps 1+2 in isolation without running the agent

### Why `asyncio.Queue` for SSE instead of WritableStream/ReadableStream?
Python's standard asyncio primitives replace JS's Web Streams API. The queue is
shared between the background workflow task and the FastAPI `StreamingResponse`
generator — same producer/consumer pattern, different runtime.

### Why plain asyncio instead of a durable workflow SDK?
There is no Python equivalent of Vercel Workflow DevKit. For production you could
wrap the steps in Temporal, Celery, or Prefect. The step functions in `workflow.py`
are designed to be drop-in replaceable.

### Why reuse demo-files from the sibling TypeScript project?
Avoids duplicating ~8 large Markdown context files. `sandbox/mock_data.py` reads
directly from `call-summary-agent-with-sandbox/demo-files/` using a relative path
(`Path(__file__).parent.parent / "call-summary-agent-with-sandbox" / "demo-files"`).

---

## Running

```bash
# Install dependencies
uv sync

# Minimum .env.local required:
# OPENAI_API_KEY=sk-...

# Start server (demo mode if no Gong keys set)
uv run uvicorn server:app --reload --port 3000
```

### Trigger a demo run (streaming SSE)
```bash
curl -X POST http://localhost:3000/webhook/gong \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{}'
```

### Trigger a non-streaming run (returns JSON summary)
```bash
curl -X POST http://localhost:3000/webhook/gong \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Test sandbox setup only (no agent, keeps alive 5 min)
```bash
uv run python test_sandbox.py
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key |
| `AI_MODEL` | No | `openai:gpt-4o` | PydanticAI model string |
| `COMPANY_NAME` | No | `Your Company` | Injected into agent system prompt |
| `GONG_ACCESS_KEY` | No | — | Gong API key (demo mode if missing) |
| `GONG_SECRET_KEY` | No | — | Gong API secret (demo mode if missing) |
| `GONG_BASE_URL` | No | `https://api.gong.io` | Gong API base URL |

---

## Structured Output Schema

```python
class CallSummaryOutput(BaseModel):
    summary: str                   # Formatted markdown summary

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
    handledScore: int              # 0–100
    handledBy: str
```

---

## Demo Mode

Enabled automatically when `GONG_ACCESS_KEY` or `GONG_SECRET_KEY` is not set.

Sandbox files uploaded in demo mode:
```
gong-calls/
├── demo-call-001-companyname---product-demo.md   # current call transcript
├── metadata.json
└── previous/
    ├── demo-call-000-discovery-call.md
    └── demo-call-intro-initial-call.md
playbooks/sales-playbook.md
research/
├── company-research.md
└── competitive-intel.md
salesforce/
├── account.md
├── contacts.md
└── opportunity.md
```

---

## Known Gotchas

- **Vercel Sandbox timeout is in milliseconds** — `Sandbox.create(timeout=600_000)` not `600`
- **`pydantic-ai[openai]` extra does not exist** — pydantic-ai includes OpenAI support by default
- **`defer_model_check=True` is required** — without it, importing `agent.py` fails if `OPENAI_API_KEY` is not set
- **`result.stdout()` and `result.stderr()` are async** — must be awaited
- **`WriteFile.content` is `bytes`** — use `content.encode()` not plain strings
