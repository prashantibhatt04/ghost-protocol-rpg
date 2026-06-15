"""
Tests for state/game_state.py

Covers: database initialization, session lifecycle, phase/alert updates,
crew health, objectives, world flags, turn history, and reset.
"""

import sqlite3
import pytest
from pathlib import Path


# ── DB initialization ──────────────────────────────────────────────────────────

class TestDatabaseInit:

    def test_all_tables_created_on_init(self, tmp_game_state):
        """All five schema tables exist after GameState is constructed."""
        with sqlite3.connect(str(tmp_game_state.db_path)) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
        expected = {"sessions", "crew_status", "objectives", "world_flags", "turn_history"}
        assert expected.issubset(tables)

    def test_new_session_assigns_id(self, tmp_path):
        """new_session() returns a positive integer session ID."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        sid = gs.new_session("Operation ALPHA")
        assert isinstance(sid, int)
        assert sid > 0

    def test_new_session_seeds_crew_members(self, tmp_game_state):
        """new_session() populates crew_status for all six crew members."""
        state = tmp_game_state.get_state()
        expected_members = {"Ghost", "Wraith", "Cipher", "Shadow", "Patch", "Vex"}
        assert expected_members == set(state["crew_detail"].keys())

    def test_new_session_seeds_genesis_objectives(self, tmp_path):
        """new_session('Operation GENESIS') pre-populates the eight heist objectives."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Operation GENESIS")
        state = gs.get_state()
        assert len(state["objectives"]) == 8

    def test_new_session_seeds_world_flags(self, tmp_game_state):
        """new_session() creates the expected initial world flags set to False."""
        flags = tmp_game_state.get_all_flags()
        expected = {"vex_appeared", "argus3_rebooting", "genvault_connected", "data_extracted"}
        assert expected.issubset(flags.keys())
        assert flags["vex_appeared"] is False


# ── get_state() structure ──────────────────────────────────────────────────────

class TestGetState:

    def test_returns_all_expected_keys(self, tmp_game_state):
        """get_state() dict includes every key consumed by GameMaster.orchestrate()."""
        state = tmp_game_state.get_state()
        required = {
            "session_id", "mission", "phase", "alert_state", "turn_count",
            "crew_status", "crew_detail", "objectives", "flags",
            "requires_roll", "roll_modifier",
        }
        assert required.issubset(state.keys())

    def test_initial_phase_is_recon(self, tmp_game_state):
        """Freshly created session starts in 'recon' phase."""
        assert tmp_game_state.get_state()["phase"] == "recon"

    def test_initial_alert_is_cold(self, tmp_game_state):
        """Freshly created session starts with 'cold' alert state."""
        assert tmp_game_state.get_state()["alert_state"] == "cold"

    def test_initial_turn_count_is_zero(self, tmp_game_state):
        """Freshly created session has turn_count of 0."""
        assert tmp_game_state.get_state()["turn_count"] == 0

    def test_crew_all_operational_on_new_session(self, tmp_game_state):
        """All crew members start as 'operational' in a new session."""
        crew = tmp_game_state.get_state()["crew_detail"]
        for name, info in crew.items():
            assert info["health_state"] == "operational", f"{name} should start operational"


# ── Phase and alert updates ────────────────────────────────────────────────────

class TestPhaseAndAlert:

    @pytest.mark.parametrize("phase", ["recon", "infiltration", "execution", "extraction", "complete"])
    def test_phase_saves_and_loads(self, tmp_game_state, phase):
        """update_phase() persists the new phase so get_state() reflects it."""
        tmp_game_state.update_phase(phase)
        assert tmp_game_state.get_state()["phase"] == phase

    def test_invalid_phase_raises_value_error(self, tmp_game_state):
        """update_phase() raises ValueError for an unrecognised phase string."""
        with pytest.raises(ValueError, match="Invalid phase"):
            tmp_game_state.update_phase("hacking")

    @pytest.mark.parametrize("alert", ["cold", "warm", "hot", "scorched"])
    def test_alert_saves_and_loads(self, tmp_game_state, alert):
        """update_alert() persists the new alert so get_state() reflects it."""
        tmp_game_state.update_alert(alert)
        assert tmp_game_state.get_state()["alert_state"] == alert

    def test_invalid_alert_raises_value_error(self, tmp_game_state):
        """update_alert() raises ValueError for an unrecognised alert string."""
        with pytest.raises(ValueError, match="Invalid alert"):
            tmp_game_state.update_alert("critical")


# ── Crew status ────────────────────────────────────────────────────────────────

