"""
Tests for all six specialist agents.

Covers: correct initialization (name, role, temperature, max_tokens),
system prompt personality traits, call() response structure,
and each agent's specialized helper methods.
"""

import pytest
from conftest import make_mock_response


# ── Initialization ─────────────────────────────────────────────────────────────

class TestAgentInitialization:

    def test_ghost_initializes_correctly(self, mock_azure_client):
        """Ghost (GameMaster) has the correct identity attributes."""
        from agents.game_master import GameMaster
        gm = GameMaster()
        assert gm.name == "Ghost"
        assert gm.role == "Game Master / Orchestrator"
        assert gm.temperature == 0.9
        assert gm.max_tokens == 700

    def test_wraith_initializes_correctly(self, mock_azure_client):
        """Wraith has correct name, role, and conservative temperature for tactical output."""
        from agents.wraith import Wraith
        w = Wraith()
        assert w.name == "Wraith"
        assert w.role == "Enforcer"
        assert w.temperature == 0.7
        assert w.max_tokens == 400

    def test_cipher_initializes_correctly(self, mock_azure_client):
        """Cipher has correct name, role, and higher temperature for technical creativity."""
        from agents.cipher import Cipher
        c = Cipher()
        assert c.name == "Cipher"
        assert c.role == "Hacker"
        assert c.temperature == 0.9
        assert c.max_tokens == 500

    def test_shadow_initializes_correctly(self, mock_azure_client):
        """Shadow has correct name, role, and mid-range temperature for precise output."""
        from agents.shadow import Shadow
        s = Shadow()
        assert s.name == "Shadow"
        assert s.role == "Infiltrator"
        assert s.temperature == 0.75
        assert s.max_tokens == 400

    def test_patch_initializes_correctly(self, mock_azure_client):
        """Patch has correct name, role, and temperature for warm, precise output."""
        from agents.patch import Patch
        p = Patch()
        assert p.name == "Patch"
        assert p.role == "Fixer"
        assert p.temperature == 0.8
        assert p.max_tokens == 450

    def test_vex_initializes_correctly(self, mock_azure_client):
        """Vex has correct name, role, and highest temperature for theatrical output."""
        from agents.vex import Vex
        v = Vex()
        assert v.name == "Vex"
        assert v.role == "Rival Operator"
        assert v.temperature == 0.95
        assert v.max_tokens == 350


# ── System prompt personality traits ──────────────────────────────────────────

class TestSystemPrompts:

    def test_wraith_prompt_is_tactical(self, mock_azure_client):
        """Wraith's system prompt establishes a tactical, combat-focused voice."""
        from agents.wraith import Wraith
        w = Wraith()
        prompt = w.system_prompt.lower()
        assert "tactical" in prompt
        assert any(kw in prompt for kw in ("guard", "combat", "neutrali", "security"))

    def test_wraith_prompt_includes_axiom_background(self, mock_azure_client):
        """Wraith's system prompt references her Axiom Phantom Division backstory."""
        from agents.wraith import Wraith
        w = Wraith()
        assert "axiom" in w.system_prompt.lower()
        assert "phantom division" in w.system_prompt.lower()

    def test_cipher_prompt_is_technical(self, mock_azure_client):
        """Cipher's system prompt establishes a hacker with hyper-verbal technical voice."""
        from agents.cipher import Cipher
        c = Cipher()
        prompt = c.system_prompt.lower()
        assert "hack" in prompt
        assert "digital" in prompt
        assert any(kw in prompt for kw in ("neural", "system", "network"))

    def test_cipher_prompt_includes_nexus_backstory(self, mock_azure_client):
        """Cipher's prompt references her father Marcus Okafor at Nexus Corp Security."""
        from agents.cipher import Cipher
        c = Cipher()
        assert "marcus okafor" in c.system_prompt.lower()
        assert "nexus" in c.system_prompt.lower()

    def test_shadow_prompt_is_stealth_focused(self, mock_azure_client):
        """Shadow's system prompt establishes minimal, sensory-focused stealth expertise."""
        from agents.shadow import Shadow
        s = Shadow()
        prompt = s.system_prompt.lower()
        assert "stealth" in prompt
        assert any(kw in prompt for kw in ("camouflage", "silent", "sound"))

    def test_shadow_prompt_references_helix_background(self, mock_azure_client):
        """Shadow's prompt references her Helix Apex test-subject origin."""
        from agents.shadow import Shadow
        s = Shadow()
        assert "helix" in s.system_prompt.lower()
        assert "apex" in s.system_prompt.lower()

    def test_patch_prompt_flags_civilian_ethics(self, mock_azure_client):
        """Patch's system prompt explicitly addresses civilian safety responsibilities."""
        from agents.patch import Patch
        p = Patch()
        prompt = p.system_prompt.lower()
        assert "civilian" in prompt
        assert any(kw in prompt for kw in ("harm", "innocent", "ethics", "flag"))

    def test_patch_prompt_includes_nexusmed_background(self, mock_azure_client):
        """Patch's prompt references her NexusMed surgical background."""
        from agents.patch import Patch
        p = Patch()
        assert "nexusmed" in p.system_prompt.lower()
        assert any(kw in p.system_prompt.lower() for kw in ("surgeon", "medical", "doctor"))

    def test_vex_prompt_references_ghost(self, mock_azure_client):
        """Vex's system prompt instructs the model to reference Ghost's shared history."""
        from agents.vex import Vex
        v = Vex()
        assert "Ghost" in v.system_prompt
        assert any(kw in v.system_prompt.lower() for kw in ("history", "complication"))

    def test_vex_prompt_is_theatrical(self, mock_azure_client):
        """Vex's system prompt establishes a theatrical, cryptic voice."""
        from agents.vex import Vex
        v = Vex()
        prompt = v.system_prompt.lower()
        assert "theatrical" in prompt
        assert "complication" in prompt


