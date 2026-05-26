"""
Free LLM Client — JARVIS BRAINIAC
===================================
100% Free & Open — Zero paid API keys required.

Priority chain (all FREE, no API key needed by default):
    1. Ollama        — local, offline, zero cost, best quality
                       Install: https://ollama.com
                       Models:  ollama pull llama3.3  (recommended)
                                ollama pull qwen2.5:14b
                                ollama pull phi4
    2. Groq          — cloud, free tier, extremely fast
                       Sign up free: https://console.groq.com
                       Set env: GROQ_API_KEY=gsk_... (free)
    3. Gemini Flash  — cloud, free tier (Google)
                       Sign up free: https://aistudio.google.com
                       Set env: GEMINI_API_KEY=... (free)
    4. HuggingFace   — cloud, free tier
                       Sign up free: https://huggingface.co
                       Set env: HF_TOKEN=hf_... (free)
    5. Smart Local   — deterministic, template-based, zero network

All providers are 100% FREE. The ones requiring an env var have
completely free sign-up tiers that require no payment info.

Usage:
    from jarvis_brainiac.free_llm import FreeLLM
    llm = FreeLLM()
    response = llm.chat("What is the capital of France?")
    print(response.text)
    print(response.provider)   # → "ollama", "groq", "gemini", etc.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterator, Optional

log = logging.getLogger(__name__)

# ─── Global constants ─────────────────────────────────────────────────────────

# HR-008 FIX: Ollama timeout reduced from 120s to avoid blocking Flask workers
OLLAMA_CHAT_TIMEOUT = 30   # seconds — increase for very slow hardware
OLLAMA_STREAM_TIMEOUT = 90  # streams can run longer

# LR-008 FIX: named constant instead of magic number 6
HF_CONTEXT_WINDOW = 6       # number of last messages sent to HuggingFace

# LR-002: Groq rate-limit retry
GROQ_MAX_RETRIES = 3
GROQ_RETRY_DELAY = 2.0      # seconds (doubles each retry for exponential backoff)


# ─── Response dataclass ───────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    tokens_used: int = 0

    def __str__(self) -> str:
        return self.text


# ─── Base provider class ──────────────────────────────────────────────────────

class BaseProvider:
    name: str = "base"
    model: str = ""
    available: bool = False

    def check(self) -> bool:
        raise NotImplementedError

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 1024) -> Optional[LLMResponse]:
        raise NotImplementedError


# ─── 1. Ollama (local, 100% free, offline) ───────────────────────────────────

class OllamaProvider(BaseProvider):
    """
    Best option: runs locally, works offline, zero cost forever.
    Install: https://ollama.com  → then: ollama pull llama3.3
    """
    name = "ollama"
    PREFERRED_MODELS = [
        "llama3.3", "llama3.2", "llama3.1", "llama3",
        "qwen2.5:14b", "qwen2.5:7b", "qwen2.5",
        "phi4", "phi3.5", "phi3",
        "mixtral", "mistral",
        "gemma3", "gemma2",
        "deepseek-r1",
    ]

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.model = ""
        self.available = False

    def check(self) -> bool:
        try:
            req = urllib.request.Request(self.base_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            if not models:
                log.warning("Ollama is running but has no models. Run: ollama pull llama3.3")
                return False
            # Pick best available model
            for pref in self.PREFERRED_MODELS:
                for m in models:
                    if pref in m.lower():
                        self.model = m
                        break
                if self.model:
                    break
            if not self.model:
                self.model = models[0]
            self.available = True
            log.info("Ollama: available — model=%s", self.model)
            return True
        except Exception as e:
            log.debug("Ollama: not available (%s)", e)
            return False

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 1024) -> Optional[LLMResponse]:
        try:
            all_messages = []
            if system:
                all_messages.append({"role": "system", "content": system})
            all_messages.extend(messages)
            payload = json.dumps({
                "model": self.model,
                "messages": all_messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": max_tokens},
            }).encode("utf-8")
            req = urllib.request.Request(
                self.base_url + "/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_CHAT_TIMEOUT) as r:
                data = json.loads(r.read())
            text = data.get("message", {}).get("content", "")
            if not text:
                return None
            return LLMResponse(text=text, provider=self.name, model=self.model)
        except Exception as e:
            log.warning("Ollama chat failed: %s", e)
            return None

    def stream(self, messages: list[dict], system: str = "") -> Iterator[str]:
        """Stream tokens from Ollama."""
        try:
            all_messages = []
            if system:
                all_messages.append({"role": "system", "content": system})
            all_messages.extend(messages)
            payload = json.dumps({
                "model": self.model,
                "messages": all_messages,
                "stream": True,
                "options": {"temperature": 0.7},
            }).encode("utf-8")
            req = urllib.request.Request(
                self.base_url + "/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_STREAM_TIMEOUT) as r:
                for line in r:
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except Exception:
                        continue
        except Exception as e:
            log.warning("Ollama stream failed: %s", e)


# ─── 2. Groq (cloud free tier, ultra-fast) ───────────────────────────────────

class GroqProvider(BaseProvider):
    """
    Groq Cloud — free tier, fastest LLM inference on the planet.
    Sign up FREE: https://console.groq.com
    Set env: GROQ_API_KEY=gsk_...
    Free limits: 100 req/day, 14,400 req/min (extremely generous)
    """
    name = "groq"
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    FREE_MODELS = [
        "llama-3.3-70b-versatile",    # Best quality, free
        "llama-3.1-8b-instant",       # Fastest, free
        "mixtral-8x7b-32768",         # Good all-rounder, free
        "gemma2-9b-it",               # Google Gemma, free
    ]

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model = self.FREE_MODELS[0]
        self.available = False

    def check(self) -> bool:
        if not self.api_key:
            log.debug("Groq: no GROQ_API_KEY set (free at console.groq.com)")
            return False
        if not (self.api_key.startswith("gsk_") and len(self.api_key) > 20):
            log.debug("Groq: invalid key format")
            return False
        # Light live check — /models costs no tokens
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                self.available = r.status == 200
                if self.available:
                    log.info("Groq: available — model=%s", self.model)
                return self.available
        except Exception as e:
            log.debug("Groq: key check failed: %s", e)
            return False

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 1024) -> Optional[LLMResponse]:
        if not self.api_key:
            return None
        # LR-002 FIX: retry on 429 rate-limit with exponential backoff
        import time as _time
        delay = GROQ_RETRY_DELAY
        for attempt in range(GROQ_MAX_RETRIES):
            try:
                all_messages = []
                if system:
                    all_messages.append({"role": "system", "content": system})
                all_messages.extend(messages)
                payload = json.dumps({
                    "model": self.model,
                    "messages": all_messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                }).encode("utf-8")
                req = urllib.request.Request(
                    self.BASE_URL, data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                text = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 0)
                return LLMResponse(text=text, provider=self.name, model=self.model, tokens_used=tokens)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < GROQ_MAX_RETRIES - 1:
                    log.warning("Groq: rate limited (429), retrying in %.1fs (attempt %d/%d)",
                                delay, attempt + 1, GROQ_MAX_RETRIES)
                    _time.sleep(delay)
                    delay *= 2  # exponential backoff
                    continue
                log.warning("Groq chat failed (HTTP %d): %s", e.code, e)
                return None
            except Exception as e:
                log.warning("Groq chat failed: %s", e)
                return None
        return None




# ─── 3. Google Gemini Flash (free tier) ──────────────────────────────────────

class GeminiProvider(BaseProvider):
    """
    Google Gemini — free tier via AI Studio.
    Sign up FREE: https://aistudio.google.com
    Set env: GEMINI_API_KEY=...
    Free limits: 15 req/min, 1M tokens/day (very generous)
    """
    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    FREE_MODELS = [
        "gemini-2.0-flash",       # Best free model
        "gemini-1.5-flash",       # Reliable fallback
        "gemini-1.5-flash-8b",    # Fastest, very cheap
    ]

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = self.FREE_MODELS[0]
        self.available = False

    def check(self) -> bool:
        if not self.api_key:
            log.debug("Gemini: no GEMINI_API_KEY set (free at aistudio.google.com)")
            return False
        if len(self.api_key) > 20:
            self.available = True
            log.info("Gemini: available — model=%s", self.model)
            return True
        return False

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 1024) -> Optional[LLMResponse]:
        if not self.api_key:
            return None
        try:
            # Convert OpenAI-style messages to Gemini format
            gemini_contents = []
            if system:
                gemini_contents.append({"role": "user", "parts": [{"text": f"[System]: {system}"}]})
                gemini_contents.append({"role": "model", "parts": [{"text": "Understood."}]})
            for msg in messages:
                role = "model" if msg["role"] == "assistant" else "user"
                gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            payload = json.dumps({
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.7,
                },
            }).encode("utf-8")
            # CR-002 FIX: use header instead of URL query param — keys in URLs
            # appear in server access logs and proxy logs.
            url = self.BASE_URL.format(model=self.model)
            req = urllib.request.Request(
                url, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,  # secure: header, not URL param
                },
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return LLMResponse(text=text, provider=self.name, model=self.model)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")[:200]
            log.warning("Gemini chat failed: HTTP %s — %s", e.code, body)
            return None
        except Exception as e:
            log.warning("Gemini chat failed: %s", e)
            return None


# ─── 4. HuggingFace Inference API (free tier) ────────────────────────────────

class HuggingFaceProvider(BaseProvider):
    """
    HuggingFace Serverless Inference — free tier.
    Sign up FREE: https://huggingface.co
    Set env: HF_TOKEN=hf_...
    Free limits: rate limited but no cost
    """
    name = "huggingface"
    BASE_URL = "https://api-inference.huggingface.co/models/{model}"
    FREE_MODELS = [
        "microsoft/Phi-3.5-mini-instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "HuggingFaceH4/zephyr-7b-beta",
    ]

    def __init__(self):
        self.api_key = os.environ.get("HF_TOKEN", "")
        self.model = self.FREE_MODELS[0]
        self.available = False

    def check(self) -> bool:
        if not self.api_key:
            log.debug("HuggingFace: no HF_TOKEN set (free at huggingface.co)")
            return False
        if self.api_key.startswith("hf_") and len(self.api_key) > 10:
            self.available = True
            log.info("HuggingFace: available — model=%s", self.model)
            return True
        return False

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 512) -> Optional[LLMResponse]:
        if not self.api_key:
            return None
        try:
            # Build prompt string from messages (HF uses different format)
            prompt_parts = []
            if system:
                prompt_parts.append(f"<|system|>\n{system}\n")
            for msg in messages[-HF_CONTEXT_WINDOW:]:  # LR-008 FIX: named constant
                role = "assistant" if msg["role"] == "assistant" else "user"
                prompt_parts.append(f"<|{role}|>\n{msg['content']}\n")
            prompt_parts.append("<|assistant|>\n")
            prompt = "".join(prompt_parts)

            payload = json.dumps({
                "inputs": prompt,
                "parameters": {"max_new_tokens": max_tokens, "temperature": 0.7, "do_sample": True},
            }).encode("utf-8")
            url = self.BASE_URL.format(model=self.model)
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            if isinstance(data, list):
                text = data[0].get("generated_text", "")
            else:
                text = data.get("generated_text", "")
            # Strip the prompt from the response
            if prompt in text:
                text = text[len(prompt):].strip()
            return LLMResponse(text=text or "(no response)", provider=self.name, model=self.model)
        except Exception as e:
            log.warning("HuggingFace chat failed: %s", e)
            return None


# ─── 5. Smart Local Fallback (zero network) ──────────────────────────────────

class SmartLocalProvider(BaseProvider):
    """
    Deterministic local fallback — no network, no LLM, no cost.
    Uses heuristic pattern matching for common queries.
    Always available.
    """
    name = "local"
    model = "pattern-matching-v1"

    PATTERNS = {
        # Time / date
        r"\btime\b|\bساعت\b|\bשעה\b": lambda: __import__("datetime").datetime.now().strftime("The current time is %H:%M:%S."),
        r"\bdate\b|\btoday\b|\bتاریخ\b|\bתאריך\b": lambda: __import__("datetime").datetime.now().strftime("Today is %A, %B %d, %Y."),
        # Identity
        r"\bwho are you\b|\bאתה מי\b|\bمن أنت\b": lambda: "I am J.A.R.V.I.S., your personal AI system. I am fully operational.",
        # Capabilities
        r"\bwhat can you do\b|\byour capabilities\b": lambda: "I can answer questions, run shell commands (!cmd), open apps (/open), manage your projects via JARVIS BRAINIAC, generate 3D websites, and scaffold full AI agent teams from a single idea.",
        # Greetings
        r"\bhello\b|\bhi\b|\bhey\b|\bשלום\b|\bمرحبا\b": lambda: "Hello. I am at your service.",
        r"\bgood morning\b|\bבוקר טוב\b|\bصباح الخير\b": lambda: "Good morning. All systems are online.",
        r"\bgood evening\b|\bערב טוב\b|\bمساء الخير\b": lambda: "Good evening. How may I assist you?",
        r"\bgood night\b|\bלילה טוב\b|\bتصبح على خير\b": lambda: "Good night. I will remain in standby.",
        # Thanks
        r"\bthank\b|\bthanks\b|\bתודה\b|\bشكرا\b": lambda: "My pleasure. Always.",
        # Status
        r"\bstatus\b|\bhealth\b|\bonline\b": lambda: "All systems operational. Memory: online. Agent registry: online. 3D Website Builder: online. IdeaToAgents Pipeline: online.",
        # Help
        r"\bhelp\b|\bעזרה\b|\bمساعدة\b": lambda: (
            "Available commands:\n"
            "  !<cmd>         — Execute shell command (god mode)\n"
            "  /open <app>    — Open an application\n"
            "  /say <text>    — Text-to-speech\n"
            "  /history       — Show conversation history\n"
            "  /clear         — Clear history\n"
            "For full AI conversation, install Ollama: https://ollama.com"
        ),
    }

    def check(self) -> bool:
        self.available = True
        return True

    def chat(self, messages: list[dict], system: str = "", max_tokens: int = 512) -> Optional[LLMResponse]:
        prompt = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                prompt = msg["content"]
                break
        if not prompt:
            return LLMResponse(
                text="Please send a message and I will respond.",
                provider=self.name, model=self.model,
            )
        p_lower = prompt.lower().strip()
        for pattern, fn in self.PATTERNS.items():
            if re.search(pattern, p_lower, re.IGNORECASE):
                return LLMResponse(text=fn(), provider=self.name, model=self.model)
        return LLMResponse(
            text=(
                f"I received your message: '{prompt[:80]}'. "
                "For full AI conversation, please install Ollama (ollama.com) — "
                "it's free, runs locally, and requires no API key. "
                "Then run: ollama pull llama3.3\n\n"
                "התקן Ollama בחינם: https://ollama.com ← ולאחר מכן: ollama pull llama3.3"
            ),
            provider=self.name, model=self.model,
        )


# ─── FreeLLM — main orchestrator ─────────────────────────────────────────────

class FreeLLM:
    """
    Main entry point. Tries providers in order, falls back gracefully.
    100% free, no payment required for any provider.

    Quick setup for best experience:
        1. Install Ollama: https://ollama.com
        2. Run: ollama pull llama3.3
        3. Start using JARVIS — no keys needed!

    Optional cloud boost (all free sign-ups):
        - Groq:  export GROQ_API_KEY=gsk_...
        - Gemini: export GEMINI_API_KEY=...
        - HuggingFace: export HF_TOKEN=hf_...
    """

    def __init__(self):
        self._providers: list[BaseProvider] = [
            OllamaProvider(),
            GroqProvider(),
            GeminiProvider(),
            HuggingFaceProvider(),
            SmartLocalProvider(),
        ]
        self._active: list[BaseProvider] = []
        self._best: Optional[BaseProvider] = None
        self._initialized = False

    def initialize(self) -> dict[str, bool]:
        """Check all providers and return availability report."""
        result: dict[str, bool] = {}
        self._active = []
        for p in self._providers:
            try:
                ok = p.check()
                result[p.name] = ok
                if ok:
                    self._active.append(p)
                    if self._best is None:
                        self._best = p
                        log.info("FreeLLM: primary provider = %s (%s)", p.name, p.model)
            except Exception as e:
                log.debug("Provider check error %s: %s", p.name, e)
                result[p.name] = False
        self._initialized = True
        return result

    def chat(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system: str = "",
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Send a chat message and return the response."""
        if not self._initialized:
            self.initialize()
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})
        for provider in self._active:
            try:
                resp = provider.chat(messages, system=system, max_tokens=max_tokens)
                if resp and resp.text.strip():
                    log.debug("FreeLLM: response from %s (%d chars)", provider.name, len(resp.text))
                    return resp
            except Exception as e:
                log.warning("FreeLLM: provider %s failed: %s", provider.name, e)
                continue
        # Should never happen — SmartLocalProvider always succeeds
        return LLMResponse(text="I am online and ready.", provider="local", model="fallback")

    def stream_chat(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system: str = "",
    ) -> Iterator[str]:
        """Stream tokens if Ollama is available, else fall back to full response."""
        if not self._initialized:
            self.initialize()
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})
        ollama = next((p for p in self._active if isinstance(p, OllamaProvider)), None)
        if ollama:
            yield from ollama.stream(messages, system=system)
        else:
            resp = self.chat(prompt, history=history, system=system)
            yield resp.text

    def status(self) -> dict:
        """Return current provider status."""
        if not self._initialized:
            self.initialize()
        return {
            "primary": self._best.name if self._best else "none",
            "model": self._best.model if self._best else "none",
            "available": [p.name for p in self._active],
            "total_providers": len(self._providers),
            "instructions": {
                "ollama": "Install: https://ollama.com then run: ollama pull llama3.3",
                "groq": "Free key: https://console.groq.com → set GROQ_API_KEY",
                "gemini": "Free key: https://aistudio.google.com → set GEMINI_API_KEY",
                "huggingface": "Free key: https://huggingface.co → set HF_TOKEN",
            },
        }


# ─── Module-level singleton ───────────────────────────────────────────────────

_llm: FreeLLM | None = None


def get_llm() -> FreeLLM:
    """Get or create the global FreeLLM singleton.
    
    MR-010 FIX: initialize() is NOT called here — it's called lazily
    at first chat() to avoid blocking Flask startup with Ollama probe.
    """
    global _llm
    if _llm is None:
        _llm = FreeLLM()
        # NOTE: Do NOT call _llm.initialize() here.
        # chat() will call initialize() lazily on first use.
    return _llm


def quick_chat(prompt: str, system: str = "") -> str:
    """One-liner convenience function."""
    return get_llm().chat(prompt, system=system).text
