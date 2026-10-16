import json
import os
import re
import urllib.request
from typing import Optional
from .keywords import ClassificationResult

class LLMClassifier:
    """Fallback LLM classifier for ambiguous videos, respecting daily spend limits."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    def classify(self, text: str, title: str = "", caption: str = "") -> ClassificationResult:
        """Calls LLM for structured classification when keywords are unclear."""
        prompt = (
            f"You are JARVIS, an AI assistant analyzing a saved short video.\n"
            f"Title: {title}\n"
            f"Caption: {caption}\n"
            f"Transcript: {text}\n\n"
            f"Respond ONLY with a JSON object in this format:\n"
            "{\n"
            '  "type": "tool" | "ai" | "other",\n'
            '  "summary": "1-2 sentence executive summary",\n'
            '  "steps": ["Step 1...", "Step 2..."],\n'
            '  "tools": ["toolA", "toolB"],\n'
            '  "links": ["https://..."]\n'
            "}"
        )

        if not self.api_key:
            # Fallback heuristic when no paid API key is supplied
            is_tech = any(w in text.lower() for w in ["tool", "software", "code", "ai", "install", "workflow"])
            if is_tech:
                return ClassificationResult(
                    category="tool",
                    confidence=0.7,
                    summary=f"Technical walkthrough discussing {title or 'software workflows'}.",
                    steps=["Review instructions in video", "Implement configuration"],
                    tools=[],
                    links=[],
                    source="heuristic_fallback"
                )
            return ClassificationResult(
                category="other",
                confidence=0.7,
                summary="",
                steps=[],
                tools=[],
                links=[],
                source="heuristic_fallback"
            )

        # Call Gemini REST API directly with standard library
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_resp)
                return ClassificationResult(
                    category=parsed.get("type", "other"),
                    confidence=0.95,
                    summary=parsed.get("summary", ""),
                    steps=parsed.get("steps", []),
                    tools=parsed.get("tools", []),
                    links=parsed.get("links", []),
                    source="llm"
                )
        except Exception as e:
            print(f"[LLMClassifier] API call failed: {e}. Defaulting to 'other'.")
            return ClassificationResult(
                category="other",
                confidence=0.5,
                source="llm_error"
            )
