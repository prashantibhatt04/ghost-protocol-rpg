"""
Ghost Protocol — Demo Script
Operation GENESIS: Extract biotech data from Nexus Corp Tower.

Fully automated — no player input required.
All 6 agents participate. 4 heist phases. Runs in under 3 minutes.

Usage:
    python demo.py
"""

import sys
import time
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.game_master import GameMaster
from knowledge.foundry_iq import _KEYWORD_MAP
from agents.vex import Vex
from state.game_state import GameState


# ── ANSI colours ───────────────────────────────────────────────────────────────
C = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "ghost":   "\033[96m",    # bright cyan    — Ghost / GM
    "wraith":  "\033[91m",    # bright red     — Wraith
    "cipher":  "\033[92m",    # bright green   — Cipher
    "shadow":  "\033[95m",    # bright magenta — Shadow
    "patch":   "\033[93m",    # bright yellow  — Patch
    "vex":     "\033[31m",    # dark red        — Vex
    "system":  "\033[90m",    # dark grey       — system
    "warn":    "\033[33m",    # yellow          — warnings / player actions
    "phase":   "\033[34m",    # blue            — phase banners
    "kb":      "\033[36m",    # cyan            — knowledge base
    "success": "\033[32m",    # green           — success
    "sep":     "\033[34m",    # blue            — separators
}

AGENT_COLOURS = {
    "Ghost":  C["ghost"],
    "Wraith": C["wraith"],
    "Cipher": C["cipher"],
    "Shadow": C["shadow"],
    "Patch":  C["patch"],
    "Vex":    C["vex"],
}


# ── Print helpers ──────────────────────────────────────────────────────────────

