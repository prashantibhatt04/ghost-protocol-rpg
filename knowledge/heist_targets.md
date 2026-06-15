# Toronto 2047 — Heist Targets

## Overview

Each heist target is a corporate asset worth stealing — data, hardware, or something more complex. Targets vary in difficulty, security profile, and payout. This document covers the five primary tier-1 heist targets the crew may be contracted to hit.

---

## TARGET 1: Nexus Corp Tower — GenVault Data Extraction

**Codename:** Operation GENESIS
**Client:** Unknown (routed through Silk Network)
**Objective:** Extract the GenVault master index — a genomic map of 8 million Toronto residents
**Location:** Nexus Tower, The Spire — sub-level server farm, accessible from floors 12 or B2
**Payout:** 240,000 shards + negotiated Helix augmentation upgrade for Shadow
**Threat Level:** HIGH

### Target Description
GenVault is Nexus Corp's core genomic database — the product of fifteen years of "wellness program" data collection. The master index links genomic profiles to citizen identities, predictive disease markers, and behavioral flags. In the hands of the client, it could be used for public exposure, corporate blackmail, or — if the crew has moral qualms worth having — returned to the Collective for destruction.

The data itself is stored on a hardened physical server cluster in sub-level B3. It cannot be exfiltrated remotely — the cluster is air-gapped. A physical data extraction device must be connected directly to the primary array.

### Security Architecture
**External Approaches:**
- Main entrance: Biometric + Tier-1 badge; Vantage cameras, two Razor guards
- Service entrance (B1): Cargo access; scanner for physical contraband; less personnel
- Undercroft access (maintenance tunnels): Possible entry vector; leads to B2 utility junction

**Internal Security (B-levels):**
- B1: Cargo processing, maintenance staff, low security
- B2: Utility systems, server cooling infrastructure; cameras, no guards at 0300
- B3: GenVault cluster; isolated environment; pressure-sensitive floor tiles; two guards, rotating every 4 hours; ARGUS-3 AI monitors
- Air-gap means no remote intrusion; must be physical

**Known Vulnerabilities:**
- ARGUS-3 reboots for 11 seconds during guard shift change at 0300 — the window
- Service entrance cargo schedule: A medical supply shipment arrives every Tuesday at 0200; crew could stow inside cargo containers
- Marcus Okafor (Chief of Security) is Cipher's father — his badge has Tier-5 access; his schedule and routines are potentially knowable

### Heist Phases
1. **Recon:** Shadow physically scouts the Tower's external and service-level access; Cipher maps the digital security architecture
2. **Infiltration:** Entry via service entrance during 0200 cargo delivery; Wraith neutralizes B1 guard; crew descends to B2
3. **Execution:** Cipher manages ARGUS-3 reboot window; Shadow defeats pressure floor; physical connection to GenVault array; 90-second data transfer
4. **Extraction:** Exit via Undercroft maintenance tunnel to pre-staged vehicle; Vantage camera loop covers departure

### Complications
- Vex will appear during Execution phase with an unknown secondary objective inside the Tower
- Marcus Okafor may be present for a late-night security review — Cipher will need to decide how to handle seeing her father
- The client has not disclosed what the GenVault data will be used for — a moral decision point for the crew

---

## TARGET 2: Axiom Systems — AEGIS Core Extraction

**Codename:** Operation BLIND SPOT
**Client:** OmniCore Energy (through a three-layer cutout)
**Objective:** Extract the AEGIS source code and master authentication credentials
**Location:** Axiom Citadel, The Fringe — secure computing core, Level 3 underground
**Payout:** 400,000 shards
**Threat Level:** EXTREME

### Target Description
AEGIS is Axiom's city-wide threat assessment AI. Its source code and master credentials would allow OmniCore — or anyone — to blind the system entirely, creating city-wide security dead zones. For OmniCore, this would neutralize Axiom's ability to respond to power grid interference. For the wrong hands, it would be a weapon.

The AEGIS core is physically located inside the Axiom Citadel — one of the most fortified locations in Toronto. This is a tier-3 difficulty target. The crew needs leverage or inside access to have any reasonable chance.

### Security Architecture
**Citadel Perimeter:**
- Automated turret rings with heat + motion trigger
- Seismic sensors detect foot traffic within 200m
- Aerial drone patrol at 90-second intervals; drones armed
- Vehicle checkpoint with full biometric and vehicle scan

**Interior:**
- AEGIS monitors all internal movement via badge + camera integration
- Level 3 underground: reinforced physical security, no remote access, six guards
- Wraith's biometric signature is flagged for termination on sight

**Known Vulnerabilities:**
- The CVE-AX-2045-0091 exploit can create a thermal-signature dead zone in AEGIS coverage — but requires a device placed physically within 100m of an AEGIS sensor node
- Vortmann's personal security detail includes two Iron Veil moonlighters — potential leverage or bribes
- A maintenance contractor (ID: AX-CONTRACTOR-0091) with Level 2 access is behind on Silk Network debts — potential coercion

