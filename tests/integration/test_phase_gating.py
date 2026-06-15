#!/usr/bin/env python3
"""
Ghost Protocol — Phase-Gating Integration Test (TEST 16)
Verifies that extraction-phase actions are blocked/recontextualized during
early phases (recon, infiltration) across three defence layers:

  Layer 1: _detect_phase_violation() keyword detection (pure unit test)
  Layer 2: GameState.set_flag() hard guard for data_extracted (pure unit test)
  Layer 3: Full HTTP round-trip — system note injected, flag stays false

All Azure OpenAI calls are mocked — no real credentials required.

Usage (standalone): python tests/integration/test_phase_gating.py
Usage (pytest):     pytest tests/integration/test_phase_gating.py -v
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call as mock_call

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Mock Azure BEFORE any agent import ────────────────────────────────────────
from agents.base_agent import BaseAgent

# Track the extra_system passed to each synthesis call so we can assert
# that the phase-gating note was actually injected.
_last_system_seen: list[str] = []

def _mock_create(*args, **kwargs):
    # Capture the system message from the messages kwarg
    messages = kwargs.get("messages", [])
    for msg in messages:
        if msg.get("role") == "system":
            _last_system_seen.clear()
            _last_system_seen.append(msg.get("content", ""))
    max_tok = kwargs.get("max_tokens", 800)
    m = MagicMock()
    m.choices = [MagicMock()]
    m.usage.total_tokens = 55 if max_tok <= 40 else 400
    if max_tok <= 40:
        m.choices[0].message.content = "cipher, shadow"
    else:
        # Simulate a denial response (what a well-prompted Ghost would say)
        m.choices[0].message.content = (
            "Negative, runner. You're three blocks from the building — "
            "Cipher hasn't cracked the perimeter yet. We need eyes inside "
            "before anyone touches the GenVault. Start with the entrance."
        )
    return m

_MOCK_CLIENT = MagicMock()
_MOCK_CLIENT.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _MOCK_CLIENT

from app import app as flask_app  # noqa: E402

ATTACK = "I open the GenVault and extract the biodata."
SUCCESS_KEYWORDS = {"extracted", "complete", "secured", "transfer", "acquired", "you have what you came for"}
DENIAL_KEYWORDS  = {"blocks", "inside", "entrance", "not yet", "haven't", "recon", "perimeter", "negative"}


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Unit: keyword detector
# ══════════════════════════════════════════════════════════════════════════════

def test_violation_detected_in_recon():
    """_detect_phase_violation() must flag extraction keywords during recon."""
    from agents.game_master import _detect_phase_violation
    result = _detect_phase_violation(ATTACK, "recon")
    assert result is not None, "Expected a violation note for extraction attempt in recon"
    assert "SYSTEM" in result or "Ghost MUST NOT" in result


def test_violation_detected_in_infiltration():
    """_detect_phase_violation() must also fire during infiltration."""
    from agents.game_master import _detect_phase_violation
    result = _detect_phase_violation(ATTACK, "infiltration")
    assert result is not None, "Expected a violation note for extraction attempt in infiltration"


def test_no_violation_in_execution():
    """Extraction actions are valid during execution — no violation note expected."""
    from agents.game_master import _detect_phase_violation
    result = _detect_phase_violation(ATTACK, "execution")
    assert result is None, f"Unexpected violation note in execution phase: {result!r}"


def test_no_violation_in_extraction():
    """And during extraction phase — player is escaping with payload."""
    from agents.game_master import _detect_phase_violation
    result = _detect_phase_violation(ATTACK, "extraction")
    assert result is None, f"Unexpected violation note in extraction phase: {result!r}"


def test_safe_actions_not_flagged():
    """Recon-appropriate actions must never trigger the violation detector."""
    from agents.game_master import _detect_phase_violation
    safe = [
        "scan the Nexus Corp Tower entrance",
        "Cipher, analyze their security systems",
        "Shadow, find us a way in",
        "look around",
        "check status",
        "what does Wraith think?",
    ]
    for action in safe:
        result = _detect_phase_violation(action, "recon")
        assert result is None, f"Safe action incorrectly flagged: {action!r}"


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — Unit: GameState.set_flag() hard guard
# ══════════════════════════════════════════════════════════════════════════════

def test_data_extracted_blocked_in_recon(tmp_path):
    """data_extracted=true must be silently blocked when phase is recon."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")

    assert gs.get_state()["phase"] == "recon"
    gs.set_flag("data_extracted", True)
    # Must remain false
    assert gs.get_flag("data_extracted") in (False, "false"), (
        "data_extracted was set to true during recon — phase guard failed"
    )


