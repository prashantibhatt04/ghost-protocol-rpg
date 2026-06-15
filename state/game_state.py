"""
Ghost Protocol — Game State
SQLite-backed persistence for heist sessions.
Tracks phase, crew health, objectives, world flags, and full turn history.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime

_DB_PATH = Path(__file__).parent.parent / "ghost_protocol.db"
_logger = logging.getLogger("ghost.state")

HEALTH_STATES = ("operational", "wounded", "critical")
ALERT_STATES  = ("cold", "warm", "hot", "scorched")
HEIST_PHASES  = ("recon", "infiltration", "execution", "extraction", "complete")

CREW_MEMBERS = ["Ghost", "Wraith", "Cipher", "Shadow", "Patch", "Vex"]

# Default objectives for the demo mission (Operation GENESIS)
_GENESIS_OBJECTIVES = [
    ("obj_recon_security",   "Map Nexus Tower B-level security layout",      "recon"),
    ("obj_recon_argus",      "Identify ARGUS-3 reboot window timing",         "recon"),
    ("obj_infiltrate_entry", "Enter Nexus Tower undetected via service bay",  "infiltration"),
    ("obj_infiltrate_b3",    "Reach sub-level B3 without triggering alert",   "infiltration"),
    ("obj_exec_connect",     "Connect intrusion deck to GenVault array",       "execution"),
    ("obj_exec_extract",     "Complete 90-second GenVault data transfer",      "execution"),
    ("obj_extract_exit",     "Exit Nexus Tower with data intact",              "extraction"),
    ("obj_extract_clean",    "Reach extraction point before pursuit closes",   "extraction"),
]


# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_name    TEXT    NOT NULL,
    phase           TEXT    NOT NULL DEFAULT 'recon',
    alert_state     TEXT    NOT NULL DEFAULT 'cold',
    turn_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    last_activity   TEXT    DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS crew_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    agent_name      TEXT    NOT NULL,
    health_state    TEXT    NOT NULL DEFAULT 'operational',
    augment_damaged INTEGER NOT NULL DEFAULT 0,
    notes           TEXT    DEFAULT '',
    updated_at      TEXT    NOT NULL,
    UNIQUE(session_id, agent_name)
);

CREATE TABLE IF NOT EXISTS objectives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    obj_key       TEXT    NOT NULL,
    description   TEXT    NOT NULL,
    phase         TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    completed_at  TEXT    DEFAULT NULL,
    UNIQUE(session_id, obj_key)
);

CREATE TABLE IF NOT EXISTS world_flags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id),
    flag_name   TEXT    NOT NULL,
    flag_value  TEXT    NOT NULL,
    set_at      TEXT    NOT NULL,
    UNIQUE(session_id, flag_name)
);

CREATE TABLE IF NOT EXISTS turn_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL REFERENCES sessions(id),
    turn_number      INTEGER NOT NULL,
    phase            TEXT    NOT NULL,
    player_input     TEXT    NOT NULL,
    narrative        TEXT    NOT NULL,
    agents_consulted TEXT    NOT NULL DEFAULT '[]',
    dice_roll        TEXT    DEFAULT NULL,
    alert_state      TEXT    NOT NULL DEFAULT 'cold',
    timestamp        TEXT    NOT NULL
);
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [STATE     ] {msg}"
    if level == "warning":
        _logger.warning(line)
    elif level == "error":
        _logger.error(line)
    else:
        _logger.info(line)
    print(line)


# ── GameState ──────────────────────────────────────────────────────────────────

class GameState:
    """
    Manages all persistent state for a Ghost Protocol session.

    Usage:
        gs = GameState()
        gs.new_session("Operation GENESIS")
        state = gs.get_state()           # pass to GameMaster.orchestrate()
        gs.add_turn(input, narrative, agents)
        gs.save()                        # explicit flush (also auto-committed)
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or _DB_PATH
        self.session_id: int = None
        self._init_db()

    # ── DB Init ────────────────────────────────────────────────────────────────

    def _init_db(self):
        """Create schema if it doesn't exist."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN last_activity TEXT DEFAULT NULL")
            except Exception:
                pass  # column already exists in this database
        _log(f"Database ready: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ── Session Lifecycle ──────────────────────────────────────────────────────

    def new_session(self, mission_name: str = "Operation GENESIS") -> int:
        """Create a fresh game session and return its ID."""
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions (mission_name, phase, alert_state, turn_count, created_at, updated_at, last_activity) "
                "VALUES (?, 'recon', 'cold', 0, ?, ?, ?)",
                (mission_name, now, now, now),
            )
            self.session_id = cur.lastrowid

            # Seed crew status for all members
            for member in CREW_MEMBERS:
                conn.execute(
                    "INSERT INTO crew_status (session_id, agent_name, health_state, updated_at) VALUES (?, ?, 'operational', ?)",
                    (self.session_id, member, now),
                )

            # Seed objectives for the mission
            if mission_name == "Operation GENESIS":
                for obj_key, desc, phase in _GENESIS_OBJECTIVES:
                    conn.execute(
                        "INSERT INTO objectives (session_id, obj_key, description, phase, status) VALUES (?, ?, ?, ?, 'pending')",
                        (self.session_id, obj_key, desc, phase),
                    )

            # Set initial world flags
            for name, value in [
                ("vex_appeared",         "false"),
                ("vex_deal_taken",       "false"),
                ("vex_trusted",          "false"),
                ("crew_loyalty",         "100"),
                ("mission_speed",        "normal"),
                ("marcus_okafor_seen",   "false"),
                ("argus3_rebooting",     "false"),
                ("genvault_connected",   "false"),
                ("data_extracted",       "false"),
                ("crew_compromised",     "false"),
                ("crew_morale",          "high"),
                ("patch_objected",       "false"),
                ("pending_confirmation", "false"),
            ]:
                conn.execute(
                    "INSERT INTO world_flags (session_id, flag_name, flag_value, set_at) VALUES (?, ?, ?, ?)",
                    (self.session_id, name, value, now),
                )

        _log(f"New session created: id={self.session_id} mission='{mission_name}'")
        return self.session_id

    def load_session(self, session_id: int) -> bool:
        """Load an existing session by ID. Returns True if found."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            _log(f"Session {session_id} not found.", level="warning")
            return False
        self.session_id = session_id
        _log(f"Session loaded: id={session_id} mission='{row['mission_name']}' phase={row['phase']}")
        return True

    def load_latest_session(self) -> bool:
        """Load the most recently created session. Returns True if any session exists."""
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return False
        return self.load_session(row["id"])

    def _require_session(self):
        if not self.session_id:
            raise RuntimeError("No active session. Call new_session() or load_session() first.")

    # ── State Read ─────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        """
        Return the current game state as a dict suitable for passing to
        GameMaster.orchestrate() and for the Flask UI.
        """
        self._require_session()
        with self._connect() as conn:
            session = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (self.session_id,)
            ).fetchone()

            crew_rows = conn.execute(
                "SELECT * FROM crew_status WHERE session_id = ?", (self.session_id,)
            ).fetchall()

            obj_rows = conn.execute(
                "SELECT * FROM objectives WHERE session_id = ? ORDER BY id", (self.session_id,)
            ).fetchall()

            flag_rows = conn.execute(
                "SELECT flag_name, flag_value FROM world_flags WHERE session_id = ?", (self.session_id,)
            ).fetchall()

        # Summarise crew for GM context string
        crew_summary_parts = []
        crew_dict = {}
        for r in crew_rows:
            crew_dict[r["agent_name"]] = {
                "health_state":    r["health_state"],
                "augment_damaged": bool(r["augment_damaged"]),
                "notes":           r["notes"],
            }
            if r["health_state"] != "operational":
                crew_summary_parts.append(f"{r['agent_name']}:{r['health_state']}")

        crew_summary = ", ".join(crew_summary_parts) if crew_summary_parts else "All operational"

        objectives = [
            {
                "key":         r["obj_key"],
                "description": r["description"],
                "phase":       r["phase"],
                "status":      r["status"],
            }
            for r in obj_rows
        ]

        flags = {r["flag_name"]: r["flag_value"] for r in flag_rows}

        return {
            "session_id":   self.session_id,
            "mission":      session["mission_name"],
            "phase":        session["phase"],
            "alert_state":  session["alert_state"],
            "turn_count":   session["turn_count"],
            "crew_status":  crew_summary,
            "crew_detail":  crew_dict,
            "objectives":   objectives,
            "flags":        flags,
            "requires_roll": False,   # caller can override before passing to orchestrate()
            "roll_modifier": 0,
        }

    # ── Phase & Alert ──────────────────────────────────────────────────────────

    def update_phase(self, new_phase: str):
        """Advance or set the heist phase."""
        if new_phase not in HEIST_PHASES:
            raise ValueError(f"Invalid phase '{new_phase}'. Must be one of {HEIST_PHASES}.")
        self._require_session()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET phase = ?, updated_at = ? WHERE id = ?",
                (new_phase, _now(), self.session_id),
            )
        _log(f"Phase → {new_phase}")

    def update_alert(self, new_alert: str):
        """Set the alert state (cold / warm / hot / scorched)."""
        if new_alert not in ALERT_STATES:
            raise ValueError(f"Invalid alert '{new_alert}'. Must be one of {ALERT_STATES}.")
        self._require_session()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET alert_state = ?, updated_at = ? WHERE id = ?",
                (new_alert, _now(), self.session_id),
            )
        _log(f"Alert → {new_alert}")

    # ── Crew Status ────────────────────────────────────────────────────────────

    def update_crew(self, agent_name: str, health_state: str, notes: str = "", augment_damaged: bool = False):
        """Update a crew member's health state."""
        if health_state not in HEALTH_STATES:
            raise ValueError(f"Invalid health state '{health_state}'. Must be one of {HEALTH_STATES}.")
        self._require_session()
        with self._connect() as conn:
            conn.execute(
                "UPDATE crew_status SET health_state = ?, notes = ?, augment_damaged = ?, updated_at = ? "
                "WHERE session_id = ? AND agent_name = ?",
                (health_state, notes, int(augment_damaged), _now(), self.session_id, agent_name),
            )
        _log(f"Crew update: {agent_name} → {health_state}{' [augment damaged]' if augment_damaged else ''}")

    def get_crew_status(self) -> dict:
        """Return full crew status dict keyed by agent name."""
        self._require_session()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM crew_status WHERE session_id = ?", (self.session_id,)
            ).fetchall()
        return {
            r["agent_name"]: {
                "health_state":    r["health_state"],
                "augment_damaged": bool(r["augment_damaged"]),
                "notes":           r["notes"],
            }
            for r in rows
        }

    # ── Objectives ─────────────────────────────────────────────────────────────

    def complete_objective(self, obj_key: str):
        """Mark an objective as complete."""
        self._require_session()
        with self._connect() as conn:
            conn.execute(
                "UPDATE objectives SET status = 'complete', completed_at = ? "
                "WHERE session_id = ? AND obj_key = ?",
                (_now(), self.session_id, obj_key),
            )
        _log(f"Objective complete: {obj_key}")

    def fail_objective(self, obj_key: str):
        """Mark an objective as failed."""
        self._require_session()
        with self._connect() as conn:
            conn.execute(
                "UPDATE objectives SET status = 'failed', completed_at = ? "
                "WHERE session_id = ? AND obj_key = ?",
                (_now(), self.session_id, obj_key),
            )
        _log(f"Objective failed: {obj_key}", level="warning")

    def get_objectives(self, phase: str = None, status: str = None) -> list:
        """Return objectives, optionally filtered by phase and/or status."""
        self._require_session()
        query = "SELECT * FROM objectives WHERE session_id = ?"
        params: list = [self.session_id]
        if phase:
            query += " AND phase = ?"
            params.append(phase)
        if status:
            query += " AND status = ?"
            params.append(status)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ── World Flags ────────────────────────────────────────────────────────────

    # Flags that require a minimum phase to be set to a truthy value.
    # Defense in depth — the LLM cannot bypass these regardless of what it generates.
    _PHASE_GATED_FLAGS: dict[str, tuple[str, ...]] = {
        "data_extracted":    ("execution", "extraction"),
        "genvault_connected": ("execution", "extraction"),
    }

    def set_flag(self, flag_name: str, flag_value):
        """Set (upsert) a world flag, enforcing phase-gates for sensitive flags."""
        self._require_session()
        value_str = str(flag_value).lower() if isinstance(flag_value, bool) else str(flag_value)

        # Defense in depth: certain flags can only be set to true in later phases.
        allowed_phases = self._PHASE_GATED_FLAGS.get(flag_name)
        if allowed_phases and value_str in ("true", "1"):
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT phase FROM sessions WHERE id = ?", (self.session_id,)
                ).fetchone()
            current_phase = row["phase"] if row else "recon"
            if current_phase not in allowed_phases:
                _log(
                    f"[PHASE GUARD] {flag_name}=true blocked — "
                    f"current phase={current_phase}, requires one of {allowed_phases}",
                    level="warning",
                )
                return  # Hard block — do not write the flag

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO world_flags (session_id, flag_name, flag_value, set_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id, flag_name) DO UPDATE SET flag_value = excluded.flag_value, set_at = excluded.set_at",
                (self.session_id, flag_name, value_str, _now()),
            )
        _log(f"Flag set: {flag_name} = {value_str}")

    def get_flag(self, flag_name: str, default=None):
        """Get a world flag value. Returns default if not set."""
        self._require_session()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT flag_value FROM world_flags WHERE session_id = ? AND flag_name = ?",
                (self.session_id, flag_name),
            ).fetchone()
        if row is None:
            return default
        val = row["flag_value"]
        if val == "true":
            return True
        if val == "false":
            return False
        return val

    def get_all_flags(self) -> dict:
        """Return all world flags for this session."""
        self._require_session()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT flag_name, flag_value FROM world_flags WHERE session_id = ?",
                (self.session_id,),
            ).fetchall()
        result = {}
        for r in rows:
            val = r["flag_value"]
            result[r["flag_name"]] = True if val == "true" else (False if val == "false" else val)
        return result

    # ── Turn History ───────────────────────────────────────────────────────────

    def add_turn(
        self,
        player_input: str,
        narrative: str,
        agents_consulted: list,
        dice_roll: dict = None,
        alert_state: str = None,
    ):
        """Log a completed turn to history and increment turn counter."""
        self._require_session()

        # Get current phase and alert for logging
        with self._connect() as conn:
            session = conn.execute(
                "SELECT phase, alert_state, turn_count FROM sessions WHERE id = ?",
                (self.session_id,),
            ).fetchone()

        current_phase = session["phase"]
        current_alert = alert_state or session["alert_state"]
        new_turn = session["turn_count"] + 1

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO turn_history "
                "(session_id, turn_number, phase, player_input, narrative, agents_consulted, dice_roll, alert_state, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.session_id,
                    new_turn,
                    current_phase,
                    player_input,
                    narrative,
                    json.dumps(agents_consulted),
                    json.dumps(dice_roll) if dice_roll else None,
                    current_alert,
                    _now(),
                ),
            )
            conn.execute(
                "UPDATE sessions SET turn_count = ?, updated_at = ?, last_activity = ? WHERE id = ?",
                (new_turn, _now(), _now(), self.session_id),
            )

        _log(f"Turn {new_turn} logged | phase={current_phase} | agents={agents_consulted}")

    def get_history(self, last_n: int = 10) -> list:
        """Return the last N turns as a list of dicts."""
        self._require_session()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM turn_history WHERE session_id = ? ORDER BY turn_number DESC LIMIT ?",
                (self.session_id, last_n),
            ).fetchall()
        history = []
        for r in reversed(rows):
            entry = dict(r)
            entry["agents_consulted"] = json.loads(entry["agents_consulted"] or "[]")
            entry["dice_roll"] = json.loads(entry["dice_roll"]) if entry["dice_roll"] else None
            history.append(entry)
        return history

    def get_conversation_history(self, last_n_turns: int = 3) -> list:
        """
        Return history formatted as OpenAI message dicts for context injection.
        Provides the last N turns as user/assistant pairs.
        """
        turns = self.get_history(last_n=last_n_turns)
        messages = []
        for turn in turns:
            messages.append({"role": "user",      "content": turn["player_input"]})
            messages.append({"role": "assistant",  "content": turn["narrative"]})
        return messages

    # ── Snapshot / Export ──────────────────────────────────────────────────────

    def save_snapshot(self, path: Path = None) -> Path:
        """Export the full current state to a JSON file for backup or inspection."""
        self._require_session()
        state = self.get_state()
        state["history"] = self.get_history(last_n=999)

        out_path = path or Path(f"session_{self.session_id}_snapshot.json")
        out_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        _log(f"Snapshot saved: {out_path}")
        return out_path

    def list_sessions(self) -> list:
        """Return a summary of all saved sessions."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, mission_name, phase, alert_state, turn_count, created_at FROM sessions ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Reset ──────────────────────────────────────────────────────────────────

    def reset_session(self):
        """Reset the current session to initial state (phase=recon, all crew operational)."""
        self._require_session()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET phase='recon', alert_state='cold', turn_count=0, updated_at=? WHERE id=?",
                (now, self.session_id),
            )
            conn.execute(
                "UPDATE crew_status SET health_state='operational', augment_damaged=0, notes='', updated_at=? "
                "WHERE session_id=?",
                (now, self.session_id),
            )
            conn.execute(
                "UPDATE objectives SET status='pending', completed_at=NULL WHERE session_id=?",
                (self.session_id,),
            )
            conn.execute(
                "UPDATE world_flags SET flag_value='false', set_at=? WHERE session_id=?",
                (now, self.session_id),
            )
            conn.execute("DELETE FROM turn_history WHERE session_id=?", (self.session_id,))
        _log("Session reset to initial state.")

    def save(self):
        """No-op — all writes auto-commit via context manager. Present for API clarity."""
        _log("State persisted (SQLite auto-commit).")
