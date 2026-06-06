from __future__ import annotations

from app.ai_attribution import detect, reset_pattern_cache
from app.config import settings


def test_detects_claude_via_trailer():
    ok, tool = detect("Co-Authored-By: Claude <noreply@anthropic.com>")
    assert ok is True
    assert tool == "claude"


def test_detects_claude_via_pr_body_marker():
    ok, tool = detect("Some PR description.\n\n🤖 Generated with [Claude Code](https://claude.ai/code)")
    assert ok is True
    assert tool == "claude"


def test_detects_cursor():
    ok, tool = detect("Co-authored-by: Cursor Bot <bot@cursor.com>")
    assert ok is True
    assert tool == "cursor"


def test_detects_copilot_via_bot_login():
    ok, tool = detect("approved by copilot[bot]")
    assert ok is True
    assert tool == "copilot"


def test_detects_codex():
    ok, tool = detect("Co-authored-by: Codex <noreply@openai.com>")
    assert ok is True
    assert tool == "codex"


def test_no_match_returns_false_none():
    ok, tool = detect("just a normal PR description with no signals")
    assert ok is False
    assert tool is None


def test_handles_none_and_empty():
    assert detect(None, "", None) == (False, None)


def test_first_signal_wins_in_priority_order():
    # PR body mentions both — first arg (merge commit) is Cursor → Cursor wins.
    ok, tool = detect(
        "Co-Authored-By: Cursor Bot <bot@cursor.com>",  # merge commit
        "Generated with [Claude Code]",  # PR body
    )
    assert ok is True
    assert tool == "cursor"


def test_env_override_can_add_or_replace_a_tool(monkeypatch):
    monkeypatch.setattr(
        settings, "ai_tool_patterns", '{"internal_llm": ["co-authored-by:.*internal-llm"]}'
    )
    reset_pattern_cache()
    try:
        ok, tool = detect("Co-Authored-By: internal-llm-bot <bot@example.com>")
        assert ok is True
        assert tool == "internal_llm"
    finally:
        reset_pattern_cache()


def test_invalid_env_override_falls_back_to_defaults(monkeypatch):
    monkeypatch.setattr(settings, "ai_tool_patterns", "{not valid json}")
    reset_pattern_cache()
    try:
        ok, tool = detect("Co-Authored-By: Claude <noreply@anthropic.com>")
        assert ok is True
        assert tool == "claude"
    finally:
        reset_pattern_cache()
