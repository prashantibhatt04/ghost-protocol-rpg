"""
Tests for knowledge/foundry_iq.py

Covers: Azure Search path (mocked), local fallback, resilience, and
GameMaster.query_knowledge() delegation.
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_search_doc(key: str, content: str) -> dict:
    """Minimal Azure Search result document."""
    return {
        "id":          f"{key}_0",
        "key":         key,
        "title":       key.upper(),
        "section":     "Overview",
        "content":     content,
        "source_file": f"{key}.md",
    }


def _foundry_without_azure():
    """FoundryIQ instance with no env vars — uses local fallback."""
    from knowledge.foundry_iq import FoundryIQ
    with patch.dict("os.environ", {}, clear=False):
        # Ensure search vars are absent
        import os
        os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
        os.environ.pop("AZURE_SEARCH_KEY", None)
        return FoundryIQ()


def _foundry_with_mock_azure(mock_client: MagicMock):
    """FoundryIQ instance whose _client is replaced with a MagicMock."""
    from knowledge.foundry_iq import FoundryIQ
    fiq = FoundryIQ.__new__(FoundryIQ)
    fiq._index = "ghost-protocol-knowledge"
    fiq._client = mock_client
    fiq._available = True
    return fiq


# ── Availability detection ─────────────────────────────────────────────────────

class TestFoundryIQAvailability:

    def test_unavailable_when_no_env_vars(self):
        """FoundryIQ marks itself unavailable when Azure Search credentials are absent."""
        fiq = _foundry_without_azure()
        assert fiq._available is False

    def test_unavailable_when_only_endpoint_set(self):
        """Both ENDPOINT and KEY must be present; one alone is not enough."""
        from knowledge.foundry_iq import FoundryIQ
        with patch.dict("os.environ", {"AZURE_SEARCH_ENDPOINT": "https://x.search.windows.net"}):
            import os
            os.environ.pop("AZURE_SEARCH_KEY", None)
            fiq = FoundryIQ()
        assert fiq._available is False

    def test_available_when_credentials_present_and_import_succeeds(self):
        """FoundryIQ._available is True when credentials are set and SearchClient constructs."""
        from knowledge.foundry_iq import FoundryIQ
        fake_client = MagicMock()
        with patch.dict("os.environ", {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_KEY":      "fake-key",
        }):
            # SearchClient is imported inside _try_connect; patch the original source.
            with patch("azure.search.documents.SearchClient", return_value=fake_client):
                fiq = FoundryIQ()
        assert fiq._available is True

    def test_unavailable_when_search_client_raises_on_init(self):
        """FoundryIQ degrades gracefully if SearchClient constructor raises."""
        from knowledge.foundry_iq import FoundryIQ
        with patch.dict("os.environ", {
            "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
            "AZURE_SEARCH_KEY":      "fake-key",
        }):
            with patch("azure.search.documents.SearchClient", side_effect=Exception("conn error")):
                fiq = FoundryIQ()
        assert fiq._available is False


# ── Local fallback ─────────────────────────────────────────────────────────────

class TestLocalFallback:

    def test_returns_dict_with_required_keys(self):
        """_local_fallback() always returns a dict with relevant, results, query."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("nexus corp tower")
        assert isinstance(result, dict)
        assert {"relevant", "results", "query"}.issubset(result.keys())

    def test_relevant_true_for_known_query(self):
        """A keyword-matching query returns relevant=True with non-empty results."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("nexus corp tower")
        assert result["relevant"] is True
        assert len(result["results"]) > 0

    def test_not_relevant_for_unknown_query(self):
        """Unrecognised queries return relevant=False with empty results (no world fallback)."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("xyzzy frobble quux")
        assert result["relevant"] is False
        assert result["results"] == ""

    def test_off_topic_real_world_query_not_relevant(self):
        """A real-world off-topic query returns relevant=False."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("What is the history of the ancient Roman Empire?")
        assert result["relevant"] is False

    @pytest.mark.parametrize("query,expected_header", [
        ("nexus corp axiom",                "CORPORATIONS INTEL"),
        ("toronto 2047 blackout war",       "WORLD INTEL"),
        ("spire district fringe",           "DISTRICTS INTEL"),
        ("ghost wraith cipher crew",        "CREW INTEL"),
        ("heist genesis mission target",    "HEISTS INTEL"),
        ("collective faction iron veil",    "FACTIONS INTEL"),
        ("augment gear weapon implant",     "GEAR INTEL"),
        ("dice roll check skill",           "RULES INTEL"),
    ])
    def test_loads_correct_file_by_keyword(self, query, expected_header):
        """Each domain keyword set maps to the correct intel header in results."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback(query)
        assert result["relevant"] is True
        assert f"=== [{expected_header}] ===" in result["results"]

    def test_respects_max_files_cap(self):
        """max_files=1 produces exactly one === [...] === header in results."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("nexus corp district toronto", max_files=1)
        assert result["relevant"] is True
        assert result["results"].count("=== [") == 1

    def test_excerpt_capped_at_1800_chars(self):
        """Each excerpt body is at most 1800 characters."""
        fiq = _foundry_without_azure()
        result = fiq._local_fallback("dice roll rules")
        assert result["relevant"] is True
        lines = result["results"].split("\n", 1)
        body = lines[1] if len(lines) > 1 else lines[0]
        assert len(body) <= 1800 + 50  # small tolerance for header


# ── Azure Search path ──────────────────────────────────────────────────────────

class TestAzureSearchPath:

    def test_calls_azure_client_search(self):
        """search() delegates to self._client.search when _available is True."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            _make_search_doc("world", "Toronto in 2047 is a city of contrasts.")
        ]
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("toronto 2047")
        mock_client.search.assert_called_once()
        assert result["relevant"] is True
        assert "WORLD INTEL" in result["results"]

    def test_azure_result_formats_as_intel_header(self):
        """Azure Search docs are formatted with === [KEY INTEL] === headers."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            _make_search_doc("corporations", "Nexus Corp towers over the Spire.")
        ]
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("nexus corp")
        assert result["relevant"] is True
        assert "=== [CORPORATIONS INTEL] ===" in result["results"]
        assert "Nexus Corp towers over the Spire." in result["results"]

    def test_multiple_results_from_same_key_merged(self):
        """Multiple docs with the same key appear under one header."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            _make_search_doc("factions", "The Iron Veil controls the Underbelly."),
            _make_search_doc("factions", "The Silk Network trades in information."),
        ]
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("factions")
        assert result["relevant"] is True
        assert result["results"].count("=== [FACTIONS INTEL] ===") == 1
        assert "Iron Veil" in result["results"]
        assert "Silk Network" in result["results"]

    def test_top_k_passed_to_azure_client(self):
        """top_k is forwarded as the `top` parameter to SearchClient.search."""
        mock_client = MagicMock()
        mock_client.search.return_value = [_make_search_doc("world", "content")]
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("query", top_k=5)
        call_kwargs = mock_client.search.call_args[1]
        assert call_kwargs.get("top") == 5
        assert isinstance(result, dict)

    def test_not_relevant_when_azure_returns_empty(self):
        """Azure returning 0 results → relevant=False (no silent local fallback)."""
        mock_client = MagicMock()
        mock_client.search.return_value = []
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("What is the ancient Roman Empire?")
        assert isinstance(result, dict)
        assert result["relevant"] is False
        assert result["results"] == ""

    def test_not_relevant_when_azure_score_too_low(self):
        """Azure result with score below threshold → relevant=False."""
        mock_client = MagicMock()
        doc = _make_search_doc("world", "Some content")
        doc["@search.score"] = 0.1   # below _MIN_RELEVANCE_SCORE=0.3
        mock_client.search.return_value = [doc]
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("vague query")
        assert result["relevant"] is False

    def test_falls_back_to_local_on_azure_exception(self):
        """Azure Search exception triggers local fallback (resilience); result is a dict."""
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("Azure connection refused")
        fiq = _foundry_with_mock_azure(mock_client)
        result = fiq.search("toronto 2047")
        assert isinstance(result, dict)
        assert result["relevant"] is True   # "toronto" matches _KEYWORD_MAP["world"]
        assert "WORLD INTEL" in result["results"]


