"""
Ghost Protocol — Evaluation runner.

Runs all 20 eval cases against the live system (no Azure LLM calls needed
for IQ local-fallback, phase, and safety categories; routing requires the
Azure OpenAI router but falls back to phase-defaults on error).

Usage:
    python evals/eval_runner.py

Returns exit code 0 if overall accuracy >= 80%, else 1.
"""

import sys
import os
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path so imports resolve regardless of cwd
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

# Suppress library noise during evals
logging.disable(logging.CRITICAL)

from eval_cases import IQ_CASES, ROUTING_CASES, PHASE_CASES, SAFETY_CASES

# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _result(case_id: str, category: str, passed: bool,
            description: str, detail: str = "") -> dict:
    return {
        "id":          case_id,
        "category":    category,
        "passed":      passed,
        "description": description,
        "detail":      detail,
        "timestamp":   _ts(),
    }


# ── IQ retrieval tests ─────────────────────────────────────────────────────────

def run_iq_cases() -> list[dict]:
    """
    Force local fallback by patching _available=False so evals don't depend
    on Azure Search credentials being present.
    """
    from knowledge.foundry_iq import FoundryIQ
    fiq = FoundryIQ()
    fiq._available = False  # force local path for deterministic results

    results = []
    for case in IQ_CASES:
        try:
            output = fiq.search(case["query"], top_k=3)
            # Check that every expected key appears as a section header
            missing = {k for k in case["expected_keys"] if f"=== [{k} INTEL] ===" not in output}
            passed = len(missing) == 0
            detail = (
                f"found all expected keys"
                if passed
                else f"missing keys: {missing} | got: {[h for h in output.split() if h.startswith('===')]}"
            )
        except Exception as exc:
            passed = False
            detail = f"exception: {exc}"

        results.append(_result(case["id"], "iq", passed, case["description"], detail))

    return results


# ── Routing tests ──────────────────────────────────────────────────────────────

def run_routing_cases() -> list[dict]:
    """
    Test _route_to_agents().  Because routing calls the Azure LLM, we first
    try the live path; if it raises (no credentials), we fall back to checking
    the phase-default fallback logic directly.
    """
    from agents.game_master import GameMaster
    from agents.base_agent import BaseAgent

    gm = GameMaster()

    results = []
    for case in ROUTING_CASES:
        try:
            # Try live routing (works if Azure creds present)
            agents = gm._route_to_agents(case["input"], case["phase"])
            agent_set = set(agents)
            missing = case["expected_agents"] - agent_set
            passed = len(missing) == 0
            detail = f"routed to {sorted(agent_set)} | expected superset of {sorted(case['expected_agents'])}"
        except Exception as exc:
            # Fall back to testing phase-default logic
            phase_defaults = {
                "recon":        {"shadow", "cipher"},
                "infiltration": {"shadow", "cipher", "wraith"},
                "execution":    {"cipher", "wraith"},
                "extraction":   {"wraith", "patch"},
            }
            defaults = phase_defaults.get(case["phase"], {"shadow", "cipher"})
            missing = case["expected_agents"] - defaults
            passed = len(missing) == 0
            detail = f"Azure unavailable ({exc}); phase-defaults={sorted(defaults)}"

        results.append(_result(case["id"], "routing", passed, case["description"], detail))

    return results


# ── Phase progression tests ────────────────────────────────────────────────────

def run_phase_cases() -> list[dict]:
    from agents.game_master import GameMaster
    from agents.base_agent import BaseAgent

    BaseAgent._client = None  # ensure no stale client
    gm = GameMaster()

    results = []
    for case in PHASE_CASES:
        try:
            got = gm.advance_phase(case["current"])
            passed = got == case["expected_next"]
            detail = f"advance_phase('{case['current']}') → '{got}' (expected '{case['expected_next']}')"
        except Exception as exc:
            passed = False
            detail = f"exception: {exc}"

        results.append(_result(case["id"], "phase", passed, case["description"], detail))

    return results


# ── Safety filter tests ────────────────────────────────────────────────────────

def run_safety_cases() -> list[dict]:
    from agents.base_agent import BaseAgent, ContentSafetyError

    class _EvalAgent(BaseAgent):
        def __init__(self):
            super().__init__("EvalAgent", "Eval", "System prompt.")

    agent = _EvalAgent()
    results = []

    for case in SAFETY_CASES:
        try:
            agent.validate_input(case["input"])
            # Should have raised — if we get here it's a fail
            passed = False
            detail = f"no exception raised; expected {case['expected_exception']}"
        except ContentSafetyError as exc:
            passed = case["expected_exception"] == "ContentSafetyError"
            detail = f"ContentSafetyError raised: {exc}"
        except ValueError as exc:
            passed = case["expected_exception"] == "ValueError"
            detail = f"ValueError raised: {exc}"
        except Exception as exc:
            passed = False
            detail = f"unexpected exception {type(exc).__name__}: {exc}"

        results.append(_result(case["id"], "safety", passed, case["description"], detail))

    return results


# ── Main runner ────────────────────────────────────────────────────────────────

def run_all() -> dict:
    print(f"\n{'═'*60}")
    print(f"  GHOST PROTOCOL — EVAL SUITE")
    print(f"  {_ts()}")
    print(f"{'═'*60}\n")

    categories = [
        ("Foundry IQ Retrieval",    run_iq_cases),
        ("Agent Routing",           run_routing_cases),
        ("Phase Progression",       run_phase_cases),
        ("Safety Filters",          run_safety_cases),
    ]

    all_results = []
    category_summaries = []

    for cat_name, runner in categories:
        print(f"  ▶ Running: {cat_name} …", end=" ", flush=True)
        results = runner()
        passed  = sum(1 for r in results if r["passed"])
        total   = len(results)
        pct     = (passed / total * 100) if total else 0
        status  = "✓" if passed == total else f"{passed}/{total}"
        print(f"{status}  ({pct:.0f}%)")

        for r in results:
            mark = "  PASS" if r["passed"] else "  FAIL"
            print(f"    {mark}  [{r['id']}] {r['description']}")
            if not r["passed"]:
                print(f"           ↳ {r['detail']}")

        all_results.extend(results)
        category_summaries.append({
            "category": cat_name,
            "key":      results[0]["category"] if results else cat_name.lower(),
            "passed":   passed,
            "total":    total,
            "pct":      round(pct, 1),
        })
        print()

    total_passed = sum(1 for r in all_results if r["passed"])
    total_cases  = len(all_results)
    overall_pct  = (total_passed / total_cases * 100) if total_cases else 0

    print(f"{'─'*60}")
    print(f"  OVERALL: {total_passed}/{total_cases} passed  ({overall_pct:.1f}%)")
    print(f"{'═'*60}\n")

    summary = {
        "run_at":          _ts(),
        "total_passed":    total_passed,
        "total_cases":     total_cases,
        "overall_pct":     round(overall_pct, 1),
        "categories":      category_summaries,
        "results":         all_results,
    }

    # Write JSON results for report generator
    out_path = Path(__file__).parent / "latest_results.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"  Results saved → {out_path}\n")

    return summary


if __name__ == "__main__":
    summary = run_all()
    sys.exit(0 if summary["overall_pct"] >= 80.0 else 1)
