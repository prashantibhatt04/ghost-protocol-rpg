"""
Ghost Protocol — CLI Game Loop
Entry point for interactive terminal play. Run `python main.py` to start.
For the web UI, run `python app.py` instead — it serves the Flask interface on localhost:5000.

Player input → Ghost (GM) → specialist agents → narrated response.
Handles heist phase progression, dice rolls, and Vex complications.
"""

import sys
import re
import textwrap
from pathlib import Path

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from agents.game_master import GameMaster
from state.game_state import GameState

# ── ANSI Colours ───────────────────────────────────────────────────────────────
C = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "ghost":   "\033[96m",    # bright cyan  — Ghost / GM
    "wraith":  "\033[91m",    # bright red   — Wraith
    "cipher":  "\033[92m",    # bright green — Cipher
    "shadow":  "\033[95m",    # bright magenta — Shadow
    "patch":   "\033[93m",    # bright yellow  — Patch
    "vex":     "\033[31m",    # dark red        — Vex
    "system":  "\033[90m",    # dark grey       — system messages
    "warn":    "\033[33m",    # yellow          — warnings
    "phase":   "\033[34m",    # blue            — phase labels
    "dice":    "\033[35m",    # magenta         — dice rolls
    "success": "\033[32m",    # green           — success
    "fail":    "\033[31m",    # red             — failure
}

AGENT_COLOURS = {
    "Ghost":  C["ghost"],
    "Wraith": C["wraith"],
    "Cipher": C["cipher"],
    "Shadow": C["shadow"],
    "Patch":  C["patch"],
    "Vex":    C["vex"],
}

PHASE_LABELS = {
    "recon":        "[ RECON ]",
    "infiltration": "[ INFILTRATION ]",
    "execution":    "[ EXECUTION ]",
    "extraction":   "[ EXTRACTION ]",
    "complete":     "[ MISSION COMPLETE ]",
}

ALERT_COLOURS = {
    "cold":     C["system"],
    "warm":     C["warn"],
    "hot":      "\033[33;1m",   # bold yellow
    "scorched": C["fail"],
}

# Actions that should trigger a dice roll
_ROLL_KEYWORDS = [
    "hack", "break", "bypass", "disable", "crack", "infiltrate", "sneak",
    "move", "climb", "jump", "fight", "shoot", "attack", "neutralise", "neutralize",
    "negotiate", "persuade", "bluff", "deceive", "steal", "grab", "extract",
    "pick", "lock", "sprint", "dodge", "hide", "scan",
]

# Objective keywords used for auto-completion hints
_PHASE_ADVANCE_HINTS = {
    "recon":        ["ready", "let's go", "move in", "begin infiltration", "start infiltration"],
    "infiltration": ["inside", "we're in", "reach b3", "found the server", "begin extraction", "execute"],
    "execution":    ["data extracted", "transfer complete", "we have it", "get out", "extract"],
    "extraction":   ["clean", "made it", "we're out", "mission complete"],
}

TERMINAL_WIDTH = 80


# ── Formatting Helpers ─────────────────────────────────────────────────────────

def _c(colour_key: str, text: str) -> str:
    return f"{C.get(colour_key, '')}{text}{C['reset']}"


def _wrap(text: str, indent: int = 0, width: int = TERMINAL_WIDTH) -> str:
    prefix = " " * indent
    lines = text.splitlines()
    wrapped = []
    for line in lines:
        if line.strip() == "":
            wrapped.append("")
        else:
            wrapped.extend(textwrap.wrap(line, width=width - indent, initial_indent=prefix, subsequent_indent=prefix))
    return "\n".join(wrapped)


def _divider(char: str = "─", width: int = TERMINAL_WIDTH) -> str:
    return _c("system", char * width)


def _section(label: str, colour: str = "ghost") -> str:
    pad = (TERMINAL_WIDTH - len(label) - 4) // 2
    return f"{C['system']}{'─' * pad}[ {C[colour]}{label}{C['reset']}{C['system']} ]{'─' * pad}{C['reset']}"


