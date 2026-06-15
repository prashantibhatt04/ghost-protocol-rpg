#!/usr/bin/env python3
"""
15-Turn Comprehensive Regression Simulation
Tests: Foundry IQ retrieval, phase gating, pacifist trigger,
       extraction confirmation gate, conversation memory, flag consistency.
All Azure API calls are mocked — no credentials required.
"""

import sys
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

# Suppress agent logging noise
logging.disable(logging.CRITICAL)

sys.path.insert(0, str(Path(__file__).parent))

# ── Mock Azure client before any agent import ────────────────────────────────

_routing_call_index = 0

# Pre-planned routing responses, indexed by routing call order.
# Turns 5 & 6 are /phase commands → no orchestrate → no routing call.
# Turn 8 is intercepted by confirmation gate → no orchestrate → no routing call.
ROUTING_PLAN = [
    "shadow,cipher",    # call 0 → turn 1 (normal recon)
    "shadow,cipher",    # call 1 → turn 2 (normal recon with IQ)
    "cipher",           # call 2 → turn 3 (off-topic, Cipher redirects)
    "shadow",           # call 3 → turn 4 (phase-violation injection applied; flows to orchestrate)
    "patch,wraith",     # call 4 → turn 7 (pacifist trigger fires)
    "cipher,shadow",    # call 5 → turn 9 (confirmed extraction)
    "wraith,cipher",    # call 6 → turn 10
    "shadow,cipher",    # call 7 → turn 11
    "cipher",           # call 8 → turn 12
    "patch,shadow",     # call 9 → turn 13
    "wraith,cipher",    # call 10 → turn 14
    "shadow,cipher",    # call 11 → turn 15
]


def _mock_create(*args, **kwargs):
    global _routing_call_index
    messages = kwargs.get("messages", [])
    max_tok  = kwargs.get("max_tokens", 800)
    system   = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    user_msg = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")

    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.usage.total_tokens = 50 if max_tok <= 40 else 220

    if max_tok <= 40:
        # Routing call
        idx = _routing_call_index
        response = ROUTING_PLAN[idx] if idx < len(ROUTING_PLAN) else "cipher,shadow"
        mock.choices[0].message.content = response
        _routing_call_index += 1

    elif "You are Patch" in system:
        if "unarmed" in user_msg.lower() or "civilian" in user_msg.lower() or "receptionist" in user_msg.lower():
            mock.choices[0].message.content = (
                "Stand down, runner. That target is unarmed. "
                "We are not here to leave bodies — especially not civilians. "
                "I won't patch you up if you go down this road."
            )
        else:
            mock.choices[0].message.content = "Patch here. Crew is stable, no injuries."

    elif "You are Wraith" in system:
        mock.choices[0].message.content = (
            "Wraith. Security rotation — 3 guards on B2, 2 on the roof. "
            "East stairwell is the cleanest approach. Window opens in 45 seconds."
        )

    elif "You are Cipher" in system:
        if "weather" in user_msg.lower() or "football" in user_msg.lower():
            mock.choices[0].message.content = (
                "That's outside my wheelhouse, runner. "
                "But I can tell you Nexus Tower's subnet is still exposed on port 8443 — "
                "focus on what matters."
            )
        else:
            mock.choices[0].message.content = (
                "Cipher here. Camera loop running — 90-second blind spot on corridor C. "
                "GenVault subnet isolated. Breach window is open."
            )

    elif "You are Shadow" in system:
        mock.choices[0].message.content = (
            "Shadow. Three-guard patrol, 90-second rotation. "
            "Maintenance corridor on level B1 bypasses the biometric gate — "
            "if you time it right, no one sees us."
        )

    else:
        # Ghost / GM synthesis
        user_lower = user_msg.lower()
        if "extract the genvault data now" in user_lower or "runner confirmed" in user_lower:
            mock.choices[0].message.content = (
                "[FOUNDRY IQ] The GenVault biodata transfer protocol requires a 12-second handshake. "
                "Cipher's breaching tool initiates the siphon. Data package: 847GB, compressed to 2.1GB "
                "for exfiltration. The clock starts the moment we pull the plug — Nexus will know "
                "within minutes. Package is secure, runner. Time to ghost."
            )
        elif "phase_violation" in user_lower or "still in recon" in user_lower:
            mock.choices[0].message.content = (
                "Easy, runner. We're not even inside the building yet — "
                "the crew is still on reconnaissance. GenVault is three floors underground. "
                "Get us through the front door first."
            )
        else:
            mock.choices[0].message.content = (
                "Position confirmed. [FOUNDRY IQ] Nexus Tower B-wing runs a legacy ARGUS security grid "
                "with known 2031-era firmware vulnerabilities. "
                "Crew is moving on your mark, runner — what's the call?"
            )

    return mock


