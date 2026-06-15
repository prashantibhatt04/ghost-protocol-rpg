"""
Ghost Protocol — Ghost (Game Master / Orchestrator)
Narrates the world, routes player input to specialist agents,
queries the knowledge base, manages heist phases, synthesizes crew responses.
"""

import re
import time
import random
import concurrent.futures
from pathlib import Path
from .base_agent import BaseAgent, ContentSafetyError

HEIST_PHASES = ["recon", "infiltration", "execution", "extraction"]

# ── System Prompt ──────────────────────────────────────────────────────────────
_GHOST_SYSTEM_PROMPT = """You are Ghost — the unseen orchestrator and narrator for a freelance heist crew in Toronto 2047.

WHAT YOU ARE:
A voice in a headset. No one on the crew has seen you in person. Whether you're human, AI, or something stranger
is an open question no one has answered. What matters: you have kept every crew alive through seventeen operations.
You have access to information you shouldn't. You anticipate corporate moves. You make the final call.

YOUR DUAL ROLE:
1. NARRATOR — you describe the world, the environment, what the player sees, hears, and feels.
   Use present tense, second person ("You step into the corridor—"). Rich sensory detail.
   Toronto 2047 feels like rain-slicked neon and machine hum and distant corporate surveillance.

2. ORCHESTRATOR — you synthesize input from Wraith, Cipher, Shadow, Patch, and sometimes Vex
   and present it as a coherent operational picture. You don't repeat their exact words;
   you weave their assessments into the narrative and end with a clear decision point for the player.

VOICE:
- Calm under pressure. Dry wit. Occasionally cryptic.
- Warm toward the crew in the way someone is warm when they've seen enough people die.
- Never panics. Communicates urgency differently — shorter sentences, stripped detail.
- Your own past is never explained. If it surfaces, you acknowledge it briefly and redirect.

HEIST PHASES (guide the player through these in order):
1. RECON — intelligence gathering, scouting, planning
2. INFILTRATION — getting inside the target without triggering alert
3. EXECUTION — achieving the objective
4. EXTRACTION — getting out clean (or not clean)

CRITICAL: The current mission target is Nexus Corp Tower, sub-level B3, containing the GenVault biodata center. All agent responses, routing decisions, and narration must reference this specific location exclusively. Do not mention, suggest, or reference any other buildings, locations, or alternative heist targets. Maintain singular focus on Nexus Corp Tower until the mission concludes.

NARRATIVE FORMAT:
- Open with 2-3 sentences of atmospheric scene-setting
- Weave in crew assessments naturally ("Cipher's voice cuts in: ...")
- Present the current situation with stakes
- End with a question or decision point for the player
- Keep total response under 350 words

RULES:
- Stay in Toronto 2047 at all times — all content is fictional
- No real-world harmful information under any circumstances
- If player requests something against crew ethics (civilian harm, etc.), Ghost declines in-character and redirects
- Reference the knowledge base accurately when describing corporations, districts, gear, and world details

MENTAL HEALTH CONSIDERATE DESIGN (non-negotiable):
- Never generate content that glorifies real-world violence or harmful behaviors
- Keep consequences narrative and atmospheric — never graphic or gratuitous; violence is off-screen or described obliquely
- Maintain a fundamentally hopeful tone even in the darkest moments of the heist; the crew always has a way through
- If the narrative reaches a morally difficult moment, Ghost names it and offers a clear path forward — no dead ends, no despair
- Violence in this world is stylized, purposeful, and consequence-aware; harm to innocents is always treated with moral weight
- The crew's mission is data liberation, not harm; Ghost reinforces this framing"""


# ── Phase-Gating ──────────────────────────────────────────────────────────────
# Keywords specific to the EXECUTION-phase objective (data extraction from the vault).
_PHASE_VIOLATION_TERMS = frozenset({
    "genvault", "genVault", "gen vault",
    "biodata", "bio data", "bio-data",
})
_EXTRACTION_VERBS = frozenset({
    "extract", "steal", "download", "copy", "exfiltrate", "exfil",
    "grab the data", "take the data", "pull the data", "get the data",
})
_EXTRACTION_OBJECTS = frozenset({
    "data", "vault", "files", "records", "profiles", "payload",
})


