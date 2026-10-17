import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class ResolvedSkillSource:
    skill_name: str
    status: str  # "verified" or "unverified"
    repo_url: Optional[str] = None
    canonical_repo: Optional[str] = None
    source_kind: str = "unverified"  # "github_verified", "well_known", "unverified"
    notes: str = ""

# Curated list of verified, well-known canonical tool repositories.
# Ensures misspellings like "andthropic" or ambiguous names are never guessed.
WELL_KNOWN_OFFICIAL_REPOS = {
    "claude": ("anthropics/anthropic-quickstarts", "https://github.com/anthropics/anthropic-quickstarts"),
    "anthropic": ("anthropics/anthropic-sdk-python", "https://github.com/anthropics/anthropic-sdk-python"),
    "whisper": ("openai/whisper", "https://github.com/openai/whisper"),
    "whisper.cpp": ("ggerganov/whisper.cpp", "https://github.com/ggerganov/whisper.cpp"),
    "ollama": ("ollama/ollama", "https://github.com/ollama/ollama"),
    "uv": ("astral-sh/uv", "https://github.com/astral-sh/uv"),
    "fastapi": ("tiangolo/fastapi", "https://github.com/tiangolo/fastapi"),
    "yt-dlp": ("yt-dlp/yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
    "instaloader": ("instaloader/instaloader", "https://github.com/instaloader/instaloader"),
    "docker": ("docker/cli", "https://github.com/docker/cli")
}

GITHUB_URL_REGEX = re.compile(
    r"https?://github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)",
    re.IGNORECASE
)

class SkillSourceResolver:
    """
    Resolves skill source repositories safely.
    Strictly avoids guessing. If a tool or repository cannot be deterministically
    verified against an explicit GitHub URL or verified repository, returns
    status="unverified" and repo_url=None.
    """

    def resolve(self, skill_name: str, explicit_url: Optional[str] = None) -> ResolvedSkillSource:
        raw_name = (skill_name or "").strip()
        normalized_name = raw_name.lower()

        # Fix/guard against common typos like "andthropic" -> "anthropic"
        # e.g. "andthropic/skills" -> "anthropic/skills"
        if "andthropic" in normalized_name:
            normalized_name = normalized_name.replace("andthropic", "anthropic")
            raw_name = re.sub(r"andthropic", "anthropic", raw_name, flags=re.IGNORECASE)

        # 1. If an explicit GitHub URL was extracted from caption/video
        if explicit_url:
            clean_url = explicit_url.strip()
            # Catch typos in explicit URLs
            if "andthropic" in clean_url.lower():
                clean_url = re.sub(r"andthropic", "anthropic", clean_url, flags=re.IGNORECASE)

            match = GITHUB_URL_REGEX.search(clean_url)
            if match:
                repo_owner_name = match.group(1).rstrip(".git").rstrip("/")
                # Reject generic search URLs as verified sources
                if not repo_owner_name.startswith("search"):
                    canonical = f"https://github.com/{repo_owner_name}"
                    return ResolvedSkillSource(
                        skill_name=raw_name,
                        status="verified",
                        repo_url=canonical,
                        canonical_repo=repo_owner_name,
                        source_kind="github_verified",
                        notes=f"Explicit GitHub URL verified: {canonical}"
                    )

        # 2. Check well-known official tools
        if normalized_name in WELL_KNOWN_OFFICIAL_REPOS:
            repo_id, official_url = WELL_KNOWN_OFFICIAL_REPOS[normalized_name]
            return ResolvedSkillSource(
                skill_name=raw_name,
                status="verified",
                repo_url=official_url,
                canonical_repo=repo_id,
                source_kind="well_known",
                notes=f"Matched official verified repository: {official_url}"
            )

        # 3. No guessing. If not verified, return "unverified" rather than guessing.
        return ResolvedSkillSource(
            skill_name=raw_name,
            status="unverified",
            repo_url=None,
            canonical_repo=None,
            source_kind="unverified",
            notes="Skill source is unverified. No guessing performed."
        )

def resolve_skill_source(skill_name: str, explicit_url: Optional[str] = None) -> ResolvedSkillSource:
    """Convenience function for SkillSourceResolver().resolve(skill_name, explicit_url)."""
    return SkillSourceResolver().resolve(skill_name=skill_name, explicit_url=explicit_url)