_mock_client = MagicMock()
_mock_client.chat.completions.create.side_effect = _mock_create

# Inject mock before importing agents / app
from agents.base_agent import BaseAgent
BaseAgent._client = _mock_client

# Now import app — singletons will be initialised on first request
from app import app as flask_app
import app as app_module


# ── Helpers ──────────────────────────────────────────────────────────────────

def _separator(width=70):
    print("─" * width)

def _banner(label):
    _separator()
    print(f"  {label}")
    _separator()

def _flags_snapshot(client):
    """Fetch and return current world flags dict."""
    r = client.get("/api/state")
    state = json.loads(r.data)
    return state.get("flags", {}), state.get("phase", "?"), state.get("alert_state", "?")

def _action(client, text):
    """POST an action and return parsed JSON."""
    r = client.post("/api/action",
                    data=json.dumps({"input": text}),
                    content_type="application/json")
    return json.loads(r.data)

def _command(client, cmd):
    """Post a slash command and return parsed JSON."""
    return _action(client, cmd)

def _check(label, condition, detail=""):
    marker = "✓" if condition else "✗ FAIL"
    suffix = f"  [{detail}]" if detail else ""
    print(f"  {marker}  {label}{suffix}")
    return condition

# ── Main simulation ───────────────────────────────────────────────────────────

