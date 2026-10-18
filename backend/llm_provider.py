"""
Provider-independent LLM interface.

Implemented providers (select with LLM_PROVIDER):
  - ollama     (default; local models or Ollama Cloud models such as gpt-oss:120b-cloud)
  - openai     (OpenAI or any OpenAI-compatible endpoint via OPENAI_BASE_URL)
  - anthropic
  - gemini
  - disabled   (no LLM; the app falls back to heuristic analysis)

Every provider exposes the same surface:
    provider.chat(messages, temperature, format, max_tokens) -> str
    provider.chat_json(messages, schema, temperature, max_tokens) -> dict
    provider.can_chat / is_enabled / is_model_configured / cloud_usage_authorized / model_name

Switching provider is a pure configuration change (.env), no code changes needed.
"""
import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Optional

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("true", "1", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "disabled")

# Safety constraints for request payloads and responses
MAX_PAYLOAD_TOTAL_CHARS = 120_000
MAX_SINGLE_MESSAGE_CHARS = 80_000
MAX_MESSAGES_COUNT = 50
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_TOKENS_CAP = 8192


class LLMProviderDisabledError(RuntimeError):
    """Raised when an LLM provider is invoked while disabled or unconfigured."""


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider request fails or inputs are invalid."""


def validate_chat_messages(messages: Any, max_total_chars: int = MAX_PAYLOAD_TOTAL_CHARS) -> None:
    if not isinstance(messages, list) or len(messages) == 0:
        raise LLMProviderError("Invalid chat payload: messages must be a non-empty list.")
    if len(messages) > MAX_MESSAGES_COUNT:
        raise LLMProviderError(f"Invalid chat payload: more than {MAX_MESSAGES_COUNT} messages.")
    total = 0
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise LLMProviderError(f"Invalid chat payload: message {idx} must be a dictionary.")
        role, content = msg.get("role"), msg.get("content")
        if not isinstance(role, str) or not role.strip():
            raise LLMProviderError(f"Invalid chat payload: message {idx} has no role.")
        if not isinstance(content, str):
            raise LLMProviderError(f"Invalid chat payload: message {idx} content must be a string.")
        if len(content) > MAX_SINGLE_MESSAGE_CHARS:
            raise LLMProviderError(f"Invalid chat payload: message {idx} is too long.")
        total += len(content)
        if total > max_total_chars:
            raise LLMProviderError("Invalid chat payload: total size exceeds safety limit.")


def parse_json_loose(raw: str) -> Any:
    """Parse JSON from model output, tolerating <think> blocks, code fences and chatter."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("empty model output")
    text = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON found in model output")


def _http_post_json(url: str, payload: dict, headers: dict, timeout: float, label: str) -> dict:
    try:
        data = json.dumps(payload).encode("utf-8")
    except Exception as e:
        raise LLMProviderError("Failed to serialize request payload.") from e
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise LLMProviderError(f"{label} response exceeded the maximum allowed size.")
            try:
                result = json.loads(raw.decode("utf-8"))
            except Exception as e:
                raise LLMProviderError(f"{label} returned a non-JSON response.") from e
            if not isinstance(result, dict):
                raise LLMProviderError(f"{label} returned an unexpected response structure.")
            return result
    except TimeoutError as e:
        raise LLMProviderError(f"{label} request timed out after {timeout:.0f}s.") from e
    except urllib.error.HTTPError as e:
        try:
            snippet = e.read(200).decode("utf-8", errors="replace").strip()
        except Exception:
            snippet = ""
        raise LLMProviderError(f"{label} HTTP error {e.code}: {snippet[:160] or e.reason}") from e
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", ""))
        if "timed out" in reason.lower():
            raise LLMProviderError(f"{label} request timed out after {timeout:.0f}s.") from e
        raise LLMProviderError(f"Failed to connect to {label} ({reason or 'host unreachable'}).") from e
    except LLMProviderError:
        raise
    except Exception as e:
        raise LLMProviderError(f"Unexpected error talking to {label}.") from e