def print_banner():
    banner = r"""
  ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗
 ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝
 ██║  ███╗███████║██║   ██║███████╗   ██║
 ██║   ██║██╔══██║██║   ██║╚════██║   ██║
 ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝
 ██████╗ ██████╗  ██████╗ ████████╗ ██████╗  ██████╗ ██████╗ ██╗
 ██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██╔═══██╗██╔════╝██╔═══██╗██║
 ██████╔╝██████╔╝██║   ██║   ██║   ██║   ██║██║     ██║   ██║██║
 ██╔═══╝ ██╔══██╗██║   ██║   ██║   ██║   ██║██║     ██║   ██║██║
 ██║     ██║  ██║╚██████╔╝   ██║   ╚██████╔╝╚██████╗╚██████╔╝███████╗
 ╚═╝     ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝"""
    print(_c("ghost", banner))
    print(_c("system", "  Toronto 2047  ·  Multi-Agent Cyberpunk Heist RPG  ·  Azure OpenAI"))
    print(_c("system", "  " + "─" * (TERMINAL_WIDTH - 2)))
    print()


def _print_crew_bar(crew_detail: dict):
    health_icons = {
        "operational": _c("success", "●"),
        "wounded":      _c("warn",    "◑"),
        "critical":     _c("fail",    "○"),
    }
    parts = []
    for name, info in crew_detail.items():
        if name == "Vex":
            continue  # Vex isn't on the crew manifest
        icon = health_icons.get(info["health_state"], "?")
        col = AGENT_COLOURS.get(name, "")
        parts.append(f"{icon} {col}{name}{C['reset']}")
    print("  " + "  ".join(parts))


def _print_state_header(state: dict):
    phase = state["phase"]
    alert = state["alert_state"]
    turn  = state["turn_count"]

    phase_label  = PHASE_LABELS.get(phase, phase.upper())
    alert_colour = ALERT_COLOURS.get(alert, C["system"])

    print(_divider())
    print(
        f"  {C['phase']}{C['bold']}{phase_label}{C['reset']}"
        f"   {alert_colour}ALERT: {alert.upper()}{C['reset']}"
        f"   {C['system']}Turn {turn}{C['reset']}"
    )
    _print_crew_bar(state.get("crew_detail", {}))
    print(_divider())


def _print_objectives(objectives: list, phase: str):
    print(_section("OBJECTIVES", "phase"))
    phase_objs = [o for o in objectives if o["phase"] == phase]
    for obj in phase_objs:
        if obj["status"] == "complete":
            marker = _c("success", "[✓]")
        elif obj["status"] == "failed":
            marker = _c("fail",    "[✗]")
        else:
            marker = _c("system",  "[ ]")
        print(f"  {marker} {_c('system', obj['description'])}")
    print()


def _print_agent_response(result: dict):
    name   = result.get("agent_name", "Unknown")
    role   = result.get("role", "")
    colour = AGENT_COLOURS.get(name, C["system"])
    text   = result.get("response", "")

    print()
    print(f"  {colour}{C['bold']}▸ {name.upper()}{C['reset']}  {C['system']}({role}){C['reset']}")
    print(_c("system", "  " + "┄" * (TERMINAL_WIDTH - 4)))
    print(_wrap(text, indent=4))


def _print_narrative(narrative: str):
    print()
    print(_section("GHOST", "ghost"))
    print()
    print(_wrap(narrative, indent=4))
    print()


def _print_dice(dice: dict):
    if not dice:
        return
    raw   = dice["raw"]
    mod   = dice["modifier"]
    total = dice["total"]
    sides = dice["sides"]
    colour = C["success"] if total >= 15 else (C["warn"] if total >= 10 else C["fail"])
    result_label = "CRITICAL SUCCESS" if total >= 20 else \
                   "SUCCESS"          if total >= 12 else \
                   "PARTIAL"          if total >= 8  else "FAILURE"
    print(
        f"  {C['dice']}🎲 d{sides}{C['reset']}"
        f"  raw={_c('dice', str(raw))}"
        f"  mod={_c('system', ('+' if mod >= 0 else '') + str(mod))}"
        f"  total={colour}{C['bold']}{total}{C['reset']}"
        f"  {colour}{result_label}{C['reset']}"
    )
    print()


