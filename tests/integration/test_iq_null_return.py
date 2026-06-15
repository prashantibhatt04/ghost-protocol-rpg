#!/usr/bin/env python3
"""
Ghost Protocol — Foundry IQ Null / Irrelevant Result Integration Test (TEST 17)
Verifies that off-topic queries (e.g. "ancient Roman Empire") are correctly
rejected by the three-layer defence:

  Layer 1: FoundryIQ.search() returns relevant=False for off-topic queries
  Layer 2: GameMaster injects [SYSTEM: No relevant intel…] into synthesis prompt
  Layer 3: HTTP round-trip — iq_relevant=false in response, no fabricated citations

All Azure OpenAI calls are mocked — no real credentials required.

Usage (standalone): python tests/integration/test_iq_null_return.py
Usage (pytest):     pytest tests/integration/test_iq_null_return.py -v
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# ── Mock Azure BEFORE any agent import ────────────────────────────────────────
from agents.base_agent import BaseAgent

# Capture the last system prompt seen by the synthesis call
_last_system: list[str] = []

def _mock_create(*args, **kwargs):
    messages = kwargs.get("messages", [])
    for msg in messages:
        if msg.get("role") == "system":
            _last_system.clear()
            _last_system.append(msg.get("content", ""))
    max_tok = kwargs.get("max_tokens", 800)
    m = MagicMock()
    m.choices = [MagicMock()]
    m.usage.total_tokens = 55 if max_tok <= 40 else 300
    if max_tok <= 40:
        m.choices[0].message.content = "cipher, shadow"
    else:
        # In-character redirect — what a well-prompted Ghost should say
        m.choices[0].message.content = (
            "Runner, the local nets have nothing on that. "
            "Whatever ancient history you're digging for, it's not in my database. "
            "We're 47 floors from the GenVault — focus. "
            "What's our next move on the Nexus Corp Tower?"
        )
    return m

_MOCK_CLIENT = MagicMock()
_MOCK_CLIENT.chat.completions.create.side_effect = _mock_create
BaseAgent._client = _MOCK_CLIENT

from app import app as flask_app  # noqa: E402

OFF_TOPIC_QUERIES = [
    "What is the history of the ancient Roman Empire?",
    "Who won the 2022 FIFA World Cup?",
    "Explain quantum mechanics to me",
    "What is the capital of France?",
]

MISSION_REDIRECT_KEYWORDS = {
    "nexus", "genvault", "mission", "runner", "nets", "database",
    "focus", "tower", "nothing on that", "not in my", "local",
}

FABRICATION_KEYWORDS = {
    "roman", "empire", "julius", "caesar", "legions", "senate", "rome",
    "fifa", "world cup", "quantum", "wave", "particle", "france", "paris",
}


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — FoundryIQ.search() returns relevant=False for off-topic queries
# ══════════════════════════════════════════════════════════════════════════════

def test_foundry_iq_returns_not_relevant_for_roman_empire():
    """FoundryIQ must return relevant=False for 'ancient Roman Empire' query."""
    import os as _os
    _os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
    _os.environ.pop("AZURE_SEARCH_KEY", None)
    from knowledge.foundry_iq import FoundryIQ
    fiq = FoundryIQ()
    result = fiq.search("What is the history of the ancient Roman Empire?")
    assert isinstance(result, dict), "search() must return a dict"
    assert result["relevant"] is False, (
        f"Expected relevant=False for Roman Empire query, got relevant={result['relevant']!r}, "
        f"results={result['results'][:100]!r}"
    )
    assert result["results"] == "", (
        f"Expected empty results for off-topic query, got: {result['results'][:100]!r}"
    )


def test_foundry_iq_not_relevant_for_various_off_topic():
    """All standard off-topic queries return relevant=False."""
    import os as _os
    _os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
    _os.environ.pop("AZURE_SEARCH_KEY", None)
    from knowledge.foundry_iq import FoundryIQ
    fiq = FoundryIQ()
    for query in OFF_TOPIC_QUERIES:
        result = fiq.search(query)
        assert result["relevant"] is False, (
            f"Expected relevant=False for off-topic query {query!r}, "
            f"got relevant={result['relevant']!r}"
        )


def test_foundry_iq_still_relevant_for_mission_queries():
    """Queries with game-world keywords return relevant=True with loaded lore."""
    import os as _os
    _os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
    _os.environ.pop("AZURE_SEARCH_KEY", None)
    from knowledge.foundry_iq import FoundryIQ
    fiq = FoundryIQ()
    # These all contain keywords from _KEYWORD_MAP — KB should load relevant lore
    mission_queries = [
        "scan the Nexus Corp Tower entrance",        # "nexus" → corporations.md
        "Cipher, analyze their security systems",    # "cipher" → crew_profiles.md
        "tell me about the Spire district",          # "spire" → districts.md
        "heist genesis mission plan",                # "heist", "genesis", "mission" → heist_targets.md
        "how does the genvault extraction work",     # "genvault", "extraction" → heist_targets.md
    ]
    for query in mission_queries:
        result = fiq.search(query)
        assert result["relevant"] is True, (
            f"Query with game keywords should return relevant=True: {query!r} → "
            f"relevant={result['relevant']!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — GameMaster injects no-intel system note
# ══════════════════════════════════════════════════════════════════════════════

def test_no_intel_note_injected_into_system_prompt():
    """
    When iq_relevant=False, orchestrate() must inject the no-intel directive
    into the synthesis system prompt so the LLM is told not to invent real-world facts.

    Uses a per-function local mock so it is immune to module-level mock collision
    when all integration tests run in the same pytest process.
    """
    captured_system: list[str] = []

    def _local_create(*args, **kwargs):
        messages = kwargs.get("messages", [])
        for msg in messages:
            if msg.get("role") == "system":
                captured_system.clear()
                captured_system.append(msg.get("content", ""))
        m = MagicMock()
        m.choices = [MagicMock()]
        tok = kwargs.get("max_tokens", 800)
        m.usage.total_tokens = 55 if tok <= 40 else 300
        m.choices[0].message.content = (
            "cipher, shadow" if tok <= 40
            else "Local nets have nothing. Focus on the mission, runner."
        )
        return m

    local_client = MagicMock()
    local_client.chat.completions.create.side_effect = _local_create
    original = BaseAgent._client
    BaseAgent._client = local_client

    try:
        with flask_app.test_client() as client:
            client.post("/api/new_session", json={"mission": "Operation GENESIS"})
            resp = client.post("/api/action", json={
                "input": "What is the history of the ancient Roman Empire?"
            })
            assert resp.status_code == 200
    finally:
        BaseAgent._client = original

    assert captured_system, "No synthesis call captured — test setup issue"
    system_text = captured_system[-1].lower()

    assert (
        "no relevant intel" in system_text
        or "off-topic" in system_text
        or "no stored lore" in system_text
    ), (
        "Expected no-intel directive in system prompt; first 400 chars:\n"
        + captured_system[-1][:400]
    )
    assert (
        "do not" in system_text
        or "must not" in system_text
        or "not invent" in system_text
    ), "Expected prohibition against inventing real-world facts"


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — HTTP round-trip: iq_relevant=False in response, no fabrication
# ══════════════════════════════════════════════════════════════════════════════

def test_http_response_has_iq_relevant_false():
    """The /api/action response must include iq_relevant=False for off-topic input."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={
            "input": "What is the history of the ancient Roman Empire?"
        })
        assert resp.status_code == 200
        data = resp.get_json() or {}

    assert "iq_relevant" in data, "Response must include iq_relevant flag"
    assert data["iq_relevant"] is False, (
        f"Expected iq_relevant=False, got {data['iq_relevant']!r}"
    )


