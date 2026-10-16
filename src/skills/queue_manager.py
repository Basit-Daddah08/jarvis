import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List
from .inspector import SkillInspectionResult

class SkillQueueManager:
    """Manages the approval queue in vault/approvals/ for untrusted skills."""

    def __init__(self, approvals_dir: Path, installed_dir: Path = None):
        self.approvals_dir = Path(approvals_dir)
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        self.installed_dir = Path(installed_dir) if installed_dir else self.approvals_dir.parent / "installed_skills"
        self.installed_dir.mkdir(parents=True, exist_ok=True)

    def queue_skill(
        self,
        skill_name: str,
        repo_url: str,
        source_note_id: str,
        inspection: SkillInspectionResult,
        files_to_copy: List[Path] = None
    ) -> Path:
        """Create a pending approval bundle in vault/approvals/<skill_name>/."""
        target_dir = self.approvals_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write markdown approval request
        reasons_list = "\n".join(f"- {r}" for r in inspection.reasons) or "- None"
        detected_files_list = "\n".join(f"- `{f}`" for f in inspection.detected_files) or "- None"

        content = f"""# Skill Approval Request: {skill_name}

- **Status:** PENDING REVIEW
- **Discovered In:** `vault/notes/{source_note_id}.md`
- **Source Repository:** {repo_url or "N/A"}
- **Risk Level:** **{inspection.risk_level}**
- **Has Executable Code:** {'YES' if inspection.has_code else 'NO'}
- **Date Queued:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## Security Inspection Findings
{reasons_list}

## Files Present
{detected_files_list}

---

## How to Approve or Reject

1. **To Approve and Install:**
   Run in your terminal:
   ```bash
   python src/skills/approve.py approve {skill_name}
   ```
2. **To Reject and Delete:**
   ```bash
   python src/skills/approve.py reject {skill_name}
   ```
"""
        approval_file = target_dir / "APPROVAL_REQUEST.md"
        with open(approval_file, "w", encoding="utf-8") as f:
            f.write(content)

        return approval_file

    def list_pending(self) -> List[str]:
        """List skill names awaiting owner approval."""
        if not self.approvals_dir.exists():
            return []
        return [p.name for p in self.approvals_dir.iterdir() if p.is_dir()]

    def approve_skill(self, skill_name: str) -> bool:
        src = self.approvals_dir / skill_name
        if not src.exists():
            return False
        dest = self.installed_dir / skill_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(src), str(dest))
        return True

    def reject_skill(self, skill_name: str) -> bool:
        src = self.approvals_dir / skill_name
        if not src.exists():
            return False
        shutil.rmtree(src)
        return True