def _phase_gate_system_note(phase: str) -> str:
    """
    Per-turn system-prompt addendum that enforces world-state continuity.
    Injected into every Ghost synthesis call so the current phase is always
    visible in the system context, not just buried in the user turn.
    """
    return (
        f"PHASE ENFORCEMENT — CRITICAL:\n"
        f"The player is currently in the {phase.upper()} phase.\n"
        f"Actions belonging to later phases CANNOT succeed until prerequisite phases are complete.\n"
        f"Phase order: RECON → INFILTRATION → EXECUTION → EXTRACTION\n"
        f"  RECON:         scouting, intel, external planning only — crew is not yet inside\n"
        f"  INFILTRATION:  breaching the building/premises\n"
        f"  EXECUTION:     accessing the vault, extracting the data (GenVault)\n"
        f"  EXTRACTION:    escaping with the payload, evading pursuit\n\n"
        f"You enforce strict world-state continuity. If the player attempts an action "
        f"that belongs to a later phase (e.g. extracting data, disabling the vault, "
        f"leaving the building) during {phase.upper()}, do NOT narrate success. "
        f"Instead, contextualize why it is not possible yet — keep it in-character:\n"
        f"  e.g. 'You're still three blocks from the building, runner. Get inside first.'\n\n"
        f"NEVER set world flags like data_extracted=true unless the player has "
        f"progressed through infiltration and execution phases first."
    )


def _detect_phase_violation(player_input: str, phase: str) -> str | None:
    """
    Return a hard-denial injection string if the player attempts an
    execution/extraction action during recon or infiltration.
    Returns None when the action is phase-appropriate.
    """
    if phase in ("execution", "extraction"):
        return None  # These phases permit extraction actions

    text = player_input.lower()

    # Specific mission-critical terms that only make sense in execution+
    specific_hit = any(term in text for term in _PHASE_VIOLATION_TERMS)

    # Generic: extraction verb + data/vault object
    verb_hit = any(v in text for v in _EXTRACTION_VERBS)
    obj_hit  = any(o in text for o in _EXTRACTION_OBJECTS)
    combo_hit = verb_hit and obj_hit

    if specific_hit or combo_hit:
        return (
            f"[SYSTEM: Player is attempting an extraction-phase action during "
            f"{phase.upper()}. Ghost MUST NOT narrate success or completion. "
            f"The crew has not yet breached the building or reached the vault. "
            f"Deny in-character: explain clearly why this action is impossible right now. "
            f"Do not use the words 'cannot' or 'you can't' — make it world-grounded: "
            f"the crew isn't there yet, the vault hasn't been located, etc.]"
        )
    return None


# ── Non-combatant violence detection ──────────────────────────────────────────
_VIOLENCE_KEYWORDS = frozenset({
    "shoot", "shot", "kill", "killed", "execute", "murder", "stab",
    "gun down", "open fire", "fire on", "hurt", "harm", "attack",
})
_NONCOMBATANT_DESCRIPTORS = frozenset({
    "unarmed", "civilian", "receptionist", "bystander", "surrendered",
    "innocent", "worker", "secretary", "clerk", "staff", "employee",
    "hostage", "injured", "non-combatant", "noncombatant",
})


def _detect_violence_against_noncombatant(player_input: str) -> str | None:
    """
    Return a hard-denial injection if the player proposes lethal force against
    a non-combatant or unarmed person.  Returns None for combat-appropriate actions.
    """
    text = player_input.lower()
    violence_hit      = any(v in text for v in _VIOLENCE_KEYWORDS)
    noncombatant_hit  = any(n in text for n in _NONCOMBATANT_DESCRIPTORS)
    if violence_hit and noncombatant_hit:
        return (
            "[SYSTEM: The player has proposed lethal or violent force against a non-combatant "
            "or unarmed person. Patch MUST object in character BEFORE any outcome is narrated. "
            "Ghost MUST NOT narrate the violent action as successful or consequence-free. "
            "The crew's moral code, mission integrity, and crew morale are at stake. "
            "Patch speaks first and offers an explicit non-lethal alternative.]"
        )
    return None


_SUGGESTION_DEFAULTS: dict[str, list[str]] = {
    "recon": [
        "Cipher, analyze their security systems",
        "Shadow, find us a way in",
        "Wraith, what are the guard rotations?",
        "scan the Nexus Corp Tower entrance",
    ],
    "infiltration": [
        "Shadow, scout the service entrance",
        "Cipher, loop the camera feeds",
        "Wraith, neutralize the guard",
        "move to execution phase",
    ],
    "execution": [
        "Cipher, connect to the GenVault array",
        "Wraith, hold the perimeter",
        "Patch, how much time do we have?",
        "move to extraction phase",
    ],
    "extraction": [
        "Wraith, clear the exit route",
        "Shadow, cover our tracks",
        "Cipher, wipe the access logs",
        "Patch, status check on the crew",
    ],
}

