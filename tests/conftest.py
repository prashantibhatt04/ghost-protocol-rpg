"""
Shared fixtures and helpers for the Ghost Protocol test suite.
All Azure OpenAI API calls are mocked — no real API keys required.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# Guarantee the project root is importable regardless of run directory
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Mock response factory ──────────────────────────────────────────────────────

def make_mock_response(content: str = "Mock agent response text.", tokens: int = 42):
    """Build a mock Azure OpenAI chat completion response object."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = content
    mock.usage.total_tokens = tokens
    return mock


# ── Core fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_openai_response():
    """Expose the make_mock_response factory so tests can build custom responses."""
    return make_mock_response


@pytest.fixture
def mock_azure_client():
    """
    Replace BaseAgent._client with a MagicMock for the duration of a test.
    Restores the original singleton after the test to avoid cross-test pollution.
    Default return value is a generic successful response.
    """
    from agents.base_agent import BaseAgent
    mock = MagicMock()
    mock.chat.completions.create.return_value = make_mock_response()
    original = BaseAgent._client
    BaseAgent._client = mock
    yield mock
    BaseAgent._client = original


@pytest.fixture
def tmp_game_state(tmp_path):
    """
    GameState backed by a throw-away SQLite file.
    A 'Test Mission' session is pre-created so tests start with a valid session.
    """
    from state.game_state import GameState
    gs = GameState(db_path=tmp_path / "test_ghost.db")
    gs.new_session("Test Mission")
    return gs


@pytest.fixture
def game_master(mock_azure_client):
    """
    GameMaster with the Azure OpenAI client mocked out and Foundry IQ forced to
    local-file fallback, so tests are not affected by real Azure Search credentials
    in the environment.
    """
    from agents.game_master import GameMaster
    from knowledge.foundry_iq import FoundryIQ
    gm = GameMaster()
    # Inject a local-only FoundryIQ so keyword-matching tests are deterministic
    fiq = FoundryIQ.__new__(FoundryIQ)
    fiq._index     = "ghost-protocol-knowledge"
    fiq._client    = None
    fiq._available = False
    gm._foundry_iq = fiq
    return gm


@pytest.fixture
def minimal_game_state():
    """
    Minimal in-memory game-state dict accepted by GameMaster.orchestrate().
    Does not touch the database — suitable for pure orchestration tests.
    """
    return {
        "session_id":  1,
        "mission":     "Test Mission",
        "phase":       "recon",
        "alert_state": "cold",
        "turn_count":  0,
        "crew_status": "All operational",
        "crew_detail": {
            name: {"health_state": "operational", "augment_damaged": False, "notes": ""}
            for name in ["Ghost", "Wraith", "Cipher", "Shadow", "Patch"]
        },
        "objectives":    [],
        "flags":         {},
        "requires_roll": False,
        "roll_modifier": 0,
    }


@pytest.fixture
def orchestrate_side_effects():
    """
    Return a helper that builds the ordered mock-response list expected by
    orchestrate() for a routing → specialists → synthesis call sequence.
    """
    def _build(routing: str = "cipher, shadow", specialist_text: str = "Specialist response."):
        specialist_names = [s.strip() for s in routing.split(",") if s.strip()]
        responses = [make_mock_response(routing)]
        for _ in specialist_names:
            responses.append(make_mock_response(specialist_text))
        responses.append(make_mock_response("Ghost narrative synthesis."))
        return responses
    return _build
