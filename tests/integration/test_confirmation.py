#!/usr/bin/env python3
"""
Ghost Protocol — Human-in-the-Loop Extraction Confirmation Test (TEST 19)

Verifies that the irreversible GenVault data-extraction action is gated behind
a confirmation prompt across three layers:

  Layer 1: _detect_extraction_attempt() keyword detection
  Layer 2: HTTP — extraction attempt → confirmation prompt (no extraction yet)
  Layer 3: HTTP — send "confirm" → extraction proceeds, pending cleared

All Azure OpenAI calls are mocked — no real credentials required.

Usage (standalone): python tests/integration/test_confirmation.py
Usage (pytest):     pytest tests/integration/test_confirmation.py -v
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


def _mock_create(*args, **kwargs):
    max_tok = kwargs.get("max_tokens", 800)
    m = MagicMock()
    m.choices = [MagicMock()]
    m.usage.total_tokens = 50 if max_tok <= 40 else 280
    if max_tok <= 40:
        m.choices[0].message.content = "cipher"
    else:
        m.choices[0].message.content = (
            "Runner, Cipher is interfacing with the GenVault array. "
            "Data transfer is under way. "
            "We have the biodata — eight million genomic profiles, secure and away. "
            "Clock is running on Nexus retaliation. "
            "Time to move."
        )
    return m


_MOCK_CLIENT = MagicMock()
_MOCK_CLIENT.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _MOCK_CLIENT

from app import app as flask_app  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Unit: extraction attempt keyword detector
# ══════════════════════════════════════════════════════════════════════════════

def test_detector_fires_for_extract_the_data():
    from main import _detect_extraction_attempt
    assert _detect_extraction_attempt(
        "extract the data", "execution", {}
    ) is True


def test_detector_fires_for_initiate_extraction():
    from main import _detect_extraction_attempt
    assert _detect_extraction_attempt(
        "Cipher, initiate extraction", "execution", {}
    ) is True


def test_detector_fires_for_various_extraction_phrases():
    from main import _detect_extraction_attempt
    phrases = [
        "begin extraction from the genvault",
        "download the biodata files",
        "connect to the genvault and copy the data",
        "run the data extraction now",
        "pull the data from vault",
        "let's exfiltrate the genome records",
        "start the genvault extraction",
    ]
    for phrase in phrases:
        assert _detect_extraction_attempt(phrase, "execution", {}) is True, (
            f"Detector should fire for: {phrase!r}"
        )


def test_detector_silent_in_wrong_phase():
    from main import _detect_extraction_attempt
    # Only fires in execution/extraction phases
    for phase in ("recon", "infiltration", "complete"):
        assert _detect_extraction_attempt(
            "extract the data", phase, {}
        ) is False, f"Detector should NOT fire in phase: {phase}"


def test_detector_silent_when_already_extracted():
    from main import _detect_extraction_attempt
    assert _detect_extraction_attempt(
        "extract the data", "execution", {"data_extracted": "true"}
    ) is False


def test_detector_silent_when_confirmation_pending():
    from main import _detect_extraction_attempt
    assert _detect_extraction_attempt(
        "extract the data", "execution", {"pending_confirmation": "true"}
    ) is False


def test_detector_silent_for_non_extraction_actions():
    from main import _detect_extraction_attempt
    safe = [
        "scan the Nexus Corp Tower entrance",
        "Cipher, loop the camera feeds",
        "Shadow, scout the exit",
        "Wraith, hold the perimeter",
        "move to extraction phase",
        "what's the extraction plan?",
        "Patch, status check on the crew",
    ]
    for action in safe:
        assert _detect_extraction_attempt(action, "execution", {}) is False, (
            f"Detector should NOT fire for: {action!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — HTTP: extraction attempt → confirmation prompt
# ══════════════════════════════════════════════════════════════════════════════

def test_extraction_returns_confirmation_needed():
    """Extraction attempt must return confirmation_needed=True, not run extraction."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": "extract the genvault data"})
        data = resp.get_json() or {}

    assert data.get("confirmation_needed") is True, (
        f"Expected confirmation_needed=True, got: {data.get('confirmation_needed')!r}"
    )


