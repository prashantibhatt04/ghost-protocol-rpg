"""
Ghost Protocol — Flask Web Application
Connects the game loop to the browser UI via a JSON API.
Single-user demo mode: GameState and GameMaster are module-level singletons.
"""

import os
import threading
import sys
from pathlib import Path

from flask import Flask, render_template, request, jsonify

sys.path.insert(0, str(Path(__file__).parent))

from agents.game_master import GameMaster
from state.game_state import GameState
from state.metrics import MetricsStore
from main import (
    _detect_roll_needed,
    _roll_modifier_for_input,
    _maybe_escalate_alert,
    _maybe_flag_vex,
    _detect_phase_advance_hint,
    _detect_extraction_attempt,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ghost-protocol-dev-key-2047")

# Allow localhost requests in dev (Flask 3.x trusted-host check)
app.config["SERVER_NAME"] = None

# ── Singleton game instances (demo / single-user) ──────────────────────────────
_lock = threading.Lock()
_gs: GameState = None
_gm: GameMaster = None
_metrics = MetricsStore()


def _dice_label(total: int) -> str:
    if total >= 20: return 'CRITICAL SUCCESS'
    if total >= 15: return 'SUCCESS'
    if total >= 10: return 'PARTIAL SUCCESS'
    return 'FAILURE'


def _get_instances():
    global _gs, _gm
    with _lock:
        if _gs is None:
            _gs = GameState()
            _gm = GameMaster()
            if not _gs.load_latest_session():
                _gs.new_session("Operation GENESIS")
    return _gs, _gm


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    gs, _ = _get_instances()
    state = gs.get_state()
    return render_template("index.html", state=state)


@app.route("/accessibility")
def accessibility():
    return render_template("accessibility.html")


@app.route("/api/state")
def api_state():
    gs, _ = _get_instances()
    return jsonify(gs.get_state())


@app.route("/api/action", methods=["POST"])
def api_action():
    gs, gm = _get_instances()

    data = request.get_json(silent=True) or {}
    player_input = (data.get("input") or "").strip()
    response_style = (data.get("response_style") or "normal").strip().lower()
    if response_style not in ("brief", "normal", "detailed"):
        response_style = "normal"

    if not player_input:
        return jsonify({"error": "Empty input"}), 400

    _metrics.record_input_validated()

    # Slash commands handled separately
    if player_input.startswith("/"):
        return _handle_command(player_input, gs, gm)

    state = gs.get_state()
    _prev_alert = state.get('alert_state', 'cold')
    flags = state.get("flags", {})

    # ── Human-in-the-loop confirmation for irreversible data extraction ────────
    _CONFIRM_WORDS = frozenset({
        "confirm", "confirmed", "yes", "do it", "go ahead",
        "proceed", "affirmative", "let's do it", "pull the trigger",
    })
    _pending = str(flags.get("pending_confirmation", "false")).lower() == "true"

    if _pending:
        # Player is responding to the confirmation prompt
        gs.set_flag("pending_confirmation", "false")
        if any(w in player_input.lower() for w in _CONFIRM_WORDS):
            # Replace their input with an unambiguous extraction command so the
            # orchestrator sets data_extracted and narrates the extraction properly
            player_input = "Extract the GenVault data now — runner confirmed."
        # else: proceed with their new action as-is (crew holds on extraction)

    elif _detect_extraction_attempt(player_input, state.get("phase", "recon"), flags):
        # Intercept — show confirmation prompt, do not run orchestrate yet
        gs.set_flag("pending_confirmation", "true")
        _confirm_narrative = (
            "This is it, runner. Once we pull this data, there's no walking it back — "
            "Nexus will know GenVault was breached, and the clock starts on retaliation.\n\n"
            "Confirm extraction? Type confirm to proceed, "
            "or give the crew different orders."
        )
        gs.add_turn(
            player_input=player_input,
            narrative=_confirm_narrative,
            agents_consulted=["Ghost"],
        )
        return jsonify({
            "narrative":          _confirm_narrative,
            "confirmation_needed": True,
            "agent_responses":    [],
            "agents_consulted":   ["Ghost"],
            "iq_relevant":        False,
            "dice_roll":          None,
            "success":            True,
            "pacifist_trigger":   False,
            "total_tokens":       0,
            "iq_mode":            "local",
            "iq_elapsed_ms":      0,
            "iq_files_hit":       [],
            "suggestions":        ["confirm", "Hold position", "Reconsider approach"],
            "state":              gs.get_state(),
        })

    # Decide dice roll
    state["requires_roll"] = _detect_roll_needed(player_input)
    state["roll_modifier"] = _roll_modifier_for_input(
        player_input, state.get("crew_detail", {})
    )

    result = gm.orchestrate(player_input, state, response_style=response_style)

    # Record blocked inputs
    if result.get("error") and not result.get("agent_responses"):
        _metrics.record_blocked(result.get("error", "unknown"))

    if result.get("success") or result.get("agent_responses"):
        _maybe_escalate_alert(result, gs, state)
        _maybe_flag_vex(result, gs)
        # Mark Vex as appeared immediately so future turns don't retrigger the full encounter
        if result.get("vex_encounter"):
            gs.set_flag("vex_appeared", True)

        # ── Non-combatant violence morale tracking ─────────────────────────────
        if result.get("pacifist_trigger"):
            if str(gs.get_flag("patch_objected", "false")).lower() == "true":
                # Player is ignoring Patch's prior objection — consequences apply
                morale_map = {"high": "ok", "ok": "low", "low": "low"}
                current_morale = gs.get_flag("crew_morale", "high") or "high"
                gs.set_flag("crew_morale", morale_map.get(str(current_morale), "low"))
                # Escalate alert by one level
                _alert_order = ["cold", "warm", "hot", "scorched"]
                _cur_alert   = state.get("alert_state", "cold")
                _cur_idx     = _alert_order.index(_cur_alert) if _cur_alert in _alert_order else 0
                if _cur_idx < len(_alert_order) - 1:
                    gs.update_alert(_alert_order[_cur_idx + 1])
            else:
                # First time Patch objects — set the flag so next repeat triggers consequences
                gs.set_flag("patch_objected", "true")
        else:
            # Player took a non-violent action — clear the pending objection
            if str(gs.get_flag("patch_objected", "false")).lower() == "true":
                gs.set_flag("patch_objected", "false")

        new_state = gs.get_state()
        turn = new_state.get('turn_count', 0)

        gs.add_turn(
            player_input=player_input,
            narrative=result.get("narrative", ""),
            agents_consulted=result.get("agents_consulted", []),
            dice_roll=result.get("dice_roll"),
            alert_state=new_state["alert_state"],
        )

        # Phase auto-advance
        if _detect_phase_advance_hint(player_input, state["phase"]):
            next_phase = gm.advance_phase(state["phase"])
            if next_phase != state["phase"]:
                gs.update_phase(next_phase)
                result["phase_advanced"] = next_phase
                _metrics.record_phase_change(next_phase, turn)

        # Record alert escalation
        _new_alert = gs.get_state().get('alert_state', 'cold')
        if _new_alert != _prev_alert:
            _metrics.record_alert_change(
                _prev_alert, _new_alert,
                'Escalated by narrative keywords', turn
            )

        # Record per-agent metrics
        for r in result.get("agent_responses", []):
            _metrics.record_agent_call(
                r.get("agent_name", "Unknown"),
                r.get("tokens_used", 0),
                r.get("elapsed_seconds", 0.0),
                r.get("success", False),
            )

        # Record IQ query
        if result.get("iq_files_hit") is not None:
            _metrics.record_iq_query(
                player_input,
                result.get("iq_files_hit", []),
                result.get("iq_elapsed_ms", 0.0),
            )

        # Record dice roll
        if result.get("dice_roll"):
            d = result["dice_roll"]
            _metrics.record_dice(d["total"], d["sides"], _dice_label(d["total"]))

    result["state"] = gs.get_state()
    return jsonify(result)


@app.route("/api/vex_choice", methods=["POST"])
def api_vex_choice():
    """
    Resolve the player's Vex moral choice (A = accept, B = reject).
    Applies flag consequences, generates Ghost's consequence narrative, and logs the turn.
    Option C (ask Patch) is handled entirely client-side — the patch_assessment is already
    embedded in the vex_encounter payload returned by /api/action.
    """
    gs, gm = _get_instances()
    data   = request.get_json(silent=True) or {}
    choice = (data.get("choice") or "").upper()

    if choice not in ("A", "B"):
        return jsonify({"error": "Invalid choice — must be A or B"}), 400

    # ── Apply consequences ─────────────────────────────────────────────────────
    try:
        loyalty = int(gs.get_flag("crew_loyalty", "100") or 100)
    except (TypeError, ValueError):
        loyalty = 100

    if choice == "A":
        gs.set_flag("vex_deal_taken", True)
        gs.set_flag("vex_trusted",    True)
        gs.set_flag("mission_speed",  "fast")
        gs.set_flag("crew_loyalty",   str(max(0, loyalty - 25)))
    else:
        gs.set_flag("vex_deal_taken", False)
        gs.set_flag("vex_trusted",    False)
        gs.set_flag("mission_speed",  "slow")
        gs.set_flag("crew_loyalty",   str(min(150, loyalty + 15)))

    gs.set_flag("vex_appeared", True)

    # ── Generate Ghost's consequence narration ─────────────────────────────────
    updated_state = gs.get_state()
    narrative = gm._vex_choice_narrative(
        "accept" if choice == "A" else "reject",
        updated_state,
    )

    gs.add_turn(
        player_input=f"[VEX CHOICE: {'ACCEPT' if choice == 'A' else 'REJECT'}]",
        narrative=narrative,
        agents_consulted=["Vex"],
    )
    _metrics.record_agent_call("Vex", 0, 0.0, True)

    return jsonify({
        "narrative":    narrative,
        "choice":       choice,
        "vex_resolved": True,
        "state":        gs.get_state(),
    })


@app.route("/api/brief", methods=["POST"])
def api_brief():
    gs, _ = _get_instances()
    data = request.get_json(silent=True) or {}
    mode = bool(data.get("mode", True))
    gs.set_flag("brief_mode", mode)
    return jsonify({"brief_mode": mode, "state": gs.get_state()})


@app.route("/api/history")
def api_history():
    gs, _ = _get_instances()
    n = request.args.get("n", 20, type=int)
    return jsonify(gs.get_history(last_n=n))


@app.route("/api/new_session", methods=["POST"])
def api_new_session():
    global _gs, _gm
    data = request.get_json(silent=True) or {}
    mission = data.get("mission", "Operation GENESIS")
    with _lock:
        _gs = GameState()
        _gm = GameMaster()
        _gs.new_session(mission)
    _metrics.reset()
    return jsonify({"status": "ok", "mission": mission, "state": _gs.get_state()})


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/metrics")
def api_metrics():
    gs, _ = _get_instances()
    data = _metrics.snapshot()
    state = gs.get_state()
    data["game"]["turn_count"]     = state.get("turn_count", 0)
    data["game"]["current_phase"]  = state.get("phase", "recon")
    data["game"]["current_alert"]  = state.get("alert_state", "cold")
    data["game"]["mission"]        = state.get("mission", "Operation GENESIS")
    return jsonify(data)


# ── Command Handler ────────────────────────────────────────────────────────────

def _handle_command(cmd: str, gs: GameState, gm: GameMaster):
    parts = cmd.strip().lower().split()
    verb  = parts[0] if parts else ""

    VALID_PHASES = ("recon", "infiltration", "execution", "extraction", "complete")
    VALID_ALERTS = ("cold", "warm", "hot", "scorched")
    VALID_CREW   = ["Wraith", "Cipher", "Shadow", "Patch"]

    def _ok(msg):
        return jsonify({"command_result": msg, "state": gs.get_state()})

    def _err(msg):
        return jsonify({"command_result": msg, "state": gs.get_state()}), 400

    if verb == "/phase":
        new = parts[1] if len(parts) > 1 else ""
        if new not in VALID_PHASES:
            return _err(f"Invalid phase. Valid: {', '.join(VALID_PHASES)}")
        gs.update_phase(new)
        return _ok(f"Phase set to: {new.upper()}")

    elif verb == "/alert":
        new = parts[1] if len(parts) > 1 else ""
        if new not in VALID_ALERTS:
            return _err(f"Invalid alert. Valid: {', '.join(VALID_ALERTS)}")
        gs.update_alert(new)
        return _ok(f"Alert level: {new.upper()}")

    elif verb == "/heal":
        name = parts[1].capitalize() if len(parts) > 1 else ""
        if name not in VALID_CREW:
            return _err("Unknown crew member. Valid: Wraith, Cipher, Shadow, Patch")
        gs.update_crew(name, "operational")
        return _ok(f"{name} restored to operational.")

    elif verb == "/wound":
        name = parts[1].capitalize() if len(parts) > 1 else ""
        if name not in VALID_CREW:
            return _err("Unknown crew member.")
        gs.update_crew(name, "wounded", notes="Field injury")
        return _ok(f"{name} marked as wounded.")

    elif verb == "/critical":
        name = parts[1].capitalize() if len(parts) > 1 else ""
        if name not in VALID_CREW:
            return _err("Unknown crew member.")
        gs.update_crew(name, "critical", notes="Critical — needs immediate stabilization")
        return _ok(f"{name} marked as critical.")

    elif verb == "/complete":
        key = parts[1] if len(parts) > 1 else ""
        if not key:
            return _err("Usage: /complete <obj_key>")
        gs.complete_objective(key)
        return _ok(f"Objective complete: {key}")

    elif verb == "/new":
        mission = " ".join(parts[1:]) if len(parts) > 1 else "Operation GENESIS"
        gs.new_session(mission.title())
        return _ok(f"New session started: {mission.title()}")

    elif verb == "/help":
        help_lines = [
            "/phase &lt;name&gt;     — set heist phase (recon/infiltration/execution/extraction)",
            "/alert &lt;level&gt;    — set alert level (cold/warm/hot/scorched)",
            "/heal &lt;name&gt;      — restore crew member to operational",
            "/wound &lt;name&gt;     — mark crew member as wounded",
            "/critical &lt;name&gt;  — mark crew member as critical",
            "/complete &lt;key&gt;   — mark objective complete",
            "/new [mission]    — start a new session",
        ]
        return _ok("<br>".join(help_lines))

    else:
        return _err(f"Unknown command: {cmd}. Type /help")


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  GHOST PROTOCOL — Web UI")
    print("  http://localhost:5000\n")
    app.run(debug=True, port=5000, use_reloader=False)