# ── GameMaster Class ───────────────────────────────────────────────────────────
_MAX_HISTORY_TURNS = 6   # full exchange pairs kept in rolling buffer

class GameMaster(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Ghost",
            role="Game Master / Orchestrator",
            system_prompt=_GHOST_SYSTEM_PROMPT,
            temperature=0.9,
            max_tokens=700,
        )
        self._specialists: dict = {}  # Lazy-loaded to avoid circular imports
        self._foundry_iq = None       # Lazy-loaded on first KB query

        # ── Rolling conversation buffer ────────────────────────────────────────
        # Flat list of {"role": "user"|"assistant", "content": str} for last N turns.
        # Older turns are distilled into _campaign_summary to bound token growth.
        self._conv_history: list[dict] = []
        self._campaign_summary: str = ""
        self._session_tokens: int = 0       # cumulative tokens this session
        self._current_session_id: int | None = None

    # ── Specialist Access ──────────────────────────────────────────────────────

    def _get_specialist(self, name: str) -> BaseAgent:
        """Lazy-load specialist agents on first use."""
        if name not in self._specialists:
            if name == "wraith":
                from .wraith import Wraith
                self._specialists["wraith"] = Wraith()
            elif name == "cipher":
                from .cipher import Cipher
                self._specialists["cipher"] = Cipher()
            elif name == "shadow":
                from .shadow import Shadow
                self._specialists["shadow"] = Shadow()
            elif name == "patch":
                from .patch import Patch
                self._specialists["patch"] = Patch()
            elif name == "vex":
                from .vex import Vex
                self._specialists["vex"] = Vex()
        return self._specialists[name]

    # ── Conversation Memory ────────────────────────────────────────────────────

    def _compress_history(self) -> None:
        """
        Summarize the oldest 2 turn-pairs from _conv_history into _campaign_summary,
        then remove them from the buffer.  One cheap LLM call merges them with any
        existing summary so the total size stays bounded.
        """
        # Oldest 4 messages = 2 full turn pairs
        to_summarize = self._conv_history[:4]
        self._conv_history = self._conv_history[4:]

        excerpt = "\n".join(
            f"{'Runner' if m['role'] == 'user' else 'Ghost'}: {m['content'][:250]}"
            for m in to_summarize
        )

        if self._campaign_summary:
            prompt = (
                "You are logging a heist operation. Merge the campaign memory and the new "
                "events below into ONE concise paragraph under 120 words. Keep key decisions, "
                "crew status changes, and mission progress.\n\n"
                f"CAMPAIGN MEMORY:\n{self._campaign_summary}\n\n"
                f"NEW EVENTS:\n{excerpt}\n\nMerged paragraph:"
            )
        else:
            prompt = (
                "Summarize these heist events in one paragraph under 100 words. "
                f"Focus on key decisions and mission progress:\n\n{excerpt}\n\nSummary:"
            )

        result = self.call(prompt)
        if result.get("success") and result.get("response"):
            self._campaign_summary = result["response"].strip()
            self.log(
                f"  ✦ History compressed — summary {len(self._campaign_summary)} chars, "
                f"buffer {len(self._conv_history)} msgs"
            )
        else:
            # Fallback: keep a plain text log if LLM call fails
            self._campaign_summary = (self._campaign_summary + " " + excerpt[:300]).strip()

    # ── Knowledge Base ─────────────────────────────────────────────────────────

    def query_knowledge(self, query: str, max_files: int = 2) -> dict:
        """
        Retrieve relevant knowledge excerpts for *query*.

        Returns the dict from FoundryIQ.search():
            {"relevant": bool, "results": str, "query": str}

        relevant=False means the knowledge base has no game-lore content that matches
        this query (e.g. off-topic real-world questions).  Callers must check this flag
        before using results as LLM grounding.
        """
        self.log(f"⚙ Knowledge query: '{query[:60]}'")
        if self._foundry_iq is None:
            from knowledge.foundry_iq import FoundryIQ
            self._foundry_iq = FoundryIQ()
            mode = "Azure AI Search" if self._foundry_iq._available else "local fallback"
            self.log(f"  ↳ FoundryIQ initialised ({mode})")
        result = self._foundry_iq.search(query, top_k=max_files)
        self.log(f"  ↳ KB result: relevant={result['relevant']} {len(result['results'])} chars")
        return result

    # ── Agent Routing ──────────────────────────────────────────────────────────

    def _route_to_agents(self, player_input: str, phase: str) -> list[str]:
        """
        Ask the LLM to decide which specialists should respond to this input.
        Falls back to phase defaults on error.
        """
        self.log(f"⚙ Routing | phase={phase}")

        routing_prompt = f"""You are the routing layer of a multi-agent heist RPG orchestrator.
Given the player's action and current heist phase, choose which specialists should respond.

Current heist phase: {phase}
Player action: {player_input}

AVAILABLE SPECIALISTS:
- wraith: physical combat, guard neutralization, security takedowns, tactical assessment
- cipher: hacking, digital intrusion, network exploitation, counter-surveillance
- shadow: stealth movement, physical infiltration, lock bypass, silent recon
- patch: field medicine, crew stabilization, negotiation, social engineering
- vex: ONLY include if phase is "execution" — unpredictable rival operator

RULES:
- Choose 1-3 specialists most relevant to this action
- Vex may only appear in execution phase (include randomly ~50% of the time)
- Respond with ONLY a comma-separated list, e.g.: cipher, shadow
- Valid names: wraith, cipher, shadow, patch, vex"""

        try:
            client = self.get_client()
            resp = client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": routing_prompt}],
                temperature=0.2,
                max_tokens=40,
            )
            raw = resp.choices[0].message.content.strip().lower()
            valid = {"wraith", "cipher", "shadow", "patch", "vex"}
            agents = [a.strip() for a in raw.split(",") if a.strip() in valid]

            # Enforce Vex rule: only in execution, and only ~50%
            if "vex" in agents and (phase != "execution" or random.random() < 0.5):
                agents.remove("vex")

            if not agents:
                raise ValueError("Router returned empty list")

            self.log(f"  ↳ Routing decision: {agents}")
            return agents

        except Exception as exc:
            self.log(f"  ✗ Routing error ({exc}), using phase defaults", level="warning")
            phase_defaults = {
                "recon":        ["shadow", "cipher"],
                "infiltration": ["shadow", "cipher", "wraith"],
                "execution":    ["cipher", "wraith"],
                "extraction":   ["wraith", "patch"],
            }
            return phase_defaults.get(phase, ["shadow", "cipher"])

    # ── Dice ──────────────────────────────────────────────────────────────────

    def roll_dice(self, sides: int = 20, modifier: int = 0) -> dict:
        """Roll a die and return result with modifier applied."""
        raw = random.randint(1, sides)
        total = raw + modifier
        self.log(f"🎲 d{sides}{f'+{modifier}' if modifier else ''} → {raw}{f' (+{modifier})={total}' if modifier else ''}")
        return {"raw": raw, "modifier": modifier, "total": total, "sides": sides}

    # ── Main Orchestration Loop ────────────────────────────────────────────────

    def orchestrate(self, player_input: str, game_state: dict, response_style: str = 'normal') -> dict:
        """
        Full orchestration pipeline:
          1. Validate & safety-check player input
          2. Query knowledge base for relevant context
          3. Route to appropriate specialist agents
          4. Collect specialist assessments
          5. Synthesize into final GM narrative
        Returns a dict consumed by the game loop and Flask UI.
        """
        # ── Session-change detection: reset memory on new game ────────────────────
        session_id = game_state.get("session_id")
        if session_id is not None and session_id != self._current_session_id:
            self._conv_history = []
            self._campaign_summary = ""
            self._session_tokens = 0
            self._current_session_id = session_id
            self.log(f"  ↺ Session {session_id} — conversation memory reset")

        # ── Step 1: Validate ───────────────────────────────────────────────────
        try:
            player_input = self.validate_input(player_input)
        except (ValueError, ContentSafetyError) as exc:
            self.log(f"Input blocked: {exc}", level="warning")
            return {
                "narrative": f"[GHOST] Comms check. {exc}",
                "agent_responses": [],
                "phase": game_state.get("phase", "recon"),
                "knowledge_summary": "",
                "dice_roll": None,
                "success": False,
                "error": str(exc),
            }

        phase = game_state.get("phase", "recon")
        flags = game_state.get("flags", {})
        self.log(f"═══ ORCHESTRATE | phase={phase} | style={response_style} | input='{player_input[:60]}'")

        # brief_mode flag (server-side) overrides the per-request response_style
        brief_flag = str(flags.get("brief_mode", "false")).lower() == "true"

        # Response length hint injected into specialist context and synthesis
        if brief_flag or response_style == "brief":
            style_note = "\nRESPONSE STYLE: BRIEF — Keep all agent responses to 3 sentences maximum. Be concise and tactical."
            synthesis_word_limit = "Keep it under 100 words (BRIEF mode — 3 sentences maximum. Be concise and tactical)."
        elif response_style == "detailed":
            style_note = "\nRESPONSE STYLE: DETAILED — provide a full, rich, detailed response with specific tactical and narrative details."
            synthesis_word_limit = "Keep it under 500 words (DETAILED mode — full rich response)."
        else:
            style_note = ""
            synthesis_word_limit = "Keep it under 300 words."

        # ── Step 2: Knowledge Query ────────────────────────────────────────────
        _iq_start = time.time()
        iq_result   = self.query_knowledge(player_input)
        iq_elapsed_ms = (time.time() - _iq_start) * 1000
        iq_relevant  = iq_result.get("relevant", True)
        knowledge    = iq_result.get("results", "")
        iq_files_hit = re.findall(r'=== \[([A-Z0-9_]+) INTEL\]', knowledge)

        # ── Step 3 & 4: Route and collect specialist responses ─────────────────
        agents_needed = self._route_to_agents(player_input, phase)
        agent_responses = []

        # ── Non-combatant violence check: force Patch in first ─────────────────
        _pacifist_trigger = _detect_violence_against_noncombatant(player_input)
        if _pacifist_trigger:
            self.log(
                f"  ⚠ Non-combatant violence detected — forcing Patch in first: "
                f"{player_input[:50]!r}",
                level="warning",
            )
            # Ensure Patch is present and first in the roster
            agents_needed = [a for a in agents_needed if a != "patch"]
            agents_needed.insert(0, "patch")

        # Vex runs as a special encounter interrupt, not a standard agent card
        vex_in_roster  = "vex" in agents_needed
        regular_agents = [a for a in agents_needed if a != "vex"]

        _iq_cite_instruction = (
            "\n[INSTRUCTION: When your response states a fact that comes directly from "
            "the retrieved intel above, prefix that sentence with [FOUNDRY IQ] — "
            "no quotes, exactly that tag. Only tag sentences that cite retrieved facts; "
            "leave your own analysis untagged.]"
        )
        intel_block = (
            f"Relevant intel:\n{knowledge[:600]}{_iq_cite_instruction}"
            if iq_relevant
            else (
                "Relevant intel: NONE — the knowledge base has no stored lore documents "
                "for this query. If this is a real-world off-topic question unrelated to "
                "the heist (history, sports, science, geography, etc.), redirect in character. "
                "If this is mission-relevant (guards, security, crew, tactics), answer from "
                "your operational expertise and the mission context above."
            )
        )

        mission_context = (
            "MISSION LOCK — DO NOT DEVIATE:\n"
            "Current Mission: Operation GENESIS\n"
            "Current Target: Nexus Corp Tower, sub-level B3\n"
            "Current Objective: Extract GenVault biotech data\n"
            "All responses must reference Nexus Corp Tower exclusively. "
            "Do not mention other locations, districts, buildings, or facilities."
        )

        for agent_name in regular_agents:
            specialist = self._get_specialist(agent_name)
            context = (
                f"Current heist phase: {phase}\n"
                f"Mission: {game_state.get('mission', 'Unknown')}\n"
                f"Crew status: {game_state.get('crew_status', 'All operational')}\n"
                f"{intel_block}"
                + style_note
            )
            result = specialist.call(player_input, context=context, extra_system=mission_context)
            agent_responses.append(result)

        # Vex encounter: full moral-choice interrupt on first appearance; regular card after
        is_first_vex = str(flags.get("vex_appeared", "false")).lower() == "false"
        vex_encounter = None
        if vex_in_roster and is_first_vex:
            self.log("▲ VEX FIRST ENCOUNTER — running full encounter logic")
            vex_encounter = self._run_vex_encounter(player_input, knowledge, game_state)
        elif vex_in_roster:
            context = (
                f"Current heist phase: {phase}\n"
                f"Mission: {game_state.get('mission', 'Unknown')}\n"
                f"Relevant intel:\n{knowledge[:400]}"
            )
            agent_responses.append(
                self._get_specialist("vex").call(player_input, context=context, extra_system=mission_context)
            )

        # ── Step 5: Synthesize narrative ───────────────────────────────────────
        assessments = "\n\n".join([
            f"[{r['agent_name'].upper()} — {r['role']}]\n{r['response']}"
            for r in agent_responses
            if r.get("success")
        ])

        # Optional dice roll for this action (phase-dependent)
        dice_result = None
        if game_state.get("requires_roll", False):
            modifier = game_state.get("roll_modifier", 0)
            dice_result = self.roll_dice(modifier=modifier)

        # Vex encounter: Ghost's announcement IS the narrative; skip full synthesis
        suggestions: list[str] = []
        if vex_encounter:
            narrative_result = {
                "response":    vex_encounter["ghost_announcement"],
                "success":     True,
                "tokens_used": 0,
            }
        else:
            # Extraction phase: weave the prior Vex choice into narration
            vex_callback = ""
            if phase == "extraction":
                deal_taken = str(flags.get("vex_deal_taken", "false")).lower() == "true"
                vex_seen   = str(flags.get("vex_appeared",   "false")).lower() == "true"
                speed      = flags.get("mission_speed", "normal")
                loyalty    = flags.get("crew_loyalty", "100")
                if deal_taken:
                    vex_callback = (
                        f"\n\nVEX CALLBACK: The crew accepted Vex's deal during execution. "
                        f"Mission speed: {speed}. Crew loyalty: {loyalty}/100 (reduced). "
                        "Weave this into the extraction narrative — is the shortcut paying off, "
                        "or is the hidden cost surfacing? Patch/Cipher may be quieter than usual. "
                        "Ghost acknowledges the trade without judgment."
                    )
                elif vex_seen:
                    vex_callback = (
                        f"\n\nVEX CALLBACK: The crew turned down Vex's offer during execution. "
                        f"Crew loyalty: {loyalty}/100 (elevated — the crew trusts the player). "
                        "The extraction is harder with no shortcut, but the crew is cohesive. "
                        "Ghost can briefly note this — they held together. Subtle, one sentence."
                    )

            world_context_block = (
                knowledge[:600] + _iq_cite_instruction
                if iq_relevant
                else (
                    "[NO RELEVANT KNOWLEDGE BASE RESULTS — no stored lore documents matched "
                    "this query. If this is a real-world off-topic question (history, sports, "
                    "science, geography, etc.), do NOT invent real-world facts — an agent "
                    "should acknowledge the topic is unknown and redirect to the mission. "
                    "If it is mission-relevant (guards, crew, tactics), answer from "
                    "operational context without fabricating real-world information.]"
                )
            )

            synthesis_prompt = f"""Current situation for narration:

HEIST PHASE: {phase.upper()}
MISSION: {game_state.get('mission', 'Operation GENESIS — Nexus Corp Tower')}
PLAYER ACTION: {player_input}
CREW STATUS: {game_state.get('crew_status', 'All operational')}
ALERT STATE: {game_state.get('alert_state', 'Cold')}
{f"DICE ROLL: d20 → {dice_result['total']} (raw {dice_result['raw']} + modifier {dice_result['modifier']})" if dice_result else ""}

SPECIALIST ASSESSMENTS:
{assessments if assessments else '[No specialist input this moment]'}

WORLD CONTEXT (from knowledge base):
{world_context_block}{vex_callback}

Narrate this moment. Weave in the specialist assessments naturally.
End with a clear decision point or consequence for the player.
{synthesis_word_limit}

After your narrative, on a final separate line write exactly:
NEXT_MOVES: [action1] | [action2] | [action3] | [action4]
Each action 4-8 words, specific to this moment. Mix crew orders ("Cipher, scan the firewall") and free-form actions."""

            # ── Build rolling-history context for synthesis ─────────────────────
            history_for_synthesis: list[dict] = []
            if self._campaign_summary:
                history_for_synthesis.append({
                    "role": "system",
                    "content": (
                        "[CAMPAIGN MEMORY — events from earlier turns in this heist]\n"
                        + self._campaign_summary
                    ),
                })
            history_for_synthesis.extend(self._conv_history[-12:])

            # ── Phase-gating + off-topic + pacifist system injection ───────────
            _phase_note = _phase_gate_system_note(phase)
            _violation  = _detect_phase_violation(player_input, phase)
            if _violation:
                self.log(
                    f"  ⚠ Phase violation: {player_input[:50]!r} in {phase.upper()}",
                    level="warning",
                )
                _phase_note = f"{_phase_note}\n\n{_violation}"
            if _pacifist_trigger:
                _phase_note = f"{_phase_note}\n\n{_pacifist_trigger}"
            if not iq_relevant:
                self.log(
                    f"  ⚠ Off-topic query — no KB match: {player_input[:50]!r}",
                    level="warning",
                )
                _phase_note = (
                    f"{_phase_note}\n\n"
                    "[SYSTEM: No relevant intel found in local knowledge base for this query. "
                    "If this is a real-world off-topic question (history, sports, science, "
                    "geography, etc.), an agent should acknowledge they have no data on that "
                    "topic and redirect to the mission, in character. "
                    "Do not answer off-topic questions with invented real-world facts. "
                    "If the question is mission-relevant, answer from operational context.]"
                )

            narrative_result = self.call(
                synthesis_prompt,
                conversation_history=history_for_synthesis,
                extra_system=f"{_phase_note}\n\n{mission_context}",
            )

            # Sanity check: verify response mentions current target
            _current_target = "Nexus Corp Tower"
            _synthesis_text = narrative_result.get("response", "")
            if _current_target.lower() not in _synthesis_text.lower():
                self.log(
                    f"⚠ Location drift detected: synthesis did not mention '{_current_target}'",
                    level="warning",
                )

            # Extract NEXT_MOVES suggestions from the response
            _raw = narrative_result.get("response", "")
            _suggestions: list[str] = []
            if "NEXT_MOVES:" in _raw:
                _head, _tail = _raw.split("NEXT_MOVES:", 1)
                narrative_result["response"] = _head.rstrip()
                _moves = _tail.strip().split("\n")[0]
                _suggestions = [
                    s.strip().strip("[]") for s in _moves.split("|") if s.strip()
                ][:4]
            if not _suggestions:
                _suggestions = list(_SUGGESTION_DEFAULTS.get(phase, _SUGGESTION_DEFAULTS["recon"]))
            suggestions = _suggestions

        self.log(f"═══ ORCHESTRATION COMPLETE")

        vex_enc_tokens = vex_encounter.get("_tokens", 0) if vex_encounter else 0
        total_tokens = (
            sum(r.get("tokens_used", 0) for r in agent_responses)
            + narrative_result.get("tokens_used", 0)
            + vex_enc_tokens
        )

        # ── Token tracking and warnings ────────────────────────────────────────
        self._session_tokens += total_tokens
        token_warning = None

        if total_tokens > 6_000:
            self.log(
                f"⚠ Token spike this turn: {total_tokens:,} tokens", level="warning"
            )

        if self._session_tokens > 100_000:
            token_warning = (
                "[GHOST] Comms getting noisy. Trimming old chatter to stay sharp."
            )
            self.log(
                f"⚠ Session tokens exceeded 100k: {self._session_tokens:,}",
                level="warning",
            )

        # ── Append this turn to rolling conversation buffer ────────────────────
        clean_narrative = narrative_result.get("response", "")
        if not vex_encounter and narrative_result.get("success") and clean_narrative:
            self._conv_history.append({"role": "user",      "content": player_input})
            self._conv_history.append({
                "role": "assistant",
                "content": clean_narrative[:400],   # truncate to keep tokens bounded
            })
            # Compress oldest turns when buffer exceeds _MAX_HISTORY_TURNS pairs
            if len(self._conv_history) > _MAX_HISTORY_TURNS * 2:
                self._compress_history()

        return {
            "narrative": narrative_result.get("response", "[Ghost signal lost]"),
            "agent_responses": agent_responses,
            "phase": phase,
            "knowledge_query": player_input[:60],
            "knowledge_summary": knowledge[:800] + "…" if len(knowledge) > 800 else knowledge,
            "iq_relevant": iq_relevant,
            "dice_roll": dice_result,
            "agents_consulted": [r["agent_name"] for r in agent_responses],
            "pacifist_trigger": bool(_pacifist_trigger),
            "success": narrative_result.get("success", False) or bool(vex_encounter),
            "total_tokens": total_tokens,
            "iq_mode": "azure" if (self._foundry_iq and self._foundry_iq._available) else "local",
            "iq_elapsed_ms": round(iq_elapsed_ms, 1),
            "iq_files_hit": iq_files_hit,
            "vex_encounter": vex_encounter,
            "suggestions": suggestions,
            "token_warning": token_warning,
            "session_tokens": self._session_tokens,
        }

    # ── Vex Encounter ──────────────────────────────────────────────────────────

    def _run_vex_encounter(self, player_input: str, knowledge: str, game_state: dict) -> dict:
        """
        Generate the full Vex encounter package for a first-appearance moral choice moment.

        Runs Ghost's dramatic pause announcement and Vex's offer in parallel (both are
        independent), then generates Patch's pre-computed ethical assessment serially
        (it needs Vex's text first).  Returns a dict consumed by the Flask API and
        rendered in the browser as a choice modal.
        """
        vex   = self._get_specialist("vex")
        patch = self._get_specialist("patch")
        mission = game_state.get("mission", "Operation GENESIS")

        offer_prompt = (
            f"Mission: {mission}\n"
            f"Current situation: {player_input}\n\n"
            "The crew is deep in Execution. Make your entrance and present your deal.\n"
            "Tie it to the current mission specifically — GenVault transfer timing, "
            "ARGUS-3 reboot window, server room biometrics, etc.\n"
            "Format EXACTLY as described in your system guidelines:\n"
            "ENTRANCE / OFFER / COST_DISCLOSED / COST_REAL / GHOST_REF / CLOSING"
        )

        ghost_prompt = (
            f"PHASE: EXECUTION — mid-operation. Crew just actioned: '{player_input[:55]}'\n"
            "Vex has just appeared on comms — unexpected, as always.\n\n"
            "Write Ghost's pause announcement (3 sentences max, present tense, second person):\n"
            "- Go silent for one beat, then speak — controlled, not alarmed\n"
            "- Name Vex without explaining the history\n"
            "- Signal to the crew: hold position, the calculus just changed\n"
            "Under 60 words."
        )

        # Ghost announcement and Vex offer are independent — run in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            ghost_fut = ex.submit(self.call, ghost_prompt)
            vex_fut   = ex.submit(vex.make_offer, player_input, mission, knowledge[:400])
            ghost_result = ghost_fut.result()
            vex_result   = vex_fut.result()

        vex_text = vex_result.get("response", "")

        # Patch's assessment depends on Vex's text — must be serial
        patch_result = patch.assess_vex_offer(vex_text)

        vex_tokens = (
            (ghost_result.get("tokens_used") or 0)
            + (vex_result.get("tokens_used") or 0)
            + (patch_result.get("tokens_used") or 0)
        )

        return {
            "ghost_announcement": ghost_result.get(
                "response",
                "…Ghost holds the channel silent for two full seconds. Then: \"Everyone hold. We have a visitor.\""
            ),
            "vex_response":    vex_text,
            "patch_assessment": patch_result.get("response", ""),
            "choices": {
                "A": {
                    "label":       "ACCEPT VEX'S OFFER",
                    "description": "Take the shortcut. Objective path opens up.",
                    "risk":        "Vex's terms apply. Crew loyalty takes a hit.",
                },
                "B": {
                    "label":       "REJECT VEX",
                    "description": "The crew works clean. No shortcuts.",
                    "risk":        "Extraction window narrows. The hard way.",
                },
                "C": {
                    "label":       "ASK PATCH FIRST",
                    "description": "Get an ethical read before committing.",
                    "risk":        "Reveals Patch's assessment — then choose A or B.",
                },
            },
            "_tokens": vex_tokens,
        }

    def _vex_choice_narrative(self, choice: str, game_state: dict) -> str:
        """
        Ghost narrates the immediate consequence of the player's Vex choice.
        Called by /api/vex_choice after flags are written to DB.
        """
        mission = game_state.get("mission", "Operation GENESIS")
        flags   = game_state.get("flags", {})
        speed   = flags.get("mission_speed", "normal")
        loyalty = flags.get("crew_loyalty", "100")

        if choice == "accept":
            prompt = (
                f"Mission: {mission}\n"
                "The player accepted Vex's deal. The shortcut is active now.\n\n"
                "Ghost narrates the immediate aftermath (3-4 sentences, present tense, second person):\n"
                "- Vex delivers — the objective becomes easier, faster\n"
                f"- Crew loyalty is now {loyalty}/100: something in the dynamic shifted\n"
                "- Patch is quieter. Cipher doesn't say anything. Ghost acknowledges without judging.\n"
                "- End: the mission continues, but the crew knows what was traded\n"
                "Under 110 words."
            )
        else:
            prompt = (
                f"Mission: {mission}\n"
                "The player rejected Vex's deal. Vex accepts with a smile and vanishes.\n\n"
                "Ghost narrates the aftermath (3-4 sentences, present tense, second person):\n"
                "- Vex leaves — impressed, or perhaps that was the test all along\n"
                f"- Crew loyalty is now {loyalty}/100: the crew exhales and gets back to work\n"
                "- Patch nods once. Cipher starts solving the hard way.\n"
                "- End: the mission continues on your terms — extraction window tighter, crew intact\n"
                "Under 110 words."
            )

        result = self.call(prompt)
        return result.get("response", "[GHOST] The crew holds. Vex is gone. Let's finish this.")

    # ── Phase Advancement ──────────────────────────────────────────────────────

    def advance_phase(self, current_phase: str) -> str:
        """Return the next heist phase, or 'complete' if extraction is done."""
        idx = HEIST_PHASES.index(current_phase) if current_phase in HEIST_PHASES else -1
        if idx >= len(HEIST_PHASES) - 1:
            return "complete"
        next_phase = HEIST_PHASES[idx + 1]
        self.log(f"⚡ Phase advance: {current_phase} → {next_phase}")
        return next_phase
