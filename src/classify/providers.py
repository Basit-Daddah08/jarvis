import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from .keywords import ClassificationResult
from .summarizer import ExtractiveTranscriptSummarizer

SYSTEM_PROMPT = """You are ELION (JARVIS), an autonomous assistant analyzing a short video transcription.
Extract a concise summary, key actionable steps, tools mentioned, and links.
Respond ONLY with a valid JSON object matching this schema:
{
  "type": "tool" | "ai" | "other",
  "summary": "2-3 sentence clear summary explaining what this video demonstrates and why it matters, drawn directly from the transcript.",
  "steps": ["Step 1 ...", "Step 2 ..."],
  "tools": ["toolA", "toolB"],
  "links": ["https://..."]
}"""

def _build_user_prompt(text: str, title: str = "", caption: str = "") -> str:
    return (
        f"Video Title: {title or 'Saved Reel'}\n"
        f"Post Caption: {caption}\n"
        f"Spoken Transcript:\n{text[:4000]}\n\n"
        "Analyze the content above and produce the requested JSON."
    )

def _parse_llm_json(raw_text: str) -> Optional[dict]:
    """Extract and parse JSON object from LLM response text."""
    if not raw_text:
        return None
    # Strip markdown code fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        # Search for first { ... } block
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None

class BaseAIProvider(ABC):
    """Abstract base class for LLM summary and classification providers."""

    @abstractmethod
    def generate(self, prompt: str) -> Optional[dict]:
        """Send prompt and return parsed JSON response."""
        pass

    @abstractmethod
    def health_check(self) -> Tuple[bool, str]:
        """Test provider connectivity and return (is_ok, message)."""
        pass

class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-haiku-latest"):
        self.api_key = (api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        self.model = model

    def generate(self, prompt: str) -> Optional[dict]:
        if not self.api_key:
            return None
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "temperature": 0.2,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("content", [])
            if content and content[0].get("type") == "text":
                return _parse_llm_json(content[0].get("text", ""))
        return None

    def health_check(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "Anthropic API key is not set."
        try:
            url = "https://api.anthropic.com/v1/messages"
            payload = {
                "model": self.model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "ping"}]
            }
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True, "Claude API connected and verified."
        except Exception as e:
            return False, f"Claude connection failed: {e}"
        return False, "Unknown response from Anthropic API."

class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT API provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = model

    def generate(self, prompt: str) -> Optional[dict]:
        if not self.api_key:
            return None
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return _parse_llm_json(content)
        return None

    def health_check(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "OpenAI API key is not set."
        try:
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True, "OpenAI API connected and verified."
        except Exception as e:
            return False, f"OpenAI connection failed: {e}"
        return False, "Unknown response from OpenAI API."

class GeminiProvider(BaseAIProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = model

    def generate(self, prompt: str) -> Optional[dict]:
        if not self.api_key:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return _parse_llm_json(parts[0].get("text", ""))
        return None

    def health_check(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "Gemini API key is not set."
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            payload = {"contents": [{"parts": [{"text": "ping"}]}]}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True, "Gemini API connected and verified."
        except Exception as e:
            return False, f"Gemini connection failed: {e}"
        return False, "Unknown response from Gemini API."

class OllamaProvider(BaseAIProvider):
    """Local Ollama model provider (runs on user's machine, 100% free & offline)."""

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama3.2"):
        self.endpoint = (endpoint or "http://localhost:11434").rstrip("/")
        self.model = model or "llama3.2"

    def generate(self, prompt: str) -> Optional[dict]:
        url = f"{self.endpoint}/api/generate"
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser Input:\n{prompt}"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2}
        }
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_response = data.get("response", "")
            return _parse_llm_json(raw_response)

    def health_check(self) -> Tuple[bool, str]:
        try:
            url = f"{self.endpoint}/api/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    model_found = any(self.model in m for m in models)
                    if model_found:
                        return True, f"Ollama is running with model '{self.model}' ready."
                    return True, f"Ollama is running ({len(models)} models available, but '{self.model}' may need to be pulled)."
        except Exception as e:
            return False, f"Ollama not reachable at {self.endpoint}. Make sure Ollama is running (`ollama serve`)."
        return False, "Could not verify Ollama status."

# ExtractiveTranscriptSummarizer is imported from .summarizer

class AIProviderManager:
    """
    Unified provider manager supporting Claude, OpenAI, Gemini, Ollama, and zero-AI fallback.
    """

    def __init__(self, provider_name: str = "claude", config: Optional[dict] = None):
        self.config = config or {}
        self.provider_name = (provider_name or "claude").lower()
        self._provider_instance: Optional[BaseAIProvider] = None
        self._init_provider()

    def _init_provider(self):
        ai_cfg = self.config.get("ai", {})
        p = self.provider_name

        if p == "claude" or p == "anthropic":
            key = ai_cfg.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY")
            model = ai_cfg.get("claude_model", "claude-3-5-haiku-latest")
            self._provider_instance = ClaudeProvider(api_key=key, model=model)
        elif p == "openai":
            key = ai_cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
            model = ai_cfg.get("openai_model", "gpt-4o-mini")
            self._provider_instance = OpenAIProvider(api_key=key, model=model)
        elif p == "gemini":
            key = ai_cfg.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
            model = ai_cfg.get("gemini_model", "gemini-1.5-flash")
            self._provider_instance = GeminiProvider(api_key=key, model=model)
        elif p == "ollama":
            endpoint = ai_cfg.get("ollama_endpoint", "http://localhost:11434")
            model = ai_cfg.get("ollama_model", "llama3.2")
            self._provider_instance = OllamaProvider(endpoint=endpoint, model=model)
        else:
            self._provider_instance = None  # None / zero-AI fallback

    def classify_and_summarize(self, transcript: str, title: str = "", caption: str = "") -> ClassificationResult:
        """
        Attempts structured LLM analysis via configured provider.
        If provider is None, not configured, or fails, seamlessly falls back to real transcript extraction.
        """
        if self._provider_instance:
            try:
                prompt = _build_user_prompt(text=transcript, title=title, caption=caption)
                res = self._provider_instance.generate(prompt)
                if res and isinstance(res, dict):
                    return ClassificationResult(
                        category=res.get("type", "tool"),
                        confidence=0.95,
                        summary=res.get("summary", ""),
                        steps=res.get("steps", []),
                        tools=res.get("tools", []),
                        links=res.get("links", []),
                        source=f"ai_{self.provider_name}"
                    )
            except Exception as e:
                print(f"[AIProviderManager] Provider '{self.provider_name}' error: {e}. Using real transcript fallback.")

        # Zero-AI Fallback: Extract directly from transcript content
        real_summary, real_steps = ExtractiveTranscriptSummarizer.summarize(
            transcript=transcript, title=title, caption=caption
        )
        # Check basic category heuristics
        combined = f"{transcript} {caption}".lower()
        is_ai = any(w in combined for w in ["ai", "llm", "claude", "chatgpt", "gemini", "ollama", "whisper", "model"])
        is_tool = any(w in combined for w in ["tool", "software", "cli", "install", "github", "npm", "pip", "docker"])
        cat = "ai" if is_ai else ("tool" if is_tool else "other")

        return ClassificationResult(
            category=cat,
            confidence=0.75,
            summary=real_summary,
            steps=real_steps,
            tools=[],
            links=[],
            source="transcript_extractive"
        )

    def test_connection(self) -> Tuple[bool, str]:
        """Test health of the currently configured AI provider."""
        if not self._provider_instance:
            return True, "No-AI Fallback mode active (runs 100% offline using real transcript summarizer)."
        return self._provider_instance.health_check()
