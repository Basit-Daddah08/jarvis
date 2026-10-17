import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .inspector import SkillInspectionResult, SkillInspector
from .queue_manager import SkillQueueManager
from .source_resolver import SkillSourceResolver

class SkillChecker:
    """Checks tools identified in saved videos by inspecting actual repository files and local artifacts."""

    def __init__(self, approvals_dir: Path, queue_all_by_default: bool = True, quarantine_dir: Optional[Path] = None):
        self.inspector = SkillInspector(queue_all_by_default=queue_all_by_default)
        self.queue_mgr = SkillQueueManager(approvals_dir=approvals_dir)
        self.resolver = SkillSourceResolver()
        self.quarantine_dir = quarantine_dir or (approvals_dir.parent / "quarantine")

    def _fetch_github_repo_files(self, repo_url: str) -> Tuple[Optional[List[Path]], Dict[str, str]]:
        """
        Inspects real files in a GitHub repository via GitHub REST API without relying on dummy sample files.
        """
        match = re.search(r"github\.com/([^/]+)/([^/?#]+)", repo_url)
        if not match:
            return None, {}

        owner, repo = match.group(1), match.group(2)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        headers = {
            "User-Agent": "Elion-SkillChecker/1.0",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list):
                        paths = []
                        contents = {}
                        for item in data:
                            name = item.get("name", "")
                            if name:
                                paths.append(Path(name))
                                # If there is a small README or markdown instruction file, fetch sample content to inspect
                                if name.lower() in ("readme.md", "skill.md", "prompt.md") and item.get("download_url"):
                                    try:
                                        dl_req = urllib.request.Request(item["download_url"], headers=headers)
                                        with urllib.request.urlopen(dl_req, timeout=3) as dl_resp:
                                            sample_text = dl_resp.read().decode("utf-8", errors="ignore")[:4000]
                                            contents[name] = sample_text
                                    except Exception:
                                        pass
                        return paths, contents
        except Exception as e:
            # Network unavailable, rate limited, or private repo
            pass

        return None, {}

    def _find_local_tool_files(self, tool_name: str) -> Tuple[List[Path], Dict[str, str]]:
        """Inspects actual local files in quarantine or drop directory if present."""
        paths = []
        contents = {}
        target_dirs = [
            self.quarantine_dir / tool_name,
            self.quarantine_dir.parent / "drop" / tool_name
        ]
        for d in target_dirs:
            if d.exists() and d.is_dir():
                for p in d.rglob("*"):
                    if p.is_file():
                        paths.append(p)
                        if p.suffix.lower() in (".md", ".txt", ".json", ".py", ".sh"):
                            try:
                                contents[str(p)] = p.read_text(encoding="utf-8", errors="ignore")[:4000]
                            except Exception:
                                pass
        return paths, contents

    def check_tool_skill(self, tool_name: str, source_note_id: str, repo_url: Optional[str] = None):
        """Analyze a tool detected in notes and queue for owner approval via real repo / artifact inspection."""
        # Resolve skill source deterministically without guessing search URLs
        resolved = self.resolver.resolve(tool_name, explicit_url=repo_url)
        final_repo_url = resolved.repo_url if resolved.status == "verified" else "unverified"

        # 1. Attempt real local file inspection first
        local_files, local_contents = self._find_local_tool_files(tool_name)
        if local_files:
            inspection = self.inspector.inspect_files(
                skill_name=tool_name,
                file_paths=local_files,
                file_contents=local_contents
            )
        # 2. Attempt real remote GitHub repository inspection if URL is verified
        elif resolved.status == "verified" and final_repo_url and "github.com" in final_repo_url:
            gh_files, gh_contents = self._fetch_github_repo_files(final_repo_url)
            if gh_files is not None:
                # Real repository files retrieved from GitHub API
                inspection = self.inspector.inspect_files(
                    skill_name=tool_name,
                    file_paths=gh_files,
                    file_contents=gh_contents
                )
            else:
                # Online lookup could not inspect live repo; require safety approval
                inspection = SkillInspectionResult(
                    skill_name=tool_name,
                    has_code=True,
                    is_markdown_only=False,
                    requires_approval=True,
                    reasons=[f"Verified repository '{final_repo_url}' exists, but live code tree could not be verified offline. Manual review required."],
                    detected_files=[],
                    risk_level="HIGH"
                )
        else:
            # 3. Unverified tool source with no inspectable files: do NOT simulate fake files
            inspection = SkillInspectionResult(
                skill_name=tool_name,
                has_code=False,
                is_markdown_only=False,
                requires_approval=True,
                reasons=["Tool repository is unverified or unknown. Untrusted skills require explicit administrator approval."],
                detected_files=[],
                risk_level="HIGH"
            )

        if inspection.requires_approval:
            approval_file = self.queue_mgr.queue_skill(
                skill_name=tool_name,
                repo_url=final_repo_url,
                source_note_id=source_note_id,
                inspection=inspection
            )
            print(f"[SkillChecker] Safety rule triggered: Queued '{tool_name}' for approval at {approval_file.name}")
            return approval_file

        print(f"[SkillChecker] Tool '{tool_name}' marked safe.")
        return None
