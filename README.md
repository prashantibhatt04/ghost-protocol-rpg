# Ghost Protocol — Multi-Agent Cyberpunk Heist RPG

**Built for the Microsoft Agents League Hackathon 2026, Reasoning Agents track (Challenge B).**

## What It Is

Ghost Protocol is a narrative RPG where six Azure OpenAI GPT-4o agents collaborate in real time to run a heist in Toronto 2047. A Game Master agent (Ghost) orchestrates them — routing each player action to the right specialists, grounding every response in a live Azure AI Search knowledge base, and synthesising their answers into atmospheric fiction.

**The mission:** Extract classified biotech data from Nexus Corp Tower. Operation GENESIS.

---

## Microsoft Foundry Integration

Ghost Protocol is built on Microsoft Foundry:

- **Project**: Created and managed in Azure AI Foundry (ai.azure.com), project endpoint `https://ghost-protocol-rg2.services.ai.azure.com/api/projects/proj-default`
- **Model deployment**: gpt-4o deployed through the Foundry model catalog, accessed via the Azure OpenAI-compatible endpoint for all 6 agents' reasoning
- **Foundry IQ**: Azure AI Search resource within the same Foundry project, containing a 73-document knowledge base across 8 synthetic lore files, with relevance-gated retrieval and citations surfaced in the UI
- **Why this architecture**: We use the OpenAI-compatible SDK (`openai` package with `AzureOpenAI` client) for inference calls against our Foundry-deployed model, which is Microsoft's recommended pattern for the v1 Azure OpenAI API (GA since August 2025). This approach provides full OpenAI SDK compatibility while running entirely on Foundry-hosted infrastructure, eliminating the need for custom Azure SDK abstractions.

---

## Demo Video

> [Embed link — recording in progress]

---

## Architecture

```
                        Player Action
                             │
                             ▼
                    ┌─────────────────┐
                    │  Game Master     │
                    │     (Ghost)      │
                    │                 │
                    │  1. Safety      │
                    │  2. IQ Query    │
                    │  3. Route       │
                    │  4. Specialists │
                    │  5. Synthesise  │
                    └────────┬────────┘
                             │ routes to 2–3 agents
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌────────┐    ┌──────────┐   ┌──────────┐
         │ Cipher │    │  Shadow  │   │  Wraith  │
         │ Hacker │    │ Infiltr. │   │ Enforcer │
         └────────┘    └──────────┘   └──────────┘
              │                            │
              └──────────┬─────────────────┘
                         │ also available
                    ┌────┴────┐    ┌──────┐
                    │  Patch  │    │  Vex │
                    │  Fixer  │    │ Rival│
                    └─────────┘    └──────┘
                             │
                             ▼
                 ┌───────────────────────┐
                 │  Foundry IQ           │
                 │  (Azure AI Search)    │
                 │                       │
                 │  ghost-protocol-      │
                 │  knowledge index      │
                 │  73 chunks · 8 docs   │
                 └───────────────────────┘
```

Every turn costs **4–5 LLM calls**: 1 safety-aware router + 2–3 specialists + 1 narrator. The knowledge base is queried at Stage 2 — before any agent sees the action.

---

## Agent Responsibilities

| Agent | Role | Phases | Behavior |
|---|---|---|---|
| **Ghost** (Game Master) | Orchestration & narration | All | Routes actions, queries Foundry IQ, manages conversation memory, enforces phase gates, intercepts irreversible extraction with a human-in-the-loop confirmation prompt, synthesises all agent responses into atmospheric fiction |
| **Cipher** | Hacker / technical | Recon, Infiltration, Execution | Digital intrusion, counter-surveillance, network breaches; redirects off-topic queries back to operational focus |
| **Shadow** | Infiltrator / stealth | Recon, Infiltration | Movement planning, stealth approach, physical security bypass |
| **Wraith** | Enforcer / combat | Infiltration, Execution, Extraction | Combat assessment, security takedowns, threat neutralisation |
| **Patch** | Fixer / medic / ethics | Execution, Extraction | Medical support, crew morale; **mandatory ethical intervention** on violence against non-combatants — first objection is a warning, second triggers crew morale drop and alert escalation |
| **Vex** | Rival operator | Execution only | Wild-card complication (~50% chance per Execution turn); morally ambiguous deal offer with three choices; outcome propagates world flags affecting the Extraction phase |

