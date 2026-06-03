"""
Model-agnostic LLM provider abstraction.

Each provider implements complete() and complete_json() — the rest of the
system calls these through call_claude() / call_claude_json() in
claude_client.py without knowing which backend is active.

Supported providers:
  - claude_cli:    claude --print subprocess (default, no API key)
  - anthropic_api: Anthropic Python SDK (direct API, actual token counts)
  - openai_api:    OpenAI-compatible APIs (OpenAI, Azure, Groq, Together, etc.)
  - ollama:        Local models via Ollama REST API

Provider selection is persistent — saved to config/settings.yaml and
restored on next startup. Switch at runtime with /provider.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str = "base"
    supports_json_mode: bool = False

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Return the model's text response."""

    def complete_json(
        self,
        prompt: str,
        schema: dict,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        """Return parsed JSON from the model. Default: append schema to prompt."""
        schema_desc = json.dumps(schema, indent=2)
        json_system = (
            (system_prompt + "\n\n" if system_prompt else "")
            + "CRITICAL: Your response MUST be valid JSON only — no markdown, no explanation, "
            "no code fences. Output a single JSON object matching this schema exactly:\n"
            + schema_desc
        )
        json_prompt = prompt + "\n\nRespond with ONLY a JSON object. No other text."

        raw = self.complete(prompt=json_prompt, system_prompt=json_system, model=model)
        return _parse_json_response(raw)

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model names for this provider."""

    @abstractmethod
    def validate(self) -> tuple[bool, str]:
        """Check if the provider is configured correctly.
        Returns (ok, message)."""


# ── JSON parsing helper ───────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    """Extract JSON from a model response, handling fences and noise."""
    # Attempt 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract from code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Attempt 3: find first {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise RuntimeError(f"Could not parse JSON from response:\n{raw[:400]}")


# ═══════════════════════════════════════════════════════════════════════
# Provider implementations
# ═══════════════════════════════════════════════════════════════════════


class ClaudeCLIProvider(LLMProvider):
    """Default provider — uses locally installed `claude --print` CLI.
    No API key needed, uses your existing Claude Code subscription."""

    name = "claude_cli"

    def __init__(self):
        self._cli_checked = False

    def _check_cli(self):
        if self._cli_checked:
            return
        if not shutil.which("claude"):
            raise RuntimeError(
                "claude CLI not found in PATH.\n"
                "Install Claude Code from https://claude.ai/code and log in once."
            )
        self._cli_checked = True

    def complete(self, prompt, system_prompt=None, model=None):
        self._check_cli()
        cmd = ["claude", "--print"]
        if model:
            cmd += ["--model", model]

        sp_file = None
        try:
            if system_prompt:
                fd, sp_file = tempfile.mkstemp(suffix=".txt", prefix="claude_sp_")
                os.write(fd, system_prompt.encode("utf-8"))
                os.close(fd)
                cmd += ["--system-prompt-file", sp_file]

            result = subprocess.run(
                cmd,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        finally:
            if sp_file:
                try:
                    os.unlink(sp_file)
                except OSError:
                    pass

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI exit {result.returncode}: {result.stderr.strip()}")

        return result.stdout.strip()

    def list_models(self):
        return ["haiku", "sonnet", "opus"]

    def validate(self):
        try:
            self._check_cli()
            return True, "claude CLI found in PATH"
        except RuntimeError as e:
            return False, str(e)


class AnthropicAPIProvider(LLMProvider):
    """Direct Anthropic API via the anthropic Python SDK.
    Provides actual token counts (not estimates).
    Requires: pip install anthropic + ANTHROPIC_API_KEY env var."""

    name = "anthropic_api"
    supports_json_mode = True

    _MODEL_MAP = {
        "haiku": "claude-sonnet-4-5-20250514",
        "sonnet": "claude-sonnet-4-5-20250514",
        "opus": "claude-sonnet-4-5-20250514",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise RuntimeError(
                    "anthropic SDK not installed. Run: pip install anthropic"
                )
            if not self.api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. Add it to your .env file or environment."
                )
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _resolve_model(self, model: str | None) -> str:
        if not model:
            return self._MODEL_MAP.get("sonnet", "claude-sonnet-4-5-20250514")
        return self._MODEL_MAP.get(model, model)

    def complete(self, prompt, system_prompt=None, model=None):
        client = self._get_client()
        kwargs = {
            "model": self._resolve_model(model),
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)
        return response.content[0].text

    def list_models(self):
        return ["haiku", "sonnet", "opus"]

    def validate(self):
        if not self.api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY not set"
        try:
            import anthropic  # noqa: F401
            return True, "anthropic SDK installed, API key present"
        except ImportError:
            return False, "anthropic SDK not installed (pip install anthropic)"


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider.
    Works with: OpenAI, Azure OpenAI, Groq, Together, Fireworks,
    and any endpoint that speaks the OpenAI chat completions format.
    Requires: pip install openai + OPENAI_API_KEY env var.
    Set OPENAI_BASE_URL for non-OpenAI endpoints."""

    name = "openai_api"
    supports_json_mode = True

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "gpt-4o",
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.default_model = default_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise RuntimeError(
                    "openai SDK not installed. Run: pip install openai"
                )
            if not self.api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY not set. Add it to your .env file or environment."
                )
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(self, prompt, system_prompt=None, model=None):
        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            max_tokens=8192,
        )
        return response.choices[0].message.content.strip()

    def list_models(self):
        try:
            client = self._get_client()
            models = client.models.list()
            return sorted([m.id for m in models.data])[:20]
        except Exception:
            return [self.default_model]

    def validate(self):
        if not self.api_key and not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY not set"
        try:
            import openai  # noqa: F401
            url_note = f" (base: {self.base_url})" if self.base_url else ""
            return True, f"openai SDK installed, API key present{url_note}"
        except ImportError:
            return False, "openai SDK not installed (pip install openai)"


