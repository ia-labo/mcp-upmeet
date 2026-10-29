---
name: ialab-anthropic-haiku-sonnet
description: Use when calling the Anthropic SDK in an IALab repository — detect via `.ialab-standards.json` at repo root (IALab harness marker) AND `anthropic` in `pyproject.toml`. Enforces model selection (Haiku for classification, Sonnet 4.6 for narratives), prompt caching, retry with backoff, and use of the project's centralized model constants. Skip if the repo uses OpenAI (UZZLE) or has no Anthropic dependency.
---

# IALab Anthropic Haiku/Sonnet usage

## Activation criteria

- `.ialab-standards.json` exists at repo root (IALab harness marker, posed by `ialab-template`)
- `anthropic` in `pyproject.toml` dependencies
- Task involves adding/modifying an LLM call

If the file imports `openai` or `pydantic_ai`, skip this skill (use `uzzle-pydantic-ai-toggle` instead).

## Model selection rules

Two model families, two use cases :

| Use case | Model | Why |
|---|---|---|
| Classification (yes/no, category) | **Haiku** (`claude-haiku-4-5-20251001`) | Cheap, fast, deterministic enough for taxonomic tasks |
| Narrative / report writing | **Sonnet 4.6** (`claude-sonnet-4-6`) | Higher reasoning, structured output, client-facing tone |
| Code analysis (OTLP logs) | **Haiku** | Per-log overhead must stay low |

Use the **centralized constants**, never the model string inline :

```python
# ✅ Good
from app.constants import ANTHROPIC_HAIKU_MODEL, ANTHROPIC_SONNET_MODEL

response = await client.messages.create(
    model=ANTHROPIC_HAIKU_MODEL,
    ...
)

# ❌ Bad
response = await client.messages.create(model="claude-haiku-4-5-20251001", ...)
```

Each IALab repo using Anthropic has these constants in `app/constants.py` or `app/config.py`. If you're starting a new file, look there first.

## Prompt caching — mandatory for prompts ≥ 1024 tokens

The Anthropic API caches reusable prompt prefixes for 5 minutes. Without `cache_control`, every call re-bills the full prompt. With it, cached portions cost ~10% of normal.

```python
response = await client.messages.create(
    model=ANTHROPIC_HAIKU_MODEL,
    system=[
        {
            "type": "text",
            "text": LONG_STABLE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # cache this
        }
    ],
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": LARGE_REFERENCE_CONTEXT,
                    "cache_control": {"type": "ephemeral"},  # cache this too
                },
                {"type": "text", "text": dynamic_query},  # not cached, that's fine
            ],
        }
    ],
    max_tokens=1024,
)
```

**Stability rule** : `cache_control` only helps if the cached text is **byte-identical** across calls. Don't include timestamps, IDs, or session data in cached blocks.

## Retry with backoff

Network calls fail. Wrap calls with retries, especially in background tasks (classifier, code analyzer) that retry idempotently :

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def classify_with_haiku(content: str) -> str:
    ...
```

Don't catch and silently swallow — `reraise=True` is important so the caller knows something failed.

## Structured output

For classification, force the model to return JSON via system prompt + minimal parser. Don't trust raw model output for downstream code paths :

```python
SYSTEM = """You classify emails into exactly one of: bug, feature, feedback, unrelated.

Output JSON: {"category": "<one of the four>", "confidence": 0.0-1.0}.
No prose, no explanation."""

response = await client.messages.create(...)
raw = response.content[0].text
parsed = json.loads(raw)  # if this raises, you have a fallback path
category = parsed["category"]
```

For narratives (Sonnet), use Pydantic v2 to validate the model's structured output if you've asked for structured fields.

## Cost / token logging

In production, log token counts per call so you can audit costs :

```python
logger.info(
    "anthropic call model=%s input_tokens=%d output_tokens=%d cached=%d",
    ANTHROPIC_HAIKU_MODEL,
    response.usage.input_tokens,
    response.usage.output_tokens,
    getattr(response.usage, "cache_read_input_tokens", 0),
)
```

The `cache_read_input_tokens` field is how you verify caching is actually hitting.

## Where to look

- `IALAB/platform/monitoring/app/analysis/classifier.py` — EmailClassifier (Haiku, YAML-driven categories)
- `IALAB/platform/monitoring/app/analysis/code.py` — CodeAnalyzer (Haiku, OTLP log analysis with project context)
- `IALAB/platform/dashboard-api/app/services/reports/` — ReportNarrator (Sonnet 4.6 for client-facing reports, Haiku fallback)

## Gotchas

- Souheil's `claude-api` skill (built-in) is also relevant — both skills can co-trigger on Anthropic SDK code. This skill adds IALab-specific constants and patterns; the built-in adds generic best practices.
- For repos that don't yet centralize model constants, propose creating `app/constants.py` and migrating any inline model strings — don't introduce yet another inline string.
- The Haiku model name has changed between versions (`claude-haiku-3-5` → `claude-haiku-4-5-20251001`). If you see an old name, suggest updating — but only after confirming with the user, since the API contract or output style might differ.
