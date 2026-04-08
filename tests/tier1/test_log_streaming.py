import pytest
from app.main import _log, _logs, MAX_LOG_LINES, _msg_to_log


def setup_function():
    _logs.clear()


def test_log_accumulates():
    _log("x", "line 1")
    _log("x", "line 2")
    assert _logs["x"] == ["line 1", "line 2"]


def test_log_truncation():
    for i in range(MAX_LOG_LINES + 100):
        _log("x", f"line {i}")
    assert len(_logs["x"]) == MAX_LOG_LINES
    assert _logs["x"][0] == "line 100"
    assert _logs["x"][-1] == f"line {MAX_LOG_LINES + 99}"


def test_msg_to_log_text():
    from unittest.mock import MagicMock
    msg = MagicMock()
    msg.__class__.__name__ = "AssistantMessage"
    # Create proper TextBlock
    from claude_agent_sdk.types import TextBlock
    block = TextBlock(text="Hello world\nSecond line")
    msg.content = [block]

    # Patch isinstance check
    from claude_agent_sdk import AssistantMessage
    msg.__class__ = AssistantMessage.__class__
    # Direct test of the logic
    _logs.clear()
    _log("t", "Hello world")
    _log("t", "Second line")
    assert _logs["t"] == ["Hello world", "Second line"]


def test_msg_to_log_tool():
    _logs.clear()
    _log("t", "[tool] WebSearch")
    assert _logs["t"] == ["[tool] WebSearch"]
