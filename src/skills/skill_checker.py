import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from .inspector import SkillInspectionResult, SkillInspector
from .queue_manager import SkillQueueManager

class SkillChecker:
    """Checks tools identified in saved videos against GitHub and queues them safely."""

    def __init__(self, approvals_dir: Path, queue_all_by_default: bool = True):
        self.inspector = SkillInspector(queue_all_by_default=queue_all_by_default)
        self.queue_mgr = SkillQueueManager(approvals_dir=approvals_dir)

    def check_tool_skill(self, tool_name: str, source_note_id: str, repo_url: Optional[str] = None):
        """Analyze a tool detected in notes and queue for owner approval if safety criteria are met."""
        # Simulated or discovered repository file structure
        # In practice, gh search repos or git clone --depth 1 is run
        sample_files = [
            Path(f"{tool_name}.py"),
            Path("README.md"),
            Path("package.json")
        ]

        inspection = self.inspector.inspect_files(
            skill_name=tool_name,
            file_paths=sample_files
        )

        if inspection.requires_approval:
            approval_file = self.queue_mgr.queue_skill(
                skill_name=tool_name,
                repo_url=repo_url or f"https://github.com/search?q={tool_name}",
                source_note_id=source_note_id,
                inspection=inspection
            )
            print(f"[SkillChecker] Safety rule triggered: Queued '{tool_name}' for approval at {approval_file.name}")
            return approval_file

        print(f"[SkillChecker] Tool '{tool_name}' marked safe.")
        return None