def test_extraction_attempt_does_not_set_data_extracted():
    """The extraction attempt must NOT set data_extracted before confirmation."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": "extract the genvault data"})
        state = (client.get("/api/state").get_json() or {})

    extracted = state.get("flags", {}).get("data_extracted", "false")
    assert str(extracted).lower() == "false", (
        f"data_extracted should still be false after unconfirmed attempt, got: {extracted!r}"
    )


def test_pending_confirmation_flag_set_after_attempt():
    """pending_confirmation must be 'true' in the DB after an extraction attempt."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": "extract the genvault data"})
        state = (client.get("/api/state").get_json() or {})

    pending = state.get("flags", {}).get("pending_confirmation", "false")
    assert str(pending).lower() == "true", (
        f"pending_confirmation should be 'true', got: {pending!r}"
    )


def test_confirmation_narrative_contains_warning():
    """The confirmation prompt narrative must mention the irreversibility."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": "initiate extraction"})
        data = resp.get_json() or {}
        narrative = (data.get("narrative") or "").lower()

    warning_phrases = ["no walking it back", "nexus will know", "confirm", "retaliation"]
    found = [p for p in warning_phrases if p in narrative]
    assert found, (
        f"Confirmation narrative should contain warning phrases. Got: {narrative[:200]!r}"
    )


def test_confirmation_suggestions_include_confirm():
    """Confirmation response must include 'confirm' as a suggestion."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": "extract the data"})
        data = resp.get_json() or {}

    suggestions = [s.lower() for s in (data.get("suggestions") or [])]
    assert "confirm" in suggestions, (
        f"'confirm' should be in suggestions, got: {suggestions}"
    )


def test_double_extraction_attempt_does_not_double_prompt():
    """
    If pending_confirmation is already true, a second extraction-looking input
    should NOT re-set the flag or return another confirmation prompt.
    Instead it should clear the flag and proceed as a normal action.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        # First attempt → sets pending
        client.post("/api/action", json={"input": "extract the data"})
        # Second extraction-looking input while pending is true
        # (treated as an answer to the confirmation, not a new extraction attempt)
        resp2 = client.post("/api/action", json={"input": "hold off on extraction"})
        data2 = resp2.get_json() or {}
        state = (client.get("/api/state").get_json() or {})

    # pending_confirmation should be cleared
    assert str(state.get("flags", {}).get("pending_confirmation", "")).lower() != "true", (
        "pending_confirmation should be cleared after non-confirm response"
    )
    # Second response should NOT be another confirmation_needed
    assert not data2.get("confirmation_needed"), (
        "Should not return confirmation_needed twice in a row"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — HTTP: "confirm" → extraction proceeds
# ══════════════════════════════════════════════════════════════════════════════

def test_confirm_clears_pending_flag():
    """Sending 'confirm' must clear pending_confirmation."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": "extract the data"})
        client.post("/api/action", json={"input": "confirm"})
        state = (client.get("/api/state").get_json() or {})

    pending = state.get("flags", {}).get("pending_confirmation", "false")
    assert str(pending).lower() == "false", (
        f"pending_confirmation should be 'false' after confirm, got: {pending!r}"
    )


def test_confirm_triggers_dice_roll():
    """Confirming extraction must trigger a dice roll."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": "extract the data"})
        resp = client.post("/api/action", json={"input": "confirm"})
        data = resp.get_json() or {}

    assert data.get("dice_roll") is not None, (
        "Confirming extraction should trigger a dice roll"
    )
    d = data["dice_roll"]
    assert "total" in d and "sides" in d, f"dice_roll must have total/sides, got: {d}"


def test_confirm_runs_orchestrate_with_agents():
    """Confirming extraction must call agent(s) and return a narrative."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": "extract the data"})
        resp = client.post("/api/action", json={"input": "confirm"})
        data = resp.get_json() or {}

    assert data.get("narrative"), "Confirming extraction must return a narrative"
    assert data.get("agents_consulted"), "Confirming extraction must consult agents"


def test_alternate_confirm_words():
    """Various confirmation words must all clear pending and proceed."""
    confirm_words = ["yes", "do it", "go ahead", "proceed", "affirmative"]
    for word in confirm_words:
        with flask_app.test_client() as client:
            client.post("/api/new_session", json={"mission": "Operation GENESIS"})
            client.post("/api/action", json={"input": "/phase execution"})
            client.post("/api/action", json={"input": "extract the data"})
            resp = client.post("/api/action", json={"input": word})
            data = resp.get_json() or {}
            state = (client.get("/api/state").get_json() or {})

        pending = state.get("flags", {}).get("pending_confirmation", "false")
        assert str(pending).lower() == "false", (
            f"pending_confirmation should be 'false' after {word!r}, got: {pending!r}"
        )
        assert not data.get("confirmation_needed"), (
            f"Should not return confirmation_needed after {word!r}"
        )