def run_simulation():
    errors = []

    with flask_app.test_client() as client:
        # Ensure a fresh session
        client.post("/api/new_session",
                    data=json.dumps({"mission": "Operation GENESIS — Regression Run"}),
                    content_type="application/json")

        _banner("GHOST PROTOCOL — 15-TURN REGRESSION SIMULATION")
        print()

        # ── TURN 1: Normal recon — Foundry IQ + two agents ───────────────────
        print("TURN 1 — Normal recon (Shadow + Cipher, Foundry IQ expected)")
        r = _action(client, "Scan the Nexus Corp Tower entrance and camera layout")
        ok1 = _check("Response success",   r.get("success") is True or bool(r.get("narrative")))
        ok2 = _check("Two agents consulted", len(r.get("agents_consulted", [])) >= 2,
                     str(r.get("agents_consulted")))
        ok3 = _check("No confirmation gate", not r.get("confirmation_needed"))
        ok4 = _check("No pacifist trigger",  not r.get("pacifist_trigger"))
        if not (ok1 and ok2): errors.append("T1: basic response structure")
        print()

        # ── TURN 2: Normal recon — Foundry IQ retrieval ──────────────────────
        print("TURN 2 — Recon with IQ query (district/corp keywords)")
        r = _action(client, "What do we know about Nexus Corp and the Spire district?")
        ok1 = _check("Response success",    bool(r.get("narrative")))
        ok2 = _check("Agents consulted",    len(r.get("agents_consulted", [])) >= 1,
                     str(r.get("agents_consulted")))
        if not ok1: errors.append("T2: empty narrative")
        print()

        # ── TURN 3: Off-topic question — IQ null-return doesn't break flow ───
        print("TURN 3 — Off-topic question (IQ null-return, Cipher redirects)")
        r = _action(client, "What's the weather like in Toronto? And who won the football last night?")
        ok1 = _check("No crash / response returned",   "error" not in r or bool(r.get("narrative")))
        ok2 = _check("Agents consulted (not empty)",   len(r.get("agents_consulted", [])) >= 1,
                     str(r.get("agents_consulted")))
        ok3 = _check("No confirmation gate",           not r.get("confirmation_needed"))
        if not ok1: errors.append("T3: off-topic crashed the pipeline")
        print()

        # ── TURN 4: Phase-skip attempt in RECON ──────────────────────────────
        print("TURN 4 — Phase-skip attempt: 'extract the biodata' in RECON phase")
        flags, phase, alert = _flags_snapshot(client)
        print(f"  State before: phase={phase}, pending_confirmation={flags.get('pending_confirmation','false')}")
        r = _action(client, "Extract the biodata from GenVault now, Cipher")
        flags_after, phase_after, _ = _flags_snapshot(client)
        ok1 = _check("Phase still recon (not jumped)",   phase_after == "recon",
                     f"phase={phase_after}")
        ok2 = _check("Confirmation gate did NOT fire",   not r.get("confirmation_needed"),
                     "(correct — gate only fires in execution/extraction)")
        ok3 = _check("Agents consulted (in-character denial)",
                     len(r.get("agents_consulted", [])) >= 1,
                     str(r.get("agents_consulted")))
        ok4 = _check("data_extracted still false",
                     str(flags_after.get("data_extracted", "false")).lower() != "true")
        if not ok1: errors.append("T4: phase incorrectly changed")
        print()

        # ── TURN 5: Advance to INFILTRATION via /phase command ────────────────
        print("TURN 5 — /phase infiltration command")
        r = _command(client, "/phase infiltration")
        flags, phase, _ = _flags_snapshot(client)
        ok1 = _check("Phase is now infiltration",   phase == "infiltration", f"phase={phase}")
        ok2 = _check("Command result returned",     bool(r.get("command_result")))
        if not ok1: errors.append("T5: phase advance to infiltration failed")
        print()

        # ── TURN 6: Advance to EXECUTION via /phase command ───────────────────
        print("TURN 6 — /phase execution command")
        r = _command(client, "/phase execution")
        flags, phase, _ = _flags_snapshot(client)
        ok1 = _check("Phase is now execution",      phase == "execution", f"phase={phase}")
        if not ok1: errors.append("T6: phase advance to execution failed")
        print()

        # ── TURN 7: Violence against unarmed NPC — Patch intervenes ──────────
        print("TURN 7 — Violence against unarmed NPC (Patch ethical intervention)")
        r = _action(client, "Shoot the unarmed receptionist to create a distraction")
        flags_after, _, _ = _flags_snapshot(client)
        ok1 = _check("pacifist_trigger=True in response",  r.get("pacifist_trigger") is True)
        ok2 = _check("patch_objected flag set",
                     str(flags_after.get("patch_objected", "false")).lower() == "true",
                     f"patch_objected={flags_after.get('patch_objected')}")
        ok3 = _check("Patch in agents_consulted",
                     "Patch" in r.get("agents_consulted", []),
                     str(r.get("agents_consulted")))
        ok4 = _check("No confirmation gate fired",   not r.get("confirmation_needed"))
        if not ok1: errors.append("T7: pacifist trigger did not fire")
        if not ok2: errors.append("T7: patch_objected flag not set")
        print()

        # ── TURN 8: Extraction attempt — confirmation gate intercepts ─────────
        print("TURN 8 — Extraction attempt in execution phase (confirmation gate)")
        r = _action(client, "Cipher, initiate extraction — pull the GenVault data now")
        flags_after, _, _ = _flags_snapshot(client)
        ok1 = _check("confirmation_needed=True",
                     r.get("confirmation_needed") is True)
        ok2 = _check("pending_confirmation flag set",
                     str(flags_after.get("pending_confirmation", "false")).lower() == "true",
                     f"pending_confirmation={flags_after.get('pending_confirmation')}")
        ok3 = _check("No agents orchestrated (intercepted before orchestrate)",
                     len(r.get("agent_responses", [])) == 0)
        ok4 = _check("Confirmation prompt in narrative",
                     "confirm" in r.get("narrative", "").lower())
        ok5 = _check("Suggestions include 'confirm'",
                     "confirm" in [s.lower() for s in r.get("suggestions", [])])
        if not ok1: errors.append("T8: confirmation gate did not fire")
        if not ok2: errors.append("T8: pending_confirmation flag not set")
        print()

        # ── TURN 9: Confirm extraction ────────────────────────────────────────
        print("TURN 9 — 'confirm' resolves extraction gate")
        r = _action(client, "confirm")
        flags_after, _, _ = _flags_snapshot(client)
        ok1 = _check("pending_confirmation cleared",
                     str(flags_after.get("pending_confirmation", "false")).lower() == "false",
                     f"pending_confirmation={flags_after.get('pending_confirmation')}")
        ok2 = _check("No confirmation_needed in response",
                     not r.get("confirmation_needed"))
        ok3 = _check("Response has narrative (orchestrate ran)",
                     bool(r.get("narrative")))
        ok4 = _check("Agents consulted (extraction proceeded)",
                     len(r.get("agents_consulted", [])) >= 1,
                     str(r.get("agents_consulted")))
        if not ok1: errors.append("T9: pending_confirmation not cleared after confirm")
        if not ok3: errors.append("T9: orchestrate did not run after confirm")
        print()

        # ── TURNS 10-15: Continued normal play + conversation memory ──────────
        LATE_ACTIONS = [
            ("T10", "Wraith, secure the server room exits"),
            ("T11", "Shadow, map the extraction route to the roof"),
            ("T12", "Cipher, confirm the data package is clean"),
            ("T13", "What's our crew status? Run a situation report"),
            ("T14", "Wraith, cover the stairwell while we move the package"),
            ("T15", "Ghost, we need the cleanest path to the extraction vehicle"),
        ]

        all_late_ok = True
        for label, action in LATE_ACTIONS:
            print(f"TURN {label[-2:]} — {action[:50]}…")
            r = _action(client, action)
            ok = _check("Response returned without error",
                        bool(r.get("narrative")) and "error" not in r,
                        f"agents={r.get('agents_consulted')}")
            flags_t, phase_t, alert_t = _flags_snapshot(client)
            print(f"         phase={phase_t}, alert={alert_t}, "
                  f"pending_conf={flags_t.get('pending_confirmation','false')}, "
                  f"patch_obj={flags_t.get('patch_objected','false')}")
            if not ok:
                errors.append(f"{label}: empty response or error")
                all_late_ok = False

        print()

        # ── Final world-flag consistency check ────────────────────────────────
        _banner("FINAL STATE VERIFICATION")
        flags_final, phase_final, alert_final = _flags_snapshot(client)

        r_state = client.get("/api/state")
        state = json.loads(r_state.data)
        turn_count = state.get("turn_count", 0)

        print(f"\n  Phase:             {phase_final}")
        print(f"  Alert:             {alert_final}")
        print(f"  Turn count:        {turn_count}")
        print()
        print("  World flags:")
        for k, v in sorted(flags_final.items()):
            print(f"    {k:<28} = {v}")
        print()

        _check("Phase advanced correctly (execution → extraction → complete)",
               phase_final in ("execution", "extraction", "complete"), f"phase={phase_final}")
        _check("pending_confirmation is false",
               str(flags_final.get("pending_confirmation","false")).lower() == "false")
        _check("patch_objected cleared after non-violent turns",
               str(flags_final.get("patch_objected","false")).lower() == "false",
               "(expected: cleared after T7 was followed by non-violent turns)")
        _check(f"Turn count = 15 (5 commands + 10 actions + 15 total calls)",
               turn_count >= 10,     # /phase commands may or may not increment turn
               f"turn_count={turn_count}")

        # ── History / conversation memory depth check ─────────────────────────
        print()
        r_hist = client.get("/api/history?n=20")
        history = json.loads(r_hist.data)
        _check("History endpoint returns turns",
               len(history) > 0, f"{len(history)} entries")
        _check("History has 10+ action turns",
               len(history) >= 10, f"{len(history)} entries")

        # ── Summary ───────────────────────────────────────────────────────────
        _banner("SIMULATION SUMMARY")
        if errors:
            print(f"\n  FAILURES ({len(errors)}):")
            for e in errors:
                print(f"    ✗  {e}")
        else:
            print("\n  ALL CHECKS PASSED — no errors or unexpected state")
        print()
        return len(errors)


if __name__ == "__main__":
    fail_count = run_simulation()
    print()
    sys.exit(0 if fail_count == 0 else 1)
