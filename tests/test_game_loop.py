"""
Tests for main.py game loop helpers.

Covers: dice-roll detection, phase-advance hint detection, roll modifier
calculation, alert escalation, Vex flag logic, and the full orchestration cycle.
"""

import pytest
from unittest.mock import patch, MagicMock
from conftest import make_mock_response


# ── Roll detection ─────────────────────────────────────────────────────────────

class TestDetectRollNeeded:

    @pytest.mark.parametrize("action", [
        "hack the badge reader",
        "bypass the security door",
        "sneak past the guard",
        "neutralise the patrol",
        "climb the ventilation shaft",
        "scan the perimeter",
        "pick the lock",
    ])
    def test_returns_true_for_roll_keywords(self, action):
        """_detect_roll_needed() returns True for actions containing roll-trigger words."""
        from main import _detect_roll_needed
        assert _detect_roll_needed(action) is True

    @pytest.mark.parametrize("action", [
        "look around the room",
        "wait for the signal",
        "ask Ghost for the plan",
        "observe the situation",
    ])
    def test_returns_false_without_roll_keywords(self, action):
        """_detect_roll_needed() returns False when no roll-trigger word is present."""
        from main import _detect_roll_needed
        assert _detect_roll_needed(action) is False

    def test_case_insensitive_detection(self):
        """_detect_roll_needed() matches keywords regardless of casing."""
        from main import _detect_roll_needed
        assert _detect_roll_needed("HACK the mainframe") is True
        assert _detect_roll_needed("Bypass the door") is True


# ── Phase advance hints ────────────────────────────────────────────────────────

class TestDetectPhaseAdvanceHint:

    @pytest.mark.parametrize("text,phase", [
        ("we're ready, let's go",        "recon"),
        ("move in, begin infiltration",   "recon"),
        ("we're inside the building",     "infiltration"),
        ("reach b3 server room",          "infiltration"),
        ("data extracted, get out",       "execution"),
        ("we have it, extract now",       "execution"),
        ("we're out, mission complete",   "extraction"),
        ("clean exit, made it",           "extraction"),
    ])
    def test_returns_true_for_matching_phrase_and_phase(self, text, phase):
        """_detect_phase_advance_hint() returns True when the text contains a phase trigger."""
        from main import _detect_phase_advance_hint
        assert _detect_phase_advance_hint(text, phase) is True

    @pytest.mark.parametrize("text,phase", [
        ("we're ready to move",  "execution"),   # 'ready' triggers recon, not execution
        ("we're inside",         "recon"),        # 'inside' triggers infiltration, not recon
        ("random action taken",  "infiltration"),
    ])
    def test_returns_false_for_mismatched_phase(self, text, phase):
        """_detect_phase_advance_hint() returns False when the phase does not match the hint."""
        from main import _detect_phase_advance_hint
        assert _detect_phase_advance_hint(text, phase) is False

    def test_returns_false_for_unknown_phase(self):
        """_detect_phase_advance_hint() returns False safely for an unrecognised phase."""
        from main import _detect_phase_advance_hint
        assert _detect_phase_advance_hint("ready", "unknown_phase") is False


# ── Roll modifier calculation ──────────────────────────────────────────────────