# ── GameMaster integration ─────────────────────────────────────────────────────

class TestGameMasterIntegration:

    def test_query_knowledge_returns_dict(self, game_master):
        """GameMaster.query_knowledge() returns a dict with relevant, results, query."""
        result = game_master.query_knowledge("nexus corp tower")
        assert isinstance(result, dict)
        assert result["relevant"] is True
        assert len(result["results"]) > 0

    def test_query_knowledge_not_relevant_for_off_topic(self, game_master):
        """Off-topic query returns relevant=False — no unrelated content passed as grounding."""
        result = game_master.query_knowledge("ancient Roman Empire history")
        assert result["relevant"] is False
        assert result["results"] == ""

    def test_query_knowledge_creates_foundry_iq_once(self, game_master):
        """FoundryIQ instance is only created once (lazy singleton per GameMaster)."""
        game_master.query_knowledge("nexus")
        first = game_master._foundry_iq
        game_master.query_knowledge("faction")
        assert game_master._foundry_iq is first

    def test_query_knowledge_uses_injected_foundry_iq(self, game_master):
        """Injecting a mock FoundryIQ lets tests control KB output."""
        mock_fiq = MagicMock()
        mock_fiq.search.return_value = {
            "relevant": True,
            "results": "=== [MOCK INTEL] ===\nInjected result.",
            "query": "anything",
        }
        game_master._foundry_iq = mock_fiq
        result = game_master.query_knowledge("anything")
        mock_fiq.search.assert_called_once_with("anything", top_k=2)
        assert result["relevant"] is True
        assert "MOCK INTEL" in result["results"]

    def test_max_files_forwarded_as_top_k(self, game_master):
        """max_files parameter is passed through to FoundryIQ.search as top_k."""
        mock_fiq = MagicMock()
        mock_fiq.search.return_value = {
            "relevant": True,
            "results": "=== [WORLD INTEL] ===\nSome content.",
            "query": "toronto",
        }
        game_master._foundry_iq = mock_fiq
        game_master.query_knowledge("toronto", max_files=1)
        mock_fiq.search.assert_called_once_with("toronto", top_k=1)