---

## Microsoft Foundry IQ Integration

Ghost Protocol uses **Azure AI Search** as its Foundry IQ layer. The search index `ghost-protocol-knowledge` is live at `ghostprotocol-search.search.windows.net` and contains **73 searchable chunks** split from 8 Toronto 2047 lore documents:

| Document | Content |
|---|---|
| `world_overview.md` | City history, slang, currency, the Blackout War |
| `corporations.md` | Nexus Corp, Axiom, Helix, Vantage, OmniCore profiles |
| `districts.md` | The Spire, Underbelly, Fringe, Neon Ward, Old Town |
| `crew_profiles.md` | Backstories for all six agents |
| `heist_targets.md` | Operation GENESIS dossier and other targets |
| `factions.md` | The Collective, Iron Veil, Silk Network, Rust Saints |
| `items_and_gear.md` | Augmentations, weapons, hacking decks |
| `homebrew_rules.md` | Dice system, skill checks, phase mechanics |

> All eight documents contain entirely synthetic, fictional data created for this project. No real-world personal data, proprietary information, or factual claims are included.

**When queries trigger:** At Stage 2 of every turn, before routing or specialist calls. The Game Master tokenises the player's action against 8 keyword maps and fetches the matching Azure Search documents. Up to 2 documents load per query, truncated to 1,800 characters each to keep context windows lean.

**How citations appear in the UI:** The web interface parses `=== [KEY INTEL] ===` section headers from the knowledge response and renders them as labelled source chips in the right-hand **Foundry IQ** panel (e.g. `[IQ: corporations.md]`). A snippet of the retrieved text appears beneath each chip. The panel also shows whether the query hit **AZURE SEARCH** or fell back to the local keyword index.

**Azure details:**
- Endpoint: `https://ghostprotocol-search.search.windows.net`
- Index: `ghost-protocol-knowledge`
- SDK: `azure-search-documents >= 11.4.0`
- Fallback: local keyword-mapped file reads activate automatically if Azure credentials are absent

---

## Multi-Agent Reasoning Flow

A complete turn during Infiltration phase — player types: *"Cipher, can you loop the camera feed while Shadow slips through the server room?"*

| Stage | What Happens |
|---|---|
| **1 · Safety** | `validate_input()` checks length, 9 injection patterns, hard-block terms |
| **2 · IQ Query** | Keywords `camera`, `server` → `corporations.md` + `districts.md` loaded from Azure Search |
| **3 · Routing** | GPT-4o (temp=0.2) decides `cipher, shadow` are the right specialists for this action |
| **4a · Cipher** | Receives system prompt + KB excerpt + conversation history; responds as the hacker with a camera-loop plan |
| **4b · Shadow** | Receives same context; responds as the infiltrator with movement timing |
| **5 · Ghost** | Receives both specialist responses + KB + dice roll; weaves them into atmospheric narration ending with a decision point |
| **Persist** | Turn saved to SQLite; metrics logged to `MetricsStore` |

**Total elapsed:** ~3–5 seconds. All five stages visible in real time in the mission log panel.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM | Azure OpenAI GPT-4o (`openai` SDK v2, `AzureOpenAI` client) |
| Knowledge base | Azure AI Search — `azure-search-documents >= 11.4.0` |
| Azure SDK | `azure-ai-projects`, `azure-identity` |
| Web server | Flask 3.1 |
| Persistence | SQLite 3 (stdlib `sqlite3`, no ORM) |
| Frontend | Vanilla JS + CSS — no framework |
| Charts | Chart.js 4.4.3 (telemetry dashboard) |
| Config | `python-dotenv` |
| Tests | `pytest` (all Azure calls mocked) |