# ── Input Helpers ──────────────────────────────────────────────────────────────

# Keywords for extraction attempt detection
_EXTRACTION_ACTION_WORDS = frozenset({
    "extract", "extraction", "pull", "download", "copy", "breach",
    "initiate", "begin", "start", "trigger", "run", "connect",
    "access", "grab", "steal", "exfiltrate", "transfer",
})
_EXTRACTION_TARGET_WORDS = frozenset({
    "data", "genvault", "gendata", "genome", "vault", "files",
    "biodata", "records",
})
_EXTRACTION_PHRASES = frozenset({
    "extract the data", "pull the data", "download the data",
    "copy the data", "grab the data", "breach the genvault",
    "access the genvault", "connect to the genvault",
    "initiate extraction", "begin extraction", "start extraction",
    "run extraction", "trigger extraction", "exfiltrate",
    "extract the genome", "genvault extraction", "data extraction",
    "do the extraction", "perform the extraction",
    "complete the extraction", "finish the extraction",
})


def _detect_extraction_attempt(
    player_input: str,
    phase: str,
    flags: dict,
) -> bool:
    """
    Returns True when the player is attempting to extract the GenVault data and
    a human-in-the-loop confirmation prompt should be shown first.

    Guards:
    - Phase must be execution or extraction
    - data_extracted must not already be true
    - pending_confirmation must not already be true (no double-trigger)
    """
    if phase not in ("execution", "extraction"):
        return False
    if str(flags.get("data_extracted", "false")).lower() == "true":
        return False
    if str(flags.get("pending_confirmation", "false")).lower() == "true":
        return False

    text = player_input.lower()
    if any(phrase in text for phrase in _EXTRACTION_PHRASES):
        return True
    has_action = any(w in text for w in _EXTRACTION_ACTION_WORDS)
    has_target = any(w in text for w in _EXTRACTION_TARGET_WORDS)
    return has_action and has_target


def _detect_roll_needed(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _ROLL_KEYWORDS)


def _detect_phase_advance_hint(text: str, phase: str) -> bool:
    text_lower = text.lower()
    hints = _PHASE_ADVANCE_HINTS.get(phase, [])
    return any(h in text_lower for h in hints)


def _roll_modifier_for_input(text: str, crew_detail: dict) -> int:
    """Derive a rough roll modifier based on active crew health."""
    modifier = 0
    text_lower = text.lower()

    # Specialist bonus for relevant actions
    if any(k in text_lower for k in ["hack", "bypass", "crack", "system", "network"]):
        cipher_state = crew_detail.get("Cipher", {}).get("health_state", "operational")
        if cipher_state == "operational":
            modifier += 3   # Cipher's hacking bonus
        elif cipher_state == "wounded":
            modifier += 1
    elif any(k in text_lower for k in ["sneak", "stealth", "shadow", "infiltrate", "move quietly"]):
        shadow_state = crew_detail.get("Shadow", {}).get("health_state", "operational")
        if shadow_state == "operational":
            modifier += 4
        elif shadow_state == "wounded":
            modifier += 2
    elif any(k in text_lower for k in ["fight", "attack", "shoot", "neutralise", "neutralize", "take down"]):
        wraith_state = crew_detail.get("Wraith", {}).get("health_state", "operational")
        if wraith_state == "operational":
            modifier += 4
        elif wraith_state == "wounded":
            modifier += 1
    elif any(k in text_lower for k in ["negotiate", "persuade", "talk", "bluff", "deceive"]):
        patch_state = crew_detail.get("Patch", {}).get("health_state", "operational")
        if patch_state == "operational":
            modifier += 3
        elif patch_state == "wounded":
            modifier += 1

    return modifier


# ── Command Handler ────────────────────────────────────────────────────────────