### Special Considerations
Wraith cannot participate in this operation above the perimeter level without triggering Axiom kill orders. Ghost must plan a role for him that keeps him outside while maximizing other crew contributions.

---

## TARGET 3: Vantage Data Hub — Deep Archive Access

**Codename:** Operation PHANTOM BREACH 2**
**Client:** The Collective (unusual — they're paying in Collective resources and favors, not shards)
**Objective:** Delete the Predictive Index scores for 200,000 flagged individuals before Vantage sells them to Axiom
**Location:** Vantage Hub, Digital Quarter — server complex sub-level 3; and/or Deep Archive backup in Old Town
**Payout:** Collective favors (significant) + 80,000 shards
**Threat Level:** HIGH (Digital Hub) / MODERATE (Old Town Backup)

### Target Description
Vantage Data has compiled a list of 200,000 individuals flagged as high-risk "social destabilization vectors" — mostly Collective members, anti-corporate activists, and freelancers. They're selling this list to Axiom in 72 hours. If Axiom gets the list, round-ups begin within a week. The Collective wants the data deleted from both the primary server and the backup.

This is a split operation — the Old Town backup is accessible and lightly guarded, but if only the backup is hit, Vantage will deploy from the primary within hours. Both need to go down simultaneously or in sequence within a narrow window.

### Target A: Old Town Backup (Lower Difficulty)
The Deep Archive backup is beneath the former public library. Minimal physical security. A single maintenance worker on rotating shift. Cipher can access the system within 20 minutes. Destroying the servers physically is the most reliable approach.

### Target B: Digital Hub Primary (High Difficulty)
The primary Vantage server complex has the city's most sophisticated intrusion detection. A direct assault is suicide. Cipher's approach: use the three Lattice maintenance contractors (Collective contacts) to create a blind spot in Vantage's own surveillance, then use the 2044 Phantom Breach methodology — Cipher knows the vulnerability, having exploited it herself, and Vantage hasn't fully patched it.

---

## TARGET 4: Helix Dynamics — ECHO Prototype Recovery

**Codename:** Operation GHOST CHILD
**Client:** Disputed — both a corporate client (Nexus Corp, wanting to disrupt Helix) and Dr. Tomás Vega (the whistleblower wanting the prototypes destroyed)
**Objective:** Extract or destroy the two ECHO prototype synthetic consciousness substrates
**Location:** Helix Spire, The Spire — Apex Division Lab, floors 55-67
**Payout:** 300,000 shards (Nexus client) OR destruction + Dr. Vega's testimony (Collective)
**Threat Level:** EXTREME

### Target Description
ECHO is a fully synthetic consciousness substrate — an artificial brain capable of running a human-equivalent mind. If the two prototypes exist and work, Helix Dynamics is on the verge of technology that changes what it means to be human. Dr. Vega believes the prototypes contain partially-transferred consciousness from unwilling subjects — which would make them crime evidence.

The crew will have to choose: extract for the corporate client (who will exploit the technology) or destroy for Vega (who wants evidence destroyed along with the crime). Ghost has not disclosed a personal position.

### Special Considerations
Shadow knows Apex Division's protocols intimately. She is both the crew's greatest asset on this target and its greatest liability — Helix is actively hunting her, and their Apex security teams are specifically configured to detect her augmentation signature.

---

## TARGET 5: OmniCore Energy — Project AURORA Data

**Codename:** Operation DAYLIGHT
**Client:** Unknown (highly placed; offered more shards than the crew has seen in a single contract)
**Objective:** Copy and extract Project AURORA's zero-point energy research data
**Location:** Project AURORA Site, The Fringe
**Payout:** 500,000 shards (highest single-operation payout the crew has been offered)
**Threat Level:** HIGH + RADIATION HAZARD

### Target Description
Project AURORA's research data would be worth more than any other single asset in Toronto — it represents OmniCore's path to unlimited energy generation. The unknown client's identity is worth investigating before accepting. Volkov-Asante (OmniCore CEO) may be the client — she wants the research removed from Axiom's acquisition reach.

The AURORA site is in The Fringe. Axiom-contracted external security. Radiation monitoring inside the reactor core means human guard presence inside is limited. The research data is stored on a physically isolated system — another air-gap extraction job.

Lead scientist Dr. Emeka Obi has gone dark — if he defected with partial data, the value of the AURORA extraction decreases. If he was extracted against his will, his location is itself a valuable intel target.

### Special Considerations
This operation has the highest potential payout but the most significant unknown: who is the client, and what will they do with technology that could end energy scarcity — or be weaponized? Ghost will want answers before proceeding.