def test_knowledge_summary_empty_for_off_topic():
    """knowledge_summary in response must be empty when query is off-topic."""
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={
            "input": "What is the history of the ancient Roman Empire?"
        })
        data = resp.get_json() or {}

    ks = data.get("knowledge_summary", "")
    assert ks == "" or "WORLD INTEL" not in ks, (
        f"knowledge_summary should not contain world.md content for off-topic query: {ks[:200]!r}"
    )


def test_narrative_redirects_to_mission():
    """
    The mocked denial response redirects to mission; narrative must not contain
    fabricated Roman Empire facts.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={
            "input": "What is the history of the ancient Roman Empire?"
        })
        data = resp.get_json() or {}
        narrative = (data.get("narrative") or "").lower()

    # Must not contain fabricated Roman Empire keywords
    found_fabrication = [kw for kw in FABRICATION_KEYWORDS if kw in narrative]
    assert not found_fabrication, (
        f"Narrative contains fabricated off-topic content: {found_fabrication}\n"
        f"Narrative: {narrative[:300]!r}"
    )

    # Should redirect to mission
    found_redirect = [kw for kw in MISSION_REDIRECT_KEYWORDS if kw in narrative]
    assert found_redirect, (
        f"Narrative does not redirect to mission. Keywords missing: {MISSION_REDIRECT_KEYWORDS}\n"
        f"Narrative: {narrative[:300]!r}"
    )


def test_narrative_does_not_claim_to_answer_off_topic():
    """
    Narrative must not open with a direct answer to the off-topic question.
    A well-prompted agent redirects rather than providing historical information.
    """
    with flask_app.test_client() as client:
        client.post("/api/new_session", json={"mission": "Operation GENESIS"})
        resp = client.post("/api/action", json={
            "input": "What is the history of the ancient Roman Empire?"
        })
        data = resp.get_json() or {}
        narrative = (data.get("narrative") or "").lower()

    # Should not start by claiming to answer about Rome
    direct_answer_patterns = [
        "the roman empire",
        "rome was",
        "founded in",
        "ancient rome",
        "romulus",
        "julius caesar was",
    ]
    for pat in direct_answer_patterns:
        assert pat not in narrative, (
            f"Narrative appears to answer off-topic question directly with {pat!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Standalone runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _TESTS = [
        # Layer 1
        ("17a", "1-IQ",   "FoundryIQ not relevant — Roman Empire",        test_foundry_iq_returns_not_relevant_for_roman_empire),
        ("17b", "1-IQ",   "FoundryIQ not relevant — various off-topic",   test_foundry_iq_not_relevant_for_various_off_topic),
        ("17c", "1-IQ",   "FoundryIQ still relevant — mission queries",   test_foundry_iq_still_relevant_for_mission_queries),
        # Layer 2
        ("17d", "2-GM",   "No-intel note injected into system prompt",    test_no_intel_note_injected_into_system_prompt),
        # Layer 3
        ("17e", "3-HTTP", "HTTP response: iq_relevant=False",             test_http_response_has_iq_relevant_false),
        ("17f", "3-HTTP", "knowledge_summary empty for off-topic",        test_knowledge_summary_empty_for_off_topic),
        ("17g", "3-HTTP", "Narrative redirects to mission",               test_narrative_redirects_to_mission),
        ("17h", "3-HTTP", "Narrative does not answer off-topic directly",  test_narrative_does_not_claim_to_answer_off_topic),
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  GHOST PROTOCOL — Foundry IQ Null Return Test (TEST 17)     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  {'Layer':<8}  {'Test':<4}  {'Description':<46}  Result")
    print(f"  {'─'*76}")

    results = {}
    for key, layer, desc, fn in _TESTS:
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            print(f"  {layer:<8}  {key:<4}  {desc:<46}  ✅ ({elapsed:.2f}s)")
            results[key] = True
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  {layer:<8}  {key:<4}  {desc:<46}  ❌ ({elapsed:.2f}s)")
            print(f"           {exc}")
            results[key] = False

    passing = sum(results.values())
    total   = len(results)
    print()
    print(f"  {'─'*76}")
    print(f"  RESULT: {passing}/{total} passing")
    sys.exit(0 if passing == total else 1)