class TestCrewStatus:

    def test_crew_health_update_persists(self, tmp_game_state):
        """update_crew() persists health state change for the named crew member."""
        tmp_game_state.update_crew("Wraith", "wounded", notes="Shoulder hit")
        crew = tmp_game_state.get_crew_status()
        assert crew["Wraith"]["health_state"] == "wounded"

    def test_crew_notes_persist(self, tmp_game_state):
        """update_crew() saves the notes string alongside the health state."""
        tmp_game_state.update_crew("Cipher", "wounded", notes="Augment disruption")
        crew = tmp_game_state.get_crew_status()
        assert crew["Cipher"]["notes"] == "Augment disruption"

    def test_crew_augment_damage_persists(self, tmp_game_state):
        """update_crew() persists augment_damaged flag."""
        tmp_game_state.update_crew("Shadow", "critical", augment_damaged=True)
        crew = tmp_game_state.get_crew_status()
        assert crew["Shadow"]["augment_damaged"] is True

    def test_invalid_health_state_raises(self, tmp_game_state):
        """update_crew() raises ValueError for an unrecognised health state."""
        with pytest.raises(ValueError, match="Invalid health state"):
            tmp_game_state.update_crew("Wraith", "dead")

    def test_crew_status_summary_reflects_non_operational(self, tmp_game_state):
        """get_state() crew_status string lists crew members who are not operational."""
        tmp_game_state.update_crew("Patch", "critical")
        state = tmp_game_state.get_state()
        assert "Patch" in state["crew_status"]

    def test_crew_status_summary_is_all_operational_when_healthy(self, tmp_game_state):
        """get_state() crew_status reads 'All operational' when everyone is healthy."""
        assert tmp_game_state.get_state()["crew_status"] == "All operational"


# ── Objectives ─────────────────────────────────────────────────────────────────

class TestObjectives:

    def test_complete_objective_changes_status(self, tmp_path):
        """complete_objective() marks the named objective as 'complete'."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Operation GENESIS")
        gs.complete_objective("obj_recon_security")
        objs = {o["key"]: o for o in gs.get_state()["objectives"]}
        assert objs["obj_recon_security"]["status"] == "complete"

    def test_fail_objective_changes_status(self, tmp_path):
        """fail_objective() marks the named objective as 'failed'."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Operation GENESIS")
        gs.fail_objective("obj_infiltrate_entry")
        objs = {o["key"]: o for o in gs.get_state()["objectives"]}
        assert objs["obj_infiltrate_entry"]["status"] == "failed"

    def test_get_objectives_filter_by_phase(self, tmp_path):
        """get_objectives() returns only objectives for the requested phase."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Operation GENESIS")
        recon_objs = gs.get_objectives(phase="recon")
        assert all(o["phase"] == "recon" for o in recon_objs)

    def test_get_objectives_filter_by_status(self, tmp_path):
        """get_objectives() returns only objectives matching the requested status."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Operation GENESIS")
        gs.complete_objective("obj_recon_security")
        complete_objs = gs.get_objectives(status="complete")
        assert all(o["status"] == "complete" for o in complete_objs)
        assert len(complete_objs) == 1


# ── World flags ────────────────────────────────────────────────────────────────

class TestWorldFlags:

    def test_set_and_get_string_flag(self, tmp_game_state):
        """set_flag() and get_flag() round-trip a string value correctly."""
        tmp_game_state.set_flag("test_custom_flag", "active")
        assert tmp_game_state.get_flag("test_custom_flag") == "active"

    def test_set_flag_true(self, tmp_game_state):
        """set_flag(True) is retrieved as Python True via get_flag()."""
        tmp_game_state.set_flag("vex_appeared", True)
        assert tmp_game_state.get_flag("vex_appeared") is True

    def test_set_flag_false(self, tmp_game_state):
        """set_flag(False) is retrieved as Python False via get_flag()."""
        tmp_game_state.set_flag("genvault_connected", False)
        assert tmp_game_state.get_flag("genvault_connected") is False

    def test_get_flag_returns_default_when_not_set(self, tmp_game_state):
        """get_flag() returns the default value for a flag that has never been set."""
        result = tmp_game_state.get_flag("nonexistent_flag", default="missing")
        assert result == "missing"

    def test_set_flag_upserts_existing_flag(self, tmp_game_state):
        """set_flag() overwrites an existing flag value (upsert behaviour)."""
        tmp_game_state.set_flag("vex_appeared", False)
        tmp_game_state.set_flag("vex_appeared", True)
        assert tmp_game_state.get_flag("vex_appeared") is True

    def test_get_all_flags_returns_dict(self, tmp_game_state):
        """get_all_flags() returns a dict of all flags for the current session."""
        flags = tmp_game_state.get_all_flags()
        assert isinstance(flags, dict)
        assert len(flags) > 0


# ── Turn history ───────────────────────────────────────────────────────────────

