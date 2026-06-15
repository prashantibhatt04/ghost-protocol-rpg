"""
Ghost Protocol — Base Agent
Shared Azure OpenAI client, call infrastructure, logging, and content safety.
"""

import os
import re
import logging
from datetime import datetime
from pathlib import Path
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

# Configure file + console logging once at module level
_log_path = Path(__file__).parent.parent / "ghost_protocol.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_path, encoding="utf-8"),
    ],
)

# ── Content Safety ─────────────────────────────────────────────────────────────
# Patterns that indicate prompt injection or attempts to subvert the game context.
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all|prior)\s+instructions",
    r"disregard\s+(your|the)\s+system\s+prompt",
    r"you\s+are\s+(now|actually)\s+(an?\s+)?(ai|gpt|llm|language model)",
    r"pretend\s+(you\s+are|to\s+be)\s+(?!.*crew|.*ghost|.*wraith|.*cipher|.*shadow|.*patch|.*vex)",
    r"act\s+as\s+(an?\s+)?(unrestricted|unfiltered|uncensored|unlimited|jailbroken)",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Hard-block content categories (outside fictional game scope)
_HARD_BLOCK_TERMS = [
    "real bomb", "real weapon", "actual hack", "real exploit",
    "real password", "real credentials", "my real name",
]

MAX_INPUT_LENGTH = 2000


class ContentSafetyError(Exception):
    pass


class BaseAgent:
    """
    Base class for all Ghost Protocol agents.
    Provides shared Azure OpenAI client, call(), validate_input(), and log().
    """

    _client: AzureOpenAI = None  # Singleton shared across all agents
    _deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        temperature: float = 0.85,
        max_tokens: int = 800,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._logger = logging.getLogger(f"ghost.{name.lower()}")

    # ── Client ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_client(cls) -> AzureOpenAI:
        if cls._client is None:
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

            if not endpoint or not api_key:
                raise EnvironmentError(
                    "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set in .env"
                )

            cls._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )
        return cls._client

    # ── Logging ────────────────────────────────────────────────────────────────

    def log(self, message: str, level: str = "info") -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        label = f"{self.name.upper():<10}"
        formatted = f"[{timestamp}] [{label}] {message}"

        if level == "warning":
            self._logger.warning(formatted)
        elif level == "error":
            self._logger.error(formatted)
        else:
            self._logger.info(formatted)

        return formatted

    # ── Content Safety ─────────────────────────────────────────────────────────

    def validate_input(self, text: str) -> str:
        """
        Sanitize and safety-check player input before it reaches any agent.
        Raises ValueError for structural issues, ContentSafetyError for safety violations.
        """
        if not text or not text.strip():
            raise ValueError("Input cannot be empty.")

        text = text.strip()

        if len(text) > MAX_INPUT_LENGTH:
            raise ValueError(
                f"Input is too long ({len(text)} chars). Maximum is {MAX_INPUT_LENGTH}."
            )

        text_lower = text.lower()

        for pattern in _COMPILED_PATTERNS:
            if pattern.search(text_lower):
                raise ContentSafetyError(
                    "Ghost comms blocked — input pattern flagged by content safety filter."
                )

        for term in _HARD_BLOCK_TERMS:
            if term in text_lower:
                raise ContentSafetyError(
                    "Ghost comms blocked — this looks like a real-world request. "
                    "Ghost Protocol only operates in fictional Toronto 2047."
                )

        return text

    def _check_output_safety(self, text: str) -> str:
        """
        Light post-generation check. Azure OpenAI's content filter handles heavy lifting;
        this strips any response that looks like the model leaked a system prompt.
        """
        if "AZURE_OPENAI" in text or "api_key" in text.lower():
            self.log("Output safety: potential credential leak scrubbed.", level="warning")
            return "[Response redacted by output safety filter]"
        return text

    # ── Core Call ──────────────────────────────────────────────────────────────

    def call(
        self,
        user_message: str,
        context: str = None,
        conversation_history: list = None,
        extra_system: str = None,
    ) -> dict:
        """
        Send a message to this agent and return a structured response dict.

        Args:
            user_message: The prompt or situation for this agent to respond to.
            context: Optional intel brief prepended to the message.
            conversation_history: List of prior {"role", "content"} dicts.
            extra_system: Additional text appended to the system prompt for this
                          call only (used for per-turn phase-gating instructions).

        Returns:
            dict with keys: agent_name, role, response, tokens_used,
                            elapsed_seconds, success, [error]
        """
        start = datetime.now()
        truncated = user_message[:80] + ("…" if len(user_message) > 80 else "")
        self.log(f"▶ Activated | {truncated}")

        # Build message list — optionally augment system prompt for this call
        system_content = self.system_prompt
        if extra_system:
            system_content = f"{system_content}\n\n{extra_system}"
        messages = [{"role": "system", "content": system_content}]

        if conversation_history:
            # Caller is responsible for window management; cap here as safety net
            messages.extend(conversation_history[-14:])

        if context:
            full_message = f"[INTEL BRIEF]\n{context}\n\n[SITUATION]\n{user_message}"
        else:
            full_message = user_message

        messages.append({"role": "user", "content": full_message})

        try:
            client = self.get_client()
            response = client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content or ""
            content = self._check_output_safety(content)
            elapsed = (datetime.now() - start).total_seconds()
            tokens = response.usage.total_tokens if response.usage else 0

            self.log(f"◀ Done in {elapsed:.2f}s | tokens={tokens}")

            return {
                "agent_name": self.name,
                "role": self.role,
                "response": content,
                "tokens_used": tokens,
                "elapsed_seconds": round(elapsed, 2),
                "success": True,
            }

        except Exception as exc:
            self.log(f"✗ ERROR: {exc}", level="error")
            return {
                "agent_name": self.name,
                "role": self.role,
                "response": f"[{self.name} — signal lost. Reconnecting…]",
                "tokens_used": 0,
                "elapsed_seconds": (datetime.now() - start).total_seconds(),
                "success": False,
                "error": str(exc),
            }
