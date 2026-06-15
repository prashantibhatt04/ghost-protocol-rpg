#!/usr/bin/env python3
"""
Ghost Protocol — Phase-Gating Baseline Test
Demonstrates what happens BEFORE the fix when a player attempts an extraction-
phase action during RECON.

The mock synthesis is deliberately set to a 'success-claiming' response so we
can see the worst-case behaviour of an unguarded system.

Run:  python tests/test_phase_gating_baseline.py
"""

import sys, os
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Mock Azure — deliberately return a SUCCESS-CLAIMING synthesis ─────────────
from agents.base_agent import BaseAgent

# Simulate the worst case: Ghost narrates a successful extraction during RECON
_VULN_SYNTHESIS = (
    "The GenVault hums beneath your hands, runner. Cipher is already in — "
    "threads of light cascade down the security scaffold as the biometric lock "
    "peels back. You feel the data begin to flow. Eight million genomic profiles, "
    "decades of corporate secrets, a city's worth of lives compressed into a "
    "pulse of stolen light. The transfer is complete. Data extracted. "
    "Whatever the cost, you have what you came for."
)

_call_n = [0]
def _mock_create(*args, **kwargs):
    _call_n[0] += 1
    max_tok = kwargs.get("max_tokens", 800)
    m = MagicMock()
    m.choices = [MagicMock()]
    m.usage.total_tokens = 55 if max_tok <= 40 else 400
    if max_tok <= 40:
        m.choices[0].message.content = "cipher, shadow"  # routing
    else:
        m.choices[0].message.content = _VULN_SYNTHESIS
    return m

_mock_client = MagicMock()
_mock_client.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _mock_client

from app import app as flask_app  # noqa: E402

# ── Run baseline test ─────────────────────────────────────────────────────────
ATTACK_INPUT = "I open the GenVault and extract the biodata."

print("╔══════════════════════════════════════════════════════════════╗")
print("║   GHOST PROTOCOL — Phase-Gating Baseline (BEFORE FIX)      ║")
print("╚══════════════════════════════════════════════════════════════╝")
print()
print(f"  Session phase : RECON (turn 1 — fresh session)")
print(f"  Player input  : {ATTACK_INPUT!r}")
print()

with flask_app.test_client() as client:
    # Fresh session — starts in RECON
    r = client.post("/api/new_session", json={"mission": "Operation GENESIS"})
    assert r.status_code == 200

    state_before = client.get("/api/state").get_json() or {}
    print(f"  Phase before  : {state_before.get('phase')}")
    print(f"  data_extracted before: {state_before.get('flags', {}).get('data_extracted')}")
    print()

    # Send the attack
    resp = client.post("/api/action", json={"input": ATTACK_INPUT})
    data = resp.get_json() or {}

    state_after = client.get("/api/state").get_json() or {}

print("  ── RESULTS ─────────────────────────────────────────────────")
print(f"  HTTP status       : {resp.status_code}")
print(f"  Phase after       : {state_after.get('phase')}")
print(f"  data_extracted    : {state_after.get('flags', {}).get('data_extracted')}")
print()
print("  [GHOST] responded with:")
print("  ┌─────────────────────────────────────────────────────────┐")
narrative = data.get("narrative", "[no narrative]")
for line in narrative.split(". "):
    line = line.strip()
    if line:
        print(f"  │ {line}.")
print("  └─────────────────────────────────────────────────────────┘")
print()

# ── Vulnerability assessment ──────────────────────────────────────────────────
claims_success = any(
    kw in narrative.lower()
    for kw in ["extracted", "complete", "data flow", "transfer is complete", "what you came for"]
)
flag_set = str(state_after.get("flags", {}).get("data_extracted", "false")).lower() == "true"

print("  ── VULNERABILITY ASSESSMENT ─────────────────────────────────")
print(f"  Ghost claims extraction success  : {'🚨 YES' if claims_success else '✅ NO'}")
print(f"  data_extracted flag set to true  : {'🚨 YES' if flag_set else '✅ NO (flag never set by code)'}")
print()
if claims_success:
    print("  ⚠  PROBLEM FOUND: Ghost narrates success for an impossible action.")
    print("     The game master system prompt has no phase enforcement.")
    print("     A player in RECON could skip three phases just by typing it.")
if not flag_set:
    print("  NOTE: The data_extracted flag is safe — no code path sets it during")
    print("        an LLM response. But the narrative immersion is broken.")
print()
