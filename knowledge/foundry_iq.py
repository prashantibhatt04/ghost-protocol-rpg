"""
Ghost Protocol — Foundry IQ knowledge retrieval

FoundryIQ wraps Azure AI Search. When Azure Search is unavailable (missing env
vars, network error, import failure) it transparently falls back to local
keyword-matched file reading so the game works without cloud credentials.

Return contract for search():
  {"relevant": bool, "results": str, "query": str}

  relevant=False when:
    - Local path: no keyword in _KEYWORD_MAP matched the query
    - Azure path: search returned 0 results, or top score < _MIN_RELEVANCE_SCORE
  relevant=True only when actual game-lore content matched the query.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("ghost_protocol")

# Azure BM25 relevance score below this → treat as no meaningful match
_MIN_RELEVANCE_SCORE = 0.3

# ── Knowledge file map (mirrors game_master constants) ─────────────────────────

_KNOWLEDGE_DIR = Path(__file__).parent

_KNOWLEDGE_FILES = {
    "world":         "world_overview.md",
    "corporations":  "corporations.md",
    "districts":     "districts.md",
    "crew":          "crew_profiles.md",
    "heists":        "heist_targets.md",
    "factions":      "factions.md",
    "gear":          "items_and_gear.md",
    "rules":         "homebrew_rules.md",
}

_KEYWORD_MAP = {
    "world":        ["toronto", "2047", "slang", "shard", "credit", "sovereignty", "blackout war"],
    "corporations": ["nexus", "axiom", "helix", "vantage", "omnicore", "corp", "argus", "aegis", "razors", "phantom division"],
    "districts":    ["spire", "underbelly", "fringe", "docks", "neon ward", "old town", "lakeshore", "digital quarter", "char zone", "district"],
    "crew":         ["ghost", "wraith", "cipher", "shadow", "patch", "vex", "crew", "kael", "mira", "anya", "declan"],
    "heists":       ["heist", "genesis", "blind spot", "daylight", "genvault", "aegis core", "extraction", "target", "mission", "operation"],
    "factions":     ["collective", "iron veil", "silk network", "rust saints", "phantom circuit", "faction", "weaver", "architect"],
    "gear":         ["gear", "weapon", "augment", "chrome", "implant", "shard", "grenade", "deck", "intrusion", "kit"],
    "rules":        ["check", "dice", "roll", "phase", "skill", "combat", "difficulty", "success", "fail", "routine"],
}

_EXCERPT_LIMIT = 1800


class FoundryIQ:
    """
    Knowledge retrieval backed by Azure AI Search (Foundry IQ).
    Falls back to local file reading when Azure Search is unavailable.
    """

    def __init__(self):
        self._client = None
        self._available = False
        self._index = os.getenv("AZURE_SEARCH_INDEX", "ghost-protocol-knowledge")
        self._try_connect()

    def _try_connect(self) -> None:
        """Attempt to initialise the Azure Search client. Silently swallows all errors."""
        endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        key      = os.getenv("AZURE_SEARCH_KEY", "")
        if not endpoint or not key:
            logger.debug("FoundryIQ: no Azure Search credentials — using local fallback")
            return
        try:
            from azure.search.documents import SearchClient
            from azure.core.credentials import AzureKeyCredential
            self._client = SearchClient(
                endpoint=endpoint,
                index_name=self._index,
                credential=AzureKeyCredential(key),
            )
            self._available = True
            logger.info("FoundryIQ: connected to Azure AI Search index '%s'", self._index)
        except Exception as exc:
            logger.warning("FoundryIQ: Azure Search unavailable (%s) — using local fallback", exc)

    # ── Public API ──────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> dict:
        """
        Return relevant knowledge excerpts for *query*.

        Tries Azure AI Search first; falls back to local file reading on any failure.

        Returns:
            {
                "relevant": bool  — True only when game-lore content matched the query,
                "results":  str   — formatted intel excerpts (empty string when not relevant),
                "query":    str   — the original query string,
            }
        """
        logger.debug("FoundryIQ.search: query='%s' top_k=%d azure=%s", query[:60], top_k, self._available)

        if self._available:
            try:
                result = self._azure_search(query, top_k)
                logger.info(
                    "FoundryIQ: Azure Search relevant=%s, %d chars for '%s'",
                    result["relevant"], len(result["results"]), query[:40],
                )
                return result
            except Exception as exc:
                logger.warning("FoundryIQ: Azure Search error (%s) — falling back to local", exc)

        return self._local_fallback(query, max_files=top_k)

    # ── Azure Search path ───────────────────────────────────────────────────────

    def _azure_search(self, query: str, top_k: int) -> dict:
        """Query Azure AI Search and format results as intel excerpts."""
        raw_results = list(
            self._client.search(
                search_text=query,
                top=top_k,
                select=["key", "title", "section", "content"],
            )
        )

        if not raw_results:
            logger.debug("FoundryIQ: Azure returned 0 results — no relevant intel")
            return {"relevant": False, "results": "", "query": query}

        # Check relevance score of the top result
        top_score = float(raw_results[0].get("@search.score", 1.0))
        if top_score < _MIN_RELEVANCE_SCORE:
            logger.debug(
                "FoundryIQ: top Azure score %.3f below threshold %.3f — not relevant",
                top_score, _MIN_RELEVANCE_SCORE,
            )
            return {"relevant": False, "results": "", "query": query}

        # Group by key so each source file appears as one headed block
        seen_keys: dict[str, list[str]] = {}
        for doc in raw_results:
            k = doc.get("key", "world")
            excerpt = doc.get("content", "")[:_EXCERPT_LIMIT]
            seen_keys.setdefault(k, []).append(excerpt)

        parts = []
        for k, excerpts in seen_keys.items():
            header = f"=== [{k.upper()} INTEL] ==="
            body   = "\n\n".join(excerpts)
            parts.append(f"{header}\n{body}")
            logger.debug("FoundryIQ: loaded key=%s (%d chars)", k, len(body))

        text = "\n\n".join(parts) if parts else ""
        return {"relevant": bool(text), "results": text, "query": query}

    # ── Local fallback ──────────────────────────────────────────────────────────

    def _local_fallback(self, query: str, max_files: int = 2) -> dict:
        """Keyword-matched local file reading."""
        query_lower = query.lower()

        matched = []
        for key, keywords in _KEYWORD_MAP.items():
            if any(kw in query_lower for kw in keywords):
                matched.append(key)

        if not matched:
            # No game-lore keywords found — this query is off-topic
            logger.debug("FoundryIQ local: no keyword match for '%s' — not relevant", query[:60])
            return {"relevant": False, "results": "", "query": query}

        # Deduplicate preserving order; cap at max_files
        seen: set = set()
        unique = [f for f in matched if not (f in seen or seen.add(f))][:max_files]

        parts = []
        for key in unique:
            file_path = _KNOWLEDGE_DIR / _KNOWLEDGE_FILES[key]
            try:
                content = file_path.read_text(encoding="utf-8")
                excerpt = content[:_EXCERPT_LIMIT]
                parts.append(f"=== [{key.upper()} INTEL] ===\n{excerpt}")
                logger.debug("FoundryIQ local: loaded %s (%d → %d chars)", key, len(content), len(excerpt))
            except FileNotFoundError:
                logger.warning("FoundryIQ local: file missing: %s", file_path)

        text = "\n\n".join(parts)
        return {"relevant": bool(text), "results": text, "query": query}