class LLMProvider(ABC):
    """Abstract provider-independent interface for chat completions."""

    provider_name: str = "base"
    model_name: str = ""

    @abstractmethod
    def _chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        json_mode: bool,
        schema: Optional[dict],
        max_tokens: int,
    ) -> str:
        ...

    @property
    @abstractmethod
    def is_enabled(self) -> bool:
        ...

    @property
    def is_model_configured(self) -> bool:
        return bool(self.model_name and self.model_name.strip())

    @property
    def cloud_usage_authorized(self) -> bool:
        return True

    @property
    def can_chat(self) -> bool:
        return self.is_enabled and self.is_model_configured and self.cloud_usage_authorized

    def _guard(self) -> None:
        if not self.is_enabled:
            raise LLMProviderDisabledError(f"LLM provider '{self.provider_name}' is disabled.")
        if not self.is_model_configured:
            raise LLMProviderDisabledError(f"No model configured for provider '{self.provider_name}'.")
        if not self.cloud_usage_authorized:
            raise LLMProviderDisabledError(
                "Cloud model usage is not authorized. Set OLLAMA_CLOUD_USAGE_AUTHORIZED=true to allow it."
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        format: Optional[str | dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        self._guard()
        validate_chat_messages(messages)
        max_tokens = kwargs.get("max_tokens")
        max_tokens = max(1, min(int(max_tokens), MAX_OUTPUT_TOKENS_CAP)) if max_tokens else self.default_max_tokens
        fmt = format if format is not None else kwargs.get("format")
        json_mode = fmt is not None
        schema = fmt if isinstance(fmt, dict) else None
        return self._chat(messages, max(0.0, min(2.0, float(temperature))), json_mode, schema, max_tokens)

    def chat_json(
        self,
        messages: list[dict[str, str]],
        schema: Optional[dict] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Chat and parse a JSON answer. Retries once on unparseable output."""
        last_err: Optional[Exception] = None
        for attempt in range(2):
            raw = self.chat(
                messages,
                temperature=temperature,
                format=schema if schema is not None else "json",
                max_tokens=max_tokens,
            )
            try:
                return parse_json_loose(raw)
            except Exception as e:  # noqa: BLE001
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": raw[:2000]},
                    {"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON object."},
                ]
        raise LLMProviderError(f"Model did not return valid JSON: {last_err}")

    default_max_tokens: int = 2048


# ---------------------------------------------------------------------------
# Ollama (local or Ollama Cloud)
# ---------------------------------------------------------------------------
class OllamaLLMProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        enabled: Optional[bool] = None,
        cloud_usage_authorized: Optional[bool] = None,
        timeout: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model_name = model_name if model_name is not None else os.getenv("OLLAMA_MODEL_NAME", "")
        self._enabled = enabled if enabled is not None else _env_bool("OLLAMA_LLM_ENABLED", False)
        self._cloud_auth = (
            cloud_usage_authorized
            if cloud_usage_authorized is not None
            else _env_bool("OLLAMA_CLOUD_USAGE_AUTHORIZED", False)
        )
        self.timeout = max(5.0, timeout if timeout is not None else _env_float("OLLAMA_TIMEOUT_SECONDS", 180.0))
        self.default_max_tokens = max(
            256,
            min(MAX_OUTPUT_TOKENS_CAP, max_output_tokens or _env_int("OLLAMA_MAX_OUTPUT_TOKENS", 4096)),
        )
        # Reasoning models (gpt-oss, deepseek-r1, qwen3...) spend output tokens on hidden thinking.
        # Keep thinking short so there is budget left for the actual JSON answer.
        self.think = os.getenv("OLLAMA_THINK", "").strip().lower()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def is_cloud_model(self) -> bool:
        return self.model_name.strip().lower().endswith("-cloud") or ":cloud" in self.model_name.lower()

    @property
    def cloud_usage_authorized(self) -> bool:
        # Local models never need cloud authorization.
        return self._cloud_auth or not self.is_cloud_model

    def _think_value(self) -> Any:
        name = self.model_name.lower()
        if self.think in ("false", "off", "none", "0"):
            return False if not name.startswith("gpt-oss") else "low"
        if self.think in ("low", "medium", "high"):
            return self.think
        if name.startswith("gpt-oss"):
            return "low"
        return None  # do not send the param for other models

    def _chat(self, messages, temperature, json_mode, schema, max_tokens) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name.strip(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        think = self._think_value()
        if think is not None:
            payload["think"] = think
        if json_mode:
            payload["format"] = schema if schema is not None else "json"
        result = _http_post_json(f"{self.base_url}/api/chat", payload, {}, self.timeout, "Ollama")
        msg = result.get("message")
        if not isinstance(msg, dict):
            raise LLMProviderError("Ollama response is missing 'message'.")
        content = msg.get("content")
        if not isinstance(content, str):
            raise LLMProviderError("Ollama response is missing string 'content'.")
        if not content.strip():
            raise LLMProviderError(
                "Ollama returned empty content (the model may have used all output tokens thinking). "
                "Increase OLLAMA_MAX_OUTPUT_TOKENS or set OLLAMA_THINK=low."
            )
        return content


# ---------------------------------------------------------------------------
# OpenAI / OpenAI-compatible
# ---------------------------------------------------------------------------
class OpenAILLMProvider(LLMProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self._key = os.getenv("OPENAI_API_KEY", "")
        self.timeout = max(5.0, _env_float("LLM_TIMEOUT_SECONDS", 120.0))
        self.default_max_tokens = _env_int("LLM_MAX_OUTPUT_TOKENS", 4096)

    @property
    def is_enabled(self) -> bool:
        return bool(self._key)

    def _chat(self, messages, temperature, json_mode, schema, max_tokens) -> str:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            if not any("json" in m["content"].lower() for m in messages):
                payload["messages"] = messages + [{"role": "user", "content": "Respond in JSON."}]
        res = _http_post_json(
            f"{self.base_url}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self._key}"},
            self.timeout,
            "OpenAI",
        )
        try:
            return res["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise LLMProviderError("OpenAI response missing message content.") from e


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
class AnthropicLLMProvider(LLMProvider):
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.model_name = os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-5")
        self._key = os.getenv("ANTHROPIC_API_KEY", "")
        self.timeout = max(5.0, _env_float("LLM_TIMEOUT_SECONDS", 120.0))
        self.default_max_tokens = _env_int("LLM_MAX_OUTPUT_TOKENS", 4096)

    @property
    def is_enabled(self) -> bool:
        return bool(self._key)

    def _chat(self, messages, temperature, json_mode, schema, max_tokens) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]
        if json_mode:
            system += "\n\nRespond with ONLY a valid JSON object. No prose, no code fences."
        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": min(1.0, temperature),
            "messages": convo,
        }
        if system.strip():
            payload["system"] = system
        res = _http_post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            {"x-api-key": self._key, "anthropic-version": "2023-06-01"},
            self.timeout,
            "Anthropic",
        )
        try:
            return "".join(b.get("text", "") for b in res["content"] if b.get("type") == "text")
        except Exception as e:
            raise LLMProviderError("Anthropic response missing text content.") from e


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------
class GeminiLLMProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(self) -> None:
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
        self._key = os.getenv("GEMINI_API_KEY", "")
        self.timeout = max(5.0, _env_float("LLM_TIMEOUT_SECONDS", 120.0))
        self.default_max_tokens = _env_int("LLM_MAX_OUTPUT_TOKENS", 4096)

    @property
    def is_enabled(self) -> bool:
        return bool(self._key)

    def _chat(self, messages, temperature, json_mode, schema, max_tokens) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        gen_cfg: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen_cfg}
        if system.strip():
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        res = _http_post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent",
            payload,
            {"x-goog-api-key": self._key},
            self.timeout,
            "Gemini",
        )
        try:
            return "".join(p.get("text", "") for p in res["candidates"][0]["content"]["parts"])
        except Exception as e:
            raise LLMProviderError("Gemini response missing text content.") from e


class DisabledLLMProvider(LLMProvider):
    provider_name = "disabled"
    model_name = ""

    @property
    def is_enabled(self) -> bool:
        return False

    def _chat(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover
        raise LLMProviderDisabledError("LLM provider is disabled.")


_PROVIDERS = {
    "ollama": OllamaLLMProvider,
    "openai": OpenAILLMProvider,
    "anthropic": AnthropicLLMProvider,
    "gemini": GeminiLLMProvider,
    "disabled": DisabledLLMProvider,
}

_llm_provider_instance: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Return the configured provider singleton (LLM_PROVIDER env var)."""
    global _llm_provider_instance
    if _llm_provider_instance is None:
        name = os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
        cls = _PROVIDERS.get(name)
        if cls is None:
            raise ValueError(f"Unsupported LLM provider '{name}'. Supported: {', '.join(_PROVIDERS)}.")
        _llm_provider_instance = cls()
    return _llm_provider_instance


def llm_available() -> bool:
    """True when an LLM can currently be called. Never raises."""
    try:
        return bool(get_llm_provider().can_chat)
    except Exception:
        return False
