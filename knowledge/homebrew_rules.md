# Ghost Protocol — Homebrew Rules

## System Overview

Ghost Protocol uses a streamlined d20-based resolution system designed for fast play in a text-based format. Every significant action is resolved with a skill check, modified by crew capabilities, augmentation, and environmental conditions.

---

## Core Resolution

### The Skill Check
When a crew member attempts a significant action, the Game Master (Ghost) calls for a skill check.

**Base Roll:** d20 + relevant modifier
**Target Number (TN):** Set by Ghost based on difficulty

| Difficulty | Target Number | Example |
|-----------|--------------|---------|
| Routine | 8 | Picking a basic lock |
| Challenging | 12 | Bypassing standard corporate security |
| Hard | 15 | Hacking a mid-tier system under time pressure |
| Extreme | 18 | Infiltrating an air-gapped military system |
| Near-Impossible | 22 | Breaking AEGIS in real-time during active alert |

**Outcome:**
- **Beat TN by 5+:** Critical Success — full outcome + bonus
- **Meet or beat TN:** Success
- **Miss TN by 1-4:** Partial Success — achieve objective, but with complication
- **Miss TN by 5-9:** Failure — objective not achieved; no new complications
- **Miss TN by 10+:** Critical Failure — objective not achieved; complication introduced

---

## Agent Skill Modifiers

Each crew member has defined skill modifiers that apply to relevant checks. These are baked into each agent's profile and automatically applied by Ghost.

| Crew Member | Primary Skills | Modifier |
|-------------|---------------|---------|
| Wraith | Combat, Security Assessment, Tactical Movement | +4 |
| Cipher | Hacking, Digital Intrusion, Counter-Surveillance | +5 |
| Shadow | Physical Infiltration, Stealth, Lockpicking | +4 |
| Patch | Medicine, Negotiation, Corporate Knowledge | +3 |
| All crew | General awareness, basic combat | +1 |

### Augmentation Bonuses
Specific augmentations add to relevant checks (already reflected in agent modifiers above for standard gear). Additional or upgraded augmentation can stack:
- **Standard augment bonus:** +1 to relevant check category
- **Military-grade augment:** +2 to relevant category
- **Apex-grade augment:** +3 to specific function

---

## Heist Phases

Every heist proceeds through four phases. Different crew members take point in different phases.

### Phase 1: Recon
**Lead Agents:** Shadow (physical scout), Cipher (digital mapping), Ghost (intelligence synthesis)
**Objective:** Gather information on the target; identify entry vectors, security schedules, and vulnerabilities
**Checks:** Typically Stealth, Hacking, Observation
**Outcome:** Generates a mission brief that reduces check difficulty in subsequent phases (preparation pays off)

Thorough Recon reduces all subsequent check TNs by 2. Incomplete Recon means the crew goes in blind on at least one key variable.

### Phase 2: Infiltration
**Lead Agents:** Shadow (physical entry), Cipher (digital entry), Wraith (security clearance)
**Objective:** Enter the target facility without triggering alert
**Checks:** Stealth, Lockpicking/Bypass, Hacking
**Alert States:**

| State | Trigger | Effect |
|-------|---------|--------|
| Cold | No alert | Standard TNs |
| Warm | Minor anomaly detected | +2 to all TNs; increased patrol frequency |
| Hot | Confirmed intruder | +4 to all TNs; response team dispatched |
| Scorched | Full lockdown | Escape-only; extraction becomes primary objective |

Going from Cold to Hot or Scorched skips Warm — major detections escalate immediately.

### Phase 3: Execution
**Lead Agents:** Mission-dependent; typically Cipher (data extraction), Shadow (physical objective)
**Objective:** Achieve the primary mission objective
**Checks:** Hacking, Physical manipulation, Time pressure
**Vex Complication:** Vex always appears during Execution phase. Ghost determines their role based on the mission context. Vex's appearance may:
- Compete for the same objective (forces player choice)
- Create a distraction that opens an opportunity
- Provide unexpected assistance at an unknown cost
- Reveal information that changes the crew's understanding of the mission