# ── call() response structure for each agent ──────────────────────────────────

@pytest.mark.parametrize("agent_class,expected_name,expected_role", [
    ("agents.wraith.Wraith",   "Wraith",  "Enforcer"),
    ("agents.cipher.Cipher",   "Cipher",  "Hacker"),
    ("agents.shadow.Shadow",   "Shadow",  "Infiltrator"),
    ("agents.patch.Patch",     "Patch",   "Fixer"),
    ("agents.vex.Vex",         "Vex",     "Rival Operator"),
])
def test_agent_call_returns_valid_structure(
    mock_azure_client, agent_class, expected_name, expected_role
):
    """Each agent's call() returns a dict with the required keys and correct identity."""
    import importlib
    module_path, class_name = agent_class.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    agent = cls()
    result = agent.call("assess the current situation")
    assert result["success"] is True
    assert result["agent_name"] == expected_name
    assert result["role"] == expected_role
    assert isinstance(result["response"], str)
    assert result["tokens_used"] >= 0


# ── Specialized helper methods ─────────────────────────────────────────────────

class TestSpecializedMethods:

    def test_wraith_assess_security_returns_result(self, mock_azure_client):
        """Wraith.assess_security() returns a valid response dict."""
        from agents.wraith import Wraith
        w = Wraith()
        result = w.assess_security("Three guards on the east corridor, one camera dead zone.")
        assert result["success"] is True
        assert result["agent_name"] == "Wraith"

    def test_wraith_plan_takedown_returns_result(self, mock_azure_client):
        """Wraith.plan_takedown() returns a valid response dict."""
        from agents.wraith import Wraith
        w = Wraith()
        result = w.plan_takedown("Guard at the B3 junction", constraints="no noise")
        assert result["success"] is True

    def test_cipher_hack_system_returns_result(self, mock_azure_client):
        """Cipher.hack_system() returns a valid response dict."""
        from agents.cipher import Cipher
        c = Cipher()
        result = c.hack_system("ARGUS-3 surveillance network with modular reboot cycle")
        assert result["success"] is True
        assert result["agent_name"] == "Cipher"

    def test_cipher_counter_surveillance_returns_result(self, mock_azure_client):
        """Cipher.counter_surveillance() returns a valid response dict."""
        from agents.cipher import Cipher
        c = Cipher()
        result = c.counter_surveillance("Nexus Tower B3 server room with biometric cameras")
        assert result["success"] is True

    def test_shadow_scout_location_returns_result(self, mock_azure_client):
        """Shadow.scout_location() returns a valid response dict."""
        from agents.shadow import Shadow
        s = Shadow()
        result = s.scout_location("Service bay entry with pressure plates on steps 3 and 7")
        assert result["success"] is True
        assert result["agent_name"] == "Shadow"

    def test_shadow_plan_infiltration_returns_result(self, mock_azure_client):
        """Shadow.plan_infiltration() returns a valid response dict."""
        from agents.shadow import Shadow
        s = Shadow()
        result = s.plan_infiltration("Nexus Tower sub-level B3", security_info="Motion sensors active")
        assert result["success"] is True

    def test_patch_assess_crew_returns_result(self, mock_azure_client):
        """Patch.assess_crew() returns a valid response dict."""
        from agents.patch import Patch
        p = Patch()
        result = p.assess_crew("Wraith has a shoulder wound. Cipher is operational.")
        assert result["success"] is True
        assert result["agent_name"] == "Patch"

    def test_patch_negotiate_returns_result(self, mock_azure_client):
        """Patch.negotiate() returns a valid response dict."""
        from agents.patch import Patch
        p = Patch()
        result = p.negotiate("Nexus Corp security checkpoint guard", leverage="Medical emergency cover")
        assert result["success"] is True

    def test_vex_appear_returns_result(self, mock_azure_client):
        """Vex.appear() returns a valid response dict from a forced execution-phase entrance."""
        from agents.vex import Vex
        v = Vex()
        result = v.appear(
            current_situation="The crew is 47 seconds into the GenVault data transfer.",
            context="Phase: execution. Wraith is at the door.",
        )
        assert result["success"] is True
        assert result["agent_name"] == "Vex"