class TestRollModifier:

    def _operational_crew(self):
        return {name: {"health_state": "operational"} for name in
                ["Ghost", "Wraith", "Cipher", "Shadow", "Patch"]}

    def _wounded_crew(self, *wounded_names):
        crew = self._operational_crew()
        for name in wounded_names:
            crew[name]["health_state"] = "wounded"
        return crew

    def test_hacking_action_with_operational_cipher_gives_plus_three(self):
        """Cipher operational adds +3 to hacking-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("hack the biometric scanner", self._operational_crew())
        assert mod == 3

    def test_hacking_action_with_wounded_cipher_gives_plus_one(self):
        """Wounded Cipher adds only +1 to hacking-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("crack the network", self._wounded_crew("Cipher"))
        assert mod == 1

    def test_stealth_action_with_operational_shadow_gives_plus_four(self):
        """Shadow operational adds +4 to stealth-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("sneak past the guard", self._operational_crew())
        assert mod == 4

    def test_stealth_action_with_wounded_shadow_gives_plus_two(self):
        """Wounded Shadow adds only +2 to stealth-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("infiltrate the room", self._wounded_crew("Shadow"))
        assert mod == 2

    def test_combat_action_with_operational_wraith_gives_plus_four(self):
        """Wraith operational adds +4 to combat-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("neutralize the patrol", self._operational_crew())
        assert mod == 4

    def test_combat_action_with_wounded_wraith_gives_plus_one(self):
        """Wounded Wraith adds only +1 to combat-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("attack the guard", self._wounded_crew("Wraith"))
        assert mod == 1

    def test_negotiate_action_with_operational_patch_gives_plus_three(self):
        """Patch operational adds +3 to negotiation-type actions."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("negotiate with the guard", self._operational_crew())
        assert mod == 3

    def test_unrecognised_action_type_gives_zero_modifier(self):
        """Actions that match no specialist keyword return a modifier of 0."""
        from main import _roll_modifier_for_input
        mod = _roll_modifier_for_input("look around the corridor", self._operational_crew())
        assert mod == 0


# ── Alert escalation ───────────────────────────────────────────────────────────

class TestAlertEscalation:

    def test_escalates_alert_when_narrative_contains_trigger_word(self, tmp_game_state):
        """_maybe_escalate_alert() bumps the alert level when narrative contains 'detected'."""
        from main import _maybe_escalate_alert
        result = {"narrative": "The crew has been detected by the ARGUS system."}
        state = {"alert_state": "cold"}
        _maybe_escalate_alert(result, tmp_game_state, state)
        assert tmp_game_state.get_state()["alert_state"] == "warm"

    def test_escalates_through_ladder_one_step_at_a_time(self, tmp_game_state):
        """_maybe_escalate_alert() increments by exactly one level per call."""
        from main import _maybe_escalate_alert
        tmp_game_state.update_alert("warm")
        result = {"narrative": "An alarm has been triggered on level B2."}
        state = {"alert_state": "warm"}
        _maybe_escalate_alert(result, tmp_game_state, state)
        assert tmp_game_state.get_state()["alert_state"] == "hot"

    def test_does_not_escalate_beyond_scorched(self, tmp_game_state, capsys):
        """_maybe_escalate_alert() does not escalate past 'scorched'."""
        from main import _maybe_escalate_alert
        tmp_game_state.update_alert("scorched")
        result = {"narrative": "Full lockdown — alert triggered everywhere."}
        state = {"alert_state": "scorched"}
        _maybe_escalate_alert(result, tmp_game_state, state)
        assert tmp_game_state.get_state()["alert_state"] == "scorched"

    def test_does_not_escalate_for_quiet_narrative(self, tmp_game_state):
        """_maybe_escalate_alert() leaves the alert unchanged for clean narrative text."""
        from main import _maybe_escalate_alert
        result = {"narrative": "Shadow moves silently through the maintenance corridor."}
        state = {"alert_state": "cold"}
        _maybe_escalate_alert(result, tmp_game_state, state)
        assert tmp_game_state.get_state()["alert_state"] == "cold"

    def test_handles_missing_narrative_key_gracefully(self, tmp_game_state):
        """_maybe_escalate_alert() does not crash when narrative key is absent."""
        from main import _maybe_escalate_alert
        _maybe_escalate_alert({}, tmp_game_state, {"alert_state": "cold"})
        assert tmp_game_state.get_state()["alert_state"] == "cold"


# ── Vex flag logic ─────────────────────────────────────────────────────────────

class TestMaybeFlagVex:

    def test_sets_vex_appeared_flag_when_vex_consulted(self, tmp_game_state):
        """_maybe_flag_vex() sets vex_appeared=True when Vex is in agents_consulted."""
        from main import _maybe_flag_vex
        result = {"agents_consulted": ["Cipher", "Vex"]}
        _maybe_flag_vex(result, tmp_game_state)
        assert tmp_game_state.get_flag("vex_appeared") is True

    def test_does_not_set_flag_when_vex_absent(self, tmp_game_state):
        """_maybe_flag_vex() leaves vex_appeared False when Vex is not consulted."""
        from main import _maybe_flag_vex
        result = {"agents_consulted": ["Cipher", "Shadow"]}
        _maybe_flag_vex(result, tmp_game_state)
        assert tmp_game_state.get_flag("vex_appeared") is False

    def test_does_not_overwrite_existing_true_flag(self, tmp_game_state):
        """_maybe_flag_vex() does not toggle an already-set vex_appeared flag."""
        from main import _maybe_flag_vex
        tmp_game_state.set_flag("vex_appeared", True)
        result = {"agents_consulted": ["Vex"]}
        _maybe_flag_vex(result, tmp_game_state)
        assert tmp_game_state.get_flag("vex_appeared") is True


# ── Full orchestration cycle ───────────────────────────────────────────────────

class TestFullOrchestrationCycle:

    def test_orchestration_completes_without_error(
        self, game_master, mock_azure_client, minimal_game_state, orchestrate_side_effects
    ):
        """A full orchestrate() call returns a result dict without raising."""
        mock_azure_client.chat.completions.create.side_effect = orchestrate_side_effects()
        result = game_master.orchestrate("scan the service bay", minimal_game_state)
        assert isinstance(result, dict)
        assert "narrative" in result

    def test_player_input_reaches_agent_context(
        self, game_master, mock_azure_client, minimal_game_state, orchestrate_side_effects
    ):
        """The player's exact input string is passed through to the API call."""
        mock_azure_client.chat.completions.create.side_effect = orchestrate_side_effects()
        game_master.orchestrate("neutralise the guard on the east corridor", minimal_game_state)
        all_calls = mock_azure_client.chat.completions.create.call_args_list
        all_content = " ".join(
            str(call.kwargs.get("messages", "")) for call in all_calls
        )
        assert "neutralise the guard on the east corridor" in all_content

    def test_orchestration_result_contains_agent_names(
        self, game_master, mock_azure_client, minimal_game_state, orchestrate_side_effects
    ):
        """orchestrate() lists the consulted agent names in agents_consulted."""
        mock_azure_client.chat.completions.create.side_effect = orchestrate_side_effects(
            routing="cipher, shadow"
        )
        result = game_master.orchestrate("hack the terminal", minimal_game_state)
        consulted = result.get("agents_consulted", [])
        assert "Cipher" in consulted or "cipher" in [a.lower() for a in consulted]

    def test_vex_only_routed_in_execution_phase(
        self, game_master, mock_azure_client, minimal_game_state
    ):
        """Vex cannot appear in the orchestration result for non-execution phases."""
        for phase in ("recon", "infiltration", "extraction"):
            mock_azure_client.chat.completions.create.reset_mock()
            mock_azure_client.chat.completions.create.side_effect = [
                make_mock_response("vex, cipher"),         # routing
                make_mock_response("Cipher response"),     # cipher (vex stripped)
                make_mock_response("Ghost narrative"),      # synthesis
            ]
            minimal_game_state["phase"] = phase
            result = game_master.orchestrate("test action", minimal_game_state)
            consulted = [a.lower() for a in result.get("agents_consulted", [])]
            assert "vex" not in consulted, f"Vex appeared in {phase} phase — should be blocked"

    def test_phase_advances_via_advance_phase(self, game_master):
        """GameMaster.advance_phase() returns the next phase in the heist sequence."""
        assert game_master.advance_phase("recon") == "infiltration"
        assert game_master.advance_phase("infiltration") == "execution"
        assert game_master.advance_phase("execution") == "extraction"
        assert game_master.advance_phase("extraction") == "complete"
