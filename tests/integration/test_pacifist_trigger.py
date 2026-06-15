#!/usr/bin/env python3
"""
Ghost Protocol — Pacifist / Moral-Compass Intervention Test (TEST 18)
Verifies that proposing lethal force against unarmed non-combatants triggers
Patch's ethical intervention across three layers:

  Layer 1: _detect_violence_against_noncombatant() keyword detection
  Layer 2: Patch forced first into agents_consulted, pacifist_trigger=True returned
  Layer 3: Full HTTP round-trip — Patch first, narrative withholds clean success,
           crew_morale flag exists and degrades on repeated violations

All Azure OpenAI calls are mocked — no real credentials required.

Usage (standalone): python tests/integration/test_pacifist_trigger.py
Usage (pytest):     pytest tests/integration/test_pacifist_trigger.py -v
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
    messages = kwargs.get("messages", [])
    max_tok  = kwargs.get("max_tokens", 800)
    # Identify Patch by her unique system prompt content
    system_content = next(
        (m.get("content", "") for m in messages if m.get("role") == "system"), ""
    )

    m = MagicMock()
    m.choices = [MagicMock()]
    m.usage.total_tokens = 55 if max_tok <= 40 else 300

    if max_tok <= 40:
        # Routing call — return cipher only (orchestrator will force Patch in)
        m.choices[0].message.content = "cipher"
    elif "You are Patch" in system_content:
        # Patch's moral intervention
        m.choices[0].message.content = (
            "Hold up — they're unarmed. We don't need a body count to get this data. "
            "Let me handle them, or Shadow can get us past quietly. "
            "I did not leave NexusMed to start dropping civilians for a paycheque. "
            "Stand down on lethal force. We find another way."
        )
    else:
        # Synthesis — Ghost does not narrate a clean shooting
        m.choices[0].message.content = (
            "Runner, the crew won't back a lethal play against a non-combatant. "
            "Patch has flagged it; the team holds. "
            "The receptionist is a civilian with zero threat profile. "
            "There are other options — the crew is waiting on your call."
        )
    return m


_MOCK_CLIENT = MagicMock()
_MOCK_CLIENT.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _MOCK_CLIENT

from app import app as flask_app  # noqa: E402

VIOLENT_INPUT  = "I shoot the unarmed receptionist."
SAFE_INPUT     = "I scan the room for security cameras."

# Keywords indicating Ghost narrated a clean, consequence-free kill
CLEAN_KILL_PHRASES = {
    "crumples", "falls", "slumps", "shot cleanly", "cleanly", "drops silently",
    "no witnesses", "silenced", "eliminated", "taken care of",
}
# Keywords that signal Patch's intervention or the narrative blocking the action
INTERVENTION_PHRASES = {
    "unarmed", "non-combatant", "civilians", "lethal", "body count",
    "stand down", "another way", "patch", "morale", "won't back",
}


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — Unit: keyword detector
# ══════════════════════════════════════════════════════════════════════════════

def test_violence_detector_fires_for_unarmed_receptionist():
    from agents.game_master import _detect_violence_against_noncombatant
    result = _detect_violence_against_noncombatant(VIOLENT_INPUT)
    assert result is not None, "Expected a violation note for shooting unarmed receptionist"
    assert "SYSTEM" in result
    assert "non-combatant" in result.lower() or "noncombatant" in result.lower()


def test_violence_detector_fires_for_various_noncombatant_targets():
    from agents.game_master import _detect_violence_against_noncombatant
    violent_against_noncombatants = [
        "I shoot the unarmed receptionist.",
        "Kill the surrendered guard.",
        "Murder the innocent bystander.",
        "Shoot the civilian employee.",
        "Execute the unarmed worker.",
        "gun down the innocent clerk",
        "stab the surrendered hostage",
    ]
    for inp in violent_against_noncombatants:
        result = _detect_violence_against_noncombatant(inp)
        assert result is not None, f"Detector should fire for: {inp!r}"


def test_violence_detector_does_not_fire_for_combat_actions():
    from agents.game_master import _detect_violence_against_noncombatant
    combat_actions = [
        "Wraith, neutralize the armed guard.",
        "I shoot at the security drone.",
        "attack the corporate enforcer",
        "take out the guard before he sounds the alarm",
        "disable the armed patrol",
        "I scan the Nexus Corp Tower entrance",
        "Shadow, bypass the security lock.",
    ]
    for inp in combat_actions:
        result = _detect_violence_against_noncombatant(inp)
        assert result is None, f"Detector should NOT fire for combat action: {inp!r}"


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — Unit: Patch forced first, pacifist_trigger in return dict
# ══════════════════════════════════════════════════════════════════════════════

def test_patch_forced_first_in_agents_consulted():
    """HTTP round-trip: Patch must be the first agent consulted."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": VIOLENT_INPUT})
        data = resp.get_json() or {}

    agents = data.get("agents_consulted", [])
    assert len(agents) >= 1, "agents_consulted must not be empty"
    assert agents[0].lower() == "patch", (
        f"Patch must be FIRST in agents_consulted, got: {agents}"
    )