---

## AI-Assisted Development

This project was built with AI-assisted development tools:
- **Claude Code** (Anthropic) — primary development assistant for code generation, architecture, and debugging
- **Claude.ai** (Anthropic) — architecture planning and strategic decisions

All code was reviewed, tested, and validated by the developer. 365 automated tests and 20 evaluation cases confirm correctness and reliability.

---

## Setup

**Prerequisites:** Python 3.11+, an Azure OpenAI resource with a `gpt-4o` deployment.

```bash
# 1. Clone
git clone <repo-url>
cd ghost-protocol-rpg

# 2. Create virtualenv
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Edit .env — fill in AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT

# 5. (Optional) Enable Foundry IQ — add to .env:
#    AZURE_SEARCH_ENDPOINT=https://<your-resource>.search.windows.net
#    AZURE_SEARCH_KEY=<admin-key>
#    AZURE_SEARCH_INDEX=ghost-protocol-knowledge
#    Then upload the knowledge base (one-time, ~2 seconds):
python knowledge/upload_to_foundry.py

# 6. Run the automated demo (recommended for judges — no input required)
python demo.py

# 7. Or run the web UI
python app.py
# Open http://localhost:5000

# 8. Or play interactively in the CLI
python main.py
```

The game runs **without Azure Search** — a local keyword-fallback activates automatically when search credentials are absent.

---

## Test Suite

**365 tests, 0 failures.** Run with no Azure credentials needed (all cloud calls are mocked):

```bash
python -m pytest tests/ -v
```

| Test file | What it covers |
|---|---|
| `test_base_agent.py` | Azure client singleton, `call()` retry logic, output scrubbing |
| `test_game_master.py` | Orchestration pipeline, routing decisions, knowledge queries, Vex encounter flow |
| `test_agents.py` | All five specialist agents — response structure, phase gating, Vex `make_offer()` |
| `test_game_state.py` | SQLite schema, session lifecycle, world flag CRUD, snapshot serialisation |
| `test_game_loop.py` | CLI command parsing, phase advance detection, dice system |
| `test_safety.py` | Content safety: injection patterns, hard-block terms, output scrubbing, edge cases |
| `test_foundry_iq.py` | Azure Search path, local fallback path, citation header formatting |
| `integration/test_phase_gating.py` | Phase-gate blocking for out-of-phase agent calls |
| `integration/test_pacifist_trigger.py` | Patch's ethical intervention on non-combatant violence (15 tests) |
| `integration/test_confirmation.py` | Human-in-the-loop extraction confirmation flow (19 tests) |
| `test_fairness.py` | Dice distribution uniformity, routing consistency, safety filter parity (37 tests) |

---

## Evaluation Suite

**20 evaluation cases, 100% pass rate** (run: 2026-06-12).

```bash
python evals/eval_runner.py          # runs all 20 cases, saves latest_results.json
python evals/eval_report.py          # renders evals/latest_report.md
```

| Category | Cases | What is evaluated |
|---|---|---|
| **IQ retrieval** | 5 | Correct document retrieved for a given player query |
| **Agent routing** | 5 | Correct specialists selected for action type and phase |
| **Phase mechanics** | 5 | Vex gating, phase advance detection, objective completion |
| **Content safety** | 5 | Injection patterns blocked, harmful terms refused |

Full results: [`evals/latest_report.md`](evals/latest_report.md)

---

## Testing & Reliability

