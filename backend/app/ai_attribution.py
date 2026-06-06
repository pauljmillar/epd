"""Detect whether a PR was produced with help from an AI coding tool.

Signals, in priority order:
  1. `Co-Authored-By:` trailer on the merge commit body (GitHub preserves trailers on
     squash-merge into the squash commit body).
  2. Co-author email patterns (e.g. `noreply@anthropic.com`).
  3. PR body markers (e.g. "Generated with [Claude Code]").

This is a lower-bound signal. Developers who use AI but strip the trailers will not be
counted. The tooltip in the UI calls this out — don't oversell the number.

Patterns are configurable via env: `AI_TOOL_PATTERNS` accepts JSON in the shape
`{"tool_name": ["regex1", "regex2"]}` and is merged into the defaults below (overriding by
key). Leave unset for the bundled defaults.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from .config import settings

log = logging.getLogger(__name__)

# (tool_name, list of regex patterns). Order matters — first match wins.
_DEFAULT_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "claude",
        [
            r"co-?authored-?by:\s*claude",
            r"noreply@anthropic\.com",
            r"generated with \[?claude code",
            r"🤖 generated with",
        ],
    ),
    (
        "cursor",
        [
            r"co-?authored-?by:.*cursor",
            r"@cursor\.com>",
            r"made with cursor",
            r"cursor-?ai\[bot\]",
        ],
    ),
    (
        "copilot",
        [
            r"co-?authored-?by:.*copilot",
            r"copilot\[bot\]",
            r"github-copilot",
        ],
    ),
    (
        "codex",
        [
            r"co-?authored-?by:.*codex",
            r"openai codex",
            r"chatgpt(?:\.com|@openai)",
        ],
    ),
    (
        "windsurf",
        [
            r"co-?authored-?by:.*windsurf",
            r"made with windsurf",
        ],
    ),
]


@lru_cache(maxsize=1)
def _compiled_patterns() -> list[tuple[str, list[re.Pattern[str]]]]:
    patterns: dict[str, list[str]] = {name: pats[:] for name, pats in _DEFAULT_PATTERNS}
    raw = getattr(settings, "ai_tool_patterns", None)
    if raw:
        try:
            overrides = json.loads(raw)
            if isinstance(overrides, dict):
                for k, v in overrides.items():
                    if isinstance(v, list):
                        patterns[k] = v
        except (json.JSONDecodeError, TypeError) as e:
            log.warning("AI_TOOL_PATTERNS ignored — invalid JSON: %s", e)
    return [
        (name, [re.compile(p, re.IGNORECASE) for p in pats]) for name, pats in patterns.items()
    ]


def detect(*texts: str | None) -> tuple[bool, str | None]:
    """Inspect each text fragment in order; return (ai_assisted, tool_name).

    The first matching tool wins. The order of `texts` lets the caller prioritize the
    highest-signal source (typically merge commit body > PR body)."""
    for text in texts:
        if not text:
            continue
        for name, patterns in _compiled_patterns():
            for p in patterns:
                if p.search(text):
                    return True, name
    return False, None


def reset_pattern_cache() -> None:
    """For tests: clear the compiled-pattern cache so env overrides take effect."""
    _compiled_patterns.cache_clear()
