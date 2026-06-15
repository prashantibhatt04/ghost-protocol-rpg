"""
Tests for agents/base_agent.py

Covers: Azure OpenAI client lifecycle, call() response structure,
content safety validation, output scrubbing, and logging.
"""

import pytest
from unittest.mock import patch, MagicMock
from conftest import make_mock_response


# ── Helpers ────────────────────────────────────────────────────────────────────

class _ConcreteAgent:
    """Minimal concrete agent used to test BaseAgent behaviour without subclass overhead."""
    def __new__(cls):
        from agents.base_agent import BaseAgent
        instance = object.__new__(BaseAgent)
        BaseAgent.__init__(instance, "TestAgent", "Test Role", "System prompt for testing.")
        return instance


def make_agent():
    from agents.base_agent import BaseAgent
    return BaseAgent.__new__(BaseAgent).__class__.__init__(
        BaseAgent.__new__(BaseAgent), "TestAgent", "Test Role", "Test system."
    )


def _make_agent():
    from agents.wraith import Wraith
    return Wraith()


# ── Client lifecycle ───────────────────────────────────────────────────────────

class TestClientLifecycle:

    def test_get_client_returns_singleton(self, mock_azure_client):
        """get_client() returns the same mock instance on repeated calls."""
        from agents.base_agent import BaseAgent
        c1 = BaseAgent.get_client()
        c2 = BaseAgent.get_client()
        assert c1 is c2

    def test_get_client_initializes_with_env_vars(self, monkeypatch):
        """get_client() creates an AzureOpenAI client using the configured env vars."""
        from agents.base_agent import BaseAgent
        original = BaseAgent._client
        BaseAgent._client = None
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key-abc")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        try:
            with patch("agents.base_agent.AzureOpenAI") as MockAzure:
                MockAzure.return_value = MagicMock()
                client = BaseAgent.get_client()
                assert client is not None
                MockAzure.assert_called_once_with(
                    azure_endpoint="https://test.openai.azure.com/",
                    api_key="test-key-abc",
                    api_version="2024-10-21",
                )
        finally:
            BaseAgent._client = original

    def test_get_client_raises_without_endpoint(self, monkeypatch):
        """get_client() raises EnvironmentError when AZURE_OPENAI_ENDPOINT is missing."""
        from agents.base_agent import BaseAgent
        original = BaseAgent._client
        BaseAgent._client = None
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        try:
            with pytest.raises(EnvironmentError, match="AZURE_OPENAI_ENDPOINT"):
                BaseAgent.get_client()
        finally:
            BaseAgent._client = original


# ── call() response structure ──────────────────────────────────────────────────

class TestCallMethod:

    def test_call_returns_all_expected_keys(self, mock_azure_client):
        """call() response dict contains the documented keys on success."""
        agent = _make_agent()
        result = agent.call("assess the security layout")
        expected_keys = {"agent_name", "role", "response", "tokens_used", "elapsed_seconds", "success"}
        assert expected_keys.issubset(result.keys())

    def test_call_returns_success_true_on_normal_response(self, mock_azure_client):
        """call() sets success=True when the API responds without error."""
        agent = _make_agent()
        result = agent.call("scan the perimeter")
        assert result["success"] is True

    def test_call_returns_response_content(self, mock_azure_client):
        """call() places the model's text in the 'response' key."""
        mock_azure_client.chat.completions.create.return_value = make_mock_response("Guard spotted on east corridor.")
        agent = _make_agent()
        result = agent.call("any input")
        assert result["response"] == "Guard spotted on east corridor."

    def test_call_returns_token_count(self, mock_azure_client):
        """call() records token usage from the API response."""
        mock_azure_client.chat.completions.create.return_value = make_mock_response(tokens=99)
        agent = _make_agent()
        result = agent.call("any input")
        assert result["tokens_used"] == 99

    def test_call_records_elapsed_seconds(self, mock_azure_client):
        """call() records a non-negative elapsed_seconds value."""
        agent = _make_agent()
        result = agent.call("any input")
        assert isinstance(result["elapsed_seconds"], float)
        assert result["elapsed_seconds"] >= 0

    def test_call_returns_failure_dict_on_api_error(self, mock_azure_client):
        """call() returns success=False and an error key when the API throws."""
        mock_azure_client.chat.completions.create.side_effect = Exception("Connection refused")
        agent = _make_agent()
        result = agent.call("test input")
        assert result["success"] is False
        assert "error" in result
        assert "Connection refused" in result["error"]

    def test_call_preserves_agent_name_on_failure(self, mock_azure_client):
        """Even on API failure, agent_name and role are set in the response."""
        mock_azure_client.chat.completions.create.side_effect = RuntimeError("timeout")
        agent = _make_agent()
        result = agent.call("test")
        assert result["agent_name"] == "Wraith"
        assert result["role"] == "Enforcer"

    def test_call_sends_system_prompt(self, mock_azure_client):
        """call() includes the agent's system prompt as the first message."""
        agent = _make_agent()
        agent.call("check the east wing")
        call_args = mock_azure_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == agent.system_prompt

    def test_call_includes_user_message(self, mock_azure_client):
        """call() places the user message in the messages list."""
        agent = _make_agent()
        agent.call("neutralise the guard on B3")
        call_args = mock_azure_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert any("neutralise the guard on B3" in m["content"] for m in user_msgs)

    def test_call_prepends_context_when_provided(self, mock_azure_client):
        """call() wraps user message with [INTEL BRIEF] when context is given."""
        agent = _make_agent()
        agent.call("enter the vault", context="Phase: execution. Alert: warm.")
        call_args = mock_azure_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "INTEL BRIEF" in user_content
        assert "enter the vault" in user_content


# ── Logging ────────────────────────────────────────────────────────────────────

class TestLogging:

    def test_log_returns_formatted_string(self, mock_azure_client):
        """log() returns a string containing the agent name and the message."""
        agent = _make_agent()
        result = agent.log("security sweep complete")
        assert "WRAITH" in result
        assert "security sweep complete" in result

    def test_log_includes_timestamp(self, mock_azure_client):
        """log() output includes a bracketed timestamp."""
        agent = _make_agent()
        result = agent.log("test")
        assert "[" in result and "]" in result

    def test_log_accepts_warning_level(self, mock_azure_client):
        """log() does not raise when called with level='warning'."""
        agent = _make_agent()
        result = agent.log("something looks wrong", level="warning")
        assert "WRAITH" in result

    def test_log_accepts_error_level(self, mock_azure_client):
        """log() does not raise when called with level='error'."""
        agent = _make_agent()
        result = agent.log("signal lost", level="error")
        assert result is not None