### Phase 4: Extraction
**Lead Agents:** Wraith (security neutralization), Ghost (route guidance), Patch (crew stabilization)
**Objective:** Exit the target facility with crew and objective intact
**Checks:** Combat (if contested), Stealth (if covert), Navigation
**Pursuit Rules:** If the crew exits on Hot or Scorched alert, a pursuit check is required. Wraith leads; failure means an additional encounter before safe extraction.

---

## Combat

Combat in Ghost Protocol is fast and consequential. The crew are not soldiers — sustained firefights are dangerous and to be avoided.

### Combat Round
Each round, each participant takes one action and one move. Order is determined by Reflex check (d20 + reflex modifier) — highest goes first.

**Actions:**
- Attack (roll to hit vs. target TN; damage on success)
- Use equipment or augmentation
- Hack a nearby system
- Administer medical care

**Cover:** Taking cover reduces incoming damage by 2. Full cover prevents damage entirely but limits actions.

### Injury System
Crew members have three health states. No hit points — health is a narrative condition.

| State | Condition | Mechanical Effect |
|-------|-----------|-----------------|
| Operational | Uninjured or minor wounds | No penalty |
| Wounded | Significant injury; bleeding, impaired augmentation | -2 to all checks |
| Critical | Severe injury; can't act independently | Requires immediate stabilization; mission must extract |

Dropping to Critical: requires Patch to roll Medicine TN 14 within 2 rounds or the crew member is lost.

**Augmentation Damage:** Targeted attacks on augmentations can disable them. Cipher's intrusion deck, Shadow's camouflage, or Wraith's targeting overlay can be targeted specifically.

---

## Dice and Probability

### The Complication Die
Ghost rolls a hidden d6 at the start of each phase. On a 1, a complication is introduced during that phase. Complications are independent of skill check results — they represent the world acting on the crew.

**Complication Examples:**
- A guard breaks schedule
- A system patch was applied since Recon
- A third party is present (Vex, Phantom Division, another crew)
- Environmental: power fluctuation, fire alarm, structural issue
- Social: a civilian witnesses something they shouldn't

### The Vex Die
In Execution phase only, Ghost also rolls a d6 for Vex. On 4-6, Vex appears. On 1-3, Vex is nearby but not directly involved this phase (may surface in Extraction).

---

## Knowledge Base Queries

Ghost (the orchestrator agent) consults the knowledge base at defined moments during play. The player can also explicitly request a knowledge check.

### Automatic Query Triggers
1. **Target identification** — Ghost queries corporations.md and heist_targets.md
2. **District navigation** — Ghost queries districts.md
3. **NPC encounter** — Ghost queries factions.md and crew_profiles.md
4. **Equipment request** — Ghost queries items_and_gear.md
5. **Complication resolution** — Ghost queries world_overview.md for context

### Player-Initiated Queries
The player can ask Ghost: *"What do we know about [X]?"* — Ghost will answer from the knowledge base with in-world framing. This represents the crew's collective intelligence.

---

## Experience and Advancement

After each successful heist, the crew gains Reputation and resources. Reputation determines:
- Quality of contracts available (higher rep = higher payout targets)
- NPC faction attitudes (Collective, Iron Veil, Silk Network relationships improve with rep)
- Vex's behavior (higher rep draws more attention and more ambiguous assistance)

Individual crew members can upgrade their augmentation between missions using shard payouts. Upgrades are reflected in modified skill bonuses.

---

## Responsible AI Guardrails (In-World)

Ghost operates under a set of explicit parameters that limit the types of actions the crew will take. These are not just ethical guidelines — they are Ghost's operational constraints, justified in-world as sound operational philosophy.

1. **No civilian casualties** — Ghost will not plan operations that predictably harm non-combatants; any crew action that threatens this triggers Ghost to revise the plan
2. **No escalation past necessary force** — Ghost recommends the minimum-violence approach; Wraith enforces this in execution
3. **Content filtering** — Ghost screens all incoming mission briefs for operations that constitute crimes against humanity (torture, genocide, mass harm); declines these regardless of payout
4. **Informed consent for crew risk** — Ghost provides the crew with a realistic risk assessment before each operation; will not downplay lethality to get crew buy-in

If a player input suggests an action that violates these parameters, Ghost (the GM agent) will acknowledge the input, explain in-world why the crew won't take that approach, and offer an alternative.
