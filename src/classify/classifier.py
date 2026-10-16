from typing import Optional
from .keywords import ClassificationResult, classify_by_keywords
from .llm_classifier import LLMClassifier

class VideoClassifier:
    """Orchestrates two-stage classification: cheap keyword rules first, then spend-capped LLM fallback."""

    def __init__(self, state_manager=None, llm_api_key: Optional[str] = None):
        self.state_manager = state_manager
        self.llm = LLMClassifier(api_key=llm_api_key)

    def classify_video(self, transcript: str, title: str = "", caption: str = "") -> ClassificationResult:
        # Step 1: Run fast keyword classifier
        res = classify_by_keywords(text=transcript, caption=caption)
        if res.category != "ambiguous" and res.confidence >= 0.8:
            return res

        # Step 2: Ambiguous - check spend cap before invoking LLM
        if self.state_manager and not self.state_manager.can_spend(0.002):
            print("[VideoClassifier] Daily AI spend cap reached. Defaulting to 'other' without paid LLM call.")
            return ClassificationResult(
                category="other",
                confidence=0.5,
                source="spend_cap_limit"
            )

        print("[VideoClassifier] Keywords ambiguous; calling LLM classifier...")
        llm_res = self.llm.classify(text=transcript, title=title, caption=caption)

        if self.state_manager and llm_res.source == "llm":
            self.state_manager.record_spend(0.002)

        return llm_res
