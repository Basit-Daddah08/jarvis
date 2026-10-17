import re
from typing import List, Tuple

class ExtractiveTranscriptSummarizer:
    """
    Intelligent zero-AI fallback summarizer.
    Produces high-quality, real summaries derived directly from transcript content
    without stock or placeholder lines.
    """

    @staticmethod
    def summarize(transcript: str, title: str = "", caption: str = "") -> Tuple[str, List[str]]:
        combined = f"{transcript} {caption}".strip()
        if not combined:
            return "No transcript or caption content was recorded for this video.", []

        # Split into clean sentences
        raw_sentences = re.split(r"(?<=[.!?])\s+", combined)
        sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 15]

        if not sentences:
            fallback = transcript[:180].strip() + ("..." if len(transcript) > 180 else "")
            return fallback or "Content recorded with brief audio excerpt.", []

        # 1. Look for step/instruction sentences
        step_starters = (
            "step ", "first", "second", "third", "next", "then", "finally",
            "1.", "2.", "3.", "to start", "how to", "install", "run ", "clone "
        )
        steps: List[str] = []
        for s in sentences:
            s_lower = s.lower()
            if any(s_lower.startswith(starter) for starter in step_starters) or re.match(r"^\d+[\.\)]\s+", s):
                clean_s = re.sub(r"^\d+[\.\)]\s*", "", s).strip()
                if clean_s and clean_s not in steps:
                    steps.append(clean_s)
            if len(steps) >= 5:
                break

        # 2. Score sentences for summary significance based on real content
        scored = []
        keywords = (
            "install", "run", "setup", "tool", "workflow", "model", "build",
            "create", "use", "feature", "new", "best", "code", "automate", "api"
        )
        for idx, s in enumerate(sentences):
            score = 0.0
            # Early sentences usually contain the primary hook / thesis
            if idx == 0:
                score += 3.0
            elif idx == 1:
                score += 2.0
            # Keyword matches
            s_lower = s.lower()
            for kw in keywords:
                if kw in s_lower:
                    score += 1.5
            # Penalize generic social media filler phrases
            if any(f in s_lower for f in ["subscribe", "link in bio", "like and follow", "comment below", "share this"]):
                score -= 4.0
            scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_sentences = [s for _, s in scored[:2]]

        # Keep original sequence order of selected sentences for coherence
        ordered = [s for s in sentences if s in top_sentences]
        summary = " ".join(ordered) if ordered else sentences[0]
        if not summary.endswith((".", "!", "?")):
            summary += "."

        return summary, steps