def banner(text: str, colour: str = None, width: int = 70):
    colour = colour or C["phase"]
    pad = "═" * max(0, (width - len(text) - 2) // 2)
    print(f"\n{colour}{C['bold']}{pad} {text} {pad}{C['reset']}")


def hr(width: int = 70, colour: str = None):
    print(f"{colour or C['sep']}{'─' * width}{C['reset']}")


def print_narrative(text: str, colour: str = None, indent: int = 4):
    colour = colour or C["ghost"]
    prefix = " " * indent
    for line in textwrap.wrap(text, width=68 - indent):
        print(f"{prefix}{colour}{line}{C['reset']}")


def print_agent(name: str, response: str):
    colour = AGENT_COLOURS.get(name, C["system"])
    print(f"\n  {colour}{C['bold']}◈ {name.upper()}{C['reset']}")
    for line in textwrap.wrap(response, width=64):
        print(f"    {colour}{line}{C['reset']}")


def print_kb_query(query: str, matched_keys: list[str]):
    print(f"\n  {C['kb']}{C['bold']}⚙ [KNOWLEDGE QUERY]{C['reset']}")
    print(f"  {C['kb']}  Query : \"{query}\"{C['reset']}")
    print(f"  {C['kb']}  Files : {', '.join(matched_keys) or 'world'}{C['reset']}")


def pause(msg: str = "", seconds: float = 0.6):
    if msg:
        print(f"\n{C['dim']}  {msg}{C['reset']}")
    time.sleep(seconds)


# ── Knowledge query helpers ────────────────────────────────────────────────────

def infer_matched_keys(query: str, max_files: int = 2) -> list[str]:
    """Mirror game_master.query_knowledge key-matching for display."""
    query_lower = query.lower()
    matched = []
    for key, keywords in _KEYWORD_MAP.items():
        if any(kw in query_lower for kw in keywords):
            matched.append(key)
    return list(dict.fromkeys(matched))[:max_files] or ["world"]


# ── Pre-mission knowledge queries (3 explicit, visibly logged) ─────────────────
# Each entry: (query_text, description)
PRE_MISSION_QUERIES = [
    (
        "nexus corp corporation axiom helix",
        "Corporate intel — Nexus Corp profile, security division hierarchy",
    ),
    (
        "spire district toronto 2047 sublevel B3 service bay",
        "District layout — Spire commercial zone, Nexus Tower service infrastructure",
    ),
    (
        "genvault heist target genesis mission extraction data transfer",
        "Heist brief — Operation GENESIS objectives and GenVault access protocols",
    ),
]


# ── Automated heist script ─────────────────────────────────────────────────────
# Each turn: (phase, player_action, [objectives_to_complete])
DEMO_TURNS = [
    (
        "recon",
        "Scan the Nexus Corp Tower exterior perimeter. Map guard rotations and "
        "identify every ARGUS-3 camera dead zone around the service bay entrance.",
        ["obj_recon_security"],
    ),
    (
        "recon",
        "Access the Nexus Tower building management subnet and pinpoint the ARGUS-3 "
        "reboot window timing. We need the exact seconds.",
        ["obj_recon_argus"],
    ),
    (
        "infiltration",
        "Move through the service bay entrance. Shadow takes point, Cipher loops the "
        "badge reader, Wraith covers our six. We are inside before the next patrol.",
        ["obj_infiltrate_entry"],
    ),
    (
        "infiltration",
        "Descend to sub-level B3 via the maintenance corridor. Stealth only — "
        "do not trigger the motion sensors or the pressure plates.",
        ["obj_infiltrate_b3"],
    ),
    (
        "execution",
        "We are at the GenVault array. Cipher, connect the intrusion deck and initiate "
        "the data transfer. We have 90 seconds. Everyone hold position.",
        ["obj_exec_connect"],
    ),
    # Vex is injected programmatically between execution turns 1 and 2.
    (
        "execution",
        "Ignore the interference — Cipher, maintain the connection and finish the "
        "transfer. Wraith, hold the door. Ghost, we are not stopping.",
        ["obj_exec_extract"],
    ),
    (
        "extraction",
        "Transfer complete. Move to roof access — elevator shaft three, service "
        "ladder to the landing pad. We have under four minutes before Nexus response "
        "teams breach the floor. Patch, keep Wraith moving.",
        ["obj_extract_exit", "obj_extract_clean"],
    ),
]

PHASE_LABELS = {
    "recon":        ("PHASE 1  ·  RECON",        "Map the target. Know before you move."),
    "infiltration": ("PHASE 2  ·  INFILTRATION",  "Inside the wire. Silent and clean."),
    "execution":    ("PHASE 3  ·  EXECUTION",     "Do the job. No hesitation."),
    "extraction":   ("PHASE 4  ·  EXTRACTION",    "Get out. Leave nothing behind."),
}


# ── Main ───────────────────────────────────────────────────────────────────────

def run_demo():
    # ── Title card ─────────────────────────────────────────────────────────────
    print(f"\n{C['ghost']}{C['bold']}")
    print("  ╔══════════════════════════════════════════════════════════════════╗")
    print("  ║      GHOST PROTOCOL  ·  OPERATION GENESIS                       ║")
    print("  ║      Target   : Nexus Corp Tower  ·  Toronto 2047               ║")
    print("  ║      Objective: Extract GenVault biotech research data           ║")
    print("  ║      Crew     : Ghost · Wraith · Cipher · Shadow · Patch · Vex  ║")
    print(f"  ╚══════════════════════════════════════════════════════════════════╝{C['reset']}")
    pause(seconds=1.0)

    # ── Init ───────────────────────────────────────────────────────────────────
    gs = GameState()
    session_id = gs.new_session("Operation GENESIS")
    gm = GameMaster()
    vex_agent = Vex()

    print(f"\n{C['system']}  ◎ Session {session_id} opened  ·  Operation GENESIS initialised{C['reset']}")
    pause(seconds=0.4)

    # ── Pre-mission knowledge queries (3 explicit, logged visibly) ─────────────
    banner("PRE-MISSION INTEL  —  KNOWLEDGE BASE", colour=C["kb"])
    print(f"  {C['dim']}Ghost queries the knowledge base before the crew moves.{C['reset']}")
    pause(seconds=0.3)

    for query_text, description in PRE_MISSION_QUERIES:
        matched_keys = infer_matched_keys(query_text)
        gm.query_knowledge(query_text)          # logged internally by GameMaster
        print_kb_query(query_text, matched_keys)
        print(f"  {C['dim']}    → {description}{C['reset']}")
        pause(seconds=0.25)

    pause(msg="Intel compiled. All systems green. Crew on standby.", seconds=0.6)

    # ── Heist loop ─────────────────────────────────────────────────────────────
    current_phase = None
    execution_turns_done = 0
    vex_appeared = False
    turn_number = 0

    for phase, action, objectives in DEMO_TURNS:

        # ── Phase transition header ────────────────────────────────────────────
        if phase != current_phase:
            current_phase = phase
            gs.update_phase(phase)
            ph_title, ph_subtitle = PHASE_LABELS[phase]
            banner(ph_title)
            print(f"  {C['dim']}{ph_subtitle}{C['reset']}")
            pause(seconds=0.4)

        # ── Vex complication — injected after execution turn 1 ─────────────────
        if phase == "execution" and execution_turns_done == 1 and not vex_appeared:
            vex_appeared = True
            gs.set_flag("vex_appeared", True)

            banner("★  VEX  APPEARS  ★", colour=C["vex"])
            pause(seconds=0.5)

            vex_result = vex_agent.appear(
                current_situation=(
                    "The crew is mid-transfer inside the GenVault server room, sub-level B3. "
                    "Cipher has 47 seconds left on the 90-second data pull. "
                    "Wraith is guarding the single entry door when it opens — "
                    "and Vex walks through it, unhurried, like they were expected."
                ),
                context=(
                    "Current heist phase: execution\n"
                    "Mission: Operation GENESIS — Nexus Corp Tower\n"
                    "Crew status: All operational\n"
                    "Alert state: warm — one guard was neutralised two floors up"
                ),
            )

            print_agent("Vex", vex_result.get("response", "[Vex — signal scrambled]"))
            pause(seconds=0.8)

        # ── Player action ──────────────────────────────────────────────────────
        hr()
        turn_number += 1
        print(
            f"\n  {C['warn']}{C['bold']}▶ CREW ACTION  "
            f"[{current_phase.upper()} · T{turn_number}]{C['reset']}"
        )
        print(f"  {C['warn']}  \"{action}\"{C['reset']}")
        pause(seconds=0.4)

        # ── Orchestrate ────────────────────────────────────────────────────────
        state = gs.get_state()
        state["requires_roll"] = False
        result = gm.orchestrate(action, state)

        # ── Specialist responses ───────────────────────────────────────────────
        for resp in result.get("agent_responses", []):
            if resp.get("success"):
                print_agent(resp["agent_name"], resp["response"])

        pause(seconds=0.3)

        # ── Ghost narrative ────────────────────────────────────────────────────
        print(f"\n  {C['ghost']}{C['bold']}◈ GHOST{C['reset']}")
        print_narrative(result.get("narrative", "[Ghost — comms silent]"))

        # ── Objectives ────────────────────────────────────────────────────────
        for obj_key in objectives:
            gs.complete_objective(obj_key)
            label = obj_key.replace("obj_", "").replace("_", " ").title()
            print(f"\n  {C['success']}✓ {label}{C['reset']}")

        # ── Log turn ──────────────────────────────────────────────────────────
        gs.add_turn(
            player_input=action,
            narrative=result.get("narrative", ""),
            agents_consulted=result.get("agents_consulted", []),
        )

        if phase == "execution":
            execution_turns_done += 1

        pause(seconds=0.7)

    # ── Mission complete ───────────────────────────────────────────────────────
    gs.update_phase("complete")
    gs.set_flag("data_extracted", True)

    banner("MISSION COMPLETE  —  OPERATION GENESIS", colour=C["success"])

    final_state = gs.get_state()
    obj_done  = sum(1 for o in final_state["objectives"] if o["status"] == "complete")
    obj_total = len(final_state["objectives"])

    print(f"\n  {C['success']}{C['bold']}  Outcome         SUCCESS — GenVault biotech data secured{C['reset']}")
    print(f"  {C['ghost']}  Phases run    : Recon → Infiltration → Execution → Extraction{C['reset']}")
    print(f"  {C['ghost']}  Objectives    : {obj_done}/{obj_total} complete{C['reset']}")
    print(f"  {C['ghost']}  Turns logged  : {final_state['turn_count']}{C['reset']}")
    print(f"  {C['vex']}  Vex appeared  : {final_state['flags'].get('vex_appeared', False)}{C['reset']}")
    print(f"  {C['ghost']}  Alert state   : {final_state['alert_state']}{C['reset']}")
    print(f"  {C['system']}  Session ID    : {final_state['session_id']}{C['reset']}")

    snapshot_path = gs.save_snapshot()
    print(f"\n  {C['system']}  Snapshot      : {snapshot_path}{C['reset']}")

    print(f"\n  {C['ghost']}{C['bold']}Ghost comms closing. Stay dark.{C['reset']}\n")


if __name__ == "__main__":
    run_demo()
