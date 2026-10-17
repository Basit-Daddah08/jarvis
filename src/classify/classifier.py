from typing import Optional
from .keywords import ClassificationResult, classify_by_keywords
from .summarizer import ExtractiveTranscriptSummarizer
from .providers import AIProviderManager

class VideoClassifier:
    """Orchestrates multi-provider AI classification and extraction, respecting daily spend limits."""

    def __init__(self, state_manager=None, llm_api_key: Optional[str] = None, config: Optional[dict] = None, provider: Optional[str] = None):
        self.state_manager = state_manager
        self.config = config or {}
        
        # Determine provider name: passed provider > config ai.provider > "claude"
        provider_name = provider or self.config.get("ai", {}).get("provider") or "claude"
        
        # If llm_api_key was provided directly (legacy or test usage), inject into config
        if llm_api_key:
            if "ai" not in self.config:
                self.config["ai"] = {}
            if provider_name in ("claude", "anthropic"):
                self.config["ai"]["anthropic_api_key"] = llm_api_key
            elif provider_name == "openai":
                self.config["ai"]["openai_api_key"] = llm_api_key
            elif provider_name == "gemini":
                self.config["ai"]["gemini_api_key"] = llm_api_key
                
        self.ai_manager = AIProviderManager(provider_name=provider_name, config=self.config)
        self.llm = self.ai_manager  # backwards compatibility

    def classify_video(self, transcript: str, title: str = "", caption: str = "") -> ClassificationResult:
        # Step 1: Run fast keyword classifier with real extractive summary
        res = classify_by_keywords(text=transcript, caption=caption)
        if res.category != "ambiguous" and res.confidence >= 0.8:
            return res

        # Step 2: Ambiguous - check spend cap before invoking paid LLM
        is_paid_provider = self.ai_manager.provider_name in ("claude", "anthropic", "openai", "gemini")
        if is_paid_provider and self.state_manager and not self.state_manager.can_spend(0.002):
            print("[VideoClassifier] Daily AI spend cap reached. Using real transcript summarizer fallback.")
            real_sum, steps = ExtractiveTranscriptSummarizer.summarize(transcript=transcript, title=title, caption=caption)
            return ClassificationResult(
                category="other",
                confidence=0.5,
                summary=real_sum,
                steps=steps,
                tools=[],
                links=[],
                source="spend_cap_limit"
            )

        print(f"[VideoClassifier] Keywords ambiguous; calling AI provider '{self.ai_manager.provider_name}'...")
        ai_res = self.ai_manager.classify_and_summarize(transcript=transcript, title=title, caption=caption)

        if is_paid_provider and self.state_manager and ai_res.source.startswith("ai_"):
            self.state_manager.record_spend(0.002)

        return ai_res
