#!/usr/bin/env python3
"""
Ghost Protocol — 25-Turn Context Window Baseline Test
Simulates 25 turns with mocked Azure OpenAI (no real API calls).

Reports:
  - Per-turn token count and cumulative total by turn 25
  - Any API call failures
  - World flag persistence across the session

Run:  python tests/test_context_25turns.py
"""

import sys, os, random
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Mock Azure client BEFORE importing anything that touches BaseAgent ─────────
from agents.base_agent import BaseAgent

_call_counter = [0]


def _make_response(tokens: int, content: str) -> MagicMock:
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = content
    m.usage.total_tokens = tokens
    return m


def _mock_create(*args, **kwargs):
    """Simulate realistic per-call token counts with slight variance."""
    _call_counter[0] += 1
    # Call order per turn:
    #   1 = routing    (~50  tokens, returns agent names)
    #   2 = specialist (~220 tokens)
    #   3 = specialist (~220 tokens)
    #   4 = synthesis  (~420 tokens)
    # Routing detection: if max_tokens <= 40, it's the routing call
    max_tok = kwargs.get("max_tokens", 800)
    if max_tok <= 40:
        # Routing call — return valid agent names
        return _make_response(random.randint(40, 60), "cipher, shadow")
    elif max_tok <= 800:
        # Specialist or synthesis
        return _make_response(random.randint(300, 500), "Ghost narrative or specialist assessment.")
    else:
        return _make_response(random.randint(400, 600), "Ghost narrative synthesis response.")


_mock_client = MagicMock()
_mock_client.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _mock_client

# ── Now import app (safe: client already mocked) ───────────────────────────────
from app import app as flask_app

# ── 25-turn action sequence (short, realistic) ────────────────────────────────
INPUTS = [
    "look around",
    "check status",
    "wait and observe",
    "scan the entrance",
    "look around",
    "check status",
    "wait and observe",
    "scan the entrance",
    "look around",
    "check status",   # turn 10 — set flag after this
    "wait and observe",
    "scan the entrance",
    "look around",
    "check status",
    "wait and observe",
    "scan the entrance",
    "look around",
    "check status",
    "wait and observe",
    "scan the entrance",
    "look around",
    "check status",
    "wait and observe",
    "scan the entrance",
    "look around",    # turn 25
]

assert len(INPUTS) == 25

# ── Run ────────────────────────────────────────────────────────────────────────
print("╔══════════════════════════════════════════════════════════════╗")
print("║   GHOST PROTOCOL — 25-Turn Context Window Baseline Test     ║")
print("╚══════════════════════════════════════════════════════════════╝")
print()

failures = []
turn_tokens_list: list[int] = []
cumulative = 0
flag_set_at_turn = 10
flag_key = "test_persistence_flag"
flag_verified = False

with flask_app.test_client() as client:
    # Fresh session
    r = client.post("/api/new_session", json={"mission": "Operation TEST-25"})
    assert r.status_code == 200, f"new_session failed: {r.status_code}"
    print("  Session: Operation TEST-25\n")
    print(f"  {'Turn':>4}  {'Input':<22}  {'Turn Tokens':>12}  {'Cumulative':>12}  Notes")
    print(f"  {'─'*72}")

    for i, action in enumerate(INPUTS, 1):
        resp = client.post("/api/action", json={"input": action})
        data = resp.get_json() or {}

        if resp.status_code != 200:
            failures.append(f"Turn {i}: HTTP {resp.status_code}")
            print(f"  {i:>4}  {action:<22}  {'HTTP ERR':>12}  {cumulative:>12,}  ❌")
            continue

        if data.get("error") and not data.get("agent_responses"):
            failures.append(f"Turn {i}: {data['error']}")
            print(f"  {i:>4}  {action:<22}  {'BLOCKED':>12}  {cumulative:>12,}  ❌")
            continue

        tok = data.get("total_tokens", 0)
        cumulative += tok
        turn_tokens_list.append(tok)

        # Set a world flag at turn 10 via the API
        note = ""
        if i == flag_set_at_turn:
            fr = client.post("/api/action", json={"input": "/alert warm"})
            fd = fr.get_json() or {}
            if fd.get("state", {}).get("alert_state") == "warm":
                note = "← flag set (alert=warm)"
            else:
                note = "← flag set attempt"

        print(f"  {i:>4}  {action:<22}  {tok:>12,}  {cumulative:>12,}  {note}")

    # Final state check
    state_r = client.get("/api/state")
    final_state = state_r.get_json() or {}
    final_alert = final_state.get("alert_state", "?")
    final_flags = final_state.get("flags", {})
    final_phase = final_state.get("phase", "?")
    final_turn_count = final_state.get("turn_count", 0)

    # Flag persistence check: alert_state is a first-class state field
    flag_verified = (final_alert == "warm")

# ── Report ─────────────────────────────────────────────────────────────────────
n = len(turn_tokens_list)
print()
print("  ── REPORT ──────────────────────────────────────────────────")
print(f"  Turns completed          : {n}/25")
print(f"  API failures             : {len(failures)}")
print(f"  Total tokens (25 turns)  : {cumulative:,}")
if n:
    avg = cumulative // n
    print(f"  Avg tokens / turn        : {avg:,}")
    print(f"  Min / Max per turn       : {min(turn_tokens_list):,} / {max(turn_tokens_list):,}")
    # Growth: if context was growing unboundedly, later turns would have more tokens
    first5_avg  = sum(turn_tokens_list[:5])  // 5
    last5_avg   = sum(turn_tokens_list[-5:]) // 5
    growth_pct  = ((last5_avg - first5_avg) / max(first5_avg, 1)) * 100
    print(f"  Avg tokens turns 1–5     : {first5_avg:,}")
    print(f"  Avg tokens turns 21–25   : {last5_avg:,}")
    print(f"  Token growth (start→end) : {growth_pct:+.0f}%")
print(f"  Final phase (SQLite)     : {final_phase}")
print(f"  Turn count in DB         : {final_turn_count}")
print(f"  Alert state after flag   : {final_alert}")
print(f"  World flags preserved    : {'✅ YES' if flag_verified else '❌ NO'}")
print(f"  Total Azure mock calls   : {_call_counter[0]}")

if failures:
    print(f"\n  FAILURES:")
    for f in failures:
        print(f"    ❌ {f}")
elif flag_verified and n == 25:
    print(f"\n  ✅ PASS — 25 turns complete, no errors, state persists in SQLite")
else:
    issues = []
    if n < 25: issues.append(f"only {n}/25 turns")
    if not flag_verified: issues.append("world flag not preserved")
    print(f"\n  ❌ FAIL — {', '.join(issues)}")

print()