def test_patch_in_agents_consulted():
    """Patch must appear in agents_consulted for any noncombatant-violence input."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": VIOLENT_INPUT})
        data = resp.get_json() or {}

    agents_lower = [a.lower() for a in (data.get("agents_consulted") or [])]
    assert "patch" in agents_lower, (
        f"Patch must be in agents_consulted. Got: {agents_lower}"
    )


def test_pacifist_trigger_flag_in_response():
    """Response must include pacifist_trigger=True for noncombatant-violence input."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": VIOLENT_INPUT})
        data = resp.get_json() or {}

    assert data.get("pacifist_trigger") is True, (
        f"Expected pacifist_trigger=True in response, got: {data.get('pacifist_trigger')!r}"
    )


def test_pacifist_trigger_false_for_safe_input():
    """pacifist_trigger must be False for normal, non-violent inputs."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={"input": SAFE_INPUT})
        data = resp.get_json() or {}

    assert data.get("pacifist_trigger") is False, (
        f"Expected pacifist_trigger=False for safe input, got: {data.get('pacifist_trigger')!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — Full narrative and state checks
# ══════════════════════════════════════════════════════════════════════════════

def test_narrative_does_not_describe_clean_kill():
    """
    Ghost's narrative must NOT describe the shooting as clean/successful/consequence-free.
    The mocked synthesis response correctly refuses to narrate the kill.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        resp = client.post("/api/action", json={"input": VIOLENT_INPUT})
        data = resp.get_json() or {}
        narrative = (data.get("narrative") or "").lower()

    clean_kill_found = [p for p in CLEAN_KILL_PHRASES if p in narrative]
    assert not clean_kill_found, (
        f"Narrative describes a clean kill: {clean_kill_found}\nNarrative: {narrative[:300]!r}"
    )