class OllamaProvider(LLMProvider):
    """Local model provider via Ollama REST API.
    No API key needed — Ollama runs locally.
    Requires: Ollama installed and running (ollama serve).
    Set OLLAMA_BASE_URL to override (default: http://localhost:11434)."""

    name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str = "llama3.1",
    ):
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.default_model = default_model

    def complete(self, prompt, system_prompt=None, model=None):
        import urllib.request
        import urllib.error

        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama connection failed ({self.base_url}): {e}. "
                "Is Ollama running? Start it with: ollama serve"
            )

    def list_models(self):
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return [self.default_model]

    def validate(self):
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                count = len(data.get("models", []))
                return True, f"Ollama running at {self.base_url} ({count} models)"
        except Exception as e:
            return False, f"Ollama not reachable at {self.base_url}: {e}"


# ═══════════════════════════════════════════════════════════════════════
# Provider registry
# ═══════════════════════════════════════════════════════════════════════

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude_cli": ClaudeCLIProvider,
    "anthropic_api": AnthropicAPIProvider,
    "openai_api": OpenAIProvider,
    "ollama": OllamaProvider,
}


def create_provider(name: str, **kwargs) -> LLMProvider:
    """Create a provider instance by name."""
    cls = PROVIDERS.get(name)
    if not cls:
        raise ValueError(
            f"Unknown provider: {name}. "
            f"Available: {', '.join(PROVIDERS.keys())}"
        )
    return cls(**kwargs)


def get_provider_info() -> list[dict]:
    """Return info about all available providers for display."""
    info = []
    for name, cls in PROVIDERS.items():
        instance = cls()
        ok, msg = instance.validate()
        info.append({
            "name": name,
            "status": "✅ Ready" if ok else "❌ Not configured",
            "detail": msg,
            "models": instance.list_models() if ok else [],
        })
    return info
