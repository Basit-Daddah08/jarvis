import re
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ClassificationResult:
    category: str  # "tool", "ai", or "other"
    confidence: float  # 0.0 to 1.0
    summary: str = ""
    steps: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    source: str = "keyword"  # "keyword" or "llm"

TOOL_KEYWORDS = {
    "tool", "cli", "terminal", "library", "framework", "npm", "pip", "github",
    "git", "install", "extension", "vscode", "repo", "docker", "database",
    "sdk", "api", "package", "plugin", "setup", "mcp"
}

AI_KEYWORDS = {
    "ai", "llm", "claude", "cursor", "chatgpt", "gpt", "gemini", "ollama",
    "whisper", "deepseek", "huggingface", "model", "prompt", "agents",
    "fine-tuning", "vibe coding", "rag", "langchain", "llama"
}

OTHER_KEYWORDS = {
    "mindset", "motivation", "discipline", "routine", "stoic", "habits",
    "gym", "fitness", "workout", "wealth", "philosophy", "naval", "meditation"
}

URL_REGEX = re.compile(r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)")
GITHUB_REGEX = re.compile(r"https?://github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)")

def extract_links(text: str) -> List[str]:
    """Find all URLs mentioned in the text, stripping trailing punctuation."""
    matches = URL_REGEX.findall(text)
    clean_urls = []
    for url in matches:
        # Strip trailing punctuation like . , ) ; !
        cleaned = re.sub(r"[.,);!]+$", "", url)
        if cleaned and cleaned not in clean_urls:
            clean_urls.append(cleaned)
    return clean_urls

def extract_tools_from_text(text: str) -> List[str]:
    """Extract tool names and GitHub repo identifiers."""
    tools = []
    # Check GitHub matches
    for match in GITHUB_REGEX.findall(text):
        repo_name = match.split("/")[-1]
        tools.append(repo_name)

    # Check common tool tokens in lowercase
    words = set(re.findall(r"\b[a-zA-Z0-9_-]{2,20}\b", text.lower()))
    common_known_tools = {
        "whisper.cpp": "whisper.cpp",
        "whisper": "whisper",
        "ollama": "ollama",
        "cursor": "cursor",
        "docker": "docker",
        "mcp": "mcp",
        "claude": "claude",
        "fastapi": "fastapi",
        "yt-dlp": "yt-dlp",
        "instaloader": "instaloader"
    }
    for token, canonical in common_known_tools.items():
        if token in words or token in text.lower():
            if canonical not in tools:
                tools.append(canonical)
    return tools

def classify_by_keywords(text: str, caption: str = "") -> ClassificationResult:
    """Classify video content using keyword density and regex heuristics."""
    combined_text = f"{caption} {text}".lower()
    links = extract_links(f"{caption} {text}")
    tools = extract_tools_from_text(f"{caption} {text}")

    words = set(re.findall(r"\b[a-z0-9_-]+\b", combined_text))

    tool_matches = words.intersection(TOOL_KEYWORDS)
    ai_matches = words.intersection(AI_KEYWORDS)
    other_matches = words.intersection(OTHER_KEYWORDS)

    tool_score = len(tool_matches)
    ai_score = len(ai_matches)
    other_score = len(other_matches)

    # If GitHub links or specific tools were found, high bias towards tool/ai
    if any("github.com" in link.lower() for link in links) or len(tools) > 0:
        tool_score += 3

    # Strong AI indicator
    if ai_score >= 2 and tool_score >= 1:
        steps = extract_heuristic_steps(text)
        return ClassificationResult(
            category="ai",
            confidence=0.85,
            summary="AI tool and workflow overview.",
            steps=steps,
            tools=tools,
            links=links,
            source="keyword"
        )
    elif tool_score >= 3:
        steps = extract_heuristic_steps(text)
        return ClassificationResult(
            category="tool",
            confidence=0.85,
            summary="Developer tool installation and usage.",
            steps=steps,
            tools=tools,
            links=links,
            source="keyword"
        )
    elif other_score >= 2 and tool_score == 0 and ai_score == 0:
        return ClassificationResult(
            category="other",
            confidence=0.90,
            summary="",
            steps=[],
            tools=[],
            links=links,
            source="keyword"
        )

    # Ambiguous - requires LLM check or default fallback
    return ClassificationResult(
        category="ambiguous",
        confidence=0.30,
        tools=tools,
        links=links,
        source="keyword"
    )

def extract_heuristic_steps(text: str) -> List[str]:
    """Extract step-like sentences (e.g. 'Step 1...', 'First...', 'Next...')"""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    step_sentences = []
    step_starters = ("step ", "first", "second", "third", "next", "then", "finally", "1.", "2.", "3.")
    for s in sentences:
        s_clean = s.strip()
        if any(s_clean.lower().startswith(starter) for starter in step_starters):
            step_sentences.append(s_clean)
        if len(step_sentences) >= 5:
            break

    if not step_sentences and len(sentences) > 0:
        # Fallback to key instructional sentences if available
        for s in sentences[:3]:
            if len(s.strip()) > 15:
                step_sentences.append(s.strip())

    return step_sentences