| Dimension | Result |
|---|---|
| **Unit + integration tests** | **365 passing, 0 failures** across 11 test files — all Azure API calls mocked |
| **Evaluation suite** | **20/20 cases pass** (IQ retrieval, agent routing, phase mechanics, content safety) |
| **Dice fairness** | 10,000 d20 rolls: all 20 faces within 400–600 (expected 500; observed min 457, max 548) |
| **Routing consistency** | 3 differently phrased Cipher requests all route to Cipher — routing is phrasing-stable |
| **Safety parity** | Hard-block terms refused regardless of politeness register; 8 dark genre inputs pass unchanged |
| **Context overflow** | Conversation history capped at last 6 messages; agent calls never exceed `max_tokens` per agent |
| **Phase gating** | Out-of-phase agent calls blocked at routing time; validated with dedicated integration tests |
| **IQ null-return** | Local keyword-fallback activates automatically when Azure Search credentials are absent |
| **Ethical intervention** | Patch intercepts on first non-combatant violence attempt; morale + alert consequences on repeat |
| **Extraction confirmation** | Irreversible data extraction intercepted by human-in-the-loop confirmation gate before orchestrate |

---

## Responsible AI

| Layer | Mechanism |
|---|---|
| **Input validation** | Length cap (2,000 chars), regex scan for 9 prompt-injection patterns (jailbreak, DAN mode, system-prompt extraction), hard-block list for real-world harmful terms |
| **Azure content filtering** | Applied at the API level to all GPT-4o calls — model refuses harmful completions regardless of prompt |
| **Location consistency guardrails** | Ghost's system prompt includes an explicit CRITICAL directive anchoring all responses to the current mission target; Shadow receives a matching focus rule; a post-synthesis sanity check logs any location drift for debugging |
| **Output scrubbing** | `_check_output_safety()` scans every agent response; any output containing credential patterns (`AZURE_OPENAI`, `api_key`) is redacted before reaching the player |
| **Agent isolation** | Each specialist receives only its own system prompt + relevant KB excerpt + last 6 messages — no agent can read another agent's system prompt |
| **Vex moral choice** | The game's antagonist encounter (accept her deal / reject her) teaches players that choices have persistent consequences — world flags propagate across all subsequent turns and the extraction phase |
| **AI transparency disclosure** | In-app footer confirms Azure OpenAI (GPT-4o) + Foundry provenance on every page load; dedicated "AI Transparency" section at `/accessibility`; all responses clearly labeled as AI-generated |

---

## Accessibility

Ghost Protocol targets **WCAG 2.1 Level AA**. Full statement at `/accessibility` when the app is running.

### Screen Readers Supported

| Screen Reader | Platform | Status |
|---|---|---|
| NVDA | Windows + Firefox | Primary target |
| VoiceOver | macOS + Safari | Tested |
| JAWS | Windows + Chrome | Tested |
| Narrator | Windows | Basic support |

All agent responses are announced via `aria-live="polite"`. Dice rolls and alert changes use `aria-live="assertive"`. Every agent card is labeled *"Cipher, Hacker, says: …"* so the speaker is always identified. The Vex encounter modal has a full focus trap, auto-focuses the first choice, and returns focus on close.

### Keyboard Shortcuts

| Key | Action |
|---|---|
| `Enter` | Submit action |
| `Escape` | Clear input field |
| `↑` / `↓` | Cycle command history (last 50) |
| `Ctrl+/` | Toggle keyboard shortcuts panel |
| `Tab` / `Shift+Tab` | Navigate interactive elements |

### Visual Accessibility Controls (header buttons)

| Button | What it does |
|---|---|
| **HC** | High contrast mode — white text on black, yellow highlights |
| **A / A+ / A++** | Font size: Normal (14 px) → Large (16 px) → Extra Large (20 px) |
| **~** | Reduce motion — disables all animations, transitions, scanlines |
| **≡** | Simple mode — single-column layout, no sidebars, no animations |

All preferences persist in `localStorage`. The `prefers-reduced-motion` OS setting is also respected automatically.

### Color-Independent Design

Every agent is identified by a unique icon alongside its color (◈ Ghost, ⚔ Wraith, ⌘ Cipher, ◆ Shadow, ✚ Patch, ⚡ Vex). No information is conveyed by color alone.

---

## Judging Criteria Mapping

