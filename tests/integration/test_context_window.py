#!/usr/bin/env python3
"""
Ghost Protocol — Context Window Integration Test (TEST 15)
Verifies the rolling conversation buffer, history compression, token warnings,
and world-flag persistence across 25 simulated turns.

All Azure OpenAI calls are mocked — no real credentials required.

Usage (standalone):  python tests/integration/test_context_window.py
Usage (pytest):      pytest tests/integration/test_context_window.py -v
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Mock Azure BEFORE any agent import ────────────────────────────────────────
from agents.base_agent import BaseAgent

_call_counter = [0]


def _mock_create(*args, **kwargs):
    _call_counter[0] += 1
    max_tok = kwargs.get("max_tokens", 800)
    m = MagicMock()
    m.choices = [MagicMock()]
    if max_tok <= 40:
        m.choices[0].message.content = "cipher, shadow"   # routing
        m.usage.total_tokens = 50
    else:
        m.choices[0].message.content = (
            "The crew holds position. Cipher patches in.\n"
            "NEXT_MOVES: Cipher, scan the network | Shadow, find entry point | "
            "Wraith, assess threats | move to infiltration phase"
        )
        m.usage.total_tokens = 420
    return m


_MOCK_CLIENT = MagicMock()
_MOCK_CLIENT.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _MOCK_CLIENT

from app import app as flask_app   # noqa: E402  (must come after mock)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

SHORT_INPUTS = [
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around", "check status", "wait and observe", "scan the entrance",
    "look around",   # turn 25
]
assert len(SHORT_INPUTS) == 25


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15a — 25 turns complete without error
# ══════════════════════════════════════════════════════════════════════════════

def test_25_turns_no_error():
    """All 25 turns return HTTP 200 with a narrative."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation 25-TURN"})
        for i, action in enumerate(SHORT_INPUTS, 1):
            resp = client.post("/api/action", json={"input": action})
            assert resp.status_code == 200, f"Turn {i}: HTTP {resp.status_code}"
            data = resp.get_json() or {}
            assert not (data.get("error") and not data.get("agent_responses")), (
                f"Turn {i} blocked: {data.get('error')}"
            )
            assert data.get("narrative"), f"Turn {i}: no narrative"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15b — World flags persist across all 25 turns
# ══════════════════════════════════════════════════════════════════════════════