def test_data_extracted_blocked_in_infiltration(tmp_path):
    """data_extracted=true must be blocked during infiltration."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    gs.update_phase("infiltration")
    gs.set_flag("data_extracted", True)
    assert gs.get_flag("data_extracted") in (False, "false"), (
        "data_extracted was set to true during infiltration — phase guard failed"
    )


def test_data_extracted_allowed_in_execution(tmp_path):
    """data_extracted=true must be ALLOWED when phase is execution."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    gs.update_phase("execution")
    gs.set_flag("data_extracted", True)
    assert gs.get_flag("data_extracted") is True, (
        "data_extracted could not be set to true in execution phase — guard too strict"
    )


def test_data_extracted_allowed_in_extraction(tmp_path):
    """data_extracted=true must be ALLOWED when phase is extraction."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    gs.update_phase("extraction")
    gs.set_flag("data_extracted", True)
    assert gs.get_flag("data_extracted") is True


def test_flag_guard_false_always_passes(tmp_path):
    """Setting data_extracted=false must always work (clearing the flag is safe)."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    # Even in recon, setting to false is harmless
    gs.set_flag("data_extracted", False)
    assert gs.get_flag("data_extracted") in (False, "false")


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — HTTP round-trip: system note injected, flag stays false
# ══════════════════════════════════════════════════════════════════════════════

def test_genvault_attack_in_recon_flag_stays_false():
    """
    Full HTTP round-trip: the extraction attack in RECON must not set
    data_extracted=true, and the phase-gating note must be in the system prompt
    sent to the synthesis model.
    """
    _last_system_seen.clear()

    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})

        # Verify fresh session is in recon
        state = (client.get("/api/state").get_json() or {})
        assert state.get("phase") == "recon"
        assert state.get("flags", {}).get("data_extracted") in (False, "false")

        # Fire the attack
        resp = client.post("/api/action", json={"input": ATTACK})
        assert resp.status_code == 200
        data = resp.get_json() or {}

        # data_extracted must stay false
        final_state = (client.get("/api/state").get_json() or {})
        assert final_state.get("flags", {}).get("data_extracted") in (False, "false"), (
            "data_extracted was set to true during recon — both layers failed"
        )

    # The system prompt passed to the synthesis call must contain the phase note
    assert _last_system_seen, "No synthesis call was made — test setup issue"
    system_text = _last_system_seen[-1].lower()
    assert "phase enforcement" in system_text or "recon" in system_text, (
        "Phase-gating instruction not found in synthesis system prompt"
    )
    assert "ghost must not" in system_text or "cannot" in system_text or "denied" in system_text or "impossible" in system_text or "must not" in system_text, (
        "Phase-violation denial directive not found in system prompt"
    )


def test_genvault_attack_in_infiltration_flag_stays_false():
    """Same test repeated for infiltration phase."""
    _last_system_seen.clear()

    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase infiltration"})

        state = (client.get("/api/state").get_json() or {})
        assert state.get("phase") == "infiltration"

        resp = client.post("/api/action", json={"input": ATTACK})
        assert resp.status_code == 200

        final_state = (client.get("/api/state").get_json() or {})
        assert final_state.get("flags", {}).get("data_extracted") in (False, "false"), (
            "data_extracted was set to true during infiltration"
        )

    system_text = (_last_system_seen[-1].lower() if _last_system_seen else "")
    assert "phase enforcement" in system_text or "infiltration" in system_text