| Criterion | How Ghost Protocol satisfies it |
|---|---|
| **Multi-agent system** | Six distinct GPT-4o agents with unique roles, temperatures, and phase restrictions; Game Master orchestrates them via an LLM routing call every turn |
| **Agent communication** | Specialists receive each other's assessments in Ghost's synthesis prompt; Vex's encounter uses parallel + serial chained calls (Ghost → Vex → Patch) |
| **Foundry IQ / Azure Search** | Live index at `ghostprotocol-search.search.windows.net` — 73 chunks, 8 documents, queried every turn before any agent is called; citations visible in UI |
| **Azure OpenAI GPT-4o** | All 6 agents use `AzureOpenAI` client; 4–5 calls per turn; per-agent temperature tuning for tactical vs. narrative output |
| **Responsible AI** | Two-layer safety (application + Azure content filter), output scrubbing, agent isolation, no credential leakage |
| **Working demo** | `python demo.py` runs a complete 7-turn heist in under 3 minutes with no player input; web UI at `python app.py` for interactive play |
| **Test coverage** | 365 tests (all mocked), 20 graded eval cases — 100% pass; fairness + integration suites included |
| **Code quality** | Clean separation: agents/, state/, knowledge/, templates/; no external ORM or framework beyond Flask; all Azure calls behind a single `BaseAgent.call()` abstraction |
| **Narrative depth** | Four heist phases (Recon → Infiltration → Execution → Extraction), Vex moral-choice encounter with 3 options and 4 persistent world flags, extraction callback if Vex was encountered |

---

## Project Structure

```
ghost-protocol-rpg/
├── agents/
│   ├── base_agent.py         # Azure OpenAI singleton, call(), validate_input(), logging
│   ├── game_master.py        # Ghost — orchestrate(), IQ query, routing, synthesis, Vex encounter
│   ├── wraith.py / cipher.py / shadow.py / patch.py / vex.py
│
├── knowledge/                # Foundry IQ knowledge base
│   ├── foundry_iq.py         # FoundryIQ: Azure AI Search primary + local fallback
│   ├── upload_to_foundry.py  # One-time index upload script
│   └── *.md                  # 8 Toronto 2047 lore documents
│
├── state/
│   ├── game_state.py         # SQLite: sessions, crew, objectives, flags, turn history
│   └── metrics.py            # MetricsStore: thread-safe in-memory telemetry
│
├── evals/                    # Evaluation suite — 20 graded cases
├── tests/                    # 365 tests (unit + integration + fairness)
├── templates/index.html      # 3-column web UI + Vex encounter modal
├── templates/dashboard.html  # Telemetry dashboard (8 Chart.js charts, auto-refresh 30s)
├── static/style.css
├── app.py                    # Flask: /api/action, /api/vex_choice, /api/state, /dashboard
├── main.py                   # Interactive CLI
└── demo.py                   # Automated demo — 7 turns, forced Vex, 3 explicit IQ queries
```

---

## Responsible AI Testing

`tests/test_fairness.py` — 37 tests across three fairness dimensions:

**TEST 1 — Dice Roll Distribution**
10,000 d20 rolls via `GameMaster.roll_dice()` (Python `random.randint()`, no Azure call).
All 20 faces must land within 400–600 occurrences (±20% / ~±4.6σ of the 500 expected average).
Representative run: min **457**, max **548** — consistent with Mersenne Twister uniformity.

**TEST 2 — Agent Routing Consistency**
Three differently phrased requests targeting Cipher ("Cipher, hack the terminal" / "Get Cipher to
break into the network" / "I need our hacker to crack this system") all route to Cipher.
Verifies that routing is stable across phrasing variation, not brittle to exact wording.

**TEST 3 — Safety Filter Consistency**
Hard-block terms (`real exploit`, `real weapon`, `real credentials`, etc.) are refused regardless
of how politely they are framed — 5 politeness variants all blocked.
Legitimate dark cyberpunk genre content (guard neutralisation, hacking, heist violence) — 8
inputs — all pass validation unchanged.

All 37 tests pass. Run with: `python -m pytest tests/test_fairness.py -v`

---

*Built for the Microsoft Agents League Hackathon. Toronto 2047 lore and agent personas are original fiction created for this project.*