class TestTurnHistory:

    def test_add_turn_appends_to_history(self, tmp_game_state):
        """add_turn() creates a new record visible in get_history()."""
        tmp_game_state.add_turn("hack the badge reader", "Cipher bypasses the lock.", ["Cipher"])
        history = tmp_game_state.get_history()
        assert len(history) == 1

    def test_add_turn_stores_player_input(self, tmp_game_state):
        """add_turn() persists the player_input field accurately."""
        tmp_game_state.add_turn("sneak through the vent", "Shadow moves silently.", ["Shadow"])
        history = tmp_game_state.get_history()
        assert history[0]["player_input"] == "sneak through the vent"

    def test_add_turn_stores_narrative(self, tmp_game_state):
        """add_turn() persists the narrative string accurately."""
        tmp_game_state.add_turn("action", "Ghost narrates the scene.", ["Ghost"])
        history = tmp_game_state.get_history()
        assert history[0]["narrative"] == "Ghost narrates the scene."

    def test_add_turn_stores_agents_consulted_as_list(self, tmp_game_state):
        """add_turn() deserialises agents_consulted back to a Python list."""
        tmp_game_state.add_turn("action", "narrative", ["Wraith", "Patch"])
        history = tmp_game_state.get_history()
        assert "Wraith" in history[0]["agents_consulted"]
        assert "Patch" in history[0]["agents_consulted"]

    def test_turn_count_increments_per_turn(self, tmp_game_state):
        """Session turn_count increments by 1 for each add_turn() call."""
        for i in range(3):
            tmp_game_state.add_turn(f"action {i}", f"narrative {i}", [])
        assert tmp_game_state.get_state()["turn_count"] == 3

    def test_get_history_limits_results(self, tmp_game_state):
        """get_history(last_n) returns at most last_n records."""
        for i in range(5):
            tmp_game_state.add_turn(f"action {i}", f"narrative {i}", [])
        history = tmp_game_state.get_history(last_n=3)
        assert len(history) == 3

    def test_get_conversation_history_format(self, tmp_game_state):
        """get_conversation_history() returns alternating user/assistant message dicts."""
        tmp_game_state.add_turn("player move", "ghost response", [])
        convo = tmp_game_state.get_conversation_history(last_n_turns=1)
        assert convo[0]["role"] == "user"
        assert convo[1]["role"] == "assistant"
        assert convo[0]["content"] == "player move"


# ── Reset ──────────────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_restores_phase_to_recon(self, tmp_game_state):
        """reset_session() resets phase back to 'recon'."""
        tmp_game_state.update_phase("execution")
        tmp_game_state.reset_session()
        assert tmp_game_state.get_state()["phase"] == "recon"

    def test_reset_restores_alert_to_cold(self, tmp_game_state):
        """reset_session() resets alert back to 'cold'."""
        tmp_game_state.update_alert("scorched")
        tmp_game_state.reset_session()
        assert tmp_game_state.get_state()["alert_state"] == "cold"

    def test_reset_restores_crew_to_operational(self, tmp_game_state):
        """reset_session() returns all crew members to 'operational' health."""
        tmp_game_state.update_crew("Wraith", "critical")
        tmp_game_state.reset_session()
        crew = tmp_game_state.get_crew_status()
        assert crew["Wraith"]["health_state"] == "operational"

    def test_reset_clears_turn_history(self, tmp_game_state):
        """reset_session() deletes all turn history records."""
        tmp_game_state.add_turn("action", "narrative", [])
        tmp_game_state.reset_session()
        assert tmp_game_state.get_history() == []

    def test_reset_resets_turn_count(self, tmp_game_state):
        """reset_session() resets the session turn_count to 0."""
        tmp_game_state.add_turn("action", "narrative", [])
        tmp_game_state.reset_session()
        assert tmp_game_state.get_state()["turn_count"] == 0


# ── Session persistence ────────────────────────────────────────────────────────

class TestSessionPersistence:

    def test_load_latest_session_returns_most_recent(self, tmp_path):
        """load_latest_session() loads the highest session ID (most recently created)."""
        from state.game_state import GameState
        db = tmp_path / "t.db"
        gs1 = GameState(db_path=db)
        sid1 = gs1.new_session("Mission Alpha")
        gs2 = GameState(db_path=db)
        sid2 = gs2.new_session("Mission Beta")
        gs3 = GameState(db_path=db)
        assert gs3.load_latest_session() is True
        assert gs3.session_id == sid2

    def test_load_session_by_id(self, tmp_path):
        """load_session(id) loads the specific session by ID."""
        from state.game_state import GameState
        db = tmp_path / "t.db"
        gs1 = GameState(db_path=db)
        sid = gs1.new_session("Target Session")
        gs2 = GameState(db_path=db)
        gs2.new_session("Other Session")
        gs3 = GameState(db_path=db)
        assert gs3.load_session(sid) is True
        assert gs3.session_id == sid

    def test_load_session_returns_false_for_unknown_id(self, tmp_path):
        """load_session() returns False when the given ID does not exist."""
        from state.game_state import GameState
        gs = GameState(db_path=tmp_path / "t.db")
        gs.new_session("Test")
        assert gs.load_session(9999) is False

    def test_list_sessions_returns_all(self, tmp_path):
        """list_sessions() returns an entry for every created session."""
        from state.game_state import GameState
        db = tmp_path / "t.db"
        gs = GameState(db_path=db)
        gs.new_session("Alpha")
        gs.new_session("Beta")
        gs.new_session("Gamma")
        sessions = gs.list_sessions()
        assert len(sessions) == 3