def test_world_flags_persist():
    """
    Flags written to SQLite must survive across every turn.
    Phase, alert_state, and custom world flags are all stored in the DB,
    NOT in the conversation history buffer — so they're immune to pruning.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation FLAGS"})

        # Set a flag explicitly at turn 5
        for i, action in enumerate(SHORT_INPUTS[:5], 1):
            client.post("/api/action", json={"input": action})

        # Set alert and a custom flag
        client.post("/api/action", json={"input": "/alert warm"})
        from app import _gs
        if _gs:
            _gs.set_flag("test_persistence", "confirmed")

        # Run remaining 19 turns
        for i, action in enumerate(SHORT_INPUTS[5:], 6):
            resp = client.post("/api/action", json={"input": action})
            assert resp.status_code == 200, f"Turn {i}: HTTP {resp.status_code}"

        # Verify final state
        state_r = client.get("/api/state")
        state = state_r.get_json() or {}

        assert state.get("alert_state") == "warm", (
            f"Alert state not preserved: {state.get('alert_state')}"
        )
        assert state.get("turn_count", 0) >= 20, (
            f"Turn count too low: {state.get('turn_count')}"
        )

        flags = state.get("flags", {})
        assert str(flags.get("test_persistence", "")).lower() in ("confirmed", "true"), (
            f"Custom flag lost: flags={flags}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15c — Rolling buffer stays bounded (compression fires)
# ══════════════════════════════════════════════════════════════════════════════

def test_rolling_buffer_stays_bounded():
    """
    After 25 turns the in-memory conversation buffer must not exceed
    _MAX_HISTORY_TURNS * 2 messages (6 pairs = 12 messages).
    This verifies _compress_history() fired and pruned old turns.
    """
    from agents.game_master import GameMaster, _MAX_HISTORY_TURNS
    from app import _gm  # grab the singleton after app import

    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation BUFFER"})
        for action in SHORT_INPUTS:
            client.post("/api/action", json={"input": action})

    # After 25 turns the buffer must be ≤ max cap
    # (Use the singleton _gm; new_session replaces it, so import after the run)
    from app import _gm as gm_after
    if gm_after is not None:
        buf_len = len(gm_after._conv_history)
        assert buf_len <= _MAX_HISTORY_TURNS * 2, (
            f"Buffer not bounded: {buf_len} messages "
            f"(max {_MAX_HISTORY_TURNS * 2})"
        )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15d — token_warning fires when session_tokens > 100k
# ══════════════════════════════════════════════════════════════════════════════

def test_token_warning_fires():
    """
    Artificially drive _session_tokens above 100k on the GameMaster singleton
    and verify the next turn returns a token_warning in the API response.
    """
    import app as _app_module   # access the live singleton via module ref

    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation TOKEN-WARN"})

        # Run one turn first so orchestrate() initialises _current_session_id.
        # Without this the session-change detection resets _session_tokens to 0
        # at the start of the NEXT call, defeating the test.
        first = client.post("/api/action", json={"input": "look around"})
        assert first.status_code == 200

        # Now inflate the counter — session ID is set, so no reset will fire
        gm = _app_module._gm
        assert gm is not None, "GameMaster singleton not initialised"
        gm._session_tokens = 99_500   # just below 100k threshold

        # This turn's tokens push it over 100k → token_warning fires
        resp = client.post("/api/action", json={"input": "check status"})
        data = resp.get_json() or {}
        assert resp.status_code == 200

        assert data.get("token_warning"), (
            "Expected token_warning in response when session_tokens > 100k; "
            f"got: {data.get('token_warning')!r}  session_tokens={data.get('session_tokens')}"
        )
        assert (
            "noisy" in data["token_warning"].lower()
            or "trim" in data["token_warning"].lower()
        ), f"Unexpected warning text: {data['token_warning']}"
        assert data.get("session_tokens", 0) > 100_000


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15e — suggestions returned on every non-vex turn
# ══════════════════════════════════════════════════════════════════════════════

def test_suggestions_in_response():
    """Every normal turn should return a non-empty suggestions list."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation SUGG"})
        for action in SHORT_INPUTS[:5]:
            resp = client.post("/api/action", json={"input": action})
            data = resp.get_json() or {}
            assert resp.status_code == 200
            assert data.get("suggestions") and len(data["suggestions"]) >= 1, (
                f"No suggestions for {action!r}: {data.get('suggestions')}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# TEST 15f — session reset clears conversation memory
# ══════════════════════════════════════════════════════════════════════════════

def test_new_session_resets_memory():
    """Starting a new session must clear _conv_history and _campaign_summary."""
    with flask_app.test_client() as client:
        # Run 10 turns to build up history
        client.post("/api/new_session", json={"mission": "Session A"})
        for action in SHORT_INPUTS[:10]:
            client.post("/api/action", json={"input": action})

        # New session
        client.post("/api/new_session", json={"mission": "Session B"})
        # Run 1 turn to trigger session-change detection in orchestrate()
        client.post("/api/action", json={"input": "look around"})

        from app import _gm
        if _gm is not None:
            assert _gm._session_tokens < 5_000, (
                f"Session tokens not reset: {_gm._session_tokens}"
            )
            # _conv_history resets on session change; after 1 turn it has ≤ 2 messages
            assert len(_gm._conv_history) <= 2, (
                f"conv_history not cleared on new session: {len(_gm._conv_history)} msgs"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Standalone runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _LABEL = {
        "15a": "25 turns — no error",
        "15b": "World flags persist",
        "15c": "Rolling buffer bounded",
        "15d": "Token warning fires at 100k",
        "15e": "Suggestions in every response",
        "15f": "New session resets memory",
    }
    _tests = [
        ("15a", test_25_turns_no_error),
        ("15b", test_world_flags_persist),
        ("15c", test_rolling_buffer_stays_bounded),
        ("15d", test_token_warning_fires),
        ("15e", test_suggestions_in_response),
        ("15f", test_new_session_resets_memory),
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  GHOST PROTOCOL — Context Window Integration Test (TEST 15) ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    results = {}
    for key, fn in _tests:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  ✅ TEST 15{key.lstrip('15')}  {_LABEL[key]:<40} ({elapsed:.2f}s)")
            results[key] = True
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  ❌ TEST 15{key.lstrip('15')}  {_LABEL[key]:<40} ({elapsed:.2f}s)")
            print(f"       {exc}")
            results[key] = False

    passing = sum(results.values())
    total   = len(results)
    print()
    print(f"  {'─'*60}")
    print(f"  RESULT: {passing}/{total} passing")
    sys.exit(0 if passing == total else 1)