def handle_command(cmd: str, gs: GameState, gm: GameMaster) -> bool:
    """
    Handle /slash commands. Returns True to continue loop, False to exit.
    """
    parts = cmd.strip().lower().split()
    verb  = parts[0] if parts else ""

    if verb in ("/quit", "/exit", "/q"):
        print()
        print(_c("ghost", "  Ghost: Signal going dark. Watch your backs out there."))
        print()
        return False

    elif verb in ("/help", "/h", "/?"):
        print()
        print(_section("COMMANDS", "phase"))
        commands = [
            ("/help",         "Show this help"),
            ("/status",       "Show full crew status"),
            ("/objectives",   "Show all mission objectives"),
            ("/phase <name>", "Manually advance phase (recon/infiltration/execution/extraction)"),
            ("/alert <level>","Set alert level (cold/warm/hot/scorched)"),
            ("/complete <key>","Mark an objective complete"),
            ("/heal <name>",  "Restore a crew member to operational"),
            ("/wound <name>", "Mark a crew member as wounded"),
            ("/sessions",     "List all saved sessions"),
            ("/new",          "Start a new session"),
            ("/load <id>",    "Load a saved session by ID"),
            ("/snapshot",     "Export current session to JSON"),
            ("/quit",         "Exit the game"),
        ]
        for cmd_str, desc in commands:
            print(f"  {_c('cipher', cmd_str):<30} {_c('system', desc)}")
        print()

    elif verb == "/status":
        state = gs.get_state()
        print()
        print(_section("CREW STATUS", "phase"))
        for name, info in state["crew_detail"].items():
            h = info["health_state"]
            col = C["success"] if h == "operational" else (C["warn"] if h == "wounded" else C["fail"])
            aug = "  [augment damaged]" if info.get("augment_damaged") else ""
            notes = f"  — {info['notes']}" if info.get("notes") else ""
            print(f"  {AGENT_COLOURS.get(name, '')}{name:<12}{C['reset']} {col}{h}{C['reset']}{aug}{_c('system', notes)}")
        print()
        print(_section("WORLD FLAGS", "phase"))
        for k, v in state["flags"].items():
            val_col = C["success"] if v is True or v == "true" else C["system"]
            print(f"  {_c('system', k):<35} {val_col}{v}{C['reset']}")
        print()

    elif verb == "/objectives":
        state = gs.get_state()
        print()
        print(_section("ALL OBJECTIVES", "phase"))
        for phase in ("recon", "infiltration", "execution", "extraction"):
            phase_objs = [o for o in state["objectives"] if o["phase"] == phase]
            if phase_objs:
                print(f"  {C['phase']}{phase.upper()}{C['reset']}")
                for obj in phase_objs:
                    s = obj["status"]
                    icon = _c("success", "✓") if s == "complete" else (_c("fail", "✗") if s == "failed" else _c("system", "·"))
                    print(f"    {icon} {_c('system', obj['description'])}")
        print()

    elif verb == "/phase":
        new_phase = parts[1] if len(parts) > 1 else ""
        valid = ("recon", "infiltration", "execution", "extraction", "complete")
        if new_phase not in valid:
            print(_c("warn", f"  Invalid phase. Choose: {', '.join(valid)}"))
        else:
            gs.update_phase(new_phase)
            print(_c("success", f"  Phase set to: {new_phase}"))
        print()

    elif verb == "/alert":
        new_alert = parts[1] if len(parts) > 1 else ""
        valid = ("cold", "warm", "hot", "scorched")
        if new_alert not in valid:
            print(_c("warn", f"  Invalid alert. Choose: {', '.join(valid)}"))
        else:
            gs.update_alert(new_alert)
            print(_c("success", f"  Alert set to: {new_alert}"))
        print()

    elif verb == "/complete":
        obj_key = parts[1] if len(parts) > 1 else ""
        if not obj_key:
            print(_c("warn", "  Usage: /complete <obj_key>"))
        else:
            gs.complete_objective(obj_key)
            print(_c("success", f"  Objective marked complete: {obj_key}"))
        print()

    elif verb == "/heal":
        name = parts[1].capitalize() if len(parts) > 1 else ""
        if name not in ["Ghost", "Wraith", "Cipher", "Shadow", "Patch"]:
            print(_c("warn", "  Unknown crew member."))
        else:
            gs.update_crew(name, "operational")
            print(_c("success", f"  {name} restored to operational."))
        print()

    elif verb == "/wound":
        name = parts[1].capitalize() if len(parts) > 1 else ""
        if name not in ["Ghost", "Wraith", "Cipher", "Shadow", "Patch"]:
            print(_c("warn", "  Unknown crew member."))
        else:
            gs.update_crew(name, "wounded", notes="Field injury")
            print(_c("warn", f"  {name} marked as wounded."))
        print()

    elif verb == "/sessions":
        sessions = gs.list_sessions()
        print()
        print(_section("SAVED SESSIONS", "phase"))
        if not sessions:
            print(_c("system", "  No sessions found."))
        for s in sessions:
            print(f"  {_c('ghost', str(s['id']))}  {s['mission_name']:<30} "
                  f"phase={_c('phase', s['phase'])}  turns={s['turn_count']}  {_c('system', s['created_at'])}")
        print()

    elif verb == "/new":
        mission = " ".join(parts[1:]) if len(parts) > 1 else "Operation GENESIS"
        gs.new_session(mission)
        print(_c("success", f"  New session started: {mission}"))
        print()

    elif verb == "/load":
        sid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        if sid is None:
            print(_c("warn", "  Usage: /load <session_id>"))
        elif gs.load_session(sid):
            print(_c("success", f"  Session {sid} loaded."))
        else:
            print(_c("fail", f"  Session {sid} not found."))
        print()

    elif verb == "/snapshot":
        path = gs.save_snapshot()
        print(_c("success", f"  Snapshot saved: {path}"))
        print()

    else:
        print(_c("warn", f"  Unknown command: {cmd}. Type /help for commands."))
        print()

    return True  # continue loop