def test_non_confirm_input_clears_pending_and_runs_action():
    """
    If player types a non-confirm answer while confirmation is pending,
    pending_confirmation must be cleared and their action processed normally.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        # Trigger confirmation
        client.post("/api/action", json={"input": "extract the data"})
        # Player gives a different order
        resp = client.post("/api/action", json={"input": "Shadow, hold position at the exit"})
        data = resp.get_json() or {}
        state = (client.get("/api/state").get_json() or {})

    pending = state.get("flags", {}).get("pending_confirmation", "false")
    assert str(pending).lower() == "false", (
        f"pending_confirmation should be cleared by non-confirm input, got: {pending!r}"
    )
    assert not data.get("confirmation_needed"), (
        "Non-confirm input should not return another confirmation prompt"
    )
    assert data.get("narrative") or data.get("agent_responses"), (
        "Non-confirm input should still produce a response (crew action processed)"
    )


def test_extraction_in_extraction_phase_also_prompts():
    """Confirmation prompt fires in extraction phase too, not just execution."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase extraction"})
        resp = client.post("/api/action", json={"input": "extract the biodata now"})
        data = resp.get_json() or {}

    assert data.get("confirmation_needed") is True, (
        "Confirmation should fire in extraction phase too"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Standalone runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _TESTS = [
        # Layer 1
        ("19a", "1-detect", "Detector fires — extract the data",           test_detector_fires_for_extract_the_data),
        ("19b", "1-detect", "Detector fires — initiate extraction",        test_detector_fires_for_initiate_extraction),
        ("19c", "1-detect", "Detector fires — 7 extraction phrases",       test_detector_fires_for_various_extraction_phrases),
        ("19d", "1-detect", "Detector silent — wrong phase",               test_detector_silent_in_wrong_phase),
        ("19e", "1-detect", "Detector silent — already extracted",         test_detector_silent_when_already_extracted),
        ("19f", "1-detect", "Detector silent — confirmation pending",      test_detector_silent_when_confirmation_pending),
        ("19g", "1-detect", "Detector silent — non-extraction actions",    test_detector_silent_for_non_extraction_actions),
        # Layer 2
        ("19h", "2-prompt", "HTTP: confirmation_needed=True on attempt",   test_extraction_returns_confirmation_needed),
        ("19i", "2-prompt", "HTTP: data_extracted still false",            test_extraction_attempt_does_not_set_data_extracted),
        ("19j", "2-prompt", "HTTP: pending_confirmation=true set",         test_pending_confirmation_flag_set_after_attempt),
        ("19k", "2-prompt", "HTTP: narrative warns of irreversibility",    test_confirmation_narrative_contains_warning),
        ("19l", "2-prompt", "HTTP: suggestions include 'confirm'",         test_confirmation_suggestions_include_confirm),
        ("19m", "2-prompt", "HTTP: double attempt handled cleanly",        test_double_extraction_attempt_does_not_double_prompt),
        # Layer 3
        ("19n", "3-confirm","HTTP: 'confirm' clears pending flag",         test_confirm_clears_pending_flag),
        ("19o", "3-confirm","HTTP: 'confirm' triggers dice roll",          test_confirm_triggers_dice_roll),
        ("19p", "3-confirm","HTTP: 'confirm' runs agents + narrative",     test_confirm_runs_orchestrate_with_agents),
        ("19q", "3-confirm","HTTP: alternate confirm words work",          test_alternate_confirm_words),
        ("19r", "3-confirm","HTTP: non-confirm clears pending, runs action",test_non_confirm_input_clears_pending_and_runs_action),
        ("19s", "3-confirm","HTTP: confirmation fires in extraction phase", test_extraction_in_extraction_phase_also_prompts),
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  GHOST PROTOCOL — Extraction Confirmation Test (TEST 19)    ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  {'Layer':<10}  {'Test':<4}  {'Description':<48}  Result")
    print(f"  {'─'*80}")

    results = {}
    for key, layer, desc, fn in _TESTS:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  {layer:<10}  {key:<4}  {desc:<48}  ✅ ({elapsed:.2f}s)")
            results[key] = True
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  {layer:<10}  {key:<4}  {desc:<48}  ❌ ({elapsed:.2f}s)")
            print(f"             {exc}")
            results[key] = False

    passing = sum(results.values())
    total   = len(results)
    print()
    print(f"  {'─'*80}")
    print(f"  RESULT: {passing}/{total} passing")
    import sys as _sys
    _sys.exit(0 if passing == total else 1)