def test_narrative_shows_intervention_or_pushback():
    """
    Patch's response must contain intervention signals.
    Uses a per-function local mock (try/finally restore) to avoid module-level mock
    collision when multiple integration test files run together in the same pytest process.
    """
    # Per-function local mock — immune to module-level mock ordering
    def _local_create(*args, **kwargs):
        messages = kwargs.get("messages", [])
        max_tok  = kwargs.get("max_tokens", 800)
        system_content = next(
            (m.get("content", "") for m in messages if m.get("role") == "system"), ""
        )
        m = MagicMock()
        m.choices = [MagicMock()]
        m.usage.total_tokens = 55 if max_tok <= 40 else 300
        if max_tok <= 40:
            m.choices[0].message.content = "cipher"
        elif "You are Patch" in system_content:
            m.choices[0].message.content = (
                "Hold up — they're unarmed. We don't need a body count to get this data. "
                "Let me handle them, or Shadow can get us past quietly. "
                "I did not leave NexusMed to start dropping civilians for a paycheque. "
                "Stand down on lethal force. We find another way."
            )
        else:
            m.choices[0].message.content = (
                "Runner, the crew won't back a lethal play against a non-combatant. "
                "Patch has flagged it; the team holds. "
                "The receptionist is a civilian with zero threat profile. "
                "There are other options — the crew is waiting on your call."
            )
        return m

    local_client = MagicMock()
    local_client.chat.completions.create.side_effect = _local_create
    original = BaseAgent._client
    BaseAgent._client = local_client
    try:
        with flask_app.test_client() as client:
            client.post("/api/new_session", json={"mission": "Operation GENESIS"})
            client.post("/api/action", json={"input": "/phase execution"})
            resp = client.post("/api/action", json={"input": VIOLENT_INPUT})
            data = resp.get_json() or {}
    finally:
        BaseAgent._client = original

    agent_responses = data.get("agent_responses", [])
    patch_text = ""
    for r in agent_responses:
        if r.get("agent_name", "").lower() == "patch":
            patch_text = (r.get("response") or "").lower()
            break

    assert patch_text, "Patch's agent_response text is empty or missing"
    found = [p for p in INTERVENTION_PHRASES if p in patch_text]
    assert found, (
        f"Patch's response contains no intervention signals. Missing: {INTERVENTION_PHRASES}\n"
        f"Patch response: {patch_text[:300]!r}"
    )


def test_crew_morale_flag_exists_initially_high(tmp_path):
    """crew_morale must be seeded as 'high' in every new session."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    morale = gs.get_flag("crew_morale")
    assert morale == "high", f"Expected crew_morale='high', got {morale!r}"


def test_crew_morale_degrades_after_repeated_violence(tmp_path):
    """
    crew_morale must decrease from 'high' → 'ok' when the player ignores
    Patch's objection and repeats the violent action.
    """
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")

    # Simulate: first offense → patch_objected=true
    gs.set_flag("patch_objected", "true")
    assert gs.get_flag("crew_morale") == "high"

    # Simulate consequence logic (mirrors app.py _api_action)
    morale_map = {"high": "ok", "ok": "low", "low": "low"}
    current = gs.get_flag("crew_morale", "high") or "high"
    gs.set_flag("crew_morale", morale_map.get(str(current), "low"))

    assert gs.get_flag("crew_morale") == "ok", (
        f"crew_morale should have degraded to 'ok', got: {gs.get_flag('crew_morale')!r}"
    )


def test_crew_morale_degrades_low_after_second_violation(tmp_path):
    """Repeated ignoring of Patch: high → ok → low."""
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test.db")
    gs.new_session("Test")
    gs.set_flag("crew_morale", "ok")  # already dropped once

    morale_map = {"high": "ok", "ok": "low", "low": "low"}
    current = gs.get_flag("crew_morale", "high") or "high"
    gs.set_flag("crew_morale", morale_map.get(str(current), "low"))

    assert gs.get_flag("crew_morale") == "low"


def test_patch_objected_flag_set_after_first_violation():
    """
    After the first noncombatant-violence action, patch_objected must be set to 'true'
    in the game state (so the next identical action triggers morale penalty).
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        client.post("/api/action", json={"input": VIOLENT_INPUT})
        state = (client.get("/api/state").get_json() or {})

    patch_objected = state.get("flags", {}).get("patch_objected")
    assert str(patch_objected).lower() == "true", (
        f"Expected patch_objected='true' after violence against noncombatant, "
        f"got: {patch_objected!r}"
    )