# ── Alert Escalation ───────────────────────────────────────────────────────────

_ALERT_LADDER = ["cold", "warm", "hot", "scorched"]

def _maybe_escalate_alert(result: dict, gs: GameState, state: dict):
    """Check narrative for escalation keywords and bump alert if needed."""
    narrative = (result.get("narrative") or "").lower()
    current   = state["alert_state"]
    idx       = _ALERT_LADDER.index(current) if current in _ALERT_LADDER else 0

    escalate_triggers = ["alert", "alarm", "detected", "compromised", "scorched", "lockdown", "guard spotted"]
    if any(t in narrative for t in escalate_triggers) and idx < len(_ALERT_LADDER) - 1:
        new_alert = _ALERT_LADDER[idx + 1]
        gs.update_alert(new_alert)
        print(_c("warn", f"\n  ⚠  Alert escalated: {current.upper()} → {new_alert.upper()}"))


def _maybe_flag_vex(result: dict, gs: GameState):
    """Set vex_appeared flag if Vex was consulted."""
    agents = result.get("agents_consulted", [])
    if "Vex" in agents and not gs.get_flag("vex_appeared"):
        gs.set_flag("vex_appeared", True)


# ── Main Loop ──────────────────────────────────────────────────────────────────

def run():
    print_banner()

    # ── Session setup ──────────────────────────────────────────────────────────
    gs = GameState()
    gm = GameMaster()

    existing = gs.list_sessions()
    if existing:
        print(_c("ghost", "  GHOST: Welcome back, operator."))
        print()
        print(f"  {_c('system', 'Existing sessions:')}")
        for s in existing[:5]:
            print(f"    {_c('ghost', str(s['id']))}  {s['mission_name']}  "
                  f"phase={s['phase']}  turns={s['turn_count']}")
        print()
        choice = input(_c("system", "  Load latest session? [Y/n/new]: ")).strip().lower()
        if choice in ("", "y", "yes"):
            gs.load_latest_session()
            print(_c("success", "  Session loaded."))
        elif choice == "new":
            gs.new_session("Operation GENESIS")
            print(_c("success", "  New session started: Operation GENESIS"))
        else:
            gs.new_session("Operation GENESIS")
    else:
        gs.new_session("Operation GENESIS")
        print(_c("ghost", "  GHOST: New session initialised. Operation GENESIS is a go."))

    print()

    # ── Opening brief ──────────────────────────────────────────────────────────
    state = gs.get_state()
    _print_state_header(state)
    print()
    print(_c("ghost", "  GHOST: You're patched in, crew. Nexus Tower. Sub-level B3."))
    print(_c("ghost", "         GenVault data. We get in, we extract, we disappear."))
    print(_c("ghost", "         No names. No traces. Type /help for commands."))
    print()
    print(_c("system", "  What's your move?"))
    print()

    # ── Main game loop ─────────────────────────────────────────────────────────
    while True:
        state = gs.get_state()
        phase = state["phase"]

        if phase == "complete":
            print()
            print(_section("MISSION COMPLETE", "success"))
            print()
            print(_c("ghost", "  GHOST: Data's clean. Crew's intact. Ghost Protocol out."))
            print()
            break

        # Prompt
        try:
            phase_label = PHASE_LABELS.get(phase, phase.upper())
            alert_col   = ALERT_COLOURS.get(state["alert_state"], C["system"])
            prompt_str  = (
                f"\n{C['phase']}{phase_label}{C['reset']} "
                f"{alert_col}{state['alert_state'].upper()}{C['reset']}"
                f"{C['system']} >{C['reset']} "
            )
            user_input = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print(_c("ghost", "\n  GHOST: Signal lost. Stay frosty."))
            break

        if not user_input:
            continue

        # /commands
        if user_input.startswith("/"):
            keep_going = handle_command(user_input, gs, gm)
            if not keep_going:
                break
            continue

        # ── Dice roll decision ─────────────────────────────────────────────────
        requires_roll = _detect_roll_needed(user_input)
        modifier      = _roll_modifier_for_input(user_input, state.get("crew_detail", {}))

        # Conversation history for GM context continuity
        conv_history = gs.get_conversation_history(last_n_turns=3)

        # Assemble game_state for orchestration
        orch_state = {**state, "requires_roll": requires_roll, "roll_modifier": modifier}

        # ── Orchestrate ────────────────────────────────────────────────────────
        print()
        print(_c("system", "  [ Processing… ]"))

        result = gm.orchestrate(user_input, orch_state)

        if not result.get("success") and not result.get("agent_responses"):
            print(_c("fail", f"  Error: {result.get('error', 'Unknown error')}"))
            continue

        # ── Display: agent responses ───────────────────────────────────────────
        print()
        _print_state_header(state)

        if result.get("agent_responses"):
            print(_section("CREW ASSESSMENT", "system"))
            for agent_result in result["agent_responses"]:
                if agent_result.get("success"):
                    _print_agent_response(agent_result)
            print()

        # ── Display: dice roll ─────────────────────────────────────────────────
        if result.get("dice_roll"):
            _print_dice(result["dice_roll"])

        # ── Display: GM narrative ──────────────────────────────────────────────
        _print_narrative(result.get("narrative", ""))

        # ── State updates ──────────────────────────────────────────────────────
        _maybe_escalate_alert(result, gs, state)
        _maybe_flag_vex(result, gs)

        # Log the turn
        gs.add_turn(
            player_input=user_input,
            narrative=result.get("narrative", ""),
            agents_consulted=result.get("agents_consulted", []),
            dice_roll=result.get("dice_roll"),
            alert_state=state["alert_state"],
        )

        # ── Phase advancement hint ─────────────────────────────────────────────
        if _detect_phase_advance_hint(user_input, phase):
            next_phase = gm.advance_phase(phase)
            if next_phase != phase:
                gs.update_phase(next_phase)
                print(_c("phase", f"\n  ▸ Phase advancing: {phase.upper()} → {next_phase.upper()}"))
                print(_c("ghost", f"  GHOST: Moving to {next_phase}. Stay sharp."))

        # ── Current objectives sidebar ─────────────────────────────────────────
        updated_state = gs.get_state()
        if updated_state["objectives"]:
            _print_objectives(updated_state["objectives"], updated_state["phase"])


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