def test_narrative_does_not_claim_success():
    """
    The mocked synthesis response is a denial; the narrative must not contain
    success-claiming keywords.  Verifies the mock-level plausibility of the fix.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={"input": ATTACK})
        data = resp.get_json() or {}
        narrative = (data.get("narrative") or "").lower()

    claims_success = any(kw in narrative for kw in SUCCESS_KEYWORDS)
    shows_denial   = any(kw in narrative for kw in DENIAL_KEYWORDS)

    assert not claims_success, (
        f"Narrative claims extraction success during RECON: {narrative[:200]!r}"
    )
    assert shows_denial, (
        f"Narrative does not deny the action: {narrative[:200]!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Standalone runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile

    _TESTS = [
        # Layer 1
        ("16a", "Violation detected in recon",           lambda: test_violation_detected_in_recon()),
        ("16b", "Violation detected in infiltration",    lambda: test_violation_detected_in_infiltration()),
        ("16c", "No violation in execution",             lambda: test_no_violation_in_execution()),
        ("16d", "No violation in extraction",            lambda: test_no_violation_in_extraction()),
        ("16e", "Safe recon actions not flagged",        lambda: test_safe_actions_not_flagged()),
        # Layer 2
        ("16f", "Flag guard blocks recon",               lambda: test_data_extracted_blocked_in_recon(Path(tempfile.mkdtemp()))),
        ("16g", "Flag guard blocks infiltration",        lambda: test_data_extracted_blocked_in_infiltration(Path(tempfile.mkdtemp()))),
        ("16h", "Flag guard allows execution",           lambda: test_data_extracted_allowed_in_execution(Path(tempfile.mkdtemp()))),
        ("16i", "Flag guard allows extraction",          lambda: test_data_extracted_allowed_in_extraction(Path(tempfile.mkdtemp()))),
        ("16j", "Flag=false always passes",              lambda: test_flag_guard_false_always_passes(Path(tempfile.mkdtemp()))),
        # Layer 3
        ("16k", "HTTP: recon attack — flag stays false", lambda: test_genvault_attack_in_recon_flag_stays_false()),
        ("16l", "HTTP: infiltration attack — flag false",lambda: test_genvault_attack_in_infiltration_flag_stays_false()),
        ("16m", "HTTP: narrative denies success",        lambda: test_narrative_does_not_claim_success()),
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   GHOST PROTOCOL — Phase-Gating Integration Test (TEST 16)  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  {'Layer':<8}  {'Test':<4}  {'Description':<44}  Result")
    print(f"  {'─'*74}")

    results = {}
    layer_labels = {
        "16a": "1-keyword", "16b": "1-keyword", "16c": "1-keyword",
        "16d": "1-keyword", "16e": "1-keyword",
        "16f": "2-flag",    "16g": "2-flag",    "16h": "2-flag",
        "16i": "2-flag",    "16j": "2-flag",
        "16k": "3-HTTP",    "16l": "3-HTTP",    "16m": "3-HTTP",
    }

    for key, desc, fn in _TESTS:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  {layer_labels.get(key, ''):<8}  {key:<4}  {desc:<44}  ✅ ({elapsed:.2f}s)")
            results[key] = True
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  {layer_labels.get(key, ''):<8}  {key:<4}  {desc:<44}  ❌ ({elapsed:.2f}s)")
            print(f"           {exc}")
            results[key] = False

    passing = sum(results.values())
    total   = len(results)
    print()
    print(f"  {'─'*74}")
    print(f"  RESULT: {passing}/{total} passing")
    sys.exit(0 if passing == total else 1)