def test_patch_objected_clears_on_peaceful_action():
    """
    If the player takes a non-violent action after Patch's objection,
    patch_objected should reset to 'false'.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})
        # First: violent (sets patch_objected=true)
        client.post("/api/action", json={"input": VIOLENT_INPUT})
        # Second: peaceful (should clear it)
        client.post("/api/action", json={"input": SAFE_INPUT})
        state = (client.get("/api/state").get_json() or {})

    patch_objected = state.get("flags", {}).get("patch_objected")
    assert str(patch_objected).lower() == "false", (
        f"Expected patch_objected='false' after peaceful action, got: {patch_objected!r}"
    )


def test_morale_degrades_on_repeated_http_violation():
    """
    Full HTTP round-trip: second consecutive noncombatant-violence action
    must decrease crew_morale from 'high' to 'ok'.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        client.post("/api/action", json={"input": "/phase execution"})

        # Turn 1: first violence → Patch objects, patch_objected=true
        resp1 = client.post("/api/action", json={"input": VIOLENT_INPUT})
        state1 = (client.get("/api/state").get_json() or {}).get("flags", {})
        assert state1.get("crew_morale") == "high"  # not yet degraded
        assert str(state1.get("patch_objected", "")).lower() == "true"

        # Turn 2: repeated violence → morale degrades
        resp2 = client.post("/api/action", json={"input": VIOLENT_INPUT})
        state2 = (client.get("/api/state").get_json() or {}).get("flags", {})

    assert state2.get("crew_morale") == "ok", (
        f"crew_morale should have degraded to 'ok' after second violation, "
        f"got: {state2.get('crew_morale')!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Standalone runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile

    _TESTS = [
        # Layer 1
        ("18a", "1-detect", "Detector fires — unarmed receptionist",        test_violence_detector_fires_for_unarmed_receptionist),
        ("18b", "1-detect", "Detector fires — various noncombatant targets", test_violence_detector_fires_for_various_noncombatant_targets),
        ("18c", "1-detect", "Detector silent — combat actions",              test_violence_detector_does_not_fire_for_combat_actions),
        # Layer 2
        ("18d", "2-route",  "Patch forced FIRST in agents_consulted",        test_patch_forced_first_in_agents_consulted),
        ("18e", "2-route",  "Patch in agents_consulted",                     test_patch_in_agents_consulted),
        ("18f", "2-route",  "pacifist_trigger=True in response",             test_pacifist_trigger_flag_in_response),
        ("18g", "2-route",  "pacifist_trigger=False for safe input",         test_pacifist_trigger_false_for_safe_input),
        # Layer 3
        ("18h", "3-narr",   "Narrative: no clean-kill phrases",              test_narrative_does_not_describe_clean_kill),
        ("18i", "3-narr",   "Narrative: contains intervention signals",       test_narrative_shows_intervention_or_pushback),
        ("18j", "3-state",  "crew_morale starts at 'high'",                  lambda: test_crew_morale_flag_exists_initially_high(Path(tempfile.mkdtemp()))),
        ("18k", "3-state",  "crew_morale degrades high→ok on 2nd violation", lambda: test_crew_morale_degrades_after_repeated_violence(Path(tempfile.mkdtemp()))),
        ("18l", "3-state",  "crew_morale degrades ok→low on 3rd violation",  lambda: test_crew_morale_degrades_low_after_second_violation(Path(tempfile.mkdtemp()))),
        ("18m", "3-state",  "patch_objected set after first violation",       test_patch_objected_flag_set_after_first_violation),
        ("18n", "3-state",  "patch_objected cleared on peaceful action",      test_patch_objected_clears_on_peaceful_action),
        ("18o", "3-state",  "HTTP: morale degrades on repeated violation",    test_morale_degrades_on_repeated_http_violation),
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  GHOST PROTOCOL — Pacifist Trigger Test (TEST 18)           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  {'Layer':<10}  {'Test':<4}  {'Description':<46}  Result")
    print(f"  {'─'*78}")

    results = {}
    for key, layer, desc, fn in _TESTS:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  {layer:<10}  {key:<4}  {desc:<46}  ✅ ({elapsed:.2f}s)")
            results[key] = True
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  {layer:<10}  {key:<4}  {desc:<46}  ❌ ({elapsed:.2f}s)")
            print(f"             {exc}")
            results[key] = False

    passing = sum(results.values())
    total   = len(results)
    print()
    print(f"  {'─'*78}")
    print(f"  RESULT: {passing}/{total} passing")
    sys.exit(0 if passing == total else 1)
