# Ghost Protocol — Architecture

Multi-agent cyberpunk heist RPG. Six Azure OpenAI agents, orchestrated in real time.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Player / Demo Script                      │
│            (CLI  ·  Flask Web UI  ·  demo.py)               │
└───────────────────────────┬─────────────────────────────────┘
                            │  plain-English action
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  GameMaster  (Ghost)                        │
│                                                             │
│   1. validate_input()     — content safety check            │
│   2. query_knowledge()    — RAG-lite KB retrieval           │
│   3. _route_to_agents()   — LLM-based routing decision      │
│   4. specialist.call() ×N — parallel specialist calls       │
│   5. synthesize()         — Ghost narrates the result       │
│                                                             │
└──────┬───────────────────────────────────────────┬──────────┘
       │ routes to 2–3 specialists                 │ synthesizes
       ▼                                           ▼
┌─────────────────────────────────┐   ┌─────────────────────┐
│        Specialist Agents        │   │   Player-facing     │
│                                 │   │   Narrative Output  │
│  ┌────────┐  ┌────────────┐     │   └─────────────────────┘
│  │ Wraith │  │   Cipher   │     │
│  │Enforcer│  │   Hacker   │     │   ┌─────────────────────┐
│  └────────┘  └────────────┘     │   │     GameState       │
│                                 │   │  (SQLite database)  │
│  ┌────────┐  ┌────────────┐     │   │                     │
│  │ Shadow │  │   Patch    │     │   │ sessions            │
│  │Infiltr.│  │   Fixer    │     │   │ crew_status         │
│  └────────┘  └────────────┘     │   │ objectives          │
│                                 │   │ world_flags         │
│  ┌─────────────────────────┐    │   │ turn_history        │
│  │   Vex  (Execution only) │    │   └─────────────────────┘
│  │   Rival Operator        │    │
│  └─────────────────────────┘    │
└─────────────────────────────────┘
```

---

## Agent Roster

All agents inherit from `BaseAgent`, which holds the shared Azure OpenAI client singleton,
content safety validation, structured logging, and the `call()` method.

| Agent | Class | Temperature | Max Tokens | Phase | Key Behaviors |
|---|---|---|---|---|---|
| Ghost | `GameMaster` | 0.90 | 700 | All | Orchestration, Foundry IQ query, phase-gate enforcement, extraction confirmation intercept, conversation memory, narrative synthesis |
| Wraith | `Wraith` | 0.70 | 400 | Infiltration, Execution, Extraction | Combat assessment, security takedowns, threat neutralisation |
| Cipher | `Cipher` | 0.90 | 500 | Recon, Infiltration, Execution | Digital intrusion, counter-surveillance; redirects off-topic queries |
| Shadow | `Shadow` | 0.75 | 400 | Recon, Infiltration | Stealth movement, physical security bypass |
| Patch | `Patch` | 0.80 | 450 | Execution, Extraction | Medical support; mandatory ethical intervention on non-combatant violence — first = warning, second = morale drop + alert escalation |
| Vex | `Vex` | 0.95 | 350 | Execution only | Wild-card rival; moral-choice encounter with 3 options; deal outcome propagates 4 world flags |

Lower temperature for tactical agents (Wraith, Shadow) produces terse, specific briefings.
Higher temperature for narrative agents (Ghost, Vex, Cipher) produces varied, expressive output.

---

## Turn Processing Pipeline

A single player action flows through nine sequential stages:

```
Player action
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1 · Input Validation                             │
│  base_agent.validate_input()                            │
│  • Length check (max 2,000 chars)                       │
│  • Regex injection pattern scan (9 patterns)            │
│  • Hard-block real-world harmful terms                  │
│  → Raises ContentSafetyError on violation               │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2 · Phase-Gate Check                             │
│  app.py pre-orchestrate guards                          │
│  • If pending_confirmation flag is set: resolve the     │
│    human-in-the-loop extraction gate (confirm/abort)    │
│  • If extraction attempt detected in execution/         │
│    extraction phase: set pending_confirmation, return   │
│    Ghost's confirmation prompt — do NOT call orchestrate│
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 3 · Non-Combatant Violence Check                 │
│  game_master._detect_violence_against_noncombatant()    │
│  • frozenset intersection: violence keywords ∩          │
│    noncombatant descriptors                             │
│  • If triggered: Patch responds with ethical            │
│    intervention; first objection = warning flag;        │
│    second = crew morale drop + alert escalation         │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 4 · Foundry IQ Query (relevance-gated)           │
│  FoundryIQ.search() — Azure AI Search primary,          │
│  local keyword-map fallback                             │
│  • Queries ghost-protocol-knowledge index               │
│  • Returns {"relevant": bool, "results": str, ...}      │
│  • Up to 600 chars of KB text prepended to context      │
│  • [FOUNDRY IQ] citation tag instructed to agents       │
│    when relevant=True                                   │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 5 · Agent Routing                                │
│  game_master._route_to_agents()                         │
│  • Sends routing prompt to GPT-4o (temp=0.2)            │
│  • Model returns comma-separated specialist list        │
│  • Validates against known agent names + phase rules    │
│  • Enforces Vex rule: Execution phase only, ~50%        │
│  • Falls back to phase defaults on error                │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 6 · Specialist Calls                             │
│  specialist.call()  (one per routed agent)              │
│  • Each agent receives: system_prompt + phase context   │
│    + knowledge excerpt + conversation history (last 6)  │
│  • Each agent responds in its own voice and role        │
│  • Responses collected as structured result dicts       │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 7 · Dice Roll (if needed)                        │
│  game_master.roll_dice()                                │
│  • _detect_roll_needed() checks action keywords         │
│  • raw = random.randint(1, 20) + roll_modifier          │
│  • No Azure API call — pure Python PRNG                 │
│  • Result included in Ghost's synthesis context         │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 8 · Narrative Synthesis                          │
│  game_master.call() — Ghost's final response            │
│  • Receives: all specialist assessments + KB excerpt    │
│    + phase + alert state + dice result                  │
│  • Weaves assessments into atmospheric narration        │
│  • Ends with a decision point for the player            │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 9 · World State Update                           │
│  • GameState.add_turn() — persists turn to SQLite       │
│  • Alert escalation check (_maybe_escalate_alert)       │
│  • Vex trigger check (_maybe_flag_vex)                  │
│  • Phase auto-advance (_detect_phase_advance_hint)      │
│  • Morale + alert consequence if pacifist_trigger       │
│  • MetricsStore updated (tokens, latency, IQ, dice)     │
│  → Full game state returned in JSON response            │
└─────────────────────────────────────────────────────────┘
```

Total LLM calls per turn: **1 router + 2–3 specialists + 1 narrator = 4–5 calls**.

---

## Knowledge Base (RAG-lite)

Eight Markdown documents in `/knowledge/` describe the world of Toronto 2047:

| File | Content |
|---|---|
| `world_overview.md` | History, slang, economy, the Blackout War |
| `corporations.md` | Nexus Corp, Axiom, Helix, Vantage, OmniCore profiles |
| `districts.md` | The Spire, Underbelly, Fringe, Neon Ward, Old Town, etc. |
| `crew_profiles.md` | Backstories for Ghost, Wraith, Cipher, Shadow, Patch, Vex |
| `heist_targets.md` | Operation GENESIS and other target dossiers |
| `factions.md` | The Collective, Iron Veil, Silk Network, Rust Saints |
| `items_and_gear.md` | Augmentations, weapons, intrusion decks, gear |
| `homebrew_rules.md` | Dice system, skill checks, phase mechanics |

**Retrieval** is keyword-based: each file is mapped to a set of trigger words. When a
player action or query contains those words, the corresponding file is loaded and its
first 1,800 characters are prepended to the agent's context. Up to 2 files load per query.
This keeps context windows lean while grounding agent responses in consistent world lore.

---

## Heist Phase System

```
RECON → INFILTRATION → EXECUTION → EXTRACTION → complete
```

Phase controls:
- Which specialists the routing LLM is permitted to select
- Which objectives are active
- Whether Vex can appear (Execution only)
- Fallback agent sets if routing fails

Phase advances either via the `/advance` CLI command, player narrative trigger
detection (`_detect_phase_advance_hint` in `main.py`), or explicitly in `demo.py`.

---

## Vex Complication Mechanic

Vex is a rival operator who appears during Execution phase as a narrative wild card.

In the interactive game, the routing LLM can include `vex` in its decision list when:
1. The current phase is `execution`, AND
2. A random roll exceeds 50%

In `demo.py`, Vex is injected deterministically between Execution turns 1 and 2,
guaranteeing the complication is visible in every demo run.

Vex's system prompt instructs the model to:
- Announce arrival theatrically
- State a partial-truth objective of her own
- Create a complication that forces adaptation without destroying the mission
- Reference cryptic shared history with Ghost
- Leave before anything is fully explained

---

## Azure OpenAI Integration

All LLM calls use the `AzureOpenAI` client from the `openai` SDK.
The client is a singleton on `BaseAgent`, shared across all six agents.

**Configuration** (from `.env`):

```
AZURE_OPENAI_ENDPOINT    — Azure OpenAI resource endpoint
AZURE_OPENAI_API_KEY     — API key
AZURE_OPENAI_DEPLOYMENT  — Model deployment name (gpt-4o)
AZURE_OPENAI_API_VERSION — API version (2024-10-21)
```

**Call pattern** (in `BaseAgent.call()`):

```python
client.chat.completions.create(
    model=self._deployment,          # deployment name, not model ID
    messages=[
        {"role": "system",    "content": agent_system_prompt},
        *conversation_history[-6:],  # last 3 turn pairs for continuity
        {"role": "user",      "content": context + player_action},
    ],
    temperature=self.temperature,    # per-agent, 0.7–0.95
    max_tokens=self.max_tokens,      # per-agent, 350–700
)
```

**Azure Content Filtering** applies at the API level to all calls.
The application adds a second layer of input validation and output scrubbing
(see `BaseAgent.validate_input()` and `_check_output_safety()`).

**Routing calls** use `temperature=0.2` and `max_tokens=40` — a lightweight,
deterministic call that decides which specialists to consult, not generate narrative.

---

## Game State — SQLite Schema

```
sessions        — one row per heist run (phase, alert_state, turn_count)
crew_status     — health and augment state per agent per session
objectives      — mission objectives with completion status
world_flags     — boolean/string flags (vex_appeared, data_extracted, etc.)
turn_history    — full log of every turn (input, narrative, agents, dice, timestamp)
```

`GameState` auto-commits via Python's `sqlite3` context manager.
`save_snapshot()` exports the full session to JSON for inspection or replay.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM API | Azure OpenAI GPT-4o (`openai` SDK v2) |
| Azure SDK | `azure-ai-projects`, `azure-identity` |
| Web server | Flask 3.1 |
| Persistence | SQLite 3 (stdlib `sqlite3`) |
| Frontend | Vanilla JS + CSS (no framework) |
| Config | `python-dotenv` |
| Logging | Python `logging` → `ghost_protocol.log` |

---

## File Map

```
agents/
  base_agent.py       — AzureOpenAI client, call(), validate_input(), logging
  game_master.py      — Orchestrator: knowledge query, routing, synthesis
  wraith.py           — Enforcer: combat, security assessment
  cipher.py           — Hacker: digital intrusion, counter-surveillance
  shadow.py           — Infiltrator: stealth recon, movement planning
  patch.py            — Fixer: medicine, negotiation, crew support
  vex.py              — Rival: Execution-phase complication

state/
  game_state.py       — SQLite schema, session lifecycle, all CRUD ops

knowledge/            — 8 × .md world documents (retrieved as RAG context)

main.py               — CLI game loop, ANSI rendering, /commands, dice
app.py                — Flask routes, JSON API, singleton state management
demo.py               — Automated demo: 7 scripted turns, forced Vex, KB queries
```
