import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set

@dataclass
class SkillInspectionResult:
    skill_name: str
    has_code: bool
    is_markdown_only: bool
    requires_approval: bool
    reasons: List[str] = field(default_factory=list)
    detected_files: List[str] = field(default_factory=list)
    risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH"

EXECUTABLE_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".sh", ".bash", ".ps1", ".bat", ".cmd",
    ".exe", ".bin", ".rb", ".go", ".rs", ".java", ".c", ".cpp"
}

PACKAGE_CONFIG_FILES: Set[str] = {
    "package.json", "setup.py", "pyproject.toml", "cargo.toml",
    "dockerfile", "makefile", "requirements.txt"
}

SUSPICIOUS_PROMPT_PATTERNS = [
    r"ignore (?:all )?previous instructions",
    r"disregard (?:all )?prior",
    r"send (?:your |the )?(?:api[ _-]?key|token|cookie|credential|env|password)",
    r"curl\s+-[a-zA-Z]*d\s+",
    r"fetch\s*\(\s*['\"]https?://",
    r"eval\s*\(",
    r"os\.system\s*\(",
    r"subprocess\.call",
]

class SkillInspector:
    """Inspects skills for executable code and prompt injection before approval/install."""

    def __init__(self, queue_all_by_default: bool = True):
        self.queue_all_by_default = queue_all_by_default

    def inspect_files(self, skill_name: str, file_paths: List[Path], file_contents: dict = None) -> SkillInspectionResult:
        file_contents = file_contents or {}
        has_code = False
        reasons = []
        detected_code_files = []

        for p in file_paths:
            suffix = p.suffix.lower()
            name_lower = p.name.lower()
            if suffix in EXECUTABLE_EXTENSIONS or name_lower in PACKAGE_CONFIG_FILES:
                has_code = True
                detected_code_files.append(p.name)

        if has_code:
            reasons.append(f"Contains executable code/scripts: {', '.join(detected_code_files[:5])}")
            return SkillInspectionResult(
                skill_name=skill_name,
                has_code=True,
                is_markdown_only=False,
                requires_approval=True,
                reasons=reasons,
                detected_files=[p.name for p in file_paths],
                risk_level="HIGH"
            )

        # Markdown-only inspection
        suspicious_findings = []
        for p in file_paths:
            if p.suffix.lower() in [".md", ".markdown", ".txt"]:
                content = file_contents.get(str(p), "")
                if not content and p.exists():
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        pass
                for pat in SUSPICIOUS_PROMPT_PATTERNS:
                    if re.search(pat, content, re.IGNORECASE):
                        suspicious_findings.append(f"Matched pattern '{pat}' in {p.name}")

        if suspicious_findings:
            reasons.extend(suspicious_findings)
            return SkillInspectionResult(
                skill_name=skill_name,
                has_code=False,
                is_markdown_only=True,
                requires_approval=True,
                reasons=reasons,
                detected_files=[p.name for p in file_paths],
                risk_level="HIGH"
            )

        # Clean markdown skill
        requires_app = self.queue_all_by_default
        if requires_app:
            reasons.append("Markdown-only skill held in approval queue as safety precaution.")

        return SkillInspectionResult(
            skill_name=skill_name,
            has_code=False,
            is_markdown_only=True,
            requires_approval=requires_app,
            reasons=reasons,
            detected_files=[p.name for p in file_paths],
            risk_level="LOW"
        )
